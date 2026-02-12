"""
Claude Code Tool — AI-powered coding assistant for developer agents.

Provides developer-facing AI coding capabilities through LiteLLM:
  - code_generate   — Generate code from specs/description
  - code_review     — Review code for bugs, security, performance
  - code_refactor   — Refactor/improve existing code
  - code_debug      — Analyze errors and suggest fixes
  - code_test       — Generate unit/integration tests
  - code_explain    — Explain code in plain language
  - code_convert    — Convert code between languages
  - code_document   — Generate documentation from code

Uses the "code" model tier from LiteLLM config (optimized for code tasks).
All handlers go through the ToolBroker chokepoint.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger()

# System prompts for each mode
_SYSTEM_PROMPTS = {
    "generate": (
        "You are an expert software engineer. Generate clean, production-ready code "
        "based on the user's specification. Include type hints, docstrings, error handling, "
        "and follow best practices. Return ONLY the code wrapped in markdown code blocks "
        "with the correct language tag. Add brief inline comments for complex logic."
    ),
    "review": (
        "You are a senior code reviewer. Analyze the code for:\n"
        "- Bugs and logic errors\n"
        "- Security vulnerabilities\n"
        "- Performance issues\n"
        "- Best practice violations\n"
        "- Readability and maintainability\n\n"
        "Rate severity as: 🔴 Critical, 🟡 Warning, 🟢 Suggestion.\n"
        "Provide specific line references and fix recommendations."
    ),
    "refactor": (
        "You are an expert software engineer specializing in code refactoring. "
        "Improve the given code while preserving its functionality. Focus on:\n"
        "- Clean code principles (SOLID, DRY, KISS)\n"
        "- Better naming and structure\n"
        "- Performance optimization\n"
        "- Modern language idioms\n\n"
        "Return the improved code with a summary of changes."
    ),
    "debug": (
        "You are an expert debugger. Analyze the code and error to:\n"
        "1. Identify the root cause\n"
        "2. Explain why the error occurs\n"
        "3. Provide the exact fix with corrected code\n"
        "4. Suggest preventive measures\n\n"
        "Be precise and reference specific lines/variables."
    ),
    "test": (
        "You are a QA engineer specializing in test automation. Generate comprehensive "
        "tests for the given code. Include:\n"
        "- Unit tests for all public functions/methods\n"
        "- Edge cases and boundary conditions\n"
        "- Error/exception handling tests\n"
        "- Mocks for external dependencies\n\n"
        "Use the appropriate testing framework for the language. "
        "Aim for high coverage."
    ),
    "explain": (
        "You are a technical educator. Explain the given code clearly:\n"
        "- What it does (high-level purpose)\n"
        "- How it works (step by step)\n"
        "- Key patterns and design choices\n"
        "- Dependencies and assumptions\n\n"
        "Use plain language. Target audience: mid-level developer."
    ),
    "convert": (
        "You are a polyglot software engineer. Convert the given code from the source "
        "language to the target language. Maintain:\n"
        "- Equivalent functionality\n"
        "- Idiomatic patterns in the target language\n"
        "- Type safety and error handling\n"
        "- Comments and documentation\n\n"
        "Use the target language's standard libraries."
    ),
    "document": (
        "You are a technical writer. Generate comprehensive documentation for the given code:\n"
        "- Module/class overview\n"
        "- Function/method signatures with descriptions\n"
        "- Parameters and return values\n"
        "- Usage examples\n"
        "- Dependencies\n\n"
        "Format as Markdown. Follow the language's documentation conventions."
    ),
}


async def _call_code_llm(
    mode: str,
    user_prompt: str,
    context: str = "",
    language: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Call the LiteLLM code model for a coding task.

    Args:
        mode: One of the _SYSTEM_PROMPTS keys.
        user_prompt: The user's coding request.
        context: Additional context (e.g., existing code, error logs).
        language: Programming language hint.
        max_tokens: Max response tokens.

    Returns:
        Dict with status, response text, model used, and token usage.
    """
    try:
        from app.core.llm_client import AgentContext, get_llm_client

        system_prompt = _SYSTEM_PROMPTS.get(mode, _SYSTEM_PROMPTS["generate"])

        if language:
            system_prompt += f"\n\nPrimary language: {language}"

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Add context as a separate message if provided
        if context:
            messages.append({
                "role": "user",
                "content": f"Here is the relevant code/context:\n\n```\n{context}\n```",
            })

        messages.append({"role": "user", "content": user_prompt})

        llm_client = get_llm_client()
        agent_ctx = AgentContext(
            agent_id="claude_code_tool",
            agent_name="claude_code_tool",
            department="tech",
            tier="code",
        )
        llm_response = await llm_client.call(
            ctx=agent_ctx,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,  # Low temperature for precise code output
        )

        logger.info(
            "claude_code_called",
            mode=mode,
            language=language,
            prompt_tokens=llm_response.prompt_tokens,
            completion_tokens=llm_response.completion_tokens,
        )

        return {
            "status": "success",
            "response": llm_response.content,
            "model": llm_response.model,
            "usage": {
                "prompt_tokens": llm_response.prompt_tokens,
                "completion_tokens": llm_response.completion_tokens,
                "total_tokens": llm_response.total_tokens,
            },
        }

    except ImportError:
        return {"status": "error", "error": "LLMClient is not available"}
    except Exception as e:
        logger.error("claude_code_error", mode=mode, error=str(e))
        return {"status": "error", "error": str(e)}


