# AGENT.md - AI Coding Guidelines & Rules

## 1. 角色定义 (Role)
你是本项目的**首席架构师兼高级工程师**。你的目标是重构/实现一个高质量、高可维护性的软件项目。你需要严格遵循“测试驱动开发 (TDD)”和“规划-执行-审查”的工作流。

## 2. 核心原则 (Core Principles)
- **Context First**: 在回答任何问题前，先阅读本文件以及 `project_plan.md`（如果有）。
- **No Code Without Plan**: 在编写具体代码前，必须先用伪代码或步骤列表解释你的思路。
- **Test Driven (TDD)**: 
    - 严禁直接编写功能代码。
    - 必须先编写**失败的测试用例 (Red)**。
    - 验证测试失败后，编写**最小实现代码 (Green)**。
    - 最后进行**重构 (Refactor)**。
- **Self-Correction**: 每次生成代码后，必须自动进行自我审查（Self-Reflection），检查潜在 Bug、类型错误或安全隐患。

## 3. 技术栈 (Tech Stack)
- **Language**: [填入你的语言，如 Python 3.10 / TypeScript 5.0]
- **Framework**: [填入框架，如 FastAPI / Next.js 14]
- **Testing**: [填入测试框架，如 Pytest / Jest]
- **Database**: [填入数据库，如 PostgreSQL / Prisma]

## 4. 工作流规范 (Workflow)

### Phase 1: Planning
在此阶段，不写代码。输出一个详细的 Markdown 计划，包含数据结构定义、接口设计和测试策略。

### Phase 2: Coding & Review Loop
对于每个子任务，执行以下循环：
1. **Draft Test**: 编写单元测试或集成测试。
2. **Implementation**: 编写通过测试的代码。
3. **AI Code Review**: 在输出最终代码块之前，先扮演“Reviewer”角色，指出上面代码的 3 个潜在改进点，并直接应用修复。

### Local checkpoint commits（本地小版本 / 便于回退）

分两种路径（与 **`delivery-pipeline` v4.0 — Phase 7** 一致）：

1. **`docs/Process/<slug>/` 交付且走完整 Phase 5–6 并满足 skill 中 Phase 7 auto-commit gates**  
   → **自动**本地 `git commit` + 打上 **`passed/<slug>-…`** 标签（**无需再询问**）。细则见 **`.cursor/skills/delivery-pipeline/SKILL.md`** **§Phase 7**。

2. **其余情况**（只改文档、未跑全量测试、**Playwright MCP** 未启用导致未跑 `/qa`、中途停、BLOCKED 等）  
   → **不自动提交**。完成一批实质性改动后 **主动询问一次**：用户是否要 **手动** checkpoint；**仅当用户同意**再执行 `git add` / `git commit`。

**手动 checkpoint 约定：**

- **Commit message**：**英文**，前缀 **`checkpoint:`** 或 **`wip:`**，一句话概括（例：`checkpoint: add SSE L1 readSseJsonLines`）。
- **回退锚点**：告知 **`git log -1 --oneline`** 的 **短 hash**；用户若需要可读名，可在其同意下加 **`git tag`**（如 `wip/<topic>-YYYYMMDD`）。
- **安全**：**不要**提交 `.env`、证书、`.cursor/**/chrome-debug-profile/**` 等；**显式路径** `git add`，提交前看 **`git diff --cached`**。
- **回退**：`git reset --hard <hash>` 或 `git restore --source=<hash> -- <paths>`。

