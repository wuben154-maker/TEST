"""Orchestrate web-threat classification, scanning, scoring, and output."""

from __future__ import annotations

from typing import Any

from .classify import classify_artifact
from .constants import MAX_INPUT_BYTES
from .entropy_layer import entropy_findings
from .forensic_supplement import build_forensic_supplement
from .http_parse import parse_http_request
from .e2b_dynamic_layer import run_e2b_dynamic, should_escalate
from .layer_env import (
    e2b_escalation_enabled,
    entropy_enabled,
    sandbox_enabled,
    yara_enabled,
)
from .models import (
    AnalysisLayersStatus,
    DecodedArtifact,
    Finding,
    ForensicSupplement,
    IOC,
    MitreTechnique,
    ParseStatus,
    SourceInfo,
    ToolError,
    WebThreatReport,
)
from .php_deobfuscation import decode_php_layers
from .webshell_intel import extract_webshell_intel
from .code_scanners import scan_hosted_code
from .sandbox_layer import run_syntax_sandbox
from .scoring import add_risk_scores, build_legacy, cap_high_critical
from .yara_loader import resolve_web_security_yara_dir
from . import yara_layer
from .traffic_analyzer import analyze_traffic_params
from .weak_signals import (
    fallback_content_signals,
    weak_signals_full_blob,
)


def _truncate_input(raw: str) -> tuple[str, bool]:
    data = raw.encode("utf-8", errors="replace")
    if len(data) <= MAX_INPUT_BYTES:
        return raw, False
    cut = data[:MAX_INPUT_BYTES].decode("utf-8", errors="replace")
    return cut, True


