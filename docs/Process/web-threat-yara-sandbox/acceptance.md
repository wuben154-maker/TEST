# Acceptance — web-threat-yara-sandbox

## Metadata

- **Slug:** `web-threat-yara-sandbox`
- **Owner:** SecManus
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope reference

- `design.md` — §Contracts、§Todo **yss-01–yss-10**。

## Environment

- 本地 `pytest`；可选系统安装 `php` 用于 L3 PHP 分支（无则验收「跳过」路径）。

## Functional criteria

| Id | Criterion |
|----|-----------|
| A-01 | `detect_web_attack` 返回中 `findings` 可含 `layer`=`L1` 且 `signals` 含 `type=yara_rule`（规则命中时）。 |
| A-02 | 默认规则目录为 `subagents/official/web-security/skills/web-security/yara/`（相对 `SERVICE_ROOT`），且存在至少一个 `.yar` 文件。 |
| A-03 | `parse_status.layers`（或等价字段）反映 YARA 加载状态（规则数、错误、不可用）。 |
| A-04 | Python 样本在启用沙箱且解释器可用时执行 **py_compile** 路径；语法错误时产生 **L3** 相关 finding 或明确状态。 |
| A-05 | `cap_high_critical` 对仅含 `yara_rule` 的 high 级 finding **不**无故降为 medium（与 `ast_sink` 同级门槛）。 |
| A-06 | `WEB_THREAT_YARA_ENABLED=false` 时跳过 YARA 扫描且不抛异常。 |

## Non-functional criteria

| Id | Criterion |
|----|-----------|
| N-01 | `pytest` 指定测试文件 exit 0。 |
| N-02 | 新增依赖 `yara-python` 写入 `requirements.txt`。 |

## Evidence (Phase 6)

| Id | Pass evidence |
|----|----------------|
| A-01–A-06 | `pytest tests/test_web_threat_yara_sandbox.py tests/test_web_security_pipeline.py tests/test_code_language.py -q` 全绿。 |
| N-01–N-02 | 同上；`requirements.txt` 含 `yara-python`。 |

## Sign-off

| Criterion id | Pass/Fail | Verifier | Date | Notes |
|--------------|-------------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-12 | yara_rule + L1 |
| A-02 | Pass | Agent | 2026-04-12 | `resolve_web_security_yara_dir()` + `.yar` |
| A-03 | Pass | Agent | 2026-04-12 | `parse_status.layers` |
| A-04 | Pass | Agent | 2026-04-12 | L3 路径在无 php/python 或干净语法时见 `sandbox` 状态 |
| A-05 | Pass | Agent | 2026-04-12 | `test_cap_preserves_yara_high` |
| A-06 | Pass | Agent | 2026-04-12 | `test_yara_disabled_via_env` |
| N-01 | Pass | Agent | 2026-04-12 | pytest exit 0 |
| N-02 | Pass | Agent | 2026-04-12 | `yara-python` in requirements |

**Outcome:** DONE（无 UI；Playwright `/qa` N/A）
