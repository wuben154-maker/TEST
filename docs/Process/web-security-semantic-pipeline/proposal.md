# Proposal — Web security: next-generation semantic pipeline

## Problem

The current `web-security` path relies on **flat regex scans** over raw strings (`detect_web_attack` in `enhanced_tools.py`), while richer logic in `subagents/official/web-security/skills/web-security/scripts/` (e.g. `detect_xss.py`, `detect_sqli.py`) is **not unified** with the tool contract. This yields:

- High **false positive** risk (no parameter boundaries, no syntax/semantic layer).
- **Webshell vs in-transit web attack** confusion (same narrative, different evidence needs).
- No clear **upgrade path** toward industry-style “semantic” analysis (structured HTTP, AST for code, confidence + evidence).

## Goals

1. Replace “regex-first” as the **sole** detection strategy with a **layered pipeline**: **parse → normalize → semantic features → scored findings → (optional) LLM narrative**.
2. **Unify** traffic analysis and **hosted code / webshell** analysis under one design, with explicit **`artifact_type`** and different analyzers.
3. Define a **stable JSON contract** for tool output so the subagent and tests do not depend on prose quality alone.
4. Preserve **backward compatibility** for callers during rollout (deprecated fields / version field), documented in `design.md`.

## Non-goals

- Matching a commercial WAF’s throughput or proprietary ML models in v1.
- Replacing enterprise IDS/Suricata deployments; this is the **agent service** analysis path.
- UI work in this delivery (no screens).

## Users

- SecManus operators using **`web-security`** subagent via `task()`.
- Developers extending detection in `python-agent-service`.

## Scope

- **In scope:** Architecture, contracts, phased implementation plan, migration from current `detect_web_attack`, test strategy, feature flags.
- **Out of scope for Phase 2 (this document set):** Actual code merge (happens in Phase 4 after approval).

## Dependencies

- Existing: Python 3.x stack in `python-agent-service`, `tool_presentation.yaml`, subagent bundle `web-security`.
- Future implementation may add **Tree-sitter** grammars or language-specific parsers (decision in `design.md` — must align with repo dependency policy in `AGENT.md`).

## Success metrics

- **Functional:** All **`acceptance.md`** criteria pass after implementation.
- **Quality:** Golden-file tests for traffic + code samples; documented **precision/recall** targets as lower bounds for regression (not marketing claims).

## Open questions (resolved for planning)

| Topic | Resolution |
|-------|------------|
| Single tool vs new tool name | Prefer **one evolved tool** (`detect_web_attack`) with `schema_version` **or** new `analyze_web_threat` with explicit migration — pick one in `design.md` (default: **versioned payload** on existing tool name to reduce churn). |
| LLM role | **Not** the primary detector; **summarization + ambiguity resolution** only, fed structured `findings`. |

## Related documents

- [design.md](./design.md) — implementation source of truth.
- [acceptance.md](./acceptance.md) — verification criteria.
