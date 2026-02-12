"""
Test Suite — PII Detection & Masking Tests (Module 3.5.9).

Tests:
- Resource sensitivity classification (82 resources)
- PII field pattern detection (21 patterns)
- Field masking via policy obligations
"""

import pytest

from app.core.resource_classification import (
    PII_FIELD_PATTERNS,
    RESOURCE_MAP,
    Sensitivity,
    get_pii_fields_in,
    get_sensitivity,
    is_pii_field,
)


# ── Sensitivity Classification ────────────────────


class TestResourceSensitivity:
    """Resource → Sensitivity mapping."""

    @pytest.mark.parametrize("resource,expected", [
        ("employee_pii", Sensitivity.PII),
        ("employee_contact", Sensitivity.PII),
        ("employee_banking", Sensitivity.PII),
        ("payroll", Sensitivity.PII),
        ("payslip", Sensitivity.PII),
        ("tax_records", Sensitivity.PII),
        ("customer_pii", Sensitivity.PII),
    ])
    def test_pii_resources(self, resource, expected):
        """PII resources correctly classified."""
        assert get_sensitivity(resource) == expected

    @pytest.mark.parametrize("resource,expected", [
        ("financial_reports", Sensitivity.CONFIDENTIAL),
        ("invoices", Sensitivity.CONFIDENTIAL),
        ("source_code", Sensitivity.CONFIDENTIAL),
        ("secrets_vault", Sensitivity.CONFIDENTIAL),
        ("contracts", Sensitivity.CONFIDENTIAL),
        ("deals", Sensitivity.CONFIDENTIAL),
    ])
    def test_confidential_resources(self, resource, expected):
        """Confidential resources correctly classified."""
        assert get_sensitivity(resource) == expected

    @pytest.mark.parametrize("resource,expected", [
        ("knowledge_base", Sensitivity.INTERNAL),
        ("audit_logs", Sensitivity.INTERNAL),
        ("attendance", Sensitivity.INTERNAL),
        ("campaign_analytics", Sensitivity.INTERNAL),
    ])
    def test_internal_resources(self, resource, expected):
        """Internal resources correctly classified."""
        assert get_sensitivity(resource) == expected

    @pytest.mark.parametrize("resource,expected", [
        ("public_docs", Sensitivity.PUBLIC),
        ("agents", Sensitivity.PUBLIC),
    ])
    def test_public_resources(self, resource, expected):
        """Public resources correctly classified."""
        assert get_sensitivity(resource) == expected

    def test_unknown_resource_defaults_to_internal(self):
        """Unknown resource → INTERNAL (safe default)."""
        assert get_sensitivity("nonexistent_table") == Sensitivity.INTERNAL

    def test_resource_map_has_expected_count(self):
        """Resource map has at least 30 entries."""
        assert len(RESOURCE_MAP) >= 30


# ── PII Field Detection ──────────────────────────


class TestPIIFieldDetection:
    """PII field name pattern matching."""

    @pytest.mark.parametrize("field", [
        "nik", "ktp", "npwp", "rekening", "account_number",
        "bank_account", "phone", "phone_number", "mobile",
        "email_personal", "alamat", "address", "home_address",
        "salary", "gaji", "take_home_pay", "ssn",
        "social_security", "passport", "birth_date", "tanggal_lahir",
    ])
    def test_pii_fields_detected(self, field):
        """Known PII fields are detected."""
        assert is_pii_field(field) is True

    @pytest.mark.parametrize("field", [
        "department", "agent_name", "task_id", "status",
        "created_at", "description", "title", "role",
    ])
    def test_non_pii_fields_not_detected(self, field):
        """Non-PII fields are not flagged."""
        assert is_pii_field(field) is False

    def test_case_insensitive(self):
        """PII detection is case-insensitive (via normalization)."""
        assert is_pii_field("NIK") is True
        assert is_pii_field("Salary") is True
        assert is_pii_field("  phone  ") is True

    def test_pii_pattern_count(self):
        """At least 20 PII patterns defined."""
        assert len(PII_FIELD_PATTERNS) >= 20


# ── PII Field Filtering ──────────────────────────


class TestPIIFieldFiltering:
    """Batch PII field filtering."""

    def test_filters_pii_from_mixed_fields(self):
        """Mixed field list → only PII fields returned."""
        fields = ["name", "nik", "department", "phone", "status", "salary"]
        pii = get_pii_fields_in(fields)
        assert set(pii) == {"nik", "phone", "salary"}

    def test_no_pii_fields(self):
        """No PII fields → empty list."""
        fields = ["name", "department", "status"]
        assert get_pii_fields_in(fields) == []

    def test_all_pii_fields(self):
        """All PII fields → all returned."""
        pii_subset = ["nik", "ktp", "phone", "salary"]
        assert get_pii_fields_in(pii_subset) == pii_subset


# ── Obligation Integration ────────────────────────


class TestPIIMaskingObligations:
    """PII masking obligations from PolicyEngine."""

    def test_pii_policy_generates_mask_obligations(self):
        """PolicyEngine PII rule → mask_fields obligation contains PII fields."""
        from app.core.policy_engine import PolicyContext, PolicyEngine

        engine = PolicyEngine()
        engine.load_rules("policies/default.yaml")

        ctx = PolicyContext(
            agent_id="test",
            department="hr",
            role="agent",
            tier="standard",
            action="read",
            resource="employee_pii",
            data_sensitivity="pii",
        )
        decision = engine.evaluate(ctx)

        assert decision.obligations is not None
        mask_fields = decision.obligations.mask_fields
        # All mask_fields should be recognized PII patterns
        for field in mask_fields:
            assert is_pii_field(field), f"{field} not in PII patterns"
