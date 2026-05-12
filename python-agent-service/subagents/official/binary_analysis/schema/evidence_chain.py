"""Evidence-chain snapshot schema — 21-bucket structure (ADR-02, v1.1.0).

The evidence chain is the single source of truth consumed by FR-08 / FR-13 /
FR-15.  Schema v1.0.0 defined 17 buckets (C2); v1.1.0 adds 4 document-specific
buckets (C1 / FR-09 AC-2) while preserving full backward compatibility (all new
fields are Optional with empty-list defaults).

Bucket ordering follows the analysis pipeline: file identification → triage →
structural analysis → decompilation → LLM reasoning → scoring → decision →
document-specific dimensions.

`dynamic_behavior` is the v1.5 placeholder bucket; it is always empty in v1
and MUST NOT be written to by any C2–C15 component (reserved for external
sandbox integration, v1.5).

New v1.1.0 document buckets (FR-09 AC-2):
- `document_analysis`  — document structure, triggers, DDE, template injection, metadata
- `macro_analysis`     — VBA / XL4 macro source, simulation events and gaps
- `embedded_payloads`  — embedded file manifests and ``child_sample_id`` references
- `delivery_chain_doc` — delivery-chain hierarchy tree and parent–child sample links
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field

from schema.indicator import Indicator


class Bucket(StrEnum):
    """Evidence-chain bucket identifiers (ADR-02).

    Each value corresponds to a domain dimension of the binary analysis
    pipeline.  The string value is used as the JSON key in
    `EvidenceChainSnapshot`.
    """

    file_meta = "file_meta"
    triage = "triage"
    headers = "headers"
    imports = "imports"
    exports = "exports"
    sections = "sections"
    resources = "resources"
    debug_info = "debug_info"
    entropy = "entropy"
    packer = "packer"
    strings_iocs = "strings_iocs"
    disassembly = "disassembly"
    behavior_chain = "behavior_chain"
    llm_inferences = "llm_inferences"
    scoring = "scoring"
    decision_gate = "decision_gate"
    dynamic_behavior = "dynamic_behavior"
    # v1.1.0 document-specific buckets (FR-09 AC-2)
    document_analysis = "document_analysis"
    macro_analysis = "macro_analysis"
    embedded_payloads = "embedded_payloads"
    delivery_chain_doc = "delivery_chain_doc"


BUCKET_NAMES: list[str] = [b.value for b in Bucket]
"""Ordered list of all 21 bucket names (matches Bucket enum declaration order).

v1.0.0: 17 buckets (file_meta … dynamic_behavior).
v1.1.0: +4 document buckets (document_analysis, macro_analysis,
         embedded_payloads, delivery_chain_doc).
"""


_LEGACY_BUCKET_ALIASES: Final[dict[str, str]] = {
    # Legacy typo in Gap-03 / older docs; canonical enum member is `packer`.
    "packing": "packer",
}


def canonical_bucket_str(raw: str) -> str:
    """Map legacy bucket spellings to the canonical string used by :class:`Bucket`.

    Args:
        raw: Bucket name from tool input, YAML, or LLM output.

    Returns:
        Canonical bucket string (e.g. ``"packer"`` when ``raw`` is ``"packing"``).
    """
    return _LEGACY_BUCKET_ALIASES.get(raw, raw)


def parse_bucket(raw: str) -> Bucket:
    """Parse a bucket string into :class:`Bucket`, accepting legacy aliases.

    Args:
        raw: Bucket name or alias (e.g. ``"packing"`` → ``Bucket.packer``).

    Returns:
        The corresponding :class:`Bucket` member.

    Raises:
        ValueError: If ``raw`` is not a valid bucket name after alias resolution.
    """
    return Bucket(canonical_bucket_str(raw))


class EvidenceChainSnapshot(BaseModel):
    """Read-only snapshot of the evidence chain (v1.1.0, 21 buckets).

    Each field corresponds to one analysis bucket and contains an ordered list
    of Indicators written by Tools or the LLM layer during a single analysis
    run.  All buckets default to an empty list so that callers can
    ``model_validate({})`` to obtain a zeroed snapshot.

    `dynamic_behavior` is always empty in v1 (reserved for v1.5 external
    sandbox integration).

    The four v1.1.0 document buckets (`document_analysis`, `macro_analysis`,
    `embedded_payloads`, `delivery_chain_doc`) also default to ``[]`` so that
    e2e01 v1.0.0 snapshots load without error (FR-09 AC-5 / NFR-12).

    The snapshot is immutable once created (``frozen=True``); downstream
    consumers MUST NOT mutate it.  Mutations are performed only through
    ``EvidenceChainStore.append`` (C3).
    """

    file_meta: list[Indicator] = Field(default_factory=list)
    triage: list[Indicator] = Field(default_factory=list)
    headers: list[Indicator] = Field(default_factory=list)
    imports: list[Indicator] = Field(default_factory=list)
    exports: list[Indicator] = Field(default_factory=list)
    sections: list[Indicator] = Field(default_factory=list)
    resources: list[Indicator] = Field(default_factory=list)
    debug_info: list[Indicator] = Field(default_factory=list)
    entropy: list[Indicator] = Field(default_factory=list)
    packer: list[Indicator] = Field(default_factory=list)
    strings_iocs: list[Indicator] = Field(default_factory=list)
    disassembly: list[Indicator] = Field(default_factory=list)
    behavior_chain: list[Indicator] = Field(default_factory=list)
    llm_inferences: list[Indicator] = Field(default_factory=list)
    scoring: list[Indicator] = Field(default_factory=list)
    decision_gate: list[Indicator] = Field(default_factory=list)
    dynamic_behavior: list[Indicator] = Field(default_factory=list)
    # v1.1.0 document-specific buckets (FR-09 AC-2); all default to [] for
    # backward compatibility — e2e01 snapshots load without error.
    document_analysis: list[Indicator] = Field(default_factory=list)
    macro_analysis: list[Indicator] = Field(default_factory=list)
    embedded_payloads: list[Indicator] = Field(default_factory=list)
    delivery_chain_doc: list[Indicator] = Field(default_factory=list)

    model_config = {"frozen": True}
