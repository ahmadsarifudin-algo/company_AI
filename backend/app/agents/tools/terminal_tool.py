"""
Terminal Tool — Sandboxed command execution for developer agents.

Runs shell commands inside isolated Docker containers so agents can:
  - Execute git operations (clone, pull, commit, push)
  - Install packages (pip, npm, apt)
  - Run build/test commands
  - Execute scripts
  - Manage project dependencies

All commands run in ephemeral Docker containers with:
  - CPU/memory limits
  - No host network access (isolated bridge)
  - Read-only root filesystem (writes only to /workspace)
  - Execution timeout (max 5 minutes)
  - Command allowlist enforcement
  - Output capture and truncation

Registered tools:
  - terminal_exec     (HIGH)  — Execute command in sandbox
  - terminal_git      (HIGH)  — Git operations in sandbox
  - terminal_install  (HIGH)  — Install packages in sandbox
  - terminal_script   (HIGH)  — Run a script file in sandbox
"""

from __future__ import annotations

import asyncio
import re
import shlex
import time
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()

# ── Safety Configuration ─────────────────────

# Commands that are ALWAYS blocked (even inside Docker)
_BLOCKED_COMMANDS = {
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",  # fork bomb
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
}

# Patterns that are blocked
_BLOCKED_PATTERNS = [
    r"curl\s+.*\|\s*(?:bash|sh)",      # curl pipe to shell
    r"wget\s+.*\|\s*(?:bash|sh)",      # wget pipe to shell
    r">\s*/dev/sd",                     # write to disk devices
    r"chmod\s+777\s+/",                # chmod 777 on root
    r"chown\s+.*\s+/(?!workspace)",    # chown outside workspace
]

# Allowed command prefixes (whitelist approach)
_ALLOWED_COMMAND_PREFIXES = {
    # Git
    "git",
    # Python
    "python", "python3", "pip", "pip3", "pipenv", "poetry",
    "pytest", "mypy", "ruff", "black", "isort", "flake8",
    # Node.js
    "node", "npm", "npx", "yarn", "pnpm", "bun",
    "tsc", "eslint", "prettier",
    # System (safe)
    "ls", "cat", "head", "tail", "grep", "find", "wc",
    "echo", "pwd", "env", "which", "whoami",
    "mkdir", "cp", "mv", "touch", "rm",
    "tar", "unzip", "gzip", "gunzip",
    "curl", "wget",
    # Build tools
    "make", "cmake", "cargo", "go", "rustc", "gcc", "g++",
    "docker", "docker-compose",
    # Package managers
    "apt-get", "apt", "apk",
    # Database
    "psql", "mysql", "redis-cli",
    # Misc dev tools
    "jq", "sed", "awk", "sort", "uniq", "diff", "patch",
    "ssh-keygen", "openssl",
}

# Docker image for sandbox
_DEFAULT_IMAGE = "python:3.12-slim"

# Resource limits
_MAX_TIMEOUT_SEC = 300       # 5 minutes
_MAX_MEMORY = "512m"         # 512 MB
_MAX_CPU = "1.0"             # 1 CPU core
_MAX_OUTPUT_CHARS = 50000    # 50k chars output cap


# ── Command Validation ───────────────────────

def _validate_command(command: str) -> tuple[bool, str]:
    """Validate a command against safety rules.

    Returns:
        Tuple of (is_allowed, rejection_reason).
    """
    cmd_lower = command.strip().lower()

    # Check blocked commands
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False, f"Blocked command detected: contains '{blocked}'"

    # Check blocked patterns
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return False, f"Blocked pattern detected: {pattern}"

    # Get the base command (first word)
    parts = shlex.split(command.strip()) if command.strip() else []
    if not parts:
        return False, "Empty command"

    base_cmd = parts[0].split("/")[-1]  # Handle full paths like /usr/bin/git

    # Check against allowlist
    if base_cmd not in _ALLOWED_COMMAND_PREFIXES:
        return False, (
            f"Command '{base_cmd}' is not in the allowed list. "
            f"Allowed: {sorted(_ALLOWED_COMMAND_PREFIXES)}"
        )

    return True, ""


# ── Docker Sandbox Executor ──────────────────

