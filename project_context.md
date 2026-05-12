## Project Overview (项目概览)

- **一句话描述**：SecManus Workspace 是一个结合前端可视化工作区、Python Deep Agent 服务与 Supabase 数据存储（本地是PostgreSql）的安全分析与研究平台，用于对 IOC、邮件、日志、Web 等多源安全情报进行 AI 驱动的深度分析与协作记录。
- **核心业务目标**：
  - **安全分析一体化**：统一承载 IOC 提取、恶意代码/邮件/Web 安全分析、SIEM 告警解析等安全场景。
  - **可解释的 AI 推理过程**：通过推理面板和多种可视化 Block 呈现 Agent 的思考链路和工具调用结果。
  - **长程会话与知识留存**：将对话、项目、共享报告和会话参数持久化到 Supabase，支持分享链接和“长期记忆”式参数存储。
  - **可扩展的技能系统**：通过后端 `skills/*` 与 `tools/*` 模块扩展新的安全技能与工具（如 VirusTotal、IOC Extractor、Web 安全脚本等）。

---

## Tech Stack (技术栈)

- **前端 (Web App)**：
  - **语言**：TypeScript `^5.8.3`
  - **运行时 / 框架**：React `^18.3.1`，基于 Vite `^5.4.19` 构建（`vite.config.ts`）。
  - **UI / 样式**：
    - Tailwind CSS `^3.4.17`（`tailwind.config.ts`, `postcss.config.js`, `index.css`）。
    - shadcn/ui 组件集（存放在 `src/components/ui/*`，基于 Radix UI，如 `@radix-ui/react-dialog` 等）。
    - `lucide-react` 图标、`sonner` 通知等。
  - **状态与数据访问**：
    - `@tanstack/react-query` `^5.83.0`：前端数据获取与缓存。
    - `react-router-dom` `^6.30.1`：路由与页面结构。
    - `@supabase/supabase-js` `^2.86.2`：前端访问 Supabase（认证、数据库、存储）。
  - **富文本与导出**：
    - `@tiptap/*` 系列：文档编辑（DocumentEditor 等）。
    - `docx`、`html2pdf.js`、`html-to-image`、`file-saver`：报告导出与下载（如 docx / PDF / 图片）。
  - **表单与校验**：
    - `react-hook-form` + `@hookform/resolvers`、`zod`：表单与 schema 校验。

- **后端 (Python Agent Service)**：
  - **语言**：Python（建议 3.11+，参考 `docs/ARCHITECTURE.md`）。
  - **Web 框架**：FastAPI `>=0.115.0`（`python-agent-service/app/main.py` 提供 `/health`、`/analyze`、`/agents`、`/tools` 等接口）。
  - **Agent / LLM 编排**：
    - `langgraph>=0.2.0`：多 Agent 图式编排（Deep Agent 架构）。
    - `langchain>=1.2.10`：LLM、工具集成封装（官方 DeepAgents v0.5.2 vendored）。
    - 各主流 LLM Provider 适配：`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`。
  - **沙箱执行**：
    - `e2b>=1.3.0`（可选）：E2B 云沙箱，按需创建隔离 VM 执行不可信代码/脚本；配置在 `config/sandbox.yaml`。
  - **配置与数据建模**：
    - `pydantic[email]>=2.10.0`、`pydantic-settings>=2.6.0`：请求/响应模型与配置管理；`app/config/settings.py` 定义 `Settings(BaseSettings)` 统一管理 70+ 配置项（模式开关、API Key、LLM 参数、HITL、Billing 等），通过 `get_settings()` LRU 缓存单例获取。
    - `python-dotenv>=1.0.0`：本地 `.env` 环境配置加载。
  - **数据库 / 存储**：
    - Supabase JS/SQL 侧配合：Python 端使用 `supabase>=2.10.0` 客户端访问 Supabase。
    - PostgreSQL 本地模式支持：`asyncpg>=0.30.0`, `psycopg2-binary>=2.9.9`。
    - 存储后端：`app/backends/*`（自研扩展：store.py、database_backend.py、composite.py、standalone_state.py、supabase_store.py、e2b_sandbox.py）；官方 Backend 从 `app._vendor.deepagents.backends` 导入。
  - **Web Server**：`uvicorn[standard]>=0.32.0` 用于开发与生产运行。
  - **测试 / 质量**：
    - `pytest`（`python-agent-service/pytest.ini`，`python-agent-service/tests`）。
    - `structlog>=24.4.0`, `tenacity>=9.0.0`：日志与重试。
    - `debugpy`：本地调试支持。

- **基础设施 & 数据库 (Supabase / Lovable Cloud)**：
  - **数据库**：PostgreSQL（由 Supabase 托管），通过 `supabase/migrations/*.sql` 管理 schema 和 RLS。
  - **认证**：Supabase `auth.users` + `public.profiles` 表。
  - **主要表**（摘自 migrations）：
    - `public.profiles`：用户资料和头像（自动跟随 `auth.users` 创建，带 RLS）。
    - `public.projects`：对话项目（会话/工作区）。
    - `public.messages`：项目内消息与分析内容（含 `reasoning`, `thinking_steps`, `blocks`）。
    - `public.shared_reports`：共享报告，用于公共链接访问（带 `share_token`）。
    - `public.session_parameters`：会话参数与长期记忆存储（加密标记、过期时间、元数据等）。
    - `public.parameter_callbacks`：参数回调队列，用于高并发参数收集/回调场景。
  - **迁移管理**：`supabase/config.toml` + `supabase/migrations/*.sql`。