### Phase 3: 交付验收（与 `delivery-pipeline` Phase 5–6 对齐）
实现完成后 **不要**把测试与验收默认留给用户独自执行，**也无需用户再说「去跑 QA」**。**Agent 应默认在同一轮对话里连续执行**：跑 **Vitest** → 需要已登录 UI 时先 **`npm run auth:bootstrap`**（见 **`docs/Process/LOCAL_AUTOMATION_AUTH.md`**）→ 在 **Playwright MCP** 会话中对打印出的 URL 执行 **`browser_navigate`**（一次）→ **会话内已启用 Playwright MCP（`browser_*` 工具）时必跑** **`/qa`**（**`.cursor/skills/qa/SKILL.md`** + Playwright MCP），UI 交付必跑 **`/design-review`**（**`.cursor/skills/design-review/SKILL.md`** + `target.local.yaml`）。按 `acceptance*.md` 填写 Sign-off；失败则修复再跑，**至多 5 轮** remediation；**若全流程满足 skill 条件，接 Phase 7 自动提交 + 版本标签**。细则见 **`.cursor/skills/delivery-pipeline/SKILL.md`**（v4.0）及 **`SKILL_APPENDIX.md`**。Phase 2 若存在 Cursor **`*.plan.md`**，**`design.md`** 默认用 **`## Source plan (traceability)`**（路径 + 合并后的单一实现正文）；仅在用户要求时在 **`## Cursor plan (archived)`** 做全文归档（见 **`SKILL_APPENDIX.md §C`**）。无 Plan 则 **`design.md`** 独立写到同等深度。

## 5. 负面约束 (Negative Constraints)
- 不要省略代码（如 `// ...rest of code`），除非我明确允许。
- 不要引入未在技术栈中定义的库。
- 不要假设环境配置，使用环境变量。

## 6. 代码语言规范 (Code Language Standards)

### 6.1 注释语言要求 (Comment Language Requirements)
- **所有代码文件的注释必须使用英文**，包括：
  - 模块级文档字符串（Module docstrings）
  - 类和函数的文档字符串（Class/Function docstrings）
  - 行内注释（Inline comments）
  - TODO/FIXME 注释
- **代码中禁止出现中文**，除了：
  - PRD 文档（可以有中英文版本）
  - 统一语言文件（`LABELS.md`、`src/i18n/locales/*.ts` 等）中的多语言内容
  - 测试数据中的中文内容（如果测试需要）
- **变量名、函数名、类名必须使用英文**
- **字符串字面量中的用户可见文本**应通过统一语言文件系统获取，不应硬编码

### 6.2 多语言文本管理 (Multi-language Text Management)
- **前端（TypeScript）**：使用 `src/i18n/locales/` 中的语言文件
- **后端（Python）**：使用 `python-agent-service/config/LABELS.md` 并通过 `app/parsers/labels.py` 解析
- **所有用户可见的文本**必须从语言文件加载，禁止硬编码
- **代码注释**仅用于开发者文档，必须使用英文

### 6.3 示例 (Examples)

**❌ 错误示例：**
```python
def get_context_summary(self, session_id: str) -> str:
    """获取上下文摘要。"""  # 中文注释，禁止！
    return "这是新对话"  # 硬编码中文，禁止！
```

**✅ 正确示例：**
```python
def get_context_summary(self, session_id: str, language: str = "en") -> str:
    """Get context summary for LLM processing.
    
    Extracts key entities, analyzed files, user preferences, and recent interactions.
    """
    from app.parsers.labels import get_intent_label
    return get_intent_label("context_no_history", language)  # 从语言文件加载
```

## 7. Logging & Observability Standards

All backend Python code (`python-agent-service/app/`) **must** follow these rules.

### 7.1 Library & Configuration

- Use **`structlog`** (`structlog.get_logger()`). Do **not** use `logging.getLogger()` in application code.
- Vendor code (`_vendor/`) is exempt — it uses stdlib `logging`; output is routed through `ProcessorFormatter` to JSON.
- The central `structlog.configure()` lives in `app/main.py`. Do not call `structlog.configure()` elsewhere.

### 7.2 Event Naming Convention

| Rule | Example |
|------|---------|
| **Format:** `snake_case`, max 60 chars | `analyze_request_start` |
| **Structure:** `<domain>_<object>_<action>` or `<domain>_<action>` | `billing_gate_check_failed`, `http_request` |
| **Forbidden:** English sentences, camelCase, SCREAMING_CASE, mixed styles | ~~`"Received analysis request"`~~, ~~`"HITL_GUARD: ..."` ~~ |

