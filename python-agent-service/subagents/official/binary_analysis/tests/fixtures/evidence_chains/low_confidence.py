"""LOW-confidence fixture for FR-13 AC-8 UNKNOWN downgrade.

Triggers two rules whose matched Indicators all carry
``confidence=LOW``:
- R-IMPORTS-SPARSE   (15)
- R-ANTIDEBUG-STRING (20)

Raw score == 35 which normally maps to SUSPICIOUS, but AC-8 downgrades the
verdict to UNKNOWN because every contributing Indicator carries LOW
confidence and the score sits under ``unknown_low_confidence_max``.
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Severity
from tests.fixtures.evidence_chains._helpers import add_fact, new_store


def build(analysis_id: str = "low-confidence-analysis") -> EvidenceChainStore:
    """Return a store whose contributing Indicators all carry LOW confidence."""
    store = new_store(analysis_id=analysis_id)
    add_fact(
        store,
        Bucket.imports,
        indicator_type="imports_sparse",
        severity=Severity.WARNING,
        confidence=Confidence.LOW,
        data={"import_count": 7, "note": "heuristic threshold, weak signal"},
    )
    add_fact(
        store,
        Bucket.strings_iocs,
        indicator_type="anti_debug_string",
        severity=Severity.WARNING,
        confidence=Confidence.LOW,
        data={"string": "debug", "note": "single-word match, weak signal"},
    )
    return store