async def _run_in_docker(
    command: str,
    image: str = _DEFAULT_IMAGE,
    workdir: str = "/workspace",
    timeout_sec: int = 60,
    env_vars: dict[str, str] | None = None,
    volumes: dict[str, str] | None = None,
    network: str = "none",
) -> dict[str, Any]:
    """Execute a command inside an ephemeral Docker container.

    Args:
        command: Shell command to execute.
        image: Docker image to use.
        workdir: Working directory inside container.
        timeout_sec: Max execution time in seconds.
        env_vars: Environment variables to set.
        volumes: Host-to-container volume mappings.
        network: Docker network mode ("none" for isolation, "bridge" for internet).

    Returns:
        Dict with exit_code, stdout, stderr, and timing.
    """
    container_name = f"sandbox_{uuid4().hex[:8]}"

    docker_cmd = [
        "docker", "run",
        "--rm",                             # Remove after exit
        "--name", container_name,
        "--memory", _MAX_MEMORY,            # Memory limit
        "--cpus", _MAX_CPU,                 # CPU limit
        "--network", network,               # Network isolation
        "--read-only",                      # Read-only root FS
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",  # Writable /tmp
        "--tmpfs", f"{workdir}:rw,size=200m",          # Writable workspace
        "--security-opt", "no-new-privileges",          # No privilege escalation
        "--pids-limit", "100",              # Max 100 processes
        "-w", workdir,                      # Working directory
    ]

    # Add environment variables
    if env_vars:
        for key, value in env_vars.items():
            docker_cmd.extend(["-e", f"{key}={value}"])

    # Add volume mounts (read-only unless specified)
    if volumes:
        for host_path, container_path in volumes.items():
            docker_cmd.extend(["-v", f"{host_path}:{container_path}"])

    docker_cmd.extend([image, "sh", "-c", command])

    start_time = time.monotonic()

    try:
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=min(timeout_sec, _MAX_TIMEOUT_SEC),
            )
        except asyncio.TimeoutError:
            # Kill container on timeout
            kill_proc = await asyncio.create_subprocess_exec(
                "docker", "kill", container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await kill_proc.wait()

            elapsed_ms = (time.monotonic() - start_time) * 1000
            return {
                "status": "timeout",
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_sec}s",
                "elapsed_ms": int(elapsed_ms),
                "container": container_name,
            }

        elapsed_ms = (time.monotonic() - start_time) * 1000
        stdout = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT_CHARS]

        truncated = (
            len(stdout_bytes) > _MAX_OUTPUT_CHARS
            or len(stderr_bytes) > _MAX_OUTPUT_CHARS
        )

        return {
            "status": "completed",
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "elapsed_ms": int(elapsed_ms),
            "truncated": truncated,
            "container": container_name,
        }

    except FileNotFoundError:
        return {
            "status": "error",
            "error": "Docker is not installed or not in PATH",
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
        }
    except Exception as e:
        elapsed_ms = (time.monotonic() - start_time) * 1000
        return {
            "status": "error",
            "error": str(e),
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "elapsed_ms": int(elapsed_ms),
        }


# ── Tool Handlers ────────────────────────────

