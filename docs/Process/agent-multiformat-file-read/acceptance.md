# Acceptance: Agent 多格式安全读取

## Metadata

- **Slug**: `agent-multiformat-file-read`（须与目录名一致）
- **Owner**: delivery-pipeline Phase 6（自动验收）
- **Last updated**: 2026-04-28
- **Outcome**: **DONE_WITH_CONCERNS**（见 Sign-off；多项 acceptance 依赖 fixture/观测尚未闭环）
- **Related**: [`proposal.md`](./proposal.md) · [`design.md`](./design.md)

## Scope reference

验收覆盖 `design.md` 中：

- §Contracts — `MultiformatReadResult` 与工具行为
- §Todo list — `core-reader`、`text-encoding`、`email-eml`、`safety-guards`
- Claude Code 借鉴项：分页、字节预算、结构化 kind、二进制门禁

## Environment

- **Local**: `python-agent-service`，Python venv 与项目 `pytest` 一致
- **Fixtures**: `python-agent-service/tests/fixtures/multiformat_read/`（实施时创建）

## Functional criteria

以下为根据需求 **「读取 webshell、二进制、邮件等文件，考虑各种特殊情况，并参考 Claude Code 优秀做法」** 整理的可验证条款。

| ID | Given / When / Then |
|----|---------------------|
| **A-01** | Given 路径为有效 **UTF-8 文本 PHP**（webshell 样本 fixture），When 调用多格式读取默认参数，Then `ok=true`，`content_kind=text`，正文非空，`truncated` 与文件大小一致。 |
| **A-02** | Given 路径为 **GB18030/GBK 编码** 的 `.php`（fixture），When 调用读取，Then `ok=true`，`text` 可解码为可读中文/符号，`encoding` 或 `warnings` 如实反映解码路径（非裸 `UnicodeDecodeError` 冒泡）。 |
| **A-03** | Given 路径为小体积 **PE/DLL** 或 `application/octet-stream` 魔数文件，When 调用读取，Then `content_kind=binary`（或与设计枚举等价），`binary_base64` 非空，**不**对全文做 UTF-8 严格解码。 |
| **A-04** | Given 路径为 **`.eml`**（含 multipart 与至少一个附件 fixture），When 调用读取，Then `content_kind=email`，`email.attachments` 含文件名与大小，默认大附件不内联正文（`skipped` 或等价标记）。 |
| **A-05** | Given 文件 **大于** 配置 `MULTIFORMAT_READ_MAX_BYTES`（或测试临时调小），When 调用读取，Then `truncated=true` 且 `truncation_reason` 含字节原因，**不**导致进程 OOM。 |
| **A-06** | Given **单行极长** 文本（无 `\n` 直至超过行窗字节预算的 fixture），When 带 `limit` 读取，Then 行为符合 `design.md` §Edge cases（截断或流式计数，不无限缓冲）。 |
| **A-07** | Given 路径为 **目录** 或不存在，When 读取，Then `ok=false`，`error_code` 为 `NOT_A_FILE` 或 `NOT_FOUND`（与设计一致）。 |
| **A-08** | Given 运行环境为 Linux 且路径为 **`/dev/zero`**（或设计黑名单之一），When 读取，Then **拒绝**，`error_code=BLOCKED_PATH`（或与 `design.md` 一致）。 |
| **A-09** | Given 需提供 **hex 头** 的选项开启且文件为二进制，When 读取，Then `hex_head` 长度 ≤ 配置的 N 字节对应十六进制长度。 |
| **A-10** | Given 同一文件同 `offset/limit` 且 **mtime 未变**（若实现 dedup），When 第二次读取，Then 返回与契约一致的 **unchanged/dedup** 或等价省 token 行为（若本期未实现则标为 **N/A 延期** 并更新 design Todo）。 |

## Non-functional criteria

