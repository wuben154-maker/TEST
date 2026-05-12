"""MALICIOUS evidence-chain fixture (FR-13 AC-1 / AC-2 upper band).

Triggers five individual rules plus the combo:
- R-ENTROPY-HIGH      (25)
- R-IMPORTS-SPARSE    (15)
- R-ANTIDEBUG-STRING  (20)
- R-PACKER-KNOWN      (30)
- R-BEHAVIOR-MAL-CHAIN (20)
- COMBO-PACKED-DROPPER bonus (+25)

Subtotal: 25+15+20+30+20 = 110, +25 combo = 135 -> clamped to 100.

Also seeds ``llm_inferences`` with a ``family_candidate`` (FR-13 AC-4)
and a ``threat_class`` inference (FR-13 AC-3) so the result covers the
full downstream schema.

Expected :func:`score_snapshot` output:
    rule_score == 100
    verdict_label == MALICIOUS
    family_name == "AgentTesla"
    threat_classes == ["InfoStealer", "RAT"]
"""

from __future__ import annotations

from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Severity
from tests.fixtures.evidence_chains._helpers import (
    add_fact,
    add_inference,
    anchor_id,
    new_store,
)


def build(analysis_id: str = "malicious-analysis") -> EvidenceChainStore:
    """Return a populated store that should score 100 / MALICIOUS."""
    store = new_store(analysis_id=analysis_id)
    anchor = anchor_id(store)

    add_fact(
        store,
        Bucket.entropy,
        indicator_type="entropy_section",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"section": ".text", "entropy": 7.91},
    )
    add_fact(
        store,
        Bucket.imports,
        indicator_type="imports_sparse",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"import_count": 3},
    )
    add_fact(
        store,
        Bucket.strings_iocs,
        indicator_type="anti_debug_string",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        data={"string": "CheckRemoteDebuggerPresent"},
    )
    add_fact(
        store,
        Bucket.packer,
        indicator_type="packer_detected",
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        data={"packer": "UPX"},
    )
    add_fact(
        store,
        Bucket.behavior_chain,
        indicator_type="behavior_segment",
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        data={"segment": "persistence -> registry_autorun"},
    )

    add_inference(
        store,
        Bucket.llm_inferences,
        indicator_type="family_candidate",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        data={"family": "AgentTesla", "rationale": "SMTP exfil + keylog hooks"},
    )
    add_inference(
        store,
        Bucket.llm_inferences,
        indicator_type="threat_class",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        evidence_refs=[anchor],
        data={"classes": ["InfoStealer", "RAT"]},
    )
    return store