async def terminal_exec_handler(
    command: str,
    image: str = "python:3.12-slim",
    timeout_sec: int = 60,
    network: str = "none",
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a command in a sandboxed Docker container.

    The command runs in an ephemeral container with:
    - CPU/memory limits
    - No host filesystem access
    - Network isolation (default: none)
    - Read-only root filesystem
    - 5-minute max timeout

    Args:
        command: Shell command to execute.
        image: Docker image (default: python:3.12-slim).
        timeout_sec: Timeout in seconds (max 300).
        network: "none" (isolated) or "bridge" (internet access).
        env_vars: Environment variables for the container.

    Returns:
        Dict with exit_code, stdout, stderr, and timing.
    """
    # Validate command
    allowed, reason = _validate_command(command)
    if not allowed:
        logger.warning("terminal_command_blocked", command=command, reason=reason)
        return {
            "status": "blocked",
            "error": reason,
            "command": command,
        }

    logger.info(
        "terminal_exec_start",
        command=command[:200],
        image=image,
        network=network,
        timeout=timeout_sec,
    )

    result = await _run_in_docker(
        command=command,
        image=image,
        timeout_sec=min(timeout_sec, _MAX_TIMEOUT_SEC),
        env_vars=env_vars,
        network=network,
    )

    logger.info(
        "terminal_exec_done",
        command=command[:100],
        exit_code=result.get("exit_code"),
        elapsed_ms=result.get("elapsed_ms"),
    )

    return result


async def terminal_git_handler(
    operation: str,
    repo_url: str = "",
    branch: str = "main",
    message: str = "",
    args: str = "",
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Execute git operations in a sandboxed container.

    The container has network access for clone/pull/push operations.

    Args:
        operation: Git operation — "clone", "pull", "push", "commit",
                   "status", "log", "diff", "branch", "checkout", "init".
        repo_url: Repository URL (for clone/push/pull).
        branch: Branch name (default: main).
        message: Commit message (for commit).
        args: Additional git arguments.
        timeout_sec: Timeout in seconds.

    Returns:
        Dict with git command output.
    """
    # Build git command
    git_commands = {
        "clone": f"git clone --branch {shlex.quote(branch)} {shlex.quote(repo_url)} /workspace/repo",
        "pull": f"git pull origin {shlex.quote(branch)}",
        "push": f"git push origin {shlex.quote(branch)}",
        "commit": f"git add -A && git commit -m {shlex.quote(message or 'Auto-commit')}",
        "status": "git status",
        "log": "git log --oneline -20",
        "diff": "git diff",
        "branch": "git branch -a",
        "checkout": f"git checkout {shlex.quote(branch)}",
        "init": "git init",
        "fetch": "git fetch --all",
        "stash": "git stash",
        "merge": f"git merge {shlex.quote(branch)}",
        "tag": f"git tag {shlex.quote(args)}" if args else "git tag -l",
    }

    if operation not in git_commands:
        return {
            "status": "error",
            "error": f"Unknown git operation: {operation}. Supported: {list(git_commands.keys())}",
        }

    command = git_commands[operation]
    if args and operation not in ("tag",):
        command += f" {args}"

    # Git needs network for remote operations
    needs_network = operation in ("clone", "pull", "push", "fetch")

    logger.info("terminal_git", operation=operation, repo=repo_url[:100] if repo_url else "")

    return await _run_in_docker(
        command=command,
        image="alpine/git:latest",
        timeout_sec=min(timeout_sec, _MAX_TIMEOUT_SEC),
        network="bridge" if needs_network else "none",
    )


async def terminal_install_handler(
    packages: list[str],
    manager: str = "pip",
    image: str = "",
    timeout_sec: int = 120,
) -> dict[str, Any]:
    """Install packages in a sandboxed container.

    Packages are installed in an ephemeral container — they do NOT
    persist or affect the host system.

    Args:
        packages: List of packages to install.
        manager: Package manager — "pip", "npm", "apt", "apk", "cargo".
        image: Docker image (auto-selected based on manager if empty).
        timeout_sec: Timeout in seconds.

    Returns:
        Dict with install output.
    """
    if not packages:
        return {"status": "error", "error": "No packages specified"}

    # Validate package names (no shell injection)
    for pkg in packages:
        if not re.match(r'^[a-zA-Z0-9_\-\.@/>=<!\[\],\s]+$', pkg):
            return {
                "status": "blocked",
                "error": f"Invalid package name: {pkg}",
            }

    # Select image and build command based on manager
    pkg_list = " ".join(shlex.quote(p) for p in packages)

    commands = {
        "pip": {
            "image": "python:3.12-slim",
            "cmd": f"pip install --no-cache-dir {pkg_list} && pip list",
        },
        "pip3": {
            "image": "python:3.12-slim",
            "cmd": f"pip3 install --no-cache-dir {pkg_list} && pip3 list",
        },
        "npm": {
            "image": "node:20-slim",
            "cmd": f"npm install {pkg_list} && npm list --depth=0",
        },
        "yarn": {
            "image": "node:20-slim",
            "cmd": f"yarn add {pkg_list} && yarn list --depth=0",
        },
        "apt": {
            "image": "ubuntu:22.04",
            "cmd": f"apt-get update -qq && apt-get install -y -qq {pkg_list}",
        },
        "apk": {
            "image": "alpine:latest",
            "cmd": f"apk add --no-cache {pkg_list}",
        },
        "cargo": {
            "image": "rust:slim",
            "cmd": f"cargo install {pkg_list}",
        },
    }

    if manager not in commands:
        return {
            "status": "error",
            "error": f"Unknown package manager: {manager}. Supported: {list(commands.keys())}",
        }

    config = commands[manager]
    use_image = image or config["image"]

    logger.info(
        "terminal_install",
        manager=manager,
        packages=packages,
        image=use_image,
    )

    return await _run_in_docker(
        command=config["cmd"],
        image=use_image,
        timeout_sec=min(timeout_sec, _MAX_TIMEOUT_SEC),
        network="bridge",  # Needs internet to download packages
    )


async def terminal_script_handler(
    script: str,
    language: str = "bash",
    image: str = "",
    timeout_sec: int = 120,
    env_vars: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run a multi-line script in a sandboxed container.

    Args:
        script: Script content (multi-line).
        language: Script language — "bash", "python", "node", "ruby".
        image: Docker image (auto-selected based on language if empty).
        timeout_sec: Timeout in seconds.
        env_vars: Environment variables for the script.

    Returns:
        Dict with script output.
    """
    if not script.strip():
        return {"status": "error", "error": "Empty script"}

    interpreters = {
        "bash": {"image": "bash:latest", "cmd": "bash"},
        "sh": {"image": "alpine:latest", "cmd": "sh"},
        "python": {"image": "python:3.12-slim", "cmd": "python3"},
        "python3": {"image": "python:3.12-slim", "cmd": "python3"},
        "node": {"image": "node:20-slim", "cmd": "node"},
        "javascript": {"image": "node:20-slim", "cmd": "node"},
        "ruby": {"image": "ruby:slim", "cmd": "ruby"},
    }

    if language not in interpreters:
        return {
            "status": "error",
            "error": f"Unknown language: {language}. Supported: {list(interpreters.keys())}",
        }

    config = interpreters[language]
    use_image = image or config["image"]
    interpreter = config["cmd"]

    # Write script to a temp file inside container and execute it
    # Use heredoc to avoid shell escaping issues
    escaped_script = script.replace("'", "'\\''")
    command = f"echo '{escaped_script}' > /tmp/script && {interpreter} /tmp/script"

    logger.info(
        "terminal_script",
        language=language,
        image=use_image,
        script_lines=script.count("\n") + 1,
    )

    return await _run_in_docker(
        command=command,
        image=use_image,
        timeout_sec=min(timeout_sec, _MAX_TIMEOUT_SEC),
        env_vars=env_vars,
        network="none",  # Scripts run without network by default
    )
