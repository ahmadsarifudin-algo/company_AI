"""
SecurityAgent — CVE scanning, dependency audit, and secret detection.

Responsibilities:
- Scan code for known CVEs in dependencies
- Audit dependency tree for risks
- Detect hardcoded secrets and credentials
- Generate security review reports
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class SecurityAgent(BaseAgent):
    """Scans for CVEs, audits dependencies, and detects secrets."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Security Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Scan dependencies for known CVEs (using advisory databases)\n"
            "2. Audit the dependency tree for supply-chain risks\n"
            "3. Detect hardcoded secrets, API keys, and credentials in code\n"
            "4. Review code for common vulnerability patterns (OWASP Top 10)\n"
            "5. Generate security assessment reports\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "cve_scan": {\n'
            '    "vulnerabilities": [{"cve_id": "CVE-...", "package": "...", "severity": "critical|high|medium|low", "fix": "..."}],\n'
            '    "total": 0, "critical": 0, "high": 0\n'
            "  },\n"
            '  "dependency_audit": {\n'
            '    "total_deps": 0, "outdated": 0,\n'
            '    "risky_packages": [{"name": "...", "reason": "..."}]\n'
            "  },\n"
            '  "secret_scan": {\n'
            '    "findings": [{"file": "...", "line": 0, "type": "api_key|password|token", "severity": "critical"}]\n'
            "  },\n"
            '  "owasp_review": [{"category": "A01-Broken Access Control", "status": "pass|fail", "notes": "..."}],\n'
            '  "risk_level": "low|medium|high|critical",\n'
            '  "recommendations": ["..."]\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        code = state.get("artifacts", {}).get("backend_code", {})
        task_desc = state.get("task_description", "")
        context = f"Task: {task_desc}"
        if code:
            files = code.get("files", [])
            deps = code.get("dependencies_added", [])
            context += f"\nFiles to review: {len(files)}\nNew dependencies: {json.dumps(deps)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("security_scan_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)

        try:
            security_output = json.loads(response.content)
        except json.JSONDecodeError:
            security_output = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["security_report"] = security_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "security_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
