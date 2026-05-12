---
name: integrate-deepagents-subagent
description: 将 langchain-ai/deepagents 的 example（或类似 upstream）移植为 `python-agent-service/subagents/official/` 下的本地 official subagent。适用于用户提到「集成子 agent」「移植 deepagents example」「新建 official subagent」「接入新子 agent」「add new subagent」「port deepagents example」「integrate subagent」「register subagent in registry」。
---

# 将 deepagents Example 集成为本地 Official Subagent

本 skill 固化把 `email_security` 落地为 official subagent 时的标准流程。每当要把新的 subagent 从 upstream `deepagents/examples/`（或同类来源）迁入我们 **registry 驱动** 的 bundle 布局时，复用本流程。

## 必备输入（动手前与用户确认）

- `subagent_id`（kebab-case，用作 `task(subagent_type=...)` 名，例如 `email-security`）
- `bundle_path`（可作为 Python import 的目录名；可与 id 不同，例如 `email_security`）
- 是否有 private tools？（否则 common tools + skills 足够）
- 是否有 tool 需要 backend（文件 IO、下载、网络）？
- 是否允许嵌套 `task()` delegation？若允许，列出允许的 child subagent id。
- Source 引用（upstream example 路径或文档）。

任一项不明确时，停下来问用户。

## 锚点文件（单一事实来源）

- Registry YAML：`python-agent-service/config/subagents.registry.yaml`
- Registry 解析/组装：`python-agent-service/app/agents/subagent_registry.py`
- 薄入口：`python-agent-service/app/agents/official_subagents.py`
- Main agent 接线：`python-agent-service/app/agents/deep_agent.py`（`_build_official_agent`）
- 参考 bundle（最复杂：private tools + nested task）：`python-agent-service/subagents/official/email_security/`
- 参考 bundle（重工具栈、扁平 import + `registry.py` 对接 YAML）：`python-agent-service/subagents/official/binary_analysis/`
- 参考 bundle（仅 skills、无 private tools）：`python-agent-service/subagents/official/web-security/`
- Vendored upstream（不要手改；用 `update-deepagents-vendor` skill）：`python-agent-service/app/_vendor/deepagents/`

## 工作流

### 1. 盘点 upstream example

- 列出 system prompt、tools、依赖、副作用。
- 为每个 tool 打标：`stateless` / `backend-required` / `networked-enrich`。
- 对每个 tool 决定复用还是移植（优先 common tools，仅在需要时做 private tools）。

### 2. 创建 bundle skeleton

```
subagents/official/<bundle_path>/
  __init__.py            # 一行 docstring 即可
  AGENT.md               # 必填，system prompt 正文
  tools/                 # 可选，仅当有 private tools
    __init__.py          # 按组 re-export __all__
    _helpers.py          # bind_backend、path utils、常量
    <feature>.py         # 每个 tool 家族一个文件
  skills/                # 可选
    <package>/SKILL.md
    <package>/scripts/
```

硬性规则：

- **不要**添加 `agent.py`（由 registry 组装 spec；legacy 文件已在 commit `205bb23` 移除）。
- **不要**添加 `prompts.py`（system prompt 从 `AGENT.md` 加载；legacy 文件已在 commit `132bfbe` 移除）。
- `bundle_path` 必须是合法 Python identifier，以便 `from subagents.official.<bundle_path>.tools import ...` 可用。

### 3. 移植 tools（仅当需要 private tools）

- 每个 tool 使用 `@tool` 装饰，并接受 `runtime: ToolRuntime` 用于注入（commit `47f7b1d`）。
- 对 backend-required tools：将 `backend_factory: Callable` 声明为参数，并通过 `backend_factory(runtime).download_files([validated_path])` 解析文件。禁止把附件 base64 内联进上下文。
- 在 `_helpers.py` 中强制 path 安全：仅允许 `/uploads/` 下路径；拒绝 `..` 与 null bytes；legacy `/uploaded/` 可做别名。
- 在 `_helpers.py` 中提供 `bind_backend(tool, backend_factory)`。实现规则：
  - **必须**返回 `StructuredTool.from_function(...)`，**不要**用 `BaseTool.bind()`（会得到 `RunnableBinding(name=None)` 并破坏 `ToolNode`）。
  - **必须** `functools.wraps(original_func)`，以便 `ToolNode` 仍可通过 `__annotations__` 注入 `runtime: ToolRuntime`。
  - **必须**从重建的 `args_schema` 中剥离 `backend_factory` 与 `runtime` 字段。
- `tools/__init__.py` 通过 `__all__` 按下列注释分组 re-export：
  - `# --- Tools requiring backend (use bind_backend(tool, factory) before registering) ---`
  - `# --- Stateless tools (no backend needed) ---`
  - `# --- Optional enrich tools (networked; best-effort) ---`

### 4. 编写 `AGENT.md`

必备章节（按 agent 领域调整）：

