"""SUSPICIOUS evidence-chain fixture (FR-13 AC-1 / AC-2 middle band).

Triggers two rules (15 + 20 = 35 total):
- R-IMPORTS-SPARSE   (bucket=imports, indicator_type=imports_sparse)
- R-ANTIDEBUG-STRING (bucket=strings_iocs, indicator_type=anti_debug_string)

The COMBO-PACKED-DROPPER requires all three of (entropy, imports, strings)
to fire, so the combo deliberately does NOT trigger here.

Expected :func:`score_snapshot` output:
    rule_score == 35
    verdict_label == SUSPICIOUS  (30 < 35 <= 70)
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Severity
from tests.fixtures.evidence_chains._helpers import add_fact, new_store


def build(analysis_id: str = "suspicious-analysis") -> EvidenceChainStore:
    """Return a populated store that should score 35 / SUSPICIOUS."""
    store = new_store(analysis_id=analysis_id)
    add_fact(
        store,
        Bucket.imports,
        indicator_type="imports_sparse",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"import_count": 4},
    )
    add_fact(
        store,
        Bucket.strings_iocs,
        indicator_type="anti_debug_string",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"string": "IsDebuggerPresent"},
    )
    return store