def analyze_web_threat(
    request_data: str,
    hint: str = "auto",
    source: SourceInfo | None = None,
    tool_error: ToolError | None = None,
) -> dict[str, Any]:
    """Run semantic pipeline; return tool dict (schema v2 + legacy top-level).

    Args:
        request_data: Raw HTTP text, log line, or source code.
        hint: ``auto``, ``http``, or ``code`` — classifier override.
    """
    text, truncated = _truncate_input(request_data)
    source_info = source or SourceInfo(kind="inline")
    source_info = source_info.model_copy(update={"truncated": truncated})
    artifact = classify_artifact(text, hint)

    parse_status = ParseStatus(truncated=truncated)
    findings: list = []
    decoded_artifacts: list[DecodedArtifact] = []
    behaviors: list[str] = []
    capabilities: list[str] = []
    iocs: list[IOC] = []
    mitre_attack: list[MitreTechnique] = []
    recommended_actions: list[str] = []
    tool_limitations: list[str] = []
    forensic_supplement: ForensicSupplement = ForensicSupplement()

    run_traffic = artifact in ("http_traffic", "mixed", "unknown")
    run_code = artifact in ("webshell_or_code", "mixed", "unknown")

    if run_traffic:
        parsed = parse_http_request(text)
        parse_status.http.ok = parsed.ok
        parse_status.http.errors = parsed.errors
        if parsed.ok:
            findings.extend(analyze_traffic_params(parsed))
        else:
            findings.extend(weak_signals_full_blob(text))
            findings.extend(fallback_content_signals(text))

    if run_code:
        layers = AnalysisLayersStatus()
        data_bytes = text.encode("utf-8", errors="replace")

        if yara_enabled():
            rules, yst, ycnt, ydetail = yara_layer.compile_rules(
                resolve_web_security_yara_dir()
            )
            layers.yara = yst
            layers.yara_rules_compiled = ycnt
            layers.yara_detail = (ydetail or "")[:500]
            if yst == "ok" and rules is not None:
                findings.extend(
                    yara_layer.scan_with_compiled(rules, data_bytes)
                )
        else:
            layers.yara = "disabled"

        if entropy_enabled():
            layers.entropy = "ok"
            findings.extend(entropy_findings(text))
        else:
            layers.entropy = "disabled"

        code_findings, ast_ok, lang = scan_hosted_code(text)
        parse_status.code.ast_ok = ast_ok
        parse_status.code.language = lang
        for cf in code_findings:
            findings.append(
                cf
                if cf.layer is not None
                else cf.model_copy(update={"layer": "L2"})
            )

        if lang == "php":
            decoded_artifacts = decode_php_layers(text)
            decoded_texts = [
                artifact.preview for artifact in decoded_artifacts
            ]
            for idx, decoded_text in enumerate(decoded_texts, start=1):
                decoded_findings, _, _ = scan_hosted_code(decoded_text)
                findings.extend(
                    _decoded_findings(decoded_findings, idx, decoded_text)
                )
            (
                behaviors,
                capabilities,
                iocs,
                mitre_attack,
                recommended_actions,
            ) = extract_webshell_intel([text, *decoded_texts], lang)
            if len(decoded_artifacts) >= 3:
                tool_limitations.append(
                    "php_deobfuscation_limited_to_three_layers"
                )
        elif lang in ("python", "jsp", "aspx", "html", "javascript"):
            (
                behaviors,
                capabilities,
                iocs,
                mitre_attack,
                recommended_actions,
            ) = extract_webshell_intel([text], lang)

        dec_previews: list[str] = []
        if lang == "php" and decoded_artifacts:
            dec_previews = [a.preview for a in decoded_artifacts[:5]]
        fs_model, extra_beh = build_forensic_supplement(
            original=text,
            decoded_layers=dec_previews,
            language=lang or "",
        )
        forensic_supplement = fs_model
        if extra_beh:
            behaviors = sorted(set(behaviors) | set(extra_beh))

        if sandbox_enabled():
            if lang in ("php", "python"):
                sf, sst, sdet = run_syntax_sandbox(text, lang)
                findings.extend(sf)
                layers.sandbox = sst
                layers.sandbox_detail = (sdet or "")[:500]
            else:
                layers.sandbox = "unsupported_lang"
                layers.sandbox_detail = lang or ""
        else:
            layers.sandbox = "disabled"

        # L4: E2B dynamic escalation when static layers are inconclusive.
        if e2b_escalation_enabled():
            escalate, reason = should_escalate(findings, lang, artifact)
            if escalate:
                ef, est, edet = run_e2b_dynamic(text, lang, reason)
                findings.extend(ef)
                layers.e2b = est
                layers.e2b_detail = (edet or "")[:500]
                layers.e2b_trigger_reason = reason
            else:
                layers.e2b = f"skipped:{reason}"
        else:
            layers.e2b = "disabled"

        parse_status.layers = layers

    if artifact == "unknown" and not findings:
        findings.extend(weak_signals_full_blob(text))
        findings.extend(fallback_content_signals(text))

    findings = add_risk_scores(cap_high_critical(findings))
    legacy = build_legacy(findings)

    report = WebThreatReport(
        artifact_type=artifact,
        parse_status=parse_status,
        findings=findings,
        legacy=legacy,
        source=source_info,
        tool_error=tool_error,
        decoded_artifacts=decoded_artifacts,
        behaviors=behaviors,
        capabilities=capabilities,
        iocs=iocs,
        mitre_attack=mitre_attack,
        recommended_actions=recommended_actions,
        tool_limitations=tool_limitations,
        forensic_supplement=forensic_supplement,
    )
    return report.to_tool_dict()


def _decoded_findings(
    findings: list[Finding],
    layer_index: int,
    decoded_text: str,
) -> list[Finding]:
    out: list[Finding] = []
    for finding in findings:
        evidence = finding.evidence.model_copy(
            update={
                "location": (
                    f"decoded[{layer_index}]:"
                    f"{finding.evidence.location}"
                ),
                "decoded": decoded_text[:1000],
            }
        )
        out.append(
            finding.model_copy(
                update={
                    "id": f"decoded-{layer_index}-{finding.id}",
                    "evidence": evidence,
                    "layer": finding.layer or "L2",
                },
                deep=True,
            )
        )
    return out


def error_report(
    code: str,
    message: str,
    *,
    source: SourceInfo | None = None,
) -> dict[str, Any]:
    """Return a schema-v2 compatible tool error report."""
    report = WebThreatReport(
        parse_status=ParseStatus(),
        source=source or SourceInfo(kind="inline"),
        tool_error=ToolError(code=code, message=message),
    )
    return report.to_tool_dict()