---

## Architecture & Structure (架构与结构)

- **整体架构模式**：
  - 前端采用 **SPA + Hooks + 组件化 UI** 的架构，结合 React Router 做路由划分，React Query 做数据层，整体偏向 “页面 + 容器组件 + UI 组件 + hooks + lib” 的经典前端分层。
  - 后端采用 **FastAPI + LangGraph 深度 Agent 架构**，通过多层模块（`agents` / `middleware` / `tools` / `backends` / `skills`）实现职责清晰的管线式处理，更接近 **分层 + pipeline + plugin/skills** 组合模式，而非传统 MVC。
  - 数据层通过 Supabase/PostgreSQL 承载，配合行级安全（RLS）与存储函数/触发器，实现 **多租户安全** 与 **长期会话数据管理**。

- **根目录关键结构**：
  - `src/`：前端 React 应用主目录。
  - `python-agent-service/`：Python Deep Agent 后端服务。
  - `supabase/`：数据库迁移与 RLS 策略。
  - `docs/ARCHITECTURE.md`：系统架构与部署说明。
  - `docs/TOOLS_AND_REGISTRY.md`：工具注册表与 ToolSpec 使用说明。
  - `docs/FLOW_ANALYSIS_CRITIQUE.md`：意图理解→任务规划→执行流程分析与设计批判。
  - `docs/FLOW_AND_SKILL_ANALYSIS.md`：流程合理性、与 DeepAgents 官方契合度、Skill 规范符合性及官方模式改造说明。
  - `docs/SUBAGENT_AND_SKILL_ARCHITECTURE.md`：Python Agent Service 运行时 Subagent / Skill 类型、配置、`task()` 与 SkillsMiddleware 调用链说明。
  - `docs/Process/`：交付流水线文档（每个交付对应 `<slug>/` 子目录，含 proposal / design / acceptance）。
  - `README.md`：仓库顶层说明。

- **前端目录说明 (`src/`)**：
  - `src/main.tsx`：应用入口，挂载 React 应用并注入路由、QueryClient、全局 Provider 等。
  - `src/App.tsx`：全局路由/布局容器，组织导航、错误边界与页面结构。
  - `src/components/`：
    - `AppErrorBoundary.tsx`：全局错误边界。
    - `TopNavbar.tsx`, `ProjectSidebar.tsx`, `NavLink.tsx`：导航和项目选择等布局组件。（`ProjectSidebar` 顶满视口高度：品牌 `t.sidebar.brandTitle`、语言/用户、折叠、新建、账户导航、历史区搜索；无搜索时默认展示最近 5 个项目，列表内「更多」每次再展开 5 条（同 `ScrollArea` 滚动）；折叠态含账户概览/设置/账单/用量图标入口。`TopNavbar` 导出菜单文案用 `t.workspace.exportMarkdownFile` / `exportPngFile`。）
    - `CommandCenter.tsx`：主输入区域，发起分析请求。
    - `LiveWorkspace.tsx` + `workspace/*`：工作区与分析 Block（如 `AnalysisBlock`, `SummaryBlock`, `DecoderBlock`, `DocumentWorkspace`, `DocumentEditor` 等）。复杂任务下报告区含 `TaskHeader`（完整用户任务标题 + 分享/导出/桌面端报告全屏）、`TaskStatsBar`（来源/会话/风险分/UTC 完成时间等，severity 与风险分可从 `stats` 或报告块解析合并）、`TaskTabPanel`（默认「报告」+ `workspaceTabs` 动态标签）。
    - `reasoning/*`：推理链 UI，包括 `AnalysisTurnPanel`, `ReActTimelineView`, `TimelineActivity`, `TaskListPanel`, `TaskExecutionFlow`, `UnderstandingCard`, `UserDecision`, `NextActions`, `TaskSummary` 等，负责展示 Agent 的思考过程与工具/子任务时间线。
    - `components/ui/*`：基于 shadcn/Radix 的通用 UI 组件库（Button、Dialog、Tabs、Toast 等），作为设计系统基础。
    - `DevModePanel.tsx`, `VoiceMicButton.tsx` 等：开发模式开关、语音输入等辅助组件。
  - `src/pages/`：
    - `Index.tsx`：主工作台页面（组合 CommandCenter + LiveWorkspace 等；左栏推理由 `CommandCenter` 内 `AnalysisTurnPanel` 承载）。
    - `Auth.tsx`：登录/注册/认证页面。
    - `SharedReport.tsx`：根据分享 token 渲染共享报告。
    - `NotFound.tsx`：404 页面。
  - `src/hooks/`：
    - `useStreamingAnalysis.ts`：封装 SSE / 流式分析接口，与后端 `/analyze` 事件协议对接。
    - `useProjects.ts`：项目/会话管理（结合 Supabase `projects`/`messages`）。
    - `useAuth.ts`：认证状态与 Supabase auth 集成。
    - `useConversationPersistence.ts`：前端会话持久化（本地 + 远端）。
    - `useShareReport.ts`：生成、读取共享报告链接（对接 `shared_reports`）。
    - `useVoiceInput.ts`：语音输入（浏览器语音 API / 集成）。
    - `use-mobile.tsx`, `use-toast.ts`：设备/提示类通用 hooks。
  - `src/lib/`：
    - `api-client.ts`：封装调用 Python Backend 与 Supabase 的 API 客户端，是前端访问后端服务的核心入口之一。
    - `config.ts`：前端运行时配置（环境变量、后端 URL 等）。
    - `decoders.ts`：解码/解析工具（如 Base64/URL/编码转换，用于 DecoderBlock）。
    - `docx-export.ts`：导出分析结果为 docx。
    - `text.ts`, `utils.ts`：文本与通用辅助函数。
  - `src/config/endpoints.ts`：
    - 封装 `pythonBackendUrl`、`localApiUrl` 等后端地址，前端通过此处配置来决定调用的后端环境。
  - `src/integrations/supabase/`：
    - `client.ts`：初始化 Supabase 客户端（使用 `VITE_SUPABASE_URL` 和 `VITE_SUPABASE_PUBLISHABLE_KEY`）。
    - `types.ts`：根据 Supabase schema 生成的 TypeScript 类型定义（与 `supabase/migrations/*.sql` 对应）。
  - `src/contexts/LanguageContext.tsx` + `src/i18n/*`：
    - 提供多语言支持（`en`, `zh`, `ja`, `ko` 等），用于 UI 文字国际化。

