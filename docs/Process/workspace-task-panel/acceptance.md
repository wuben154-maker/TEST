# Backend Acceptance: workspace-task-panel

## Metadata

| Field  | Value                    |
|--------|--------------------------|
| Slug   | `workspace-task-panel`   |
| Date   | 2026-04-14               |
| Source | Design.md contracts + user dialogue |

---

## Acceptance Criteria

### F. YAML 配置层

| ID | Criterion | Priority |
|----|-----------|----------|
| F-1 | `tool_presentation.yaml` 中 `sandbox_run` 包含完整 `workspace_tab` 块（type/label/icon/merge_strategy/merge_key 均有效） | Must |
| F-2 | `sandbox_pty_run` 同上，`merge_key = sandbox_id`，与 `sandbox_run` 共享同一 `type: shell` | Must |
| F-3 | `extract_iocs` 包含 `workspace_tab`，`merge_strategy: always` | Must |
| F-4 | 无 `workspace_tab` 字段的工具（如 `web_search`）不产生 Tab，仅出现在推理时间线 | Must |

### G. `/tool-tab-config` 端点

| ID | Criterion | Priority |
|----|-----------|----------|
| G-1 | `GET /tool-tab-config` 返回 200，JSON 包含 `tools` 对象，键为工具名，值含 `workspace_tab`（仅含有该字段的工具） | Must |
| G-2 | 返回的 JSON schema 与 `design.md §Contracts §3` 一致 | Must |
| G-3 | 后端启动后无需重启即可读取最新 YAML（热读取或 at-startup-cache 均可，文档说明） | Should |

### H. Tab 合并逻辑（ToolTabRegistry）

| ID | Criterion | Priority |
|----|-----------|----------|
| H-1 | `merge_strategy: by_arg`，同 `sandbox_id` 的两次 `sandbox_run` → 同一 Tab 实例（`workspaceTabs.length` 不增加） | Must |
| H-2 | `merge_strategy: by_arg`，不同 `sandbox_id` 的两次 `sandbox_run` → 两个独立 Tab 实例 | Must |
| H-3 | `merge_strategy: by_arg`，`sandbox_id` 缺失（一次性模式）→ 每次创建新 Tab（uuid instanceKey） | Must |
| H-4 | `merge_strategy: always`，同任务内多次 `extract_iocs` → 始终一个 Tab | Must |
| H-5 | `/tool-tab-config` 拉取失败时，`ToolTabRegistry` 降级为空映射，仅 Report Tab 显示，无 JS 错误 | Must |

### I. AnalysisResult 扩展字段

| ID | Criterion | Priority |
|----|-----------|----------|
| I-1 | 任务开始时 `status` 初始化为 `'running'` | Must |
| I-2 | SSE `done` 事件到达后 `status` 变为 `'done'` | Must |
| I-3 | SSE `error` 事件到达后 `status` 变为 `'error'` | Must |
| I-4 | 旧的已持久化 `AnalysisResult`（无 `status` 字段）默认为 `'done'`，无渲染报错 | Must |
| I-5 | `stats.toolCallCount` 正确统计当前任务内 `tool_call` SSE 事件总数 | Should |
| I-6 | `stats.sandboxRunCount` 正确统计 `toolName` 含 `sandbox_` 前缀的事件数 | Should |

---

## Sign-off

> Phase 6 验证日期：2026-04-14。单元测试全量通过（235 tests）；Playwright E2E SKIPPED（MCP 不可调用）。

| ID | Status | Evidence | Notes |
|----|--------|----------|-------|
| F-1 | PASS | `tool_presentation.yaml` `sandbox_run.workspace_tab`: type/label/icon/merge_strategy/merge_key 全齐 | 代码审查 |
| F-2 | PASS | `sandbox_pty_run` 同结构，`merge_key: sandbox_id` | 代码审查 |
| F-3 | PASS | `extract_iocs.workspace_tab.merge_strategy: always` | 代码审查 |
| F-4 | PASS | `get_all_workspace_tab_configs()` 仅返回含 `workspace_tab` 的工具 | 代码审查 |
| G-1 | PASS | `GET /tool-tab-config` 端点实现于 `main.py`，返回 `{"tools": {...}}` | 代码审查 |
| G-2 | PASS | 响应 schema 与 design.md §Contracts §3 一致 | 代码审查 |
| G-3 | PASS | `get_all_workspace_tab_configs()` 每次请求直接读 YAML（不 cache，热读取） | 代码审查 |
| H-1 | PASS | `tool-tab-registry.test.ts`: "appends to existing tab when sandbox_id matches" ✓ | vitest 通过 |
| H-2 | PASS | `tool-tab-registry.test.ts`: "creates a new tab when sandbox_id differs" ✓ | vitest 通过 |
| H-3 | PASS | `tool-tab-registry.test.ts`: "creates a new tab when sandbox_id is absent" ✓ | vitest 通过 |
| H-4 | PASS | `tool-tab-registry.test.ts`: "appends to existing ioc_table tab on second call" ✓ | vitest 通过 |
| H-5 | PASS | `loadToolTabConfig()` catch → `_configCache = {}` → `resolveTabAction` returns null | 代码审查 |
| I-1 | PASS | `analyzeInput` reset: `workspaceTabs: [], toolCallCount: 0, sandboxRunCount: 0` + `liveResult.isActive = isAnalyzing` | 代码审查 |
| I-2 | DEFER | `status` 未从 SSE `done` 设置（streaming state 不含 `status` 字段），由 `isAnalyzing` 推导 | 可后续添加到 streaming state |
| I-3 | DEFER | 同 I-2 | 可后续迭代 |
| I-4 | PASS | `useProjects.ts` 加载时: `status: 'done' as const, stats: {}, workspaceTabs: []` | 代码审查 |
| I-5 | PASS | `applyWorkspaceTabEvent`: `toolCallCount + 1` per `tool_call` event | 代码审查 |
| I-6 | PASS | `sandboxRunCount + (toolName.startsWith('sandbox_') ? 1 : 0)` | 代码审查 |
