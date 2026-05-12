"""Schema package — v1.1.0 (C1, NFR-12).

Exports the complete public surface of the schema layer.  Downstream batches
(C3 / C6 / C11 / C12 / C13) MUST import from this package rather than from
individual sub-modules so that the import path remains stable across SemVer
bumps.

Stability contract (NFR-12 SemVer):
- All names exported here are considered public API.
- Removing or renaming any export requires a major version bump.
- New exports may be added freely (minor / patch bump).

v1.1.0 additions (C1 / FR-09 / FR-13 / FR-15):
- document_enums: DocumentFormat, DocumentTier, DocumentRole, UnknownDowngradeReason
- indicator_types_v1_1: DOC_ANALYSIS_TYPES, MACRO_ANALYSIS_TYPES,
  EMBEDDED_PAYLOADS_TYPES, DELIVERY_CHAIN_DOC_TYPES, ALL_DOC_INDICATOR_TYPES
- Bucket: 4 new document buckets
- EvidenceChainSnapshot: 4 new bucket fields
- ReportV1: schema_version=1.1.0 + 9 new Optional document fields
"""

from schema.document_enums import (
    DocumentFormat,
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.evidence_chain import (
    BUCKET_NAMES,
    Bucket,
    EvidenceChainSnapshot,
    canonical_bucket_str,
    parse_bucket,
)
from schema.indicator import (
    Confidence,
    Indicator,
    Severity,
    new_indicator_id,
)
from schema.indicator_types_v1_1 import (
    ALL_DOC_INDICATOR_TYPES,
    DELIVERY_CHAIN_DOC_TYPES,
    DOC_ANALYSIS_TYPES,
    EMBEDDED_PAYLOADS_TYPES,
    MACRO_ANALYSIS_TYPES,
)
from schema.report import (
    AnalysisCoverage,
    BehaviorChain,
    BehaviorEdge,
    BehaviorNode,
    CoverageStatus,
    EscalationLevel,
    EscalationRecommendation,
    FileMeta,
    Fingerprints,
    MalwareFamily,
    ReportV1,
    RiskScore,
    ThreatClass,
    Verdict,
    VerdictLabel,
)

__all__ = [
    # indicator
    "Severity",
    "Confidence",
    "Indicator",
    "new_indicator_id",
    # evidence chain
    "Bucket",
    "BUCKET_NAMES",
    "EvidenceChainSnapshot",
    "canonical_bucket_str",
    "parse_bucket",
    # document enums (v1.1.0)
    "DocumentFormat",
    "DocumentTier",
    "DocumentRole",
    "UnknownDowngradeReason",
    # indicator type sets (v1.1.0)
    "DOC_ANALYSIS_TYPES",
    "MACRO_ANALYSIS_TYPES",
    "EMBEDDED_PAYLOADS_TYPES",
    "DELIVERY_CHAIN_DOC_TYPES",
    "ALL_DOC_INDICATOR_TYPES",
    # report sub-models
    "VerdictLabel",
    "EscalationLevel",
    "CoverageStatus",
    "FileMeta",
    "Fingerprints",
    "Verdict",
    "RiskScore",
    "ThreatClass",
    "MalwareFamily",
    "BehaviorNode",
    "BehaviorEdge",
    "BehaviorChain",
    "EscalationRecommendation",
    "AnalysisCoverage",
    # top-level report
    "ReportV1",
]
