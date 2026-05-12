"""DecisionGateTool — post-scoring escalation gateway (FR-14, C12).

The decision gateway converts the deterministic scoring result plus
coverage signals into a structured escalation recommendation.  It does
NOT execute any dynamic analysis in v1 — the output is advisory only
(FR-14 AC-3 ``escalation_status = RECOMMENDED_NOT_EXECUTED``) and is
consumed by C13 :class:`ReportGenTool` to render the Markdown "升级建议"
section.

Three layers, pure → side-effectful:

1. :func:`decide_escalation` — pure function mapping an
   :class:`~schema.evidence_chain.EvidenceChainSnapshot`
   to a :class:`DecisionGateResult`.  No I/O, trivially unit-testable.
2. :class:`DecisionGateTool` — LangChain ``BaseTool`` wrapper that runs
   layer 1 against the shared
   :class:`~evidence_chain.store.EvidenceChainStore` and
   appends a single ``fact``-kind Indicator to the ``decision_gate``
   bucket (FR-14 AC-7).
3. :func:`markdown_disclaimer` — returns the fixed Chinese disclaimer
   string mandated by FR-14 AC-5; C13 embeds it verbatim into the
   Markdown report's escalation section.

Red lines
---------

- Decision rules are deterministic: same snapshot → same result.  No LLM,
  no randomness, no I/O inside :func:`decide_escalation`.
- ``escalation_status`` is ALWAYS
  :data:`ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED` in v1 (AC-3 red-line);
  no external sandbox integration until v1.5.
- ``dynamic_behavior`` is an empty list placeholder kept for v1.5
  forward-compatibility (AC-4 / ADR-02).  v1 components MUST NOT write to
  the ``dynamic_behavior`` bucket.
- Every non-empty ``escalation_reasons`` entry MUST cite at least one
  Indicator ID in ``evidence_refs`` (AC-2).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from audit import log_indicator_write
from evidence_chain.store import EvidenceChainStore
from schema.document_enums import (
    DocumentRole,
    DocumentTier,
    UnknownDowngradeReason,
)
from schema.evidence_chain import Bucket, EvidenceChainSnapshot
from schema.indicator import Confidence, Indicator, Severity
from schema.report import VerdictLabel

# ---------------------------------------------------------------------------
# Fixed constants (AC-3, AC-5)
# ---------------------------------------------------------------------------

ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED: Literal["RECOMMENDED_NOT_EXECUTED"] = (
    "RECOMMENDED_NOT_EXECUTED"
)
"""FR-14 AC-3: v1 only emits advisory recommendations, never executes them."""

MARKDOWN_DISCLAIMER: str = (
    "⚠️ 免责声明：本系统当前版本不执行样本代码，以下为静态分析后的下一步建议，"
    "请由分析师或 SOAR 平台自行调度动态分析。"
)
"""FR-14 AC-5 fixed Chinese disclaimer embedded verbatim by the Markdown report."""


def markdown_disclaimer() -> str:
    """Return the FR-14 AC-5 fixed Chinese disclaimer string.

    Provided as a function (rather than importing :data:`MARKDOWN_DISCLAIMER`
    directly) so downstream callers have a stable public entry point even
    if the constant is ever relocated behind a feature flag.

    Returns:
        The verbatim disclaimer text.
    """
    return MARKDOWN_DISCLAIMER


# ---------------------------------------------------------------------------
# Recommendation enum (AC-1)
# ---------------------------------------------------------------------------


class RecommendedEscalation(StrEnum):
    """Structured escalation recommendation (FR-14 AC-1).

    Values:
    - ``NONE``            — static-only analysis is sufficient, no further
      action recommended.
    - ``SANDBOX``         — suggest dynamic sandbox execution (evasion
      techniques detected / LLM overall low confidence).
    - ``MANUAL_REVERSE``  — suggest manual reverse engineering
      (decompilation coverage below threshold / behavior chain missing /
      targeted-attack indicators).
    - ``BOTH``            — both sandbox and manual paths recommended.
    """

    NONE = "NONE"
    SANDBOX = "SANDBOX"
    MANUAL_REVERSE = "MANUAL_REVERSE"
    BOTH = "BOTH"


# ---------------------------------------------------------------------------
# Result model (AC-1~5, AC-7 payload)
# ---------------------------------------------------------------------------


class EscalationReason(BaseModel):
    """One structured justification inside :class:`DecisionGateResult`.

    Args:
        reason_text: Short human-readable rationale (Chinese, analyst-facing).
        evidence_refs: Indicator IDs supporting this reason.  MUST contain
            at least one entry per FR-14 AC-2.
        trigger: Which escalation lane this reason belongs to — ``sandbox``
            or ``manual`` — used when synthesising the final enum.
    """

    reason_text: str
    evidence_refs: list[str] = Field(default_factory=list)
    trigger: Literal["sandbox", "manual"]

    model_config = ConfigDict(frozen=True)


class DecisionGateResult(BaseModel):
    """Deterministic decision-gateway output (FR-14 AC-1~5).

    Produced by :func:`decide_escalation` and embedded as the ``data``
    payload of the ``decision_gate`` bucket Indicator by
    :class:`DecisionGateTool`.
    """

    recommended_escalation: RecommendedEscalation
    escalation_reasons: list[EscalationReason] = Field(default_factory=list)
    escalation_status: Literal["RECOMMENDED_NOT_EXECUTED"] = (
        ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED
    )
    dynamic_behavior: list[Any] = Field(default_factory=list)
    markdown_disclaimer: str = MARKDOWN_DISCLAIMER

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Snapshot scanners (pure)
# ---------------------------------------------------------------------------


def _latest_scoring_indicator(snapshot: EvidenceChainSnapshot) -> Indicator | None:
    """Return the most recent ``indicator_type='scoring'`` fact, if any."""
    for ind in reversed(snapshot.scoring):
        if ind.indicator_type == "scoring":
            return ind
    return None


def _verdict_from_snapshot(snapshot: EvidenceChainSnapshot) -> VerdictLabel:
    """Extract the verdict produced by ScoringTool (falls back to UNKNOWN).

    DecisionGateTool is designed to run AFTER ScoringTool; when the
    ``scoring`` bucket is empty we treat the verdict as UNKNOWN so that
    coverage-gap triggers still apply.
    """
    scoring = _latest_scoring_indicator(snapshot)
    if scoring is None:
        return VerdictLabel.UNKNOWN
    label = scoring.data.get("verdict")
    if not isinstance(label, str):
        return VerdictLabel.UNKNOWN
    try:
        return VerdictLabel(label)
    except ValueError:
        return VerdictLabel.UNKNOWN


def _evasion_reasons(snapshot: EvidenceChainSnapshot) -> list[EscalationReason]:
    """Detect evasion / anti-analysis facts that justify sandbox escalation."""
    reasons: list[EscalationReason] = []
    if snapshot.packer:
        refs = [ind.id for ind in snapshot.packer]
        packer_names = sorted(
            {
                str(ind.data.get("packer", "unknown"))
                for ind in snapshot.packer
                if isinstance(ind.data, dict)
            }
        )
        reasons.append(
            EscalationReason(
                reason_text=(
                    f"检测到加壳/保护器（{', '.join(packer_names) or 'unknown'}），"
                    "建议在沙箱中观察解壳后的运行时行为。"
                ),
                evidence_refs=refs,
                trigger="sandbox",
            )
        )
    anti_debug_refs = [
        ind.id
        for ind in snapshot.strings_iocs
        if ind.indicator_type == "anti_debug_string"
    ]
    if anti_debug_refs:
        reasons.append(
            EscalationReason(
                reason_text=(
                    "样本包含反调试/反分析字符串，存在规避静态分析的迹象，"
                    "建议在动态沙箱验证真实执行路径。"
                ),
                evidence_refs=anti_debug_refs,
                trigger="sandbox",
            )
        )
    return reasons


def _low_confidence_reason(
    snapshot: EvidenceChainSnapshot,
) -> EscalationReason | None:
    """Flag an overall LLM low-confidence signal if every inference is LOW."""
    inferences = [ind for ind in snapshot.llm_inferences if ind.confidence is not None]
    if not inferences:
        return None
    if not all(ind.confidence is Confidence.LOW for ind in inferences):
        return None
    return EscalationReason(
        reason_text=(
            "LLM 推断整体置信度偏低（全部为 LOW），建议结合沙箱动态证据复核推断。"
        ),
        evidence_refs=[ind.id for ind in inferences],
        trigger="sandbox",
    )


def _coverage_reasons(
    snapshot: EvidenceChainSnapshot, verdict: VerdictLabel
) -> list[EscalationReason]:
    """Detect decompilation / behavior-chain coverage gaps for manual triggers.

    Coverage gaps on a BENIGN verdict do NOT trigger manual reverse —
    BENIGN implies the available evidence was already sufficient (AC-6).
    """
    if verdict is VerdictLabel.BENIGN:
        return []
    scoring = _latest_scoring_indicator(snapshot)
    anchor_refs = [scoring.id] if scoring is not None else []

    reasons: list[EscalationReason] = []
    if not snapshot.disassembly:
        reasons.append(
            EscalationReason(
                reason_text=(
                    "反编译覆盖度不足（disassembly 桶为空），"
                    "建议人工逆向补齐关键函数分析。"
                ),
                evidence_refs=anchor_refs,
                trigger="manual",
            )
        )
    if not snapshot.behavior_chain:
        reasons.append(
            EscalationReason(
                reason_text=(
                    "行为链未能重建（behavior_chain 桶为空），"
                    "建议人工逆向梳理样本的核心恶意路径。"
                ),
                evidence_refs=anchor_refs,
                trigger="manual",
            )
        )
    return reasons


def _targeted_attack_reason(
    snapshot: EvidenceChainSnapshot,
) -> EscalationReason | None:
    """Flag targeted-attack / APT indicators that justify manual review."""
    refs = [
        ind.id
        for ind in snapshot.llm_inferences
        if ind.indicator_type == "targeted_attack_indicator"
    ]
    if not refs:
        return None
    return EscalationReason(
        reason_text=("LLM 推断出疑似定向攻击特征，建议交由资深分析师人工逆向深挖。"),
        evidence_refs=refs,
        trigger="manual",
    )


# ---------------------------------------------------------------------------
# Document-specific snapshot readers (FR-14 AC-3)
# ---------------------------------------------------------------------------


def _document_tier_from_snapshot(snapshot: EvidenceChainSnapshot) -> str | None:
    """Read ``document_tier`` from the most recent ``file_meta`` indicator."""
    for ind in reversed(snapshot.file_meta):
        val = ind.data.get("document_tier")
        if val is not None:
            return str(val)
    return None


def _document_role_from_snapshot(snapshot: EvidenceChainSnapshot) -> str | None:
    """Read ``document_role`` from the most recent ``scoring`` indicator."""
    scoring = _latest_scoring_indicator(snapshot)
    if scoring is None:
        return None
    val = scoring.data.get("document_role")
    return str(val) if val is not None else None


def _unknown_downgrade_reason_from_snapshot(
    snapshot: EvidenceChainSnapshot,
) -> str | None:
    """Read ``unknown_downgrade_reason`` from scoring or llm_inferences bucket.

    Primary source is the scoring indicator (written by ScoringTool / C9).
    Secondary source is the ``llm_inferences`` bucket, which supports the
    parallel-batch mock interface (C10 ∥ C5).
    """
    scoring = _latest_scoring_indicator(snapshot)
    if scoring is not None:
        val = scoring.data.get("unknown_downgrade_reason")
        if val is not None:
            return str(val)
    for ind in reversed(snapshot.llm_inferences):
        val = ind.data.get("unknown_downgrade_reason")
        if val is not None:
            return str(val)
    return None


# ---------------------------------------------------------------------------
# Document-specific escalation triggers (FR-14 AC-3)
# ---------------------------------------------------------------------------

_INCOMPLETE_RECURSION_REASONS: frozenset[str] = frozenset(
    [
        UnknownDowngradeReason.RECURSION_BUDGET_EXCEEDED,
        UnknownDowngradeReason.DOCUMENT_PARSER_FAILED,
    ]
)
"""Downgrade reasons that indicate a sub-payload was not fully recursed."""


def _infection_source_incomplete_recursion_reason(
    snapshot: EvidenceChainSnapshot,
) -> EscalationReason | None:
    """Trigger SANDBOX when an infection-source document has incomplete recursion.

    FR-14 AC-3 condition 1: ``document_role = infection_source`` AND
    ``unknown_downgrade_reason`` is ``recursion_budget_exceeded`` or
    ``document_parser_failed`` → recommend ``SANDBOX`` so that a dynamic
    sandbox can complete the sub-payload analysis.
    """
    role = _document_role_from_snapshot(snapshot)
    if role != DocumentRole.INFECTION_SOURCE:
        return None
    downgrade_reason = _unknown_downgrade_reason_from_snapshot(snapshot)
    if downgrade_reason not in _INCOMPLETE_RECURSION_REASONS:
        return None
    refs: list[str] = []
    scoring = _latest_scoring_indicator(snapshot)
    if scoring is not None:
        refs.append(scoring.id)
    refs.extend(ind.id for ind in snapshot.embedded_payloads)
    if not refs:
        return None
    return EscalationReason(
        reason_text=(
            "文档角色为感染源（infection_source）且子载荷未能完整递归分析"
            f"（{downgrade_reason}），建议在沙箱中完成子样本动态分析。"
        ),
        evidence_refs=refs,
        trigger="sandbox",
    )


def _p2_tier_active_content_reason(
    snapshot: EvidenceChainSnapshot,
) -> EscalationReason | None:
    """Trigger MANUAL_REVERSE for P2-tier documents with active content.

    FR-14 AC-3 condition 2: ``document_tier = P2`` AND at least one of
    VBA macro / embedded JS / embedded PE present → recommend
    ``MANUAL_REVERSE`` because P2-tier parsers have limited coverage and
    active content may hide malicious behaviour.

    Detection logic (mirrors scoring rule definitions):
    - VBA macro: any indicator in ``macro_analysis`` bucket.
    - Embedded JS: ``document_analysis`` indicator with
      ``indicator_type == "pdf_action_chain"`` and ``data["tag"] == "js_trigger"``.
    - Embedded PE: ``embedded_payloads`` indicator with
      ``data["suggested_format"] == "pe"``.
    """
    tier = _document_tier_from_snapshot(snapshot)
    if tier != DocumentTier.P2:
        return None
    vba_refs = [ind.id for ind in snapshot.macro_analysis]
    js_refs = [
        ind.id
        for ind in snapshot.document_analysis
        if ind.indicator_type == "pdf_action_chain"
        and ind.data.get("tag") == "js_trigger"
    ]
    pe_refs = [
        ind.id
        for ind in snapshot.embedded_payloads
        if ind.data.get("suggested_format") == "pe"
    ]
    active_refs = [*vba_refs, *js_refs, *pe_refs]
    if not active_refs:
        return None
    parts: list[str] = []
    if vba_refs:
        parts.append("VBA 宏")
    if js_refs:
        parts.append("嵌入 JS")
    if pe_refs:
        parts.append("嵌入 PE")
    return EscalationReason(
        reason_text=(
            f"文档分析复杂度为 P2 层级且包含活跃内容（{'、'.join(parts)}），"
            "P2 格式解析器覆盖度有限，建议人工逆向深入分析。"
        ),
        evidence_refs=active_refs,
        trigger="manual",
    )


def _encrypted_office_no_password_reason(
    snapshot: EvidenceChainSnapshot,
) -> EscalationReason | None:
    """Trigger MANUAL_REVERSE when an encrypted Office file has no matching password.

    FR-14 AC-3 condition 3: ``unknown_downgrade_reason =
    encrypted_office_no_password`` → recommend ``MANUAL_REVERSE`` so an
    analyst can attempt manual password recovery or reverse the encryption logic.

    Evidence refs are collected from the scoring indicator (primary) and any
    ``llm_inferences`` indicator that carries the same marker (mock path).
    """
    refs: list[str] = []
    scoring = _latest_scoring_indicator(snapshot)
    if (
        scoring is not None
        and scoring.data.get("unknown_downgrade_reason")
        == UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD
    ):
        refs.append(scoring.id)
    for ind in snapshot.llm_inferences:
        if (
            ind.data.get("unknown_downgrade_reason")
            == UnknownDowngradeReason.ENCRYPTED_OFFICE_NO_PASSWORD
        ):
            refs.append(ind.id)
    if not refs:
        return None
    return EscalationReason(
        reason_text=(
            "Office 文档已加密但密码字典中无匹配密码（encrypted_office_no_password），"
            "内容未能解密，建议人工尝试密码或逆向加密逻辑。"
        ),
        evidence_refs=refs,
        trigger="manual",
    )


# ---------------------------------------------------------------------------
# Pure decision entry point (AC-1 / AC-6)
# ---------------------------------------------------------------------------


def decide_escalation(snapshot: EvidenceChainSnapshot) -> DecisionGateResult:
    """Map an evidence-chain snapshot to a :class:`DecisionGateResult` (pure).

    Decision algorithm (FR-14):

    1. Extract verdict from the latest ``scoring`` bucket Indicator
       (fallback: UNKNOWN).
    2. Collect sandbox-lane reasons (packer / anti-debug strings /
       all-LOW LLM inferences).
    3. Collect manual-lane reasons (missing decompilation / missing
       behavior chain / targeted-attack indicators) — skipped when the
       verdict is BENIGN per AC-6.
    4. Combine triggers:
       - sandbox ∧ manual → BOTH
       - sandbox only     → SANDBOX
       - manual only      → MANUAL_REVERSE
       - neither          → NONE (static-only analysis is sufficient)

    Args:
        snapshot: Read-only snapshot from the evidence-chain store.

    Returns:
        :class:`DecisionGateResult` carrying the recommendation, reasons
        with evidence IDs, fixed status constant, empty dynamic-behavior
        placeholder, and the Chinese disclaimer.
    """
    verdict = _verdict_from_snapshot(snapshot)

    reasons: list[EscalationReason] = []

    # FR-14 AC-3: Document-specific triggers (inserted before binary rules)
    doc_infection = _infection_source_incomplete_recursion_reason(snapshot)
    if doc_infection is not None:
        reasons.append(doc_infection)
    doc_p2 = _p2_tier_active_content_reason(snapshot)
    if doc_p2 is not None:
        reasons.append(doc_p2)
    doc_enc = _encrypted_office_no_password_reason(snapshot)
    if doc_enc is not None:
        reasons.append(doc_enc)

    # Binary / generic triggers
    reasons.extend(_evasion_reasons(snapshot))
    low_conf = _low_confidence_reason(snapshot)
    if low_conf is not None:
        reasons.append(low_conf)
    reasons.extend(_coverage_reasons(snapshot, verdict))
    targeted = _targeted_attack_reason(snapshot)
    if targeted is not None:
        reasons.append(targeted)

    has_sandbox = any(r.trigger == "sandbox" for r in reasons)
    has_manual = any(r.trigger == "manual" for r in reasons)

    if has_sandbox and has_manual:
        recommendation = RecommendedEscalation.BOTH
    elif has_sandbox:
        recommendation = RecommendedEscalation.SANDBOX
    elif has_manual:
        recommendation = RecommendedEscalation.MANUAL_REVERSE
    else:
        recommendation = RecommendedEscalation.NONE

    return DecisionGateResult(
        recommended_escalation=recommendation,
        escalation_reasons=reasons,
        escalation_status=ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED,
        dynamic_behavior=[],
        markdown_disclaimer=MARKDOWN_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# LangChain tool wrapper (AC-7 side effect)
# ---------------------------------------------------------------------------


class DecisionGateInput(BaseModel):
    """Input schema for :class:`DecisionGateTool`."""

    analysis_id: str

    model_config = ConfigDict(extra="forbid")


_RECOMMENDATION_SEVERITY: dict[RecommendedEscalation, Severity] = {
    RecommendedEscalation.NONE: Severity.INFO,
    RecommendedEscalation.SANDBOX: Severity.WARNING,
    RecommendedEscalation.MANUAL_REVERSE: Severity.WARNING,
    RecommendedEscalation.BOTH: Severity.WARNING,
}


def _aggregate_evidence_refs(reasons: list[EscalationReason]) -> list[str]:
    """Return a de-duplicated, stable-ordered union of all reason refs."""
    seen: set[str] = set()
    out: list[str] = []
    for reason in reasons:
        for ref in reason.evidence_refs:
            if ref not in seen:
                seen.add(ref)
                out.append(ref)
    return out


def _decision_gate_data_payload(result: DecisionGateResult) -> dict[str, Any]:
    """Serialise :class:`DecisionGateResult` into the Indicator ``data`` field."""
    payload = result.model_dump(mode="json")
    payload["recommended_escalation"] = result.recommended_escalation.value
    return payload


class DecisionGateTool(BaseTool):
    """LangChain tool that runs the decision gateway and writes the bucket.

    Args:
        store: Shared per-analysis
            :class:`~evidence_chain.store.EvidenceChainStore`.

    The tool is synchronous: :func:`decide_escalation` is pure and the
    single side effect (append one Indicator) is synchronous.
    """

    name: str = "decision_gate"
    description: str = (
        "Run the deterministic decision gateway over the current evidence "
        "chain and emit a structured escalation recommendation. Produces "
        "the FR-14 advisory output: recommended_escalation (NONE / SANDBOX "
        "/ MANUAL_REVERSE / BOTH), escalation_reasons with Indicator "
        "evidence_refs, the fixed escalation_status "
        "'RECOMMENDED_NOT_EXECUTED' (v1 does not execute samples), an "
        "empty dynamic_behavior placeholder (reserved for v1.5), and the "
        "fixed Chinese Markdown disclaimer. Appends a single 'fact' "
        "Indicator to the 'decision_gate' bucket (FR-14 AC-7)."
    )
    args_schema: type[BaseModel] = DecisionGateInput
    store: EvidenceChainStore

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        DecisionGateInput(**kwargs)
        snapshot = self.store.snapshot()
        result = decide_escalation(snapshot)
        indicator = self._build_decision_indicator(result)
        self.store.append(Bucket.decision_gate, indicator)
        log_indicator_write(
            indicator_id=indicator.id,
            bucket=Bucket.decision_gate.value,
            kind=indicator.kind,
            severity=indicator.severity.value,
            source_fr=indicator.source_fr,
        )
        payload = _decision_gate_data_payload(result)
        payload["indicator_id"] = indicator.id
        return payload

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return self._run(**kwargs)

    def _build_decision_indicator(self, result: DecisionGateResult) -> Indicator:
        """Build the ``decision_gate`` bucket Indicator (FR-14 AC-7)."""
        refs = _aggregate_evidence_refs(result.escalation_reasons)
        return Indicator(
            source_fr="FR-14",
            indicator_type="decision_gate",
            severity=_RECOMMENDATION_SEVERITY[result.recommended_escalation],
            confidence=Confidence.HIGH,
            kind="fact",
            evidence_refs=refs,
            data=_decision_gate_data_payload(result),
        )


__all__ = [
    "ESCALATION_STATUS_RECOMMENDED_NOT_EXECUTED",
    "MARKDOWN_DISCLAIMER",
    "DecisionGateInput",
    "DecisionGateResult",
    "DecisionGateTool",
    "EscalationReason",
    "RecommendedEscalation",
    "decide_escalation",
    "markdown_disclaimer",
    # document-specific helpers (FR-14 AC-3)
    "_INCOMPLETE_RECURSION_REASONS",
    "_document_tier_from_snapshot",
    "_document_role_from_snapshot",
    "_unknown_downgrade_reason_from_snapshot",
    "_infection_source_incomplete_recursion_reason",
    "_p2_tier_active_content_reason",
    "_encrypted_office_no_password_reason",
]
