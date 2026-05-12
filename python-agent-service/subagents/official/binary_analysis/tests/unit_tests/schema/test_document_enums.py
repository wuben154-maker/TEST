"""Unit tests for binary_analysis.schema.document_enums.

C1 / FR-13 AC-6 / FR-15 AC-3:
- DocumentFormat — 11 members covering OOXML / OLE2 / PDF / RTF / HTA / OneNote / encrypted
- DocumentTier   — 3 members: P0 / P1 / P2
- DocumentRole   — 4 members: clean / carrier / payload_host / infection_source
- UnknownDowngradeReason — 6 members including historical all_low_confidence / llm_unrecoverable
"""

from __future__ import annotations

import pytest

from schema.document_enums import (
    DocumentFormat,
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)

# ---------------------------------------------------------------------------
# DocumentFormat
# ---------------------------------------------------------------------------


class TestDocumentFormat:
    def test_all_members_present(self) -> None:
        expected = {
            "ooxml_docx_macro",
            "ooxml_xlsx_macro",
            "ooxml_pptx_macro",
            "ole2_doc",
            "ole2_xls",
            "ole2_ppt",
            "pdf",
            "rtf",
            "hta",
            "onenote",
            "encrypted_office",
        }
        actual = {m.value for m in DocumentFormat}
        assert actual == expected

    def test_member_count(self) -> None:
        assert len(DocumentFormat) == 11

    def test_is_str_enum(self) -> None:
        assert isinstance(DocumentFormat.PDF, str)
        assert DocumentFormat.PDF == "pdf"

    def test_enum_by_value(self) -> None:
        assert DocumentFormat("ooxml_docx_macro") is DocumentFormat.OOXML_DOCX_MACRO
        assert DocumentFormat("encrypted_office") is DocumentFormat.ENCRYPTED_OFFICE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            DocumentFormat("not_a_format")

    def test_string_equality(self) -> None:
        assert DocumentFormat.OLE2_DOC == "ole2_doc"
        assert DocumentFormat.ONENOTE == "onenote"

    def test_ooxml_group(self) -> None:
        ooxml = {
            DocumentFormat.OOXML_DOCX_MACRO,
            DocumentFormat.OOXML_XLSX_MACRO,
            DocumentFormat.OOXML_PPTX_MACRO,
        }
        for member in ooxml:
            assert member.value.startswith("ooxml_")

    def test_ole2_group(self) -> None:
        ole2 = {
            DocumentFormat.OLE2_DOC,
            DocumentFormat.OLE2_XLS,
            DocumentFormat.OLE2_PPT,
        }
        for member in ole2:
            assert member.value.startswith("ole2_")


# ---------------------------------------------------------------------------
# DocumentTier
# ---------------------------------------------------------------------------


class TestDocumentTier:
    def test_all_members_present(self) -> None:
        assert {m.value for m in DocumentTier} == {"P0", "P1", "P2"}

    def test_member_count(self) -> None:
        assert len(DocumentTier) == 3

    def test_is_str_enum(self) -> None:
        assert isinstance(DocumentTier.P0, str)
        assert DocumentTier.P0 == "P0"

    def test_enum_by_value(self) -> None:
        assert DocumentTier("P0") is DocumentTier.P0
        assert DocumentTier("P2") is DocumentTier.P2

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            DocumentTier("P3")

    def test_tier_ordering_by_name(self) -> None:
        tiers = list(DocumentTier)
        assert tiers[0] == DocumentTier.P0
        assert tiers[1] == DocumentTier.P1
        assert tiers[2] == DocumentTier.P2


# ---------------------------------------------------------------------------
# DocumentRole
# ---------------------------------------------------------------------------


class TestDocumentRole:
    def test_all_members_present(self) -> None:
        expected = {"clean", "carrier", "payload_host", "infection_source"}
        assert {m.value for m in DocumentRole} == expected

    def test_member_count(self) -> None:
        assert len(DocumentRole) == 4

    def test_is_str_enum(self) -> None:
        assert isinstance(DocumentRole.CLEAN, str)
        assert DocumentRole.CLEAN == "clean"

    def test_enum_by_value(self) -> None:
        assert DocumentRole("clean") is DocumentRole.CLEAN
        assert DocumentRole("infection_source") is DocumentRole.INFECTION_SOURCE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            DocumentRole("unknown_role")

    def test_string_equality(self) -> None:
        assert DocumentRole.CARRIER == "carrier"
        assert DocumentRole.PAYLOAD_HOST == "payload_host"
        assert DocumentRole.INFECTION_SOURCE == "infection_source"


# ---------------------------------------------------------------------------
# UnknownDowngradeReason (FR-13 AC-6)
# ---------------------------------------------------------------------------


class TestUnknownDowngradeReason:
    def test_all_members_present(self) -> None:
        expected = {
            "all_low_confidence",
            "llm_unrecoverable",
            "encrypted_office_no_password",
            "document_parser_failed",
            "onenote_parser_unavailable",
            "recursion_budget_exceeded",
        }
        assert {m.value for m in UnknownDowngradeReason} == expected

    def test_member_count(self) -> None:
        assert len(UnknownDowngradeReason) == 6

    def test_is_str_enum(self) -> None:
        assert isinstance(UnknownDowngradeReason.ALL_LOW_CONFIDENCE, str)

    def test_historical_values_present(self) -> None:
        """Historical e2e01 values must be preserved for backward compatibility."""
        assert (
            UnknownDowngradeReason("all_low_confidence")
            is UnknownDowngradeReason.ALL_LOW_CONFIDENCE
        )
        assert (
            UnknownDowngradeReason("llm_unrecoverable")
            is UnknownDowngradeReason.LLM_UNRECOVERABLE
        )

    def test_new_document_values(self) -> None:
        assert (
            UnknownDowngradeReason("encrypted_office_no_password")
            is UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD
        )
        assert (
            UnknownDowngradeReason("document_parser_failed")
            is UnknownDowngradeReason.DOCUMENT_PARSER_FAILED
        )
        assert (
            UnknownDowngradeReason("onenote_parser_unavailable")
            is UnknownDowngradeReason.ONENOTE_PARSER_UNAVAILABLE
        )
        assert (
            UnknownDowngradeReason("recursion_budget_exceeded")
            is UnknownDowngradeReason.RECURSION_BUDGET_EXCEEDED
        )

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            UnknownDowngradeReason("not_a_reason")

    def test_string_equality(self) -> None:
        assert UnknownDowngradeReason.ALL_LOW_CONFIDENCE == "all_low_confidence"
        assert UnknownDowngradeReason.LLM_UNRECOVERABLE == "llm_unrecoverable"
