"""SSE result renderer for ``detect_web_attack``.

Converts the structured ``WebThreatReport`` (schema v2) into a concise,
English, plain-text rendering for the UI ``<pre>`` block. Lives in the
subagent package so the generic ``app.sse.tool_result_humanizer`` stays
schema-agnostic and zero-maintenance.

Importing this module has the side effect of registering the renderer with
:mod:`app.sse.tool_result_renderers`.
"""

from __future__ import annotations

from typing import Any

from app.sse.tool_result_renderers import register_renderer

_LAYER_ORDER: tuple[str, ...] = ("yara", "entropy", "sandbox", "e2b")
_MAX_FINDINGS = 10
_MAX_SNIPPET = 240
_MAX_LOCATION = 240


@register_renderer("detect_web_attack")
def render_detect_web_attack(data: dict[str, Any]) -> str:
    """Render a ``detect_web_attack`` payload as plain English text.

    The renderer tolerates partial payloads (legacy v1, trimmed fields) and
    returns an empty string on truly unusable input so the caller falls back
    to the generic humanizer.
    """
    if not isinstance(data, dict):
        return ""

    header = _render_header(data)

    parse_err = _parse_error(data.get("parse_status"))
    if parse_err:
        return f"{header}\nParse failed: {parse_err}"

    findings_block = _render_findings(data.get("findings") or [])
    layers_block = _render_layers(_extract_layers(data.get("parse_status")))

    matrix = data.get("forensic_supplement") or {}
    matrix_block = _render_forensic_supplement(matrix)

    sections: list[str] = [header]
    if findings_block:
        sections.append(findings_block)
    else:
        sections.append("No threats detected.")
    if matrix_block:
        sections.append(matrix_block)
    if layers_block:
        sections.append(layers_block)

    return "\n\n".join(sections).rstrip()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_forensic_supplement(block: dict[str, Any]) -> str:
    """Summarize deterministic forensic supplement (capability matrix + previews)."""
    rows = block.get("capability_matrix")
    if not isinstance(rows, list) or not rows:
        return ""

    lines: list[str] = ["Capability matrix (deterministic):"]
    detected = [r for r in rows if isinstance(r, dict) and r.get("detected")]
    if not detected:
        lines.append("  (no high-signal capability rows matched)")
        hdr_only = block.get("file_header_preview")
        if isinstance(hdr_only, str) and hdr_only.strip():
            lines.append("File header preview:")
            lines.append(f"  {_truncate(hdr_only.strip(), 400)}")
        return "\n".join(lines)

    shown = detected[:12]
    for raw in shown:
        rid = str(raw.get("id") or "")
        label = str(raw.get("label") or rid)
        try:
            cf = float(raw.get("confidence") or 0.0)
            cft = f"{cf:.2f}"
        except (TypeError, ValueError):
            cft = "—"
        lines.append(f"  · {label}  (id={rid}, conf≈{cft})")
        snips = raw.get("snippets")
        if isinstance(snips, list):
            for sn in snips[:2]:
                if isinstance(sn, str) and sn.strip():
                    lines.append(f"      {_truncate(sn.strip(), _MAX_SNIPPET)}")

    hdr = block.get("file_header_preview")
    if isinstance(hdr, str) and hdr.strip():
        lines.append("File header preview:")
        lines.append(f"  {_truncate(hdr.strip(), 400)}")

    hidden = len(detected) - len(shown)
    if hidden > 0:
        lines.append(f"  ... {hidden} more capability row(s)")
    return "\n".join(lines)


def _render_header(data: dict[str, Any]) -> str:
    artifact = str(data.get("artifact_type") or "unknown")
    code_block = (data.get("parse_status") or {}).get("code", {}) or {}
    lang = _safe_str(code_block.get("language"))
    if lang:
        artifact = f"{artifact} ({lang})"

    severity = str(data.get("severity") or "info")
    count = _coerce_int(
        data.get("attack_count"),
        fallback=len(data.get("findings") or []),
    )
    action = bool(data.get("requires_immediate_action"))

    parts = [
        f"Artifact: {artifact}",
        f"Severity: {severity}    Threats: {count}"
        + ("    Action required" if action else ""),
    ]
    return "\n".join(parts)


def _parse_error(parse_status: Any) -> str:
    """Return a short reason string if parsing clearly failed; else ``""``."""
    if not isinstance(parse_status, dict):
        return ""
    http = parse_status.get("http") or {}
    code = parse_status.get("code") or {}
    http_ok = bool(http.get("ok")) if isinstance(http, dict) else False
    ast_ok = bool(code.get("ast_ok")) if isinstance(code, dict) else False
    if http_ok or ast_ok:
        return ""
    errors = http.get("errors") if isinstance(http, dict) else None
    if isinstance(errors, list) and errors:
        return _truncate(str(errors[0]), _MAX_LOCATION)
    return ""


def _render_findings(findings: list[Any]) -> str:
    if not isinstance(findings, list) or not findings:
        return ""

    lines: list[str] = ["Findings:"]
    shown = findings[:_MAX_FINDINGS]
    for idx, raw in enumerate(shown, start=1):
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "info")
        conf = _fmt_confidence(raw.get("confidence"))
        category = str(raw.get("category") or "other")
        layer = _safe_str(raw.get("layer"))
        signal_tag = _primary_signal(raw.get("signals"))

        head_bits: list[str] = [f"[{severity} · confidence {conf}] {category}"]
        if layer:
            head_bits.append(layer)
        if signal_tag:
            head_bits.append(signal_tag)

        lines.append(f"  {idx}. " + "  ".join(head_bits))

        evidence = raw.get("evidence") or {}
        if isinstance(evidence, dict):
            location = _safe_str(evidence.get("location"))
            snippet = _safe_str(evidence.get("snippet"))
            if location:
                lines.append(
                    f"     location: {_truncate(location, _MAX_LOCATION)}"
                )
            if snippet:
                lines.append(
                    f"     snippet: {_truncate(snippet, _MAX_SNIPPET)}"
                )

    hidden = len(findings) - len(shown)
    if hidden > 0:
        lines.append(f"  ... {hidden} more finding(s) omitted")

    return "\n".join(lines)


def _extract_layers(parse_status: Any) -> dict[str, Any]:
    if not isinstance(parse_status, dict):
        return {}
    layers = parse_status.get("layers")
    return layers if isinstance(layers, dict) else {}


def _render_layers(layers: dict[str, Any]) -> str:
    if not layers:
        return ""

    parts: list[str] = []
    for key in _LAYER_ORDER:
        status = _safe_str(layers.get(key))
        if not status:
            continue
        chunk = f"{key}={status}"
        if key == "yara":
            compiled = _coerce_int(
                layers.get("yara_rules_compiled"), fallback=0
            )
            if compiled:
                chunk += f"({compiled} rules)"
        detail_key = f"{key}_detail"
        detail = _safe_str(layers.get(detail_key))
        if detail:
            chunk += f"({_truncate(detail, 80)})"
        parts.append(chunk)

    if not parts:
        return ""
    return "Layers: " + "  ".join(parts)


def _primary_signal(signals: Any) -> str:
    if not isinstance(signals, list) or not signals:
        return ""
    first = signals[0]
    if not isinstance(first, dict):
        return ""
    stype = _safe_str(first.get("type"))
    name = _safe_str(first.get("name"))
    if stype and name:
        return f"{stype} {name}"
    return stype or name


def _fmt_confidence(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def _coerce_int(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
