"""
Finance Department Tools — Registration of finance-specific tools.

All tool executions go through the chokepoint architecture.
"""

from app.core.tool_registry import ToolRegistry, ToolMeta, RiskLevel


def _parse_excel_handler(args: dict) -> dict:
    return {"status": "success", "file": args.get("file_path", ""), "rows": 0, "columns": []}


def _generate_report_handler(args: dict) -> dict:
    return {"status": "success", "report_type": args.get("type", ""), "format": args.get("format", "pdf")}


def _reconcile_ledger_handler(args: dict) -> dict:
    return {"status": "success", "account": args.get("account", ""), "matched": 0, "unmatched": 0}


def _calculate_tax_handler(args: dict) -> dict:
    return {"status": "success", "type": args.get("tax_type", ""), "amount": 0}


def _submit_filing_handler(args: dict) -> dict:
    return {"status": "success", "filing_id": "", "type": args.get("filing_type", "")}


def register_finance_tools() -> None:
    """Register all Finance Department tools in the global ToolRegistry."""
    registry = ToolRegistry()

    finance_tools = [
        ToolMeta(
            name="parse_excel",
            description="Parse Excel/CSV financial documents",
            handler=_parse_excel_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["accounting", "budget_planning", "treasury", "tax", "audit"],
            allowed_departments=["finance"],
            egress_domains=[],
        ),
        ToolMeta(
            name="generate_financial_report",
            description="Generate financial reports (P&L, BS, CF, aging)",
            handler=_generate_report_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["accounting", "budget_planning", "forecasting", "treasury", "audit"],
            allowed_departments=["finance"],
            egress_domains=[],
        ),
        ToolMeta(
            name="reconcile_ledger",
            description="Reconcile general ledger accounts against bank statements",
            handler=_reconcile_ledger_handler,
            risk_level=RiskLevel.MEDIUM,
            allowed_roles=["accounting", "audit"],
            allowed_departments=["finance"],
            egress_domains=[],
        ),
        ToolMeta(
            name="calculate_tax",
            description="Calculate tax obligations (PPh, PPN)",
            handler=_calculate_tax_handler,
            risk_level=RiskLevel.MEDIUM,
            allowed_roles=["tax", "accounting"],
            allowed_departments=["finance"],
            egress_domains=[],
        ),
        ToolMeta(
            name="submit_tax_filing",
            description="Submit tax filing documents to authorities",
            handler=_submit_filing_handler,
            risk_level=RiskLevel.HIGH,
            allowed_roles=["tax"],
            allowed_departments=["finance"],
            egress_domains=["efiling.pajak.go.id"],
        ),
    ]

    for tool in finance_tools:
        registry.register(tool)
