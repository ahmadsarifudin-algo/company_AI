"""
ResourceClassification — Data sensitivity map for the enterprise OS.

Maps resource names (tables, data types) to their sensitivity level.
Used by DataAccessLayer and PolicyEngine to determine access requirements.

Sensitivity Levels:
- public:       Freely accessible, no restrictions
- internal:     Available within department, logged
- confidential: Restricted access, requires specific role
- pii:          Personally Identifiable Information — requires ticket + approval
"""

from enum import Enum

import structlog

logger = structlog.get_logger()


class Sensitivity(str, Enum):
    """Data sensitivity classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"


# ── Resource → Sensitivity mapping ──────────────

RESOURCE_MAP: dict[str, Sensitivity] = {
    # ── Employee / HR data ──
    "employee_profile": Sensitivity.INTERNAL,
    "employee_pii": Sensitivity.PII,          # NIK, KTP, alamat
    "employee_contact": Sensitivity.PII,       # telepon, email pribadi
    "employee_banking": Sensitivity.PII,       # rekening bank
    "payroll": Sensitivity.PII,
    "payslip": Sensitivity.PII,
    "performance_review": Sensitivity.CONFIDENTIAL,
    "attendance": Sensitivity.INTERNAL,

    # ── Finance data ──
    "financial_reports": Sensitivity.CONFIDENTIAL,
    "invoices": Sensitivity.CONFIDENTIAL,
    "budget_allocation": Sensitivity.CONFIDENTIAL,
    "tax_records": Sensitivity.PII,
    "expense_reports": Sensitivity.INTERNAL,
    "revenue_data": Sensitivity.CONFIDENTIAL,
    "treasury": Sensitivity.CONFIDENTIAL,

    # ── Sales / CRM data ──
    "customer_profile": Sensitivity.INTERNAL,
    "customer_pii": Sensitivity.PII,           # kontak kustomer
    "deals": Sensitivity.CONFIDENTIAL,
    "pricing": Sensitivity.CONFIDENTIAL,
    "contracts": Sensitivity.CONFIDENTIAL,
    "leads": Sensitivity.INTERNAL,

    # ── Legal data ──
    "legal_contracts": Sensitivity.CONFIDENTIAL,
    "case_files": Sensitivity.CONFIDENTIAL,
    "regulatory_filings": Sensitivity.CONFIDENTIAL,
    "ip_portfolio": Sensitivity.CONFIDENTIAL,
    "nda_records": Sensitivity.CONFIDENTIAL,

    # ── Marketing data ──
    "campaign_analytics": Sensitivity.INTERNAL,
    "ad_spend": Sensitivity.INTERNAL,
    "content_drafts": Sensitivity.INTERNAL,
    "social_credentials": Sensitivity.CONFIDENTIAL,

    # ── Tech / Development data ──
    "source_code": Sensitivity.CONFIDENTIAL,
    "secrets_vault": Sensitivity.CONFIDENTIAL,
    "infrastructure_config": Sensitivity.CONFIDENTIAL,
    "deployment_logs": Sensitivity.INTERNAL,
    "error_logs": Sensitivity.INTERNAL,

    # ── Knowledge / General ──
    "knowledge_base": Sensitivity.INTERNAL,
    "knowledge_documents": Sensitivity.INTERNAL,
    "public_docs": Sensitivity.PUBLIC,
    "meeting_notes": Sensitivity.INTERNAL,

    # ── BizDev data ──
    "market_research": Sensitivity.INTERNAL,
    "partnership_eval": Sensitivity.CONFIDENTIAL,
    "competitor_analysis": Sensitivity.CONFIDENTIAL,

    # ── System / Audit ──
    "audit_logs": Sensitivity.INTERNAL,
    "audit_events": Sensitivity.INTERNAL,
    "trace_index": Sensitivity.INTERNAL,
    "metrics_rollups": Sensitivity.INTERNAL,
    "users": Sensitivity.INTERNAL,
    "agents": Sensitivity.PUBLIC,
    "prompt_history": Sensitivity.INTERNAL,
    "tasks": Sensitivity.INTERNAL,
}


# ── PII field patterns ──────────────────────────
#
# These field names should be masked when obligations require PII masking.
PII_FIELD_PATTERNS: list[str] = [
    "nik",
    "ktp",
    "npwp",
    "rekening",
    "account_number",
    "bank_account",
    "phone",
    "phone_number",
    "mobile",
    "email_personal",
    "alamat",
    "address",
    "home_address",
    "salary",
    "gaji",
    "take_home_pay",
    "ssn",
    "social_security",
    "passport",
    "birth_date",
    "tanggal_lahir",
]


def get_sensitivity(resource: str) -> Sensitivity:
    """Get the sensitivity level for a resource.

    Args:
        resource: Resource name (e.g., "employee_pii", "knowledge_base").

    Returns:
        Sensitivity level. Defaults to INTERNAL if not mapped.
    """
    sensitivity = RESOURCE_MAP.get(resource, Sensitivity.INTERNAL)
    return sensitivity


def is_pii_field(field_name: str) -> bool:
    """Check if a field name matches known PII patterns.

    Args:
        field_name: Column/field name to check.

    Returns:
        True if the field likely contains PII.
    """
    normalized = field_name.lower().strip()
    return normalized in PII_FIELD_PATTERNS


def get_pii_fields_in(field_names: list[str]) -> list[str]:
    """Filter a list of field names to those that are PII.

    Args:
        field_names: List of column/field names.

    Returns:
        Subset that are PII fields.
    """
    return [f for f in field_names if is_pii_field(f)]