- **后端目录说明 (`python-agent-service/app/`)**：
  - `main.py`：
    - FastAPI 应用入口，注册路由、中间件和事件流处理。
    - 定义核心请求/响应模型（如 `AnalyzeRequest`, `ThinkingEvent`, `HealthResponse` 等）。
    - 基于环境变量（如 `AGENT_MODE`, `DATABASE_MODE`）配置 Agent 模式与数据库后端。
  - `api/`：
    - `auth.py`：账号注册、登录与用户信息接口（`RegisterRequest`, `LoginRequest`, `AuthResponse`, `UserResponse`）。
    - `projects.py`：项目 CRUD，与 Supabase `projects`/`messages` 表联动（`ProjectCreate`, `ProjectUpdate`, `ProjectResponse`）。
    - `messages.py`：消息记录读写（`MessageCreate`, `MessageResponse`）。
  - `agents/`：
    - `deep_agent.py`：Deep Agent 主入口，基于官方 create_deep_agent；所有请求经主 Agent astream；open_deep_research 仅通过 `task(deep-research)` 子代理进入。
    - `security_agent.py`：独立安全 Agent 图（供 legacy 或测试用）。
    - `official_subagents.py`：create_security_subagents 定义 SubAgent。
    - `subagent_registry.py`：声明式 SubAgent 注册表加载器，从 `config/subagents.registry.yaml` + `subagents/official/<bundle>/` 构建运行时子代理列表。
  - `middleware/`：
    - `intent_models.py`：任务/参数等共享数据模型（`IntentResult` 等）；主流程不再跑独立意图分类服务。
    - `task_instruction_builder.py`：遗留的任务指令拼装（当前主路径由主模型直接 `task()`）。
    - `file_parser.py`、`context_retriever.py`、`policy_guard.py`、`task_payload_sanitize.py`、`user_input_unwrap.py` 等支撑解析与策略。
    - `deep_research_synthesis_skip.py`：纯 deep-research 子任务后跳过主模型再合成一轮。
    - `skill_events.py`：SkillEvent 兼容类型。
  - `tools/`：
    - `tool_spec.py`：`ToolSpec` / `ToolRisk` 元数据 dataclass，用于工具治理与策略钩子。
    - `common_tool_registry.py`：通用工具注册表（canonical name → mounter），按 `tool_presentation.yaml` 声明顺序装配 StructuredTool 到主 Agent 和子 Agent。
    - `enhanced_tools.py`：通用与安全相关工具输入模型，如 `ExtractIOCsInput`, `DecodeBase64Input`, `DecodeURLInput`, `AnalyzeEmailHeadersInput`, `DetectWebAttackInput` 等。
    - `security_tools.py`：威胁情报与日志分析输入模型（`ThreatIntelInput`, `LogAnalysisInput`）。
    - `research_tools.py`：研究类工具输入（`WebSearchInput`, `ScrapeUrlInput`, `SummarizeInput`）。
    - `sandbox_tools.py`：E2B 按需沙箱工具（`sandbox_create`, `sandbox_destroy`, `sandbox_run`, `sandbox_pty_run`）——条件挂载，仅在 `E2B_API_KEY` 配置时对 Agent 可见。
    - `sandbox_sse.py`：沙箱执行输出的 SSE 实时推流适配。
    - `web_security/`：Web 威胁检测多层管线模块（详见下方 § Web Security Pipeline）。
  - `backends/`：
    - 自研扩展：`store.py`（BaseStore/PostgresStore/InMemoryStore）、`database_backend.py`（Supabase/PostgreSQL）、`composite.py`（create_layered_backend）、`standalone_state.py`、`supabase_store.py`、`e2b_sandbox.py`（E2BSandboxBackend，同步实现 BaseSandbox 协议）。
    - 官方 Backend 协议与实现：从 `app._vendor.deepagents.backends` 导入（CompositeBackend、FilesystemBackend、StateBackend、LangSmithBackend 等）。
  - `parsers/`：
    - `events.py`：事件可见性配置（EVENTS.md 解析）。
    - `labels.py`：事件/技能标签解析（与 `config/LABELS.md` 对应）。
    - `deepagents_stream_adapter.py`：将 agent.astream() 映射为 SSE 事件（adapt_astream_to_sse）；adapt_subagent_astream_to_skill_events 直接产出 camelCase dict。
  - `prompts/`：
    - `MASTER_AGENT.md`：主 Agent 系统 Prompt。
    - `skills/`：技能模块。`discovery.py` 仅解析 frontmatter（name、description）供 SubAgent 构建；`loader.py` 保留供测试/legacy。SkillsMiddleware 在 SubAgent 运行时从 backend 加载，LLM 按需 read_file SKILL.md（渐进式加载）。
  - `skills/*`：
    - `binary-analysis`, `email-security`, `web-security`, `vuln-scan`, `soc-alert`, `deep-research` 等技能模块。每个技能含 `SKILL.md`（YAML frontmatter + Markdown 正文）和可选 `scripts/`。遵循 Anthropic Agent Skills 规范，SkillsMiddleware 实现渐进式加载（Level 1 元数据常驻，Level 2 SKILL.md 按需 read_file）。
  - `subagents/official/`：
    - 声明式 SubAgent Bundle 目录，每个 bundle 含 `AGENT.md`（子代理系统 Prompt + HITL/执行纪律说明）及 `skills/<name>/SKILL.md`。
    - 由 `config/subagents.registry.yaml` 统一注册（schema v2），当前 5 个官方子代理：`binary-analysis`、`email-security`、`web-security`、`soc-alert`、`deep-research`。
    - `AGENT.md` 包含：角色定义、HITL 澄清场景表、Tool-first 执行纪律、E2B 沙箱路径约定。
  - `config/`：
    - `subagents.registry.yaml`：SubAgent 声明式注册表（id、bundle_path、description、routing_hints、tool_profile、runtime）。
    - `sandbox.yaml`：E2B 沙箱全局配置（模板、超时、网络策略）。
    - `tool_presentation.yaml`：工具展示与下发策略热配置。
    - `env.md`, `EVENTS.md`, `LABELS.md`：环境变量、事件流、标签的文档说明。

