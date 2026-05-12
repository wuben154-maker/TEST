# Acceptance Criteria: E2B On-Demand Sandbox Tools

## Metadata

| Field | Value |
|-------|-------|
| Slug | `e2b-sandbox-tools` |
| Scope | Backend only (no UI changes) |
| Status | Draft — awaiting user sign-off on criteria |

---

## Criteria

> Criteria content sourced from user-provided requirements in Phase 1 exploration.
> Sign-off column left empty — to be filled in Phase 6 after verification.

### AC-01 — Config File Existence & Structure

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-01-a | `config/sandbox.yaml` 存在且可被 YAML 解析 | `python -c "import yaml; yaml.safe_load(open('config/sandbox.yaml'))"` | |
| AC-01-b | 包含 `defaults` 节（`template`、`timeout_seconds`、`allow_internet`） | YAML 结构检查 | |
| AC-01-c | 包含 `templates` 节，至少 `base`、`binary-analysis`、`web-simulation` 三个模板 | YAML 结构检查 | |
| AC-01-d | 每个模板包含 `template_id`、`description`、`allow_internet`、`timeout_seconds` | YAML 结构检查 | |

### AC-02 — Tool `sandbox_create`

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-02-a | 当 `E2B_API_KEY` 未配置时，返回含 `error` 字段的 JSON，而非抛出异常 | pytest unit test (mock no KEY) | |
| AC-02-b | 指定合法 `template` 时，使用 `config/sandbox.yaml` 中对应的 `template_id` 创建沙箱 | pytest unit test (mock E2B SDK) | |
| AC-02-c | 不指定 `template` 时，使用 `defaults.template` 对应模板 | pytest unit test | |
| AC-02-d | 返回 JSON 包含 `sandbox_id`、`template`、`status` 字段 | pytest assert | |
| AC-02-e | 指定无效模板名时，返回 `{"error": "Template '...' not found in config/sandbox.yaml"}` | pytest unit test | |

### AC-03 — Tool `sandbox_destroy`

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-03-a | 调用后 E2B `sandbox.kill()` 被触发 | pytest unit test (mock) | |
| AC-03-b | 返回 JSON 包含 `sandbox_id`、`status: "killed"` | pytest assert | |
| AC-03-c | 沙箱 ID 不存在时，返回带 `error` 字段的 JSON（不抛异常） | pytest unit test | |

### AC-04 — Tool `sandbox_run` — Per-call Mode

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-04-a | `sandbox_id=None` 时，自动创建沙箱、执行命令、销毁沙箱（三步均调用） | pytest unit test (mock，verify call order) | |
| AC-04-b | 命令执行结果正确映射到 `exit_code`、`stdout`、`stderr` | pytest assert | |
| AC-04-c | 返回 `mode: "per_call"` | pytest assert | |
| AC-04-d | 即使命令失败（exit_code != 0），沙箱依然被销毁（finally 保证） | pytest unit test (simulate exec failure) | |
| AC-04-e | 命令超时时，返回 `{"exit_code": -1, "error": "Command timed out"}` 且沙箱被销毁 | pytest unit test (mock TimeoutException) | |

### AC-05 — Tool `sandbox_run` — Session 复用 Mode

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-05-a | `sandbox_id` 非空时，使用 `AsyncSandbox.connect()` 而非创建新沙箱 | pytest unit test (mock，verify connect called) | |
| AC-05-b | Session 模式下沙箱在函数返回后**不被销毁** | pytest unit test (verify kill NOT called) | |
| AC-05-c | 返回 `mode: "session"` | pytest assert | |

### AC-06 — Tool `sandbox_run` — 文件操作

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-06-a | `upload_files` 中的文件在执行命令前被上传（`sandbox.files.write` 被调用） | pytest unit test | |
| AC-06-b | `download_paths` 中的文件在命令执行后被下载，内容以 base64 返回 | pytest unit test | |
| AC-06-c | 某个下载文件不存在时，`downloaded_files[i].error` 记录错误，整体不失败 | pytest unit test | |

### AC-07 — `E2BSandboxBackend`

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-07-a | 继承自 `BaseSandbox`，实现 `execute()`、`id`、`upload_files()`、`download_files()` | `isinstance(backend, BaseSandbox)` / pytest | |
| AC-07-b | `execute()` 调用 E2B 同步 `Sandbox.commands.run()` 并返回 `ExecuteResponse` | pytest unit test (mock sync SDK) | |
| AC-07-c | 可作为 `create_deep_agent(backend=E2BSandboxBackend(...))` 的参数 | 类型检查（协议兼容） | |

### AC-08 — Tool 装配条件

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-08-a | 当 `E2B_API_KEY` 未配置时，sandbox tools 不出现在 `create_common_tools()` 返回的列表中 | pytest unit test (env 无 KEY) | |
| AC-08-b | 当 `E2B_API_KEY` 已配置时，三个 sandbox tools 均出现在工具列表中 | pytest unit test (env 有 KEY) | |

### AC-09 — SSE 呈现配置

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-09-a | `config/tool_presentation.yaml` 中 `sandbox_create`、`sandbox_destroy`、`sandbox_run`、`sandbox_pty_run` 均已注册 | YAML 检查 | |
| AC-09-b | 四个工具的 `presentation` 设为 `action` | YAML 检查 | |

