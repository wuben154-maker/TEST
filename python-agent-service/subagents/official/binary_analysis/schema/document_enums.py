"""Document-specific enumerations for Schema v1.1.0 (C1 / FR-13 / FR-15).

These enums are used by:
- `ReportV1` Optional fields (FR-15 AC-3)
- Scoring rule engine for `document_role` classification (FR-13 AC-4/6)
- EvidenceChain document bucket validation (IR-DOC-06)

All members use StrEnum so that values serialize naturally to strings in
Pydantic JSON output without extra configuration.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentFormat(StrEnum):
    """Detected document format label (FR-01, IR-DOC-06).

    Members are grouped by format family:
    - OOXML: macro-enabled Office Open XML formats
    - OLE2: legacy binary Office formats
    - Other: PDF, RTF, HTA, OneNote, encrypted Office
    """

    OOXML_DOCX_MACRO = "ooxml_docx_macro"
    OOXML_XLSX_MACRO = "ooxml_xlsx_macro"
    OOXML_PPTX_MACRO = "ooxml_pptx_macro"
    OLE2_DOC = "ole2_doc"
    OLE2_XLS = "ole2_xls"
    OLE2_PPT = "ole2_ppt"
    PDF = "pdf"
    RTF = "rtf"
    HTA = "hta"
    ONENOTE = "onenote"
    ENCRYPTED_OFFICE = "encrypted_office"


class DocumentTier(StrEnum):
    """Analysis-complexity tier for a document format (IR-DOC-06).

    Semantics:
    - P0 — fully supported: docx / xlsx / doc / xls / pdf (≥ 100% pass rate)
    - P1 — best-effort: pptx / ppt / rtf / hta (≥ 80% pass rate)
    - P2 — degraded-path: onenote / encrypted_office (≥ 50% pass rate)
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class DocumentRole(StrEnum):
    """Role of the document in the threat delivery chain (FR-13 AC-4).

    Produced deterministically by the scoring rule engine — never by LLM.

    Semantics:
    - clean            — no suspicious Indicators present
    - carrier          — contains delivery logic (download / launch) but no embedded payload
    - payload_host     — directly embeds a malicious payload (PE / script)
    - infection_source — contains both delivery logic and an embedded payload
    """

    CLEAN = "clean"
    CARRIER = "carrier"
    PAYLOAD_HOST = "payload_host"
    INFECTION_SOURCE = "infection_source"


class UnknownDowngradeReason(StrEnum):
    """Reason why the verdict was downgraded to UNKNOWN (FR-13 AC-6).

    Replaces the free-string field from e2e01; all legal values are enumerated
    here.  Historical values ``all_low_confidence`` and ``llm_unrecoverable``
    are preserved for backward compatibility.
    """

    ALL_LOW_CONFIDENCE = "all_low_confidence"
    LLM_UNRECOVERABLE = "llm_unrecoverable"
    ENCRYPTED_OFFICE_NO_PASSWORD = "encrypted_office_no_password"
    DOCUMENT_PARSER_FAILED = "document_parser_failed"
    ONENOTE_PARSER_UNAVAILABLE = "onenote_parser_unavailable"
    RECURSION_BUDGET_EXCEEDED = "recursion_budget_exceeded"