- **数据库结构 (Supabase)**：
  - **profiles**：与 `auth.users` 一对一，自动创建，存储用户名与头像；通过触发器 `handle_new_user` 和行级策略控制访问。
  - **projects**：会话/项目主体（`id`, `user_id`, `title`, `created_at`, `updated_at`），索引按用户与更新时间。
  - **messages**：项目内消息历史（`type: user/assistant`, `content`, `reasoning`, `thinking_steps`, `blocks`），按 `project_id` 和 `created_at` 索引。
  - **shared_reports**：共享报告，持久化前端 `blocks` 结构，并通过 `share_token` 提供只读访问；支持过期时间和所有者 RLS。
  - **session_parameters**：与 `session_id` / `user_id` 绑定的参数存储，支持加密标志与过期时间，用于“长期记忆”与参数缓存。
  - **parameter_callbacks**：参数回调队列表，用于异步参数收集与回调状态跟踪（`pending/completed/expired`）。

---

## Key Data Models (核心数据模型)

> 以下模型综合了后端 Pydantic 模型与 Supabase 表结构，主要关注“项目/消息/共享报告/会话参数”四类核心实体及其关系。

- **User & Profile (用户与档案)**：
  - **Supabase**：
    - `auth.users`：由 Supabase 托管，承载基础账号信息（email、密码、OAuth）。
    - `public.profiles`：
      - 字段：`id`, `user_id`, `username`, `avatar_url`, `created_at`, `updated_at`。
      - 约束：`user_id` 唯一且外键指向 `auth.users(id)`，伴随触发器自动创建记录。
  - **关系**：
    - 一个 `auth.users` 对应一个 `profiles`。

- **Project (项目 / 会话)**：
  - **Supabase 表**：`public.projects`
    - 字段：`id`, `user_id`, `title`, `created_at`, `updated_at`。
    - RLS：仅所有者可 `SELECT/INSERT/UPDATE/DELETE` 自己的项目。
  - **后端模型**（`app/api/projects.py`）：
    - `ProjectCreate`：创建项目时的输入（如 `title`）。
    - `ProjectUpdate`：更新项目标题等。
    - `ProjectResponse`：返回项目详情。
  - **关系**：
    - `User (auth.users/profiles)` 1 — N `projects`。

