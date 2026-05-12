"""LLM-degraded facts-only report path (FR-08 AC-11 / E2E-01 E4)."""

from __future__ import annotations

import shutil
from pathlib import Path

from audit import log_llm_request
from evidence_chain.store import EvidenceChainStore
from schema.report import (
    EscalationLevel,
    EscalationRecommendation,
    Verdict,
    VerdictLabel,
)
from tools.report_gen import (
    ReportGenResult,
    build_report_v1,
    render_json,
    render_markdown,
)

__all__ = ["build_facts_only_report"]


def _cleanup_analysis_tmpdir(tmp_root: Path | None, analysis_id: str) -> bool:
    """Remove ``<tmp_root>/deepagent-analyze-<analysis_id>/`` (IR-03).

    Duplicates :func:`binary_analysis.tools.report_gen._cleanup_analysis_tmp`
    so the facts-only path stays independent of the full ReportGenTool
    machinery (the degraded report does not run
    ``scoring``/``decision_gate`` so we cannot invoke ReportGenTool).
    """
    if tmp_root is None:
        return False
    target = Path(tmp_root) / f"deepagent-analyze-{analysis_id}"
    if not target.exists():
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not target.exists()


def build_facts_only_report(
    *,
    store: EvidenceChainStore,
    analysis_id: str,
    output_dir: Path | str,
    reason: str,
    tmp_root: Path | str | None = None,
    model_label: str = "unknown",
) -> ReportGenResult:
    """Emit a minimal UNKNOWN report from tool-derived facts only (FR-08 AC-11).

    This is the E2E-01 E4 degradation path: after three consecutive
    unrecoverable LLM failures the host short-circuits the Agent and
    calls this helper.  The rendered report reuses
    :func:`build_report_v1` / :func:`render_json` / :func:`render_markdown`
    but forces ``verdict.label=UNKNOWN`` and
    ``escalation_recommendation.level=MANUAL_REVERSE`` so downstream
    consumers cannot interpret it as a high-confidence call.

    Args:
        store: :class:`EvidenceChainStore` containing at minimum the
            FR-01 ``file_meta`` Indicator (raises ``ValueError``
            otherwise).
        analysis_id: ULID of the analysis run.
        output_dir: Directory for ``<sha256>.report.{json,md}``.
        reason: Human-readable description of the LLM failure mode
            (e.g. ``"three consecutive LlmSchemaError"``); surfaced in
            ``analysis_coverage.gaps`` and the audit log.
        tmp_root: Optional host tmpdir; when supplied the
            ``deepagent-analyze-<analysis_id>`` sub-directory is cleaned
            up per FR-15 AC-10 / IR-03.
        model_label: Model identifier recorded in the audit entry
            (``"fake-llm"`` in tests, actual model slug in production).

    Returns:
        :class:`ReportGenResult` with the paths of the written artefacts
        and the cleanup flag.
    """
    snapshot = store.snapshot()
    base_report = build_report_v1(snapshot, analysis_id=analysis_id)

    gap_note = f"LLM layer degraded: {reason}"
    existing_gaps = list(base_report.analysis_coverage.gaps)
    if gap_note not in existing_gaps:
        existing_gaps.append(gap_note)
    degraded_coverage = base_report.analysis_coverage.model_copy(
        update={"gaps": existing_gaps},
    )
    degraded = base_report.model_copy(
        update={
            "verdict": Verdict(label=VerdictLabel.UNKNOWN, rule_score=0.0),
            "escalation_recommendation": EscalationRecommendation(
                level=EscalationLevel.MANUAL_REVERSE,
                reasons=[gap_note],
                evidence_gaps=[reason],
            ),
            "analysis_coverage": degraded_coverage,
        },
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    sha256 = degraded.fingerprints.sha256
    json_path = output_path / f"{sha256}.report.json"
    md_path = output_path / f"{sha256}.report.md"
    json_path.write_text(render_json(degraded), encoding="utf-8")
    md_path.write_text(render_markdown(degraded), encoding="utf-8")

    cleanup_performed = _cleanup_analysis_tmpdir(
        Path(tmp_root) if tmp_root is not None else None,
        analysis_id,
    )

    log_llm_request(
        model=model_label,
        stage="facts_only_fallback",
        prompt_tokens=0,
        completion_tokens=0,
        duration_ms=0.0,
        success=False,
        error_code="LLM_UNRECOVERABLE",
    )

    return ReportGenResult(
        json_path=str(json_path),
        md_path=str(md_path),
        sha256=sha256,
        schema_version=degraded.schema_version,
        cleanup_performed=cleanup_performed,
    )