# ── Tool Handlers ────────────────────────────


async def code_generate_handler(
    description: str,
    language: str = "python",
    framework: str = "",
    requirements: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Generate code from a specification or description.

    Args:
        description: What the code should do.
        language: Target programming language.
        framework: Framework to use (e.g., FastAPI, React, Django).
        requirements: Specific requirements or constraints.
        max_tokens: Max response length.

    Returns:
        Dict with generated code and metadata.
    """
    prompt = f"Generate {language} code for: {description}"
    if framework:
        prompt += f"\nFramework: {framework}"
    if requirements:
        prompt += f"\nRequirements: {requirements}"

    return await _call_code_llm(
        mode="generate",
        user_prompt=prompt,
        language=language,
        max_tokens=max_tokens,
    )


async def code_review_handler(
    code: str,
    language: str = "",
    focus: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Review code for bugs, security issues, and improvements.

    Args:
        code: Source code to review.
        language: Programming language (auto-detected if empty).
        focus: Focus area — "security", "performance", "bugs", "all".
        max_tokens: Max response length.

    Returns:
        Dict with review findings and recommendations.
    """
    prompt = "Review this code thoroughly."
    if focus:
        prompt += f" Focus on: {focus}."

    return await _call_code_llm(
        mode="review",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )


async def code_refactor_handler(
    code: str,
    language: str = "",
    goals: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Refactor and improve existing code.

    Args:
        code: Source code to refactor.
        language: Programming language.
        goals: Refactoring goals — e.g., "improve readability", "optimize performance".
        max_tokens: Max response length.

    Returns:
        Dict with refactored code and change summary.
    """
    prompt = "Refactor this code."
    if goals:
        prompt += f" Goals: {goals}"

    return await _call_code_llm(
        mode="refactor",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )


async def code_debug_handler(
    code: str,
    error: str = "",
    expected_behavior: str = "",
    language: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Debug code — analyze errors and suggest fixes.

    Args:
        code: Source code with the bug.
        error: Error message or stack trace.
        expected_behavior: What the code should do.
        language: Programming language.
        max_tokens: Max response length.

    Returns:
        Dict with root cause analysis and fix.
    """
    prompt = "Debug this code."
    if error:
        prompt += f"\n\nError/stack trace:\n```\n{error}\n```"
    if expected_behavior:
        prompt += f"\n\nExpected behavior: {expected_behavior}"

    return await _call_code_llm(
        mode="debug",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )


async def code_test_handler(
    code: str,
    language: str = "python",
    framework: str = "pytest",
    coverage_targets: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Generate tests for the given code.

    Args:
        code: Source code to test.
        language: Programming language.
        framework: Test framework — "pytest", "unittest", "jest", "mocha", etc.
        coverage_targets: Specific functions/classes to target.
        max_tokens: Max response length.

    Returns:
        Dict with generated test code.
    """
    prompt = f"Generate {framework} tests for this code."
    if coverage_targets:
        prompt += f"\nFocus on: {coverage_targets}"

    return await _call_code_llm(
        mode="test",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )


async def code_explain_handler(
    code: str,
    language: str = "",
    detail_level: str = "medium",
    audience: str = "developer",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Explain code in plain language.

    Args:
        code: Source code to explain.
        language: Programming language.
        detail_level: "brief", "medium", or "detailed".
        audience: Target audience — "beginner", "developer", "architect".
        max_tokens: Max response length.

    Returns:
        Dict with code explanation.
    """
    prompt = f"Explain this code at a {detail_level} level for a {audience}."

    return await _call_code_llm(
        mode="explain",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )


async def code_convert_handler(
    code: str,
    source_language: str,
    target_language: str,
    target_framework: str = "",
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Convert code between programming languages.

    Args:
        code: Source code to convert.
        source_language: Original language (e.g., "python").
        target_language: Target language (e.g., "typescript").
        target_framework: Target framework (e.g., "express", "spring").
        max_tokens: Max response length.

    Returns:
        Dict with converted code.
    """
    prompt = f"Convert this {source_language} code to {target_language}."
    if target_framework:
        prompt += f" Use the {target_framework} framework."

    return await _call_code_llm(
        mode="convert",
        user_prompt=prompt,
        context=code,
        language=target_language,
        max_tokens=max_tokens,
    )


async def code_document_handler(
    code: str,
    language: str = "",
    doc_format: str = "markdown",
    include_examples: bool = True,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Generate documentation from source code.

    Args:
        code: Source code to document.
        language: Programming language.
        doc_format: Output format — "markdown", "docstring", "jsdoc", "openapi".
        include_examples: Include usage examples.
        max_tokens: Max response length.

    Returns:
        Dict with generated documentation.
    """
    prompt = f"Generate {doc_format} documentation for this code."
    if include_examples:
        prompt += " Include usage examples."

    return await _call_code_llm(
        mode="document",
        user_prompt=prompt,
        context=code,
        language=language,
        max_tokens=max_tokens,
    )