- **Message (消息 / 对话记录)**：
  - **Supabase 表**：`public.messages`
    - 字段：`id`, `project_id`, `user_id`, `type` (`user`/`assistant`), `content`, `reasoning`, `thinking_steps`, `blocks`, `created_at`。
    - 用途：
      - `content`：原始文本内容。
      - `reasoning`：Agent 的显式推理文本。
      - `thinking_steps`：结构化思考步骤（JSON）。
      - `blocks`：用于前端 `LiveWorkspace` 渲染的 Block 结构（分析卡片、总结、日志等）。
    - RLS：用户仅能访问、插入和删除自己的消息。
  - **后端模型**（`app/api/messages.py`）：
    - `MessageCreate`：创建新消息/分析请求。
    - `MessageResponse`：返回历史消息。
  - **关系**：
    - `Project` 1 — N `Messages`。
    - `User` 1 — N `Messages`。

- **SharedReport (共享报告)**：
  - **Supabase 表**：`public.shared_reports`
    - 字段：`id`, `user_id`, `title`, `blocks`, `created_at`, `expires_at`, `share_token`。
    - 特点：
      - `blocks`：完整的报告结构（通常由工作区 Blocks 序列化而来）。
      - `share_token`：唯一索引，用于公共访问。
      - 通过函数 `public.get_shared_report_by_token(p_token TEXT)` 在数据库侧安全地按 token 读取报告（`SECURITY DEFINER`）。
    - RLS：
      - 所有者可 `INSERT/DELETE/UPDATE` 自己的报告。
      - 公共访问通过 function + 应用层校验 share_token 实现，而非开放表级 SELECT。
  - **前端模型**：
    - `src/hooks/useShareReport.ts` + `src/pages/SharedReport.tsx` 负责创建与读取共享报告。

- **SessionParameters & ParameterCallbacks (会话参数 / 回调)**：
  - **Supabase 表**：`public.session_parameters`
    - 字段：`id`, `session_id`, `user_id`, `param_name`, `param_value`, `param_type`, `encrypted`, `created_at`, `updated_at`, `expires_at`, `metadata`。
    - 主要用例：
      - 存储与某个 `session_id` 相关的参数（例如长期记忆、用户偏好、分析上下文）；
      - 支持匿名会话（`user_id IS NULL` 且绑定 `session_id`）。
    - RLS：基于 `auth.uid()` 与请求头中的 `x-session-id` 控制。
  - **Supabase 表**：`public.parameter_callbacks`
    - 字段：`id`, `session_id`, `request_id`, `status`, `parameters`, `created_at`, `completed_at`, `expires_at`。
    - 用例：异步参数请求/回调队列（例如需要用户补充某些参数时）。

- **分析输入/工具输入模型 (后端 Pydantic)**：
  - `app/main.py`：
    - `AnalyzeRequest`：分析请求主入口，携带 `message`, `stream`, `session_id`, `project_id` 等。
    - `ThinkingEvent`, `HealthResponse` 等：SSE 事件与健康检查返回结构。
  - `app/tools/enhanced_tools.py`：
    - `ExtractIOCsInput`, `DecodeBase64Input`, `DecodeURLInput`, `AnalyzeEmailHeadersInput`, `DetectWebAttackInput` 等，描述各安全工具所需输入。
  - `app/tools/security_tools.py`：
    - `ThreatIntelInput`, `LogAnalysisInput`：威胁情报和日志分析工具的输入。
  - `app/tools/research_tools.py`：
    - `WebSearchInput`, `ScrapeUrlInput`, `SummarizeInput`：研究/抓取/总结类工具输入。

---

## Current Status & Roadmap (当前状态)

