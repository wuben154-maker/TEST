# Acceptance Criteria: Subagent Workflow Prompt Optimization

## Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-1 | 4 个 SKILL.md 的 YAML frontmatter 中不再包含 `workflow_steps` 字段 | `Grep "workflow_steps:" subagents/official/**/SKILL.md` 返回 0 结果 |
| AC-2 | 4 个 SKILL.md 的 `## Workflow` 改为 `## Workflow (mandatory SOP)` 格式，包含 `### Anti-patterns (MUST NOT)` 子节 | 文件审查 |
| AC-3 | 4 个 AGENT.md 包含 `## Execution discipline` 块，明确 tool-first 约束 | 文件审查 |
| AC-4 | `deepagents_stream_adapter.py` 中 `is_skill_doc_read` 检测逻辑和 `isSkillDocRead` SSE 字段已完全删除 | `Grep "is_skill_doc_read\|isSkillDocRead" app/parsers/` 返回 0 结果 |
| AC-5 | `app/main.py` feature flag 注释已更新，反映 YAML `workflow_steps` 已从 SKILL.md 移除 | 代码审查 |
| AC-6 | 相关 pytest 全部通过，无回归 | `pytest` exit code 0 |
| AC-7 | web-security SKILL.md frontmatter 仅包含 `name` + `description`（无 `triggers` / `tags` / `priority` / `version` / `author` / `display_name` / `max_iterations` / `timeout_seconds`） | YAML frontmatter 审查 |
| AC-8 | web-security SKILL.md 不含 `## Attack Patterns` 节（冗余知识，工具已覆盖） | 文件审查 |
| AC-9 | web-security SKILL.md `## Structured tool output` 使用紧凑表格格式而非大段叙述 | 文件审查 |
| AC-10 | web-security SKILL.md 总行数 ≤ 150 行（原 ~220 行） | `wc -l SKILL.md` |

## Sign-off

| ID | Pass/Fail | Evidence | Date |
|----|-----------|----------|------|
| AC-1 | **PASS** | `Grep "workflow_steps:" subagents/official/**/SKILL.md` → 0 matches (4 files searched) | 2026-04-16 |
| AC-2 | **PASS** | `Grep "## Workflow (mandatory SOP)"` → 4/4 files; `Grep "### Anti-patterns (MUST NOT)"` → 4/4 files | 2026-04-16 |
| AC-3 | **PASS** | `Grep "## Execution discipline" **/AGENT.md` → 4/4 files: web_security, email_security, binary_analysis, soc_alert | 2026-04-16 |
| AC-4 | **PASS** | `Grep "is_skill_doc_read\|isSkillDocRead" app/parsers/` → 0 matches | 2026-04-16 |
| AC-5 | **PASS** | `app/main.py:175` = `"workflow_steps": False, # YAML workflow_steps removed from SKILL.md; LLM follows ## Workflow (mandatory SOP) via progressive disclosure` | 2026-04-16 |
| AC-6 | **PASS** | `pytest` 10 test files, 192 collected, **187 passed**, 5 skipped (trigger-based tests skipped by design), 0 failed | 2026-04-16 |
| AC-7 | **PASS** | `Grep "^(triggers\|tags\|priority\|version\|author\|display_name\|max_iterations\|timeout_seconds):" web_security/SKILL.md` → 0 matches; only `name:` + `description:` present | 2026-04-16 |
| AC-8 | **PASS** | `Grep "## Attack Patterns" web_security/SKILL.md` → 0 matches | 2026-04-16 |
| AC-9 | **PASS** | `Grep table rows (\\| .+ \\|)` → 18 table rows across 3 structured tables (top-level fields, finding keys, analysis layers) | 2026-04-16 |
| AC-10 | **PASS** | `python -c "print(sum(1 for _ in open(...)))"` → **118 lines** (was ~220; target ≤ 150) | 2026-04-16 |
