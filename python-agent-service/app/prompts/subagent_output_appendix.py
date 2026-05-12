"""Appendix for standard subagent system prompts (English; aligned with MASTER_AGENT)."""

# Headings must match app.parsers.final_message_split SUBAGENT_*_HEADING constants.
SUBAGENT_OUTPUT_APPENDIX = """

## Final assistant message shape (required)

When you finish with **no further tool calls**, put the **complete** structured deliverable for the
parent agent **first** in the message: evidence, steps, tables, and detailed conclusions (full
markdown). The UI timeline streams **only** a short preview from **## SM_SUBAGENT_WRAPUP**; the
parent consumes the **main body above** via the task tool return.

After your deliverable, add **one** machine section (heading verbatim):

## SM_SUBAGENT_WRAPUP
2–6 sentences or a short bullet list: what you did (tools/skills), key findings, and outcome.
**Process-oriented** recap only. Do **not** write an executive summary for the whole user request,
global risk posture, or prioritized next steps for the product—those are produced by the **parent**
agent after it reads your full deliverable.

**Do not** duplicate the full deliverable under **## SM_SUBAGENT_FULL_REPORT**. For very short
answers only (under ~200 characters total), you may instead use the legacy shape: **WRAPUP** then
**FULL_REPORT** with the substantive content under FULL_REPORT and a minimal WRAPUP.

**Forbidden:** Renaming **## SM_SUBAGENT_WRAPUP**; placing WRAPUP before your main deliverable when
the deliverable is more than a trivial line.

**Language:** Write the deliverable and WRAPUP **body** in the language indicated by the session
language directive (same as the user's language when provided by the parent agent). Required
heading line stays English as specified above.

## Security findings stats payload (security subagents only)

If — and only if — your task produced security analysis findings (web/email/binary/SOC analysis;
malware, phishing, web shells, vulnerabilities, IOC matches, suspicious behavior, etc.), append
**one** fenced ```json``` block **after** ## SM_SUBAGENT_WRAPUP. This payload powers the
analyst-facing stats bar; **never** mention it in prose, never duplicate the report inside it.

**Sentinel (required before the JSON):** Emit the line **`### SM_STATS_PAYLOAD`** verbatim on its
own line, then a blank line, then the fenced ```json``` block. The chat UI strips the sentinel and
everything after it from your wrapup preview, so this guarantees the JSON never leaks into the
visible chat bubble. Do **not** emit any prose between the sentinel and the fenced block.

Shape (sentinel + JSON, in this exact order):

```
### SM_STATS_PAYLOAD

```json
{ ... findings JSON here ... }
```
```

Schema:

```json
{
  "findings": [
    {
      "type": "web_shell | xss | sqli | rce | phishing | malware | cve | misconfig | data_leak | ioc_match | other",
      "severity": "critical | high | medium | low | info",
      "risk": 0,
      "evidence": "short locator, e.g. file path or rule id"
    }
  ]
}
```

Rules (strict):
- `type`, `severity` are **required**; use lowercase snake_case for `type`.
- `risk` is an integer in 0–100 (omit if not applicable).
- `evidence` is a short reference (≤ 80 chars); omit if not applicable.
- One entry per **distinct** finding — do **not** emit a finding per evidence line if they share
  the same root cause; consolidate.
- Severity ladder: critical = active compromise / RCE / confirmed exfil; high = exploitable
  vulnerability or webshell; medium = misconfig / weak crypto / suspicious-but-unconfirmed;
  low = policy / hardening; info = observation only.
- If no security findings (clean scan), **omit the entire payload** — including the
  `### SM_STATS_PAYLOAD` sentinel; do **not** emit `{"findings": []}` and do not write a
  "no findings" stub.
- Research / non-security subagents must **not** emit this block.
"""