- **当前已实现的主要功能模块（基于代码结构与架构文档推断）**：
  - **前端**：
    - 集成 Supabase 认证的登录/注册与会话持久化（`useAuth`, `integrations/supabase/*`, `pages/Auth.tsx`）。
    - 支持多语言 UI（中/英/日/韩）与语言上下文切换（`contexts/LanguageContext.tsx`, `i18n/*`）。
    - 具备完整的主工作台（索引页）、共享报告查看页与基础导航/错误边界。
    - 提供推理面板、思考链可视化以及多种 Block 形式展示分析输出（分析卡片、总结、文档编辑、日志、文本块、Decoder 等）。
    - 实现 SSE 流式分析客户端逻辑（`useStreamingAnalysis.ts`）与与后端 `/analyze` 协议对接。
    - 支持生成并访问共享报告链接（`useShareReport.ts`, `SharedReport.tsx`）。
    - 提供语音输入按钮与移动端适配辅助 hooks（`VoiceMicButton.tsx`, `use-mobile.tsx`, `useVoiceInput.ts`）。
  - **后端**：
    - FastAPI 应用与 `/health`、`/analyze`、`/agents`、`/tools` 等核心接口。
    - 官方 DeepAgents 架构（`app._vendor.deepagents` v0.5.2 vendored）：create_deep_agent、SubAgentMiddleware（含 async_subagents）、SkillsMiddleware、PermissionsMiddleware。
    - **Workspace 沙箱统一**（`workspace-sandbox-unification`）：新增 `/workspace/` 虚拟根作为 LLM/UI 唯一可见的工作目录；`app/backends/workspace_facade.py` 对物理 owner-scoped 路径（`u_<uid>/p_<pid>` 或 `s_<sid>`）做双向改写；`app/backends/owner_scoped_store.py` 为 `/memories/` 与 `/parameters/` 注入 per-request 命名空间隔离；`app/backends/workspace_scope.py` 以 `ContextVar` 固定每请求的根目录；`app/parsers/path_scrub.py` 在 SSE 事件出站时把内部路径改写成 `Workspace/...`、`System Skill: <name>`、`Memory: <file>`、`Parameters` 等 UI 友好标签。交付验收含 Playwright：`e2e/tests/workspace-sandbox-unification.spec.ts`；`vitest.config.ts` 已排除 `e2e/**`，避免 `npm run test` 误跑 Playwright 用例。
        - **2026-04-20 UX 加固**：`app/backends/path_aliases.py` 新增 `PathAliasBackend`，把 LLM 传入的 `Workspace/...`、`/Workspace/...`、以及含残留 owner 片段的 `/workspace/u_<id>/default/<file>` 归一化成规范形态 `/workspace/<file>`；`sandbox_tools._reject_host_virtual_paths` 在 `sandbox_run` / `sandbox_pty_run` 执行前验证 `command`/`upload_files`/`cwd`，检测到宿主虚拟路径时返回结构化错误。Master + 4 subagent AGENT.md 新增 `read_file failure = hard stop` 规则，禁止回退到 `ls`/`glob` 探测已知路径。
        - **2026-04-20 ls/glob 限制解除**：鉴于提示词层已经有 `read_file failure = hard stop` 硬规则，代码层不再对 `ls`/`glob` 做路径范围限制。`app/_vendor/deepagents/middleware/filesystem.py` 回退到 upstream（零 diff）；`tests/test_middleware_ls_glob_scope.py` 删除；`path_scrub.py` 对应的 vendor ls/glob 错误重写规则（`_VENDOR_LS_ERROR`）和 `test_path_scrub.py` 的对应用例一并下线。`MASTER_AGENT.md` 与 `web_security/AGENT.md` 移除“`ls`/`glob` are restricted to `/workspace/`”这类描述性条款（已与代码事实不符），但保留 hard-stop 规则。`PathAliasBackend`、UI owner-segment 剥离、sandbox 宿主路径 guard 均保留。
        - **2026-04-20 facade ↔ CompositeBackend 契约修复**：复盘时发现上传文件后 `read_file` 返回 `Error: path must be under /workspace/` — 根因是 `CompositeBackend._route_for_path` 会把 `/workspace/` 前缀剥掉再下派给 `WorkspaceFacadeBackend`，而旧 facade 的 `_strip_virtual` 仍然要求入参必须以 `/workspace/` 开头，所以路由进来的请求全部被判定为 out-of-scope。同时 `CompositeBackend.ls/glob/grep` 会把 routed backend 返回的 path 再拼回 `/workspace` 前缀，因此 facade 必须返回 **route-local** suffix 而非完整 `/workspace/...`，否则出现 `/workspace/workspace/...` 双前缀。修复：重写 `app/backends/workspace_facade.py`，新契约 — 入参同时兼容 stripped (`/a.txt`) 与 legacy (`/workspace/a.txt`) 两种形态，`ls`/`glob`/`grep`/`upload`/`download` 返回 owner-stripped 的 route-local suffix；`write`/`edit` 仍返回完整 `/workspace/...`（对真实链路无影响，CompositeBackend 会用调用方传入的 path 覆盖）；新增 `_FORBIDDEN_TOP_LEVEL` 拒绝 `/memories`、`/skills`、`/etc` 等跨 namespace 误用。`tests/test_workspace_facade.py` 拆成 **contract tests**（facade 直连 + route-local 入参）与 **integration tests**（`CompositeBackend(/workspace/ → facade)`），后者覆盖 LLM 真实链路防回归；回归断言：`composite.read('/workspace/a.txt')` 不能再返回 "path must be under /workspace/"。77/77 pytest 全绿。
    - 主流程：官方 DeepAgent 主循环 + SubAgent（`task`）；研究类由主模型按 `MASTER_AGENT.md` 委派 `deep-research`。无独立的 Phase1/Phase2 意图 LLM 流水线。
    - **声明式 SubAgent 注册**：`config/subagents.registry.yaml`（schema v2）+ `subagents/official/<bundle>/`（AGENT.md + skills/）；当前 5 个官方子代理。
    - Skill 加载采用官方模式：`discovery.py` 仅解析 frontmatter；SubAgent 配置 `skills=[/skills/{name}/]`；SkillsMiddleware 在运行时注入元数据，LLM 按需 read_file SKILL.md（渐进式加载）。
    - **通用工具注册表**：`common_tool_registry.py` + `ToolSpec` 元数据；按 `tool_presentation.yaml` 声明顺序统一装配。
    - **E2B 按需沙箱**：`sandbox_tools.py`（4 个 StructuredTool）+ `sandbox_sse.py`（实时推流）+ `config/sandbox.yaml`（6 个模板）+ `e2b_sandbox.py`（BaseSandbox 后端）。
    - **Web 安全多层管线**：`web_security/` 模块——schema v2 语义管线 → 多语言静态扫描（PHP/JSP/Python/ASPX）→ YARA 签名 → 熵分析 → 语法沙箱。
    - 中间件层：以 `file_parser`、`context_retriever`、`intent_models`、`task_instruction_builder` 等为辅助；分析与路由在 LangGraph 主 Agent 内完成。
    - 与 Supabase 的数据库模式对接：projects/messages/profiles/shared_reports/session_parameters/parameter_callbacks 等表已通过迁移定义且具备 RLS 策略。
    - 测试脚手架：`python-agent-service/tests/`（`test_skills.py`, `test_common_tool_registry.py`, `test_sandbox_tools.py`, `test_web_threat_yara_sandbox.py`, `test_code_language.py` 等）。
  - **数据库与基础设施**：
    - Supabase migrations 已覆盖用户档案、项目/消息、共享报告、会话参数与参数回调等核心表。
    - 文档中给出了 Railway / Docker / Lovable Cloud 的部署流程与环境变量说明。

