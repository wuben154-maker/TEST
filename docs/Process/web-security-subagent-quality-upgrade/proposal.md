# Proposal: Web security subagent quality upgrade

## Problem

The `web-security` subagent currently underperforms on realistic Web security inputs because the agent and tool contracts are misaligned:

- File-based tasks are delegated as `/workspace/...` paths, but `detect_web_attack` only accepts raw text. The LLM must decide whether to call `read_file`, copy content, then call the scanner, which creates path/content confusion and weak reproducibility.
- The scanner handles canonical raw HTTP requests and hosted code better than URL-only strings, access logs, JSON bodies, cookies, headers, multipart fields, and WAF/proxy log formats.
- The routing promise is broader than the implemented analyzers. The master prompt routes HTML/JS/TS/TSX/Web files to `web-security`, while hosted-code analysis mainly covers PHP/JSP/Python/ASPX.
- Tests prove the pipeline shape and some scanner cases, but do not strictly prove correct subagent selection, internal file reading, mandatory scanner usage, structured evidence quality, or UI stats metadata.

## Goals

1. Upgrade `detect_web_attack` so it can analyze either raw `request_data` or a workspace `file_path`, with file reads performed inside the tool through the DeepAgents backend rather than by the LLM.
2. Preserve the existing `detect_web_attack(request_data=...)` compatibility path while making file-based analysis deterministic and owner-scoped.
3. Improve realistic input coverage for URL-only, HTTP logs, JSON body, headers, cookies, and common Web security probes.
4. Keep one `web-security` subagent, but split its internal SOP into traffic/app-analysis and webshell/hosted-code branches driven by `artifact_type`.
5. Add structured risk and evidence fields so final reports and `conclusion.meta.security` can be derived from tool output instead of brittle markdown parsing.
6. Strengthen tests so regressions in routing, file-path handling, scanner coverage, and report/stat contracts fail early.

## Non-goals

- No active external site scanning, authenticated crawling, browser-based DAST, or exploitation of live targets.
- No split into separate `webshell` and `web` subagents in this delivery.
- No new frontend UI component work; existing stats rendering may consume richer backend metadata without UI redesign.
- No replacement of the existing YARA/static/sandbox layers with a large third-party scanning framework.
- No broad OWASP Top 10 platform build. This delivery focuses on high-confidence offline artifact analysis.

## Users

- **Security analysts** who upload Web files, HTTP samples, URLs, or logs and expect actionable triage.
- **Incident responders** who need webshell/RCE evidence, source paths, and containment guidance.
- **Developers** who need precise vulnerability locations and remediation advice.
- **Operators** who need deterministic tool behavior, bounded input handling, and safer multi-tenant file access.

## Scope

- `detect_web_attack` input contract and internal workspace file reading through runtime backend.
- Tool result schema enrichment for source metadata, risk score, and evidence locations.
- Web artifact normalization for common raw text formats: URL-only, access logs, JSON bodies, headers, cookies, and form data.
- Hosted-code branch improvements for JavaScript/TypeScript/HTML surface areas where feasible without adding heavy dependencies.
- `web-security` `AGENT.md` and `SKILL.md` SOP updates.
- Backend/unit/integration tests and targeted LLM-flow tests for subagent behavior.

## Dependencies

- DeepAgents `ToolRuntime` and backend routing for `/workspace/` paths.
- Existing `CompositeBackend`, `WorkspaceFacadeBackend`, `WorkspaceScopedFilesystemBackend`, and workspace owner scope context.
- Existing `detect_web_attack` schema v2 pipeline under `subagents/official/web_security/tools/`.
- Existing conclusion stats metadata path in `app/parsers/stats_meta.py`.
- Existing subagent registry and tool profile assembly in `app/agents/subagent_registry.py`.

## Success metrics

- File upload analysis calls `detect_web_attack(file_path="/workspace/...")` and detects the same findings as direct raw-content analysis.
- URL-only and access-log samples with encoded XSS/SQLi no longer return clean `unknown` results when clear payloads are present.
- JSON body, cookie, and header payload locations are represented as structured evidence locations.
- High/critical findings include source path or request-field attribution, confidence, risk score, and actionable remediation.
- Existing web-security tests remain green, with added tests covering realistic input formats and file-path mode.
- The final security stats path can derive severity, risk score, threat classes, validation dimensions, and actionable counts from structured findings.

## Open questions resolved for planning

| Topic | Direction |
|-------|-----------|
| Separate webshell skill? | Do not split in this delivery. Keep one `web-security` subagent and branch internally by `artifact_type`. |
| File analysis tool shape | Upgrade `detect_web_attack` with optional `file_path`; avoid a second `detect_web_attack_file` tool. |
| Local path conversion | Never call local `open("/workspace/...")`; use runtime backend so `/workspace/` facade enforces owner scope. |
| LLM value | LLM is the analyst and synthesizer, not the detector. Tools produce evidence; LLM correlates, explains impact, and recommends action. |

## Related documents

- [design.md](./design.md) — implementation source of truth.
- [acceptance.md](./acceptance.md) — backend verification criteria.