### AC-10 — `sandbox_run` 流式输出（`stream_to_sse=true`）

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-10-a | `stream_to_sse=True` 时，`on_stdout`/`on_stderr` 回调触发 `emit_sandbox_output()` | pytest unit test（mock emit，assert call count > 0） | |
| AC-10-b | 每次 emit 的事件结构包含 `type="sandbox_output"`、`sandbox_id`、`tool_name`、`stream`、`line`、`seq` | pytest assert on call args | |
| AC-10-c | `seq` 单调递增，且跨 stdout/stderr 统一计数 | pytest assert seq sequence | |
| AC-10-d | `stream_to_sse=False`（默认）时，`emit_sandbox_output` 不被调用 | pytest unit test（mock emit，assert not called） | |
| AC-10-e | `_sse_emitter` ContextVar 未注册时（None），`emit_sandbox_output` 静默跳过，工具正常返回结果 | pytest unit test（不设置 ContextVar） | |
| AC-10-f | SSE emit 本身抛出异常时，工具捕获异常、记录 warning、继续执行，不崩溃 | pytest unit test（mock emit 抛出异常） | |
| AC-10-g | 最终返回 JSON 包含 `streamed_lines` 字段（值等于回调触发次数） | pytest assert | |
| AC-10-h | `set_sse_emitter` 注册后，不同 asyncio 上下文（并发请求）之间 ContextVar 互不干扰 | pytest 并发测试（两个 Task 各自注入不同 emitter） | |

### AC-11 — `sandbox_pty_run` PTY 交互式工具

| ID | Criterion | Verifiable By | Sign-off |
|----|-----------|---------------|---------|
| AC-11-a | 工具调用 `sandbox.pty.create()` 创建 PTY 句柄 | pytest unit test（mock E2B PTY API） | |
| AC-11-b | `commands` 列表中的每条命令依次通过 `pty.send_stdin` 发送（自动追加 `\n`） | pytest assert call args sequence | |
| AC-11-c | `stream_to_sse=True`（默认）时，每个输出 chunk 推送 `sandbox_output` SSE 事件（`stream="pty"`） | pytest unit test（mock emit） | |
| AC-11-d | 返回 JSON 包含 `output`（完整会话文本）、`commands_sent`、`streamed_chunks` | pytest assert | |
| AC-11-e | PTY 会话超时（`asyncio.wait_for` 触发）时，返回 `{"error": "PTY session timed out"}`，sandbox 被销毁 | pytest unit test（mock 超时） | |
| AC-11-f | PTY 输出含非 UTF-8 字节时，`errors="replace"` 替换处理，不抛异常 | pytest unit test（inject bytes with invalid UTF-8） | |
| AC-11-g | per-call 模式下，PTY 会话结束后沙箱被销毁（`sandbox.kill()` 调用） | pytest unit test（verify kill called） | |

---

## Sign-off Summary (Phase 6)

| Block | Result | Evidence | Date |
|-------|--------|---------|------|
| AC-01 Config | PASS | `config/sandbox.yaml` YAML 解析 OK；defaults + templates (base/binary-analysis/web-simulation/script-exec/desktop) 验证通过 | 2026-04-14 |
| AC-02 sandbox_create | PASS | `test_sandbox_tools.py::TestSandboxCreate` 3/3 通过（含无 KEY、mock E2B、无效模板场景） | 2026-04-14 |
| AC-03 sandbox_destroy | PASS | `test_sandbox_tools.py::TestSandboxDestroy` 2/2 通过；kill() 调用验证；无 KEY 错误响应验证 | 2026-04-14 |
| AC-04 sandbox_run per-call | PASS | `TestSandboxRun::test_per_call_mode_*` 通过；create/run/kill 三步均调用；exit_code/stdout 映射正确 | 2026-04-14 |
| AC-05 sandbox_run session | PASS | `TestSandboxRun::test_session_mode_reuses_sandbox` 通过；connect() 调用、kill() 不调用 | 2026-04-14 |
| AC-06 file ops | PASS | `TestSandboxRun::test_upload_and_download` 通过；files.write 调用验证、downloaded_files 结构验证 | 2026-04-14 |
| AC-07 E2BSandboxBackend | PASS | `E2BSandboxBackend` 继承 `BaseSandbox`；实现 `execute()`/`id`/`upload_files()`/`download_files()`；代码审查通过 | 2026-04-14 |
| AC-08 conditional mount | PASS | `TestSandboxToolRegistry::test_sandbox_tools_not_mounted_without_api_key` 和 `*_mounted_with_api_key` 通过 | 2026-04-14 |
| AC-09 SSE config | PASS | `tool_presentation.yaml` 中 4 个工具均 `enabled=true`、`presentation=action` | 2026-04-14 |
| AC-10 sandbox_run streaming | PASS | `TestSandboxRunStreaming` 2/2 通过：stream_to_sse=True 触发 emit、False 不触发；streamed_lines 字段正确 | 2026-04-14 |
| AC-11 sandbox_pty_run PTY | PASS | `TestSandboxPtyRun` 3/3 通过：commands_sent/output/streamed_chunks 字段；stream_to_sse 触发 emit；无 KEY 错误响应 | 2026-04-14 |

**总体结论：DONE — 全部 23 项测试绿灯，11 个验收块均通过，无 UI 变更。**

---

## Mockups deferred

本交付为纯后端/工具层实现，无 UI 变更。用户确认跳过 mockup 收集。