- **Roadmap / 近期已落地交付**：
  - **`detect_web_attack` schema v2**（`web-security-semantic-pipeline`）：结构化 HTTP 解析、按参数的 XSS/SQLi 特征、PHP 危险 sink 扫描、弱信号与严重度门控；实现位于 `python-agent-service/app/tools/web_security/`。
  - **Web 安全多语言静态分析**（`web-security-multilang-static`）：新增 PHP/JSP/Python/ASPX 托管 sink 扫描器（`aspx_sinks.py`、`jsp_sinks.py`、`python_sinks.py`、`code_language.py`、`code_scanners.py`），管线自动识别代码语言并路由到对应扫描器。
  - **Web 威胁 YARA + 熵 + 沙箱层**（`web-threat-yara-sandbox`）：L1 YARA 签名匹配（`yara_layer.py` + `yara_loader.py`，内置 webshell_php / webshell_scripting 规则）、熵分析层（`entropy_layer.py`）、L3 语法沙箱（`sandbox_layer.py`）；多层流水线通过 `layer_env.py` 共享上下文。
  - **通用工具注册表 + ToolSpec**（`python-agent-tool-registry-toolspec`）：`tool_spec.py` 定义元数据，`common_tool_registry.py` 实现按 YAML 声明顺序的统一工具装配。
  - **E2B 按需沙箱工具**（`e2b-sandbox-tools`）：4 个 StructuredTool + SSE 实时推流 + `config/sandbox.yaml` 模板（base / binary-analysis / web-simulation / script-exec / desktop / web-dynamic）。
  - **DeepAgents vendor 升级 v0.5.2**：新增 `async_subagents`、`permissions` middleware、`profiles/` 模块、`LangSmithBackend`；重写的 `summarization` / `filesystem` middleware；SECMANUS patches 持续维护。
  - **SubAgent 工作流 + Prompt 优化**（`subagent-workflow-prompt-optimization`）：统一 SOP workflow 模式，新建 `subagents/official/` bundle 目录体系（AGENT.md + SKILL.md），web-security skill 重构为 Tool-first 执行纪律，清理废弃代码。
  - `TODO(by maintainer)`: 在此处维护后续 Roadmap，例如：
    - 新的安全技能/场景支持（如云安全、容器安全等）。
    - 增强项目/报告协作能力（评论、标签、导入导出模板等）。
    - 更细粒度的权限与审计日志。
    - 性能优化与成本控制（缓存、批量处理、向量存储等）。

---

## Development Guidelines (开发备忘)

- **总体原则**：
  - 严格遵守 `AGENT.md` 中定义的工作流：**先规划/伪代码，再编写测试（TDD），再最小实现，最后重构与自检**。
  - 任何对架构或核心模型的变更，完成后应同步更新此 `project_context.md` 以及 `docs/ARCHITECTURE.md` 保持一致性。

