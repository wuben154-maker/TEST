"""Unit tests for binary_analysis.schema.evidence_chain.

FR-09 AC-1: 17-bucket evidence chain declaration (including dynamic_behavior v1 empty placeholder).
FR-09 AC-2 (v1.1.0): 4 new document-specific buckets added (C1).
FR-09 AC-5 (v1.1.0): schema upgrade is backward-compatible; existing 17 buckets unchanged.
"""

from __future__ import annotations

from schema.evidence_chain import (
    BUCKET_NAMES,
    Bucket,
    EvidenceChainSnapshot,
    canonical_bucket_str,
    parse_bucket,
)

EXPECTED_BUCKETS_V1_0 = [
    "file_meta",
    "triage",
    "headers",
    "imports",
    "exports",
    "sections",
    "resources",
    "debug_info",
    "entropy",
    "packer",
    "strings_iocs",
    "disassembly",
    "behavior_chain",
    "llm_inferences",
    "scoring",
    "decision_gate",
    "dynamic_behavior",
]

NEW_V1_1_BUCKETS = [
    "document_analysis",
    "macro_analysis",
    "embedded_payloads",
    "delivery_chain_doc",
]

EXPECTED_BUCKETS = EXPECTED_BUCKETS_V1_0 + NEW_V1_1_BUCKETS


class TestBucketEnum:
    def test_all_17_legacy_buckets_present(self) -> None:
        for name in EXPECTED_BUCKETS_V1_0:
            assert name in BUCKET_NAMES, f"Bucket '{name}' missing from BUCKET_NAMES"

    def test_bucket_count(self) -> None:
        assert len(BUCKET_NAMES) == 21

    def test_all_21_buckets_present(self) -> None:
        for name in EXPECTED_BUCKETS:
            assert name in BUCKET_NAMES, f"Bucket '{name}' missing from BUCKET_NAMES"

    def test_bucket_enum_members(self) -> None:
        enum_values = {b.value for b in Bucket}
        for name in EXPECTED_BUCKETS:
            assert name in enum_values, f"Bucket enum missing '{name}'"

    def test_bucket_is_string_enum(self) -> None:
        assert isinstance(Bucket.file_meta, str)
        assert Bucket.file_meta == "file_meta"

    def test_dynamic_behavior_present(self) -> None:
        assert Bucket.dynamic_behavior == "dynamic_behavior"

    def test_packing_alias_maps_to_packer(self) -> None:
        assert canonical_bucket_str("packing") == "packer"
        assert parse_bucket("packing") == Bucket.packer
        assert parse_bucket("packer") == Bucket.packer

    def test_new_v1_1_bucket_members(self) -> None:
        assert Bucket.document_analysis == "document_analysis"
        assert Bucket.macro_analysis == "macro_analysis"
        assert Bucket.embedded_payloads == "embedded_payloads"
        assert Bucket.delivery_chain_doc == "delivery_chain_doc"


class TestEvidenceChainSnapshot:
    def test_default_produces_21_empty_buckets(self) -> None:
        snap = EvidenceChainSnapshot.model_validate({})
        dumped = snap.model_dump()
        assert len(dumped) == 21
        for name in EXPECTED_BUCKETS:
            assert name in dumped, f"Field '{name}' missing from snapshot"
            assert dumped[name] == [], f"Bucket '{name}' should default to []"

    def test_dynamic_behavior_always_empty_by_default(self) -> None:
        snap = EvidenceChainSnapshot.model_validate({})
        assert snap.dynamic_behavior == []

    def test_new_doc_buckets_default_to_empty_list(self) -> None:
        snap = EvidenceChainSnapshot.model_validate({})
        assert snap.document_analysis == []
        assert snap.macro_analysis == []
        assert snap.embedded_payloads == []
        assert snap.delivery_chain_doc == []

    def test_v1_0_snapshot_loads_without_doc_buckets(self) -> None:
        """e2e01 snapshots (no document buckets) must load without error (FR-09 AC-5)."""
        v1_0_payload: dict = {
            "file_meta": [],
            "triage": [],
            "headers": [],
            "imports": [],
            "exports": [],
            "sections": [],
            "resources": [],
            "debug_info": [],
            "entropy": [],
            "packer": [],
            "strings_iocs": [],
            "disassembly": [],
            "behavior_chain": [],
            "llm_inferences": [],
            "scoring": [],
            "decision_gate": [],
            "dynamic_behavior": [],
        }
        snap = EvidenceChainSnapshot.model_validate(v1_0_payload)
        assert snap.document_analysis == []
        assert snap.delivery_chain_doc == []

    def test_snapshot_accepts_indicator_list(self) -> None:
        from schema.indicator import Indicator, Severity

        ind = Indicator.model_validate(
            {
                "source_fr": "FR-04",
                "indicator_type": "pe_header",
                "severity": Severity.INFO,
                "confidence": "HIGH",
                "kind": "fact",
                "data": {},
            }
        )
        snap = EvidenceChainSnapshot.model_validate({"file_meta": [ind.model_dump()]})
        assert len(snap.file_meta) == 1
        assert snap.file_meta[0].indicator_type == "pe_header"

    def test_doc_bucket_accepts_indicator_list(self) -> None:
        from schema.indicator import Indicator, Severity

        ind = Indicator.model_validate(
            {
                "source_fr": "FR-09",
                "indicator_type": "ole_structure",
                "severity": Severity.INFO,
                "kind": "fact",
                "data": {},
            }
        )
        snap = EvidenceChainSnapshot.model_validate(
            {"document_analysis": [ind.model_dump()]}
        )
        assert len(snap.document_analysis) == 1
        assert snap.document_analysis[0].indicator_type == "ole_structure"

    def test_bucket_names_constant_matches_enum(self) -> None:
        enum_values = {b.value for b in Bucket}
        assert set(BUCKET_NAMES) == enum_values
