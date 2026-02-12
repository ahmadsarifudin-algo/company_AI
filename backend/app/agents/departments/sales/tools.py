"""Sales Department Tools — CRM and pipeline management tools."""

from app.core.tool_registry import ToolRegistry, ToolMeta, RiskLevel


def _query_crm_handler(args: dict) -> dict:
    return {"status": "success", "query": args.get("query", ""), "results": []}

def _update_deal_handler(args: dict) -> dict:
    return {"status": "success", "deal_id": args.get("deal_id", ""), "stage": args.get("stage", "")}

def _send_proposal_handler(args: dict) -> dict:
    return {"status": "success", "proposal_id": "", "recipient": args.get("recipient", "")}

def _generate_quote_handler(args: dict) -> dict:
    return {"status": "success", "quote_id": "", "total": 0}

def _analyze_market_handler(args: dict) -> dict:
    return {"status": "success", "segment": args.get("segment", ""), "insights": []}


def register_sales_tools() -> None:
    """Register all Sales Department tools in the global ToolRegistry."""
    registry = ToolRegistry()
    sales_tools = [
        ToolMeta(name="query_crm", description="Query CRM for leads, deals, accounts",
                 handler=_query_crm_handler, risk_level=RiskLevel.LOW,
                 allowed_roles=["lead_scoring", "deal_intelligence", "sales_forecasting",
                                "pricing", "contract_review"],
                 allowed_departments=["sales"], egress_domains=[]),
        ToolMeta(name="update_deal_stage", description="Update deal stage in CRM pipeline",
                 handler=_update_deal_handler, risk_level=RiskLevel.MEDIUM,
                 allowed_roles=["deal_intelligence", "sales_forecasting"],
                 allowed_departments=["sales"], egress_domains=[]),
        ToolMeta(name="send_proposal", description="Send sales proposal to prospect",
                 handler=_send_proposal_handler, risk_level=RiskLevel.HIGH,
                 allowed_roles=["deal_intelligence", "pricing"],
                 allowed_departments=["sales"], egress_domains=["smtp.company.com"]),
        ToolMeta(name="generate_quote", description="Generate price quote for deal",
                 handler=_generate_quote_handler, risk_level=RiskLevel.MEDIUM,
                 allowed_roles=["pricing"], allowed_departments=["sales"], egress_domains=[]),
        ToolMeta(name="analyze_market", description="Analyze market segment and trends",
                 handler=_analyze_market_handler, risk_level=RiskLevel.LOW,
                 allowed_roles=["deal_intelligence", "sales_forecasting", "lead_scoring"],
                 allowed_departments=["sales"], egress_domains=[]),
    ]
    for tool in sales_tools:
        registry.register(tool)