- **环境变量与配置约定**：
  - **前端环境变量**（来自架构文档与集成代码）：
    - `VITE_SUPABASE_URL`：Supabase/Lovable Cloud 项目 URL。
    - `VITE_SUPABASE_PUBLISHABLE_KEY`：Supabase/Lovable Cloud 公钥。
    - 其他后端地址在 `src/config/endpoints.ts` 中集中配置（`pythonBackendUrl`, `localApiUrl`）；修改后端部署地址时优先更新此文件。
  - **后端环境变量**（详细参考 `python-agent-service/config/env.md` 与 `docs/ARCHITECTURE.md`）：
    - 典型包括：`GOOGLE_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `AGENT_MODE`, `DATABASE_MODE`, `VIRUSTOTAL_API_KEY`, `FIRECRAWL_API_KEY`, `MAX_ITERATIONS`, `TIMEOUT_SECONDS` 等。
    - `E2B_API_KEY`：E2B 云沙箱 API Key（可选），配置后自动挂载 `sandbox_*` 工具；`E2B_DEFAULT_TEMPLATE` 可覆盖默认模板。
    - `TAVILY_API_KEY` / `SERPER_API_KEY`：Web 搜索 API（Tavily 优先，Serper 作为补充）。
    - `READ_FILE_DEFAULT_LIMIT`：`read_file` 工具默认分页行数（未显式传 `limit` 时生效），当前默认 `1000`。
    - 工具展示与 `toolOutput` 下发策略采用热配置：`python-agent-service/config/tool_presentation.yaml`（推荐三节：`common_tools` **按声明顺序**且 `enabled: true` 的项由 `common_tool_registry.py` 装配到**主 Agent**与 **`tool_profile: default`** 子 Agent；`system_tools` / `subagent_tools` 主要为内置与 SSE/UI 元数据）。`subagents.registry.yaml` 的 **`tool_profile: email-security`** / **`web-security`** 在 `app/agents/subagent_registry.py` 的 `build_tool_profiles()` 中与 **`create_email_tools()`** / **`create_web_tools()`** 合并（按工具名去重）。热重载由 `app/sse/tool_presentation.py` 完成。旧版单一 `tools:` 仍支持。
    - `AGENT_MODE`：硬编码为 `deepagent`（`Settings._force_deepagent_mode` 强制覆盖）。
    - `DATABASE_MODE`：`supabase` | `local` | `memory`。
    - `INTENT_LLM_BACKEND`：意图分类 LLM 后端（`langchain` | `gateway` | `auto`）。
  - **Supabase 侧 headers 约定**：
    - 某些 RLS 策略（如 `session_parameters`）依赖 `current_setting('request.headers', true)::json->>'x-session-id'`，调用层必须在请求头中传递 `x-session-id` 以确保匿名会话能访问自身参数。

- **错误处理与事件流**：
  - 后端 API 错误返回统一结构（见 `docs/ARCHITECTURE.md`）：
    - 形如 `{ "detail": "...", "error_code": "ERROR_CODE", "timestamp": "..." }`，前端在处理错误时应优先根据 `error_code`/`detail` 判定展示策略。
  - SSE 事件类型：
    - `thinking`, `tool_start`, `tool_result`, `agent_response`, `error`, `done` 等。
    - 前端 `useStreamingAnalysis` 与推理/工作区组件应继续遵守此事件协议，扩展新事件类型时需要同步更新后端 `parsers/events.py` 和前端消费逻辑。

- **安全与隐私约定**：
  - 数据库层对 `projects`, `messages`, `shared_reports`, `session_parameters`, `parameter_callbacks` 等均启用 RLS，业务逻辑开发时要避免绕过 RLS（除非通过安全的 `SECURITY DEFINER` 函数，如 `get_shared_report_by_token`）。
  - `session_parameters.param_value` 默认视为敏感/加密数据（`encrypted = true`），调用端应在写入前自行加密或使用安全通道；新增字段或表时如涉及敏感信息，应对 RLS 与加密策略进行评审。
  - 共享报告访问通过 `share_token` 且限制生命周期（`expires_at`），前端不要在公开位置泄露 `user_id` 等隐私字段。

- **前后端协同注意事项**：
  - **Blocks 协议**：
    - 前端 `LiveWorkspace` 与后端 `AnalyzeResponse`/`MessageResponse` 通过 `blocks` 字段进行解耦；新增 Block 类型时需要：
      - 后端定义新的 Block schema（或在 `blocks` 中增加 `type`/`payload` 约定）。
      - 前端 workspace 组件新增对应渲染分支（如新的 `XYZBlock.tsx`）。
  - **类型同步**：
    - Supabase 表结构变更后，需要更新 `supabase/migrations` 并重新生成 `src/integrations/supabase/types.ts`，同时检查 `src/types/*` 中的手写类型是否需要更新。
  - **多语言内容**：
    - 新增 UI 文案时，应同步在 `i18n/locales/*` 中添加对应键值，避免硬编码字符串散落在组件中。

- **测试与本地开发建议**：
  - 后端：
    - 使用 `python -m uvicorn app.main:app --reload --port 8000` 启动本地开发服务器。
    - 使用 `pytest` 运行 `python-agent-service/tests` 中的测试；新增技能或工具时应添加对应单元测试或集成测试。
  - 前端：
    - 使用 `npm run dev` 启动 Vite 开发环境。
    - 使用 `npm run build` / `npm run preview` 验证构建与部署行为。

---

> 本文件用于 AI / 开发者在后续维护中快速重建项目全局认知。如有架构、模型或关键流程变动，请同步更新本文件以及相关文档（例如 `docs/ARCHITECTURE.md`）。