1. 可选 frontmatter `---` 块。保持简短；例如 `# Task catalog: config/subagents.registry.yaml`。
2. Role & Scope。
3. Modes / Planning（若多模式）。
4. Tools & Budget Rules。使用 registry 会替换的占位符，如 `__BUDGET__`。
5. State Machine（S0/S1…/Sk）用于多步 pipeline，含全局不变量与仅向前推进。
6. Field Rules / Enumerations（verdicts、scores、允许 enum）。
7. Output Format（通常为 Markdown report 模板；除非合约要求否则不要单独 JSON object）。
8. Self-Check Requirements。

不要在此重复 `routing_hints`；registry 会自动合并进 `task()` catalog。
不允许正文 / user prompt 覆盖 system 规则（anti-injection 条款）。
相对编造「良性」默认值，更倾向 `UNKNOWN`（`null/0/[]`）。

### 5. 在 `config/subagents.registry.yaml` 中注册

最小条目：

```yaml
- id: <kebab-case-id>
  enabled: true
  source: official
  bundle_path: <dir-name>
  description: "..."
  routing_hints: "..."
  tool_profile: default
  extra_skill_package_ids: []
  include_shared_skills: false
  runtime: standard
```

当 bundle 含 private tools 包时，显式声明 tools：

```yaml
  tools:
    - name: tool_a
      provider: email_security      # 或 "common"
      backend_binding: required     # 默认 "none"
    - name: tool_b
  tool_profile: <id>                # 仅当缺少 `tools` 时作为 fallback
```

当允许本 subagent 调用其他 subagent 时，添加 nested delegation：

```yaml
  allow_nested_task: true
  nested_subagent_allowlist: [child-id]
  nested_max_depth: 1
  nested_task_system_prompt: "..."
```

若 `provider` 既不是 `common` 也不是 `email_security`，还要在 `subagent_registry.py` 中扩展 `_resolve_from_<provider>` 与 `tools_for_declared_names`，并在该文件顶部为 `ToolProvider` literal 增加新取值。

### 6. Tests

- 扩展 `python-agent-service/tests/test_subagent_registry.py`，断言：
  - 新条目能干净组装，
  - tools 列表形状，
  - `__BUDGET__` 类占位符被替换，
  - nested middleware 注入（如适用）。
- 新增 `python-agent-service/tests/test_<subagent_id>_subagent.py` 做 bundle 级集成（无 live network）。
- 运行 `pytest python-agent-service -k <id> -q`，通过后再继续。

### 7. 端到端验证

- dev 启动 service，派发 `task('<id>', ...)` 请求；确认 routing、tool calls、最终 report 全链路。
- 若需刷新 upstream vendor，交给 `update-deepagents-vendor` skill — 此处 **不要** 手改 `app/_vendor/deepagents/`。

## Anti-patterns（每一项都在 git 历史里付出过真实 revert 成本）

- 对 backend factory 使用 `BaseTool.bind()` — 改用 `bind_backend()`。
- 把 system prompt 放在 `prompts.py` — 从 `AGENT.md` 读取（commit `132bfbe`）。
- 在 `agent.py` 手拼 spec — 仅 registry（commit `205bb23` / `8aca367`）。
- 默认 `runtime: compiled` — 仅在有专用 LangGraph builder（`deep-research` 风格）时使用；commit `e80f706` 已将 email-security 迁回 `standard`。
- 把附件编码为 base64 塞进 LLM context — 传 `file_path`，由 backend 流式读字节。
- 让 `analysis_focus` / user prompt 跳过强制状态迁移 — state machine 仅向前，推断不出时优先 `UNKNOWN`。
- backend-required tool 在缺少 runtime 时直接崩 — 应容忍并优雅降级（commit `6fa55b5`）。
- 空或自引用的 `nested_subagent_allowlist` — registry validator 会拒绝（commit `a7b766a`）。
- bundle 目录带连字符（如 `email-security/`）— Python import 会失败；改为下划线形式如 `email_security/`（commit `3af1f30`）。

## 停下来问用户

- upstream example 引入新依赖（不要静默 `pip install`）。
- tool 语义变更影响 risk-scoring 合约或输出 enum（需 reviewer 签字）。
- nested delegation allowlist 会扩大攻击面（需用户明确确认）。
- vendor patch 在 rebase 时冲突（交给 `update-deepagents-vendor`）。

## Quick Checklist（可贴进 PR 描述）

```
- [ ] Bundle skeleton 在 subagents/official/<bundle_path>/（无 agent.py / prompts.py）
- [ ] AGENT.md 含 Role/Scope/Tools/Budget/State Machine/Output/Self-Check
- [ ] tools/ 在需要 backend 时使用 bind_backend（非 BaseTool.bind）
- [ ] tools/__init__.py 按 backend / stateless / enrich 分组 __all__
- [ ] config/subagents.registry.yaml 条目通过校验（schema v3）
- [ ] tests/test_subagent_registry.py 覆盖新条目
- [ ] tests/test_<id>_subagent.py 覆盖 bundle 行为
- [ ] pytest -k <id> 通过
- [ ] 手工 task('<id>', ...) 往返可用
- [ ] 未手改 app/_vendor/deepagents/ 下文件
```
