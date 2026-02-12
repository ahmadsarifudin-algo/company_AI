"""HR Department Tools — PII-sensitive tools with strict RBAC."""

from app.core.tool_registry import ToolRegistry, ToolMeta, RiskLevel


def _screen_cv_handler(args: dict) -> dict:
    return {"status": "success", "file": args.get("cv_path", ""), "score": 0}

def _query_hris_handler(args: dict) -> dict:
    return {"status": "success", "query": args.get("query", ""), "results": []}

def _generate_contract_handler(args: dict) -> dict:
    return {"status": "success", "template": args.get("template", ""), "output": ""}

def _calculate_payroll_handler(args: dict) -> dict:
    return {"status": "success", "employee_count": 0, "total_gross": 0, "total_net": 0}

def _check_compliance_handler(args: dict) -> dict:
    return {"status": "success", "regulation": args.get("regulation", ""), "compliant": True}


def register_hr_tools() -> None:
    """Register all HR Department tools in the global ToolRegistry."""
    registry = ToolRegistry()
    hr_tools = [
        ToolMeta(name="screen_cv", description="Screen CV/resume against job requirements",
                 handler=_screen_cv_handler, risk_level=RiskLevel.MEDIUM,
                 allowed_roles=["recruitment"], allowed_departments=["hr"], egress_domains=[]),
        ToolMeta(name="query_hris", description="Query HR Information System (PII-sensitive)",
                 handler=_query_hris_handler, risk_level=RiskLevel.HIGH,
                 allowed_roles=["recruitment", "payroll", "performance", "benefits", "compliance"],
                 allowed_departments=["hr"], egress_domains=[]),
        ToolMeta(name="generate_contract", description="Generate employment contract from template",
                 handler=_generate_contract_handler, risk_level=RiskLevel.HIGH,
                 allowed_roles=["onboarding"], allowed_departments=["hr"], egress_domains=[]),
        ToolMeta(name="calculate_payroll", description="Calculate payroll with tax withholding",
                 handler=_calculate_payroll_handler, risk_level=RiskLevel.HIGH,
                 allowed_roles=["payroll"], allowed_departments=["hr"], egress_domains=[]),
        ToolMeta(name="check_labor_compliance", description="Check against UU Ketenagakerjaan",
                 handler=_check_compliance_handler, risk_level=RiskLevel.LOW,
                 allowed_roles=["compliance"], allowed_departments=["hr"], egress_domains=[]),
    ]
    for tool in hr_tools:
        registry.register(tool)