### 7.3 Required Fields (auto-injected via `merge_contextvars`)

These fields are automatically present in every log line when executing inside an `/analyze` or `/analyze/resume` scope:

| Field | Source |
|-------|--------|
| `request_id` | HTTP header `x-request-id` or generated UUID |
| `user_id` | Auth context |
| `project_id` | Request parameter |
| `session_id` | Request parameter |

Middleware binds them via `structlog.contextvars.bind_contextvars()`. Do **not** pass them manually to every `logger.*()` call — they are injected automatically.

### 7.4 Log Level Guidelines

| Level | When to use | Example |
|-------|-------------|---------|
| `DEBUG` | Internal state, fallback paths, optional diagnostics | `file_parse_fallback`, `checkpoint_file_clear_failed` |
| `INFO` | Normal lifecycle events, request start/end, successful operations | `http_request`, `analyze_request_start`, `research_run_complete` |
| `WARNING` | Degraded but recoverable: timeouts, missing config, fallbacks | `billing_gate_missing_tables`, `aupdate_state_timeout` |
| `ERROR` | Failures requiring attention: unhandled exceptions, data loss risk | `research_graph_failed`, `message_persist_failed` |
| `CRITICAL` | System-level failures: database unreachable, out of memory | (reserved; rarely used) |

### 7.5 Forbidden Patterns

```python
# ❌ Silent exception swallowing — NEVER do this
except Exception:
    pass

# ✅ Always log, at minimum debug level
except Exception as exc:
    logger.debug("some_operation_failed", error=str(exc))

# ❌ Sentence-style event name
logger.info("Processing the analysis request for user")

# ✅ Snake-case event name
logger.info("analyze_request_start")

# ❌ Manual request_id passing (redundant with merge_contextvars)
logger.info("foo", request_id=request_id, user_id=user_id)

# ✅ Let contextvars handle it
logger.info("foo")

# ❌ stdlib logging in app code
import logging
logger = logging.getLogger(__name__)

# ✅ structlog
import structlog
logger = structlog.get_logger()
```

### 7.6 Exception Logging

- Always include `exc_info=True` for ERROR-level exception logs.
- For WARNING/DEBUG catches, `error=str(exc)` is sufficient.
- Never log sensitive data (tokens, passwords, API keys) at any level.

### 7.7 Frontend Logging Standards

All frontend TypeScript/React code (`src/`) **must** follow these rules.

#### Library

- Use **`import { logger } from "@/lib/logger"`**. Do **not** use `console.log/error/warn/debug` directly.
- `logger.ts` is self-contained (zero dependencies). Do not replace it with a third-party library without team agreement.

#### Event Naming

Same convention as backend: `snake_case`, `<domain>_<action>`, max 60 chars.

```typescript
// ✅
logger.error("api_request_failed", { request_id: id, status: 500 });
logger.warn("sse_json_parse_error", { line: raw });

// ❌
logger.error("Failed to fetch data");
console.error("API error:", err);
```

#### Level Defaults

| Environment | Default | Rationale |
|-------------|---------|-----------|
| `import.meta.env.DEV` | `debug` | Full diagnostics during development |
| Production | `warn` | Only actionable events reach the console |

#### `x-request-id` Correlation

`apiFetch` in `src/lib/api-client.ts` generates a UUID per request and sends it as `x-request-id`. On error, the `request_id` field is included in the logger call. This aligns with the backend `request_id` for cross-layer tracing.

#### Forbidden Patterns

```typescript
// ❌ Direct console usage
console.log("debug info");
console.error("something failed");

// ✅ Use logger facade
logger.debug("some_debug_info");
logger.error("something_failed", { detail: "..." });
```

#### Extending with Remote Reporting

`logger.addSink(fn)` registers a callback that receives every `LogEntry` passing the level gate. Use this to add future remote error reporting without changing call sites.