| ID | Criterion |
|----|-----------|
| **N-01** | 单次读取在 **max_bytes** 限制下 **p95 耗时** 在本地 SSD fixture 集 < 2s（不含冷启动；具体数值可在实施时收紧）。 |
| **N-02** | 日志 / metrics 含 `content_kind`、`truncated`，**不含**完整 `text` 或 base64 正文（防日志泄露）。 |
| **N-03** | 核心模块单元测试覆盖率目标：行覆盖 ≥ 80%（`multiformat_read` 包）或团队基线。 |

## Evidence（Phase 6 填写）

| ID | Pass evidence |
|----|----------------|
| **Phase 5** | `npm run test`（Vitest）exit 0，407 tests passed，`C:/chenf/SecManus/secmanus-workspace` |
| **Phase 5** | `pytest tests/test_sread_file.py tests/test_common_tool_registry.py tests/test_common_tools_from_registry.py` exit 0，18 passed，`python-agent-service/` |
| A-02 | `tests/test_sread_file.py::test_decode_utf8_and_gbk` |
| A-03（部分） | `tests/test_sread_file.py::test_looks_binary_sniff`（魔数启发）；无整文件 PE `SReadFile` 集成夹具 |
| 路径/文本 | `test_sread_file_text_via_runtime`、`test_sread_file_invalid_path`、`test_sread_file_no_runtime` |
| **A-01 / A-04–A-09** | 无专用文件夹具或场景测试 → 记 **CONCERNS**，见 Sign-off |
| **N-01** | 未跑 p95 专用 benchmark → CONCERNS |
| **N-02** | `SReadFile` 尚未接 `structlog` 结构化事件 → CONCERNS（`design.md` §缺口） |
| **N-03** | 未生成 ≥85% 行覆盖报告 → CONCERNS |

### Exploratory（GR-MCP）

| Gate | Status | Reason |
|------|--------|--------|
| `/qa`（Playwright MCP） | **SKIP** | 本交付为后端工具 + 文档；当前 Agent 会话未对活站点执行 Playwright 探索 |
| `/design-review` | **SKIP** | `acceptance-ui.md` 已声明无 UI |

## Sign-off

| Criterion id | pass/fail | verifier | date | notes |
|--------------|-----------|----------|------|-------|
| A-01 | CONCERNS | automated | 2026-04-28 | 有 FakeBackend 文本路径；无真实 UTF-8 PHP fixture |
| A-02 | pass | automated | 2026-04-28 | `test_decode_utf8_and_gbk` |
| A-03 | CONCERNS | automated | 2026-04-28 | sniff 已测；返回字段为 `base64`（非文案 `binary_base64`） |
| A-04 | CONCERNS | automated | 2026-04-28 | `.eml` 逻辑在代码中；无 multipart fixture 测试 |
| A-05 | CONCERNS | automated | 2026-04-28 | `max_bytes` 截断在实现中；无超大文件专项测试 |
| A-06 | CONCERNS | automated | 2026-04-28 | `_line_window` 行长截断；无「单行巨型」集成测试 |
| A-07 | CONCERNS | automated | 2026-04-28 | 非法路径为 `INVALID_PATH`；后端错误为 `READ_FAILED`，与原文 NOT_A_FILE 表述略异 |
| A-08 | N/A | automated | 2026-04-28 | 虚拟路径工具未实现 `/dev/*` 黑名单；Linux 直连场景延期 |
| A-09 | CONCERNS | automated | 2026-04-28 | `hex_head` 已实现；无专用断言测试 |
| A-10 | N/A | automated | 2026-04-28 | dedup 未实现（与设计 Todo 一致） |
| N-01 | CONCERNS | automated | 2026-04-28 | 未测 p95 |
| N-02 | CONCERNS | automated | 2026-04-28 | 见 Evidence |
| N-03 | CONCERNS | automated | 2026-04-28 | 未跑 coverage 门槛 |
| /qa | SKIP | automated | 2026-04-28 | 无 UI / 无本会话 Playwright 对站 |
| /design-review | SKIP | automated | 2026-04-28 | 无 UI |
