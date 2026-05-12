# Acceptance — web-security-multilang-static

## Metadata

- **Slug:** `web-security-multilang-static`
- **Owner:** SecManus
- **Last updated:** 2026-04-09
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope reference

- `design.md` — §Todo list **ml-01–ml-06**、§Contracts、§Code touch list。

## Environment

- 本地：`python-agent-service` 下 `pytest`；Python 3.x 与项目既有依赖。

## Functional criteria

| Id | Criterion |
|----|-----------|
| A-01 | 对含 `<?php` 的样例，`parse_status.code.language` 为 `php`，且仍存在至少一条 `php:ast:Call` 类 finding（回归）。 |
| A-02 | 对 **JSP** 样例（含 `<%` 等标记），`language` 为 `jsp`，且存在 `jsp:sink:` 前缀的 finding 与 `ast_sink` 信号。 |
| A-03 | 对 **Python** 样例（shebang 或约定 webshell 形态），`language` 为 `python`，且存在 `python:sink:` 前缀的 finding。 |
| A-04 | 对 **ASPX/C#** 样例（`<%@ Page` 或 `runat="server"` 等），`language` 为 `aspx`，且存在 `aspx:sink:` 前缀的 finding。 |
| A-05 | **语言优先级**：同一段文本同时可被多语言解释时，主语言符合 **PHP → JSP → Python → ASPX**（由测试固定一例）。 |
| A-06 | `hint="code"` 时，非 HTTP 纯流量样例仍走代码扫描分支且不抛异常。 |

## Non-functional criteria

| Id | Criterion |
|----|-----------|
| N-01 | 相关测试命令 `pytest` 针对本模块路径 **exit 0**。 |
| N-02 | 不引入新的必需原生依赖（仅 stdlib + 现有 `requirements`）。 |

## Evidence (Phase 6)

| Id | Pass evidence |
|----|----------------|
| A-01–A-06 | `pytest python-agent-service/tests/test_web_security_pipeline.py python-agent-service/tests/test_code_language.py -q` 全绿（13 passed，2026-04-09）。 |
| N-01 | 同上命令 exit code 0。 |

## Sign-off

| Criterion id | Pass/Fail | Verifier | Date | Notes |
|--------------|-------------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-09 | `test_a03_php_eval_ast_sink` |
| A-02 | Pass | Agent | 2026-04-09 | `test_fixtures_multilang_locations` (jsp_runtime.txt) |
| A-03 | Pass | Agent | 2026-04-09 | `python_subprocess.py` fixture |
| A-04 | Pass | Agent | 2026-04-09 | `aspx_process.txt` fixture |
| A-05 | Pass | Agent | 2026-04-09 | `test_infer_php_wins_over_aspx_markers`, `test_a05_fixture_priority_php_in_pipeline` |
| A-06 | Pass | Agent | 2026-04-09 | `hint="code"` in multilang tests |
| N-01 | Pass | Agent | 2026-04-09 | `pytest tests/test_web_security_pipeline.py tests/test_code_language.py` exit 0 |
| N-02 | Pass | Agent | 2026-04-09 | No new deps |

**Outcome:** DONE（无 UI；`/qa` Playwright N/A）
