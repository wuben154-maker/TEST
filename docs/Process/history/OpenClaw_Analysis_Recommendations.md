# OpenClaw 源码分析与 SecManus 可参考点

> 本文档基于 OpenClaw 开源项目源码分析，从**意图理解**、**工具使用**、**Skill 系统**三方面提炼 SecManus 项目可借鉴的设计思路与实现参考。

---

## 一、OpenClaw 架构概览

OpenClaw 是 Gateway 中心化的个人 AI 助手平台，主要特点：

- **核心**: 单一 WebSocket/HTTP 网关 (port 18789)，所有客户端通过 JSON-RPC 与之通信
- **语言**: 主要是 TypeScript，规模约 4,885 文件、6.8M tokens
- **Agent 引擎**: `src/agents/`（约 60+ tools，9 层策略）
- **消息管线**: `src/auto-reply/` — 解析、鉴权、命令检测、队列、Agent 执行
- **技能系统**: `skills/` 目录，AgentSkills 兼容格式，ClawHub 注册表
- **插件系统**: `extensions/` 下有 34 个插件

---

## 二、意图理解 (Intent Understanding)

### 2.1 OpenClaw 的做法

OpenClaw 不采用“独立意图分类器”，而是采用 **命令 + 管线** 模式：

1. **命令检测 (`command-detection.ts`)**
   - 基于 `commands-registry.data.ts` 的静态命令列表
   - 支持 `/status`, `/new`, `/compact`, `/think`, `/verbose`, `/restart` 等
   - 使用 `hasControlCommand()`, `isControlCommandMessage()` 判断是否为控制命令
   - 支持 `hasInlineCommandTokens()` 检测内联指令（如 "hey /status"）
   - 区分“是否需要计算 CommandAuthorized”以控制鉴权成本

2. **Auto-reply 管线 (`auto-reply/`)**
   - 处理流程：Parse → Authorize → Debounce → Session init → **Command check** → Trigger check → Directives → Queue → Agent execution
   - 命令优先于 LLM：若命中命令，直接执行，不走 Agent 主循环
   - 支持 Trigger check（关键词/模式匹配）作为另一种分流

3. **Link / Media Understanding**
   - `link-understanding/` 与 `media-understanding/` 分别处理链接和多媒体理解
   - 将“链接/图片/视频”等特定输入类型单独预处理，再注入 Agent 上下文

### 2.2 SecManus 当前做法

- **IntentClassifier**: 两阶段 LLM 意图理解
  - Phase 1: 初始分类 + context sufficiency check
  - Phase 2: 上下文增强（当前关闭，复杂理解交给 SubAgent）
- **IntentUnderstandingMiddleware**: 文件解析 → 上下文加载 → IntentClassifier → 参数回调
- **输出**: `IntentResult` 含 task_category、confidence、tasks、parameter_requests 等

### 2.3 可参考点

| 方面 | OpenClaw 思路 | SecManus 可借鉴做法 |
|------|---------------|---------------------|
| **快速分流** | 命令/Trigger 优先于 LLM | 在 LLM 意图理解前增加「命令/快捷键」层：如 `/status`、`/compact`、`/new` 等，直接走预定义逻辑，减少 LLM 调用 |
| **注册表模式** | `commands-registry.data.ts` 定义命令列表与别名 | 新增 `app/middleware/commands_registry.py`，用 YAML/JSON 维护命令与别名，便于扩展 |
| **多模态理解** | link-understanding、media-understanding 独立模块 | 参考其结构：对 URL、图片、文档等类型做专门解析，再作为「结构化上下文」注入 IntentClassifier 输入 |
| **内联指令** | `hasInlineCommandTokens()` 检测 `/xxx` | 在用户消息中识别内联指令，拆分「命令部分」与「内容部分」，分别路由 |
| **Debounce** | `inbound-debounce.ts` 合并短时间内的多发消息 | 在 `understand()` 前增加消息去抖逻辑，避免频繁 LLM 调用 |

**建议落地步骤：**

1. 在 `intent_understanding.py` 最前面增加 `_check_chat_command()`，命中则直接返回对应 handler 结果，不调 LLM。
2. 新增 `config/commands_registry.yaml`，定义命令及其处理逻辑（如 `compact` → 调用 context_retriever.compact）。
3. 在 FileParser 或单独模块中，对 URL、图片、文档做「结构化摘要」，作为 `UserInput` 的 `structured_context` 字段传给 IntentClassifier。

---

## 三、工具使用 (Tool Usage)

### 3.1 OpenClaw 的做法

1. **统一工具接口 (`AgentTool`)**
   ```typescript
   type AgentTool<TSchema, TContext> = {
     label: string;
     name: string;
     description: string;
     parameters: TSchema;  // TypeBox schema
     execute: (toolCallId, params, context?) => Promise<AgentToolResult>;
   }
   ```
   - 使用 TypeBox 定义 schema，天然支持 JSON Schema 校验
   - 返回 `content: Array<{ type: "text" | "image"; text?; data?; mimeType? }>`

2. **9 层策略引擎 (`pi-tools.ts`)**
   - 1.Subagent → 2.Sandbox → 3.Group → 4.Agent provider → 5.Per-agent → 6.Provider global → 7.Global → 8.Profile provider → 9.Profile
   - 任意层 deny 即禁止该工具
   - 便于：主 Agent 全权限，子 Agent/群组/沙箱逐级收窄

3. **工具分类**
   - 核心: grep, find, ls, process, exec, read, write, edit, apply_patch
   - Web: browser, web_fetch, web_search
   - 通信: sessions_spawn, sessions_send, message
   - 基础设施: nodes, canvas, cron, memory_search, memory_get

4. **Auth Profile 轮换**
   - 按计费错误自动切换到备用 API Key，支持多 Key 负载均衡

### 3.2 SecManus 当前做法

- 工具定义：`app/tools/enhanced_tools.py`, `security_tools.py`, `research_tools.py`
- 输入：Pydantic 模型（ExtractIOCsInput, DecodeBase64Input 等）
- 集成：通过 LangChain StructuredTool 暴露给 DeepAgent
- 无分层工具策略，权限主要依赖 Agent 配置

### 3.3 可参考点

| 方面 | OpenClaw 思路 | SecManus 可借鉴做法 |
|------|---------------|---------------------|
| **统一返回结构** | `AgentToolResult` 支持 text + image | 定义 `ToolResult(content: List[TextBlock | ImageBlock])`，便于前端统一渲染（文字、图片、表格等） |
| **分层策略** | 9 层策略，deny 即禁止 | 引入简化的策略层：Profile（全局）→ Session（会话）→ Skill（技能内）。用于控制高风险工具（如 exec、外部 API）在非主会话中的使用 |
| **TypeBox/Schema** | 用 JSON Schema 描述参数 | 已有 Pydantic，可考虑将工具 schema 导出为 JSON Schema，供 Gateway/前端展示，便于调试和文档生成 |
| **Auth 轮换** | 多 API Key 自动 failover | 在 settings 中支持 `LLM_API_KEYS: [key1, key2, ...]`，失败时自动切换，并记录 per-profile 错误窗口 |

**建议落地步骤：**

1. 定义 `ToolResult` 模型，统一工具返回格式（含 text/image/table 等类型）。
2. 新增 `app/middleware/tool_policy.py`，实现 Profile/Session/Skill 三层策略检查。
3. 在 `settings.py` 中增加 `LLM_API_KEYS` 列表，在 LLM 调用失败时实现轮换逻辑。

---

## 四、Skill 系统

### 4.1 OpenClaw 的做法

1. **Skill 格式 (AgentSkills 兼容)**
   - 每个 Skill 一个目录，内含 `SKILL.md`
   - Frontmatter 示例：
   ```yaml
   ---
   name: clawhub
   description: Use ClawHub CLI to search, install, update skills
   metadata:
     { "openclaw": { "requires": { "bins": ["clawhub"] }, "install": [...] } }
   ---
   ```
   - 支持：`command-dispatch`, `command-tool`, `disable-model-invocation`, `user-invocable`, `homepage`

2. **加载位置与优先级**
   - `/skills` (workspace) > `~/.openclaw/skills` (managed) > bundled skills
   - 支持 `skills.load.extraDirs` 扩展目录

3. **Gating（按条件加载）**
   - `requires.bins`: 依赖可执行文件
   - `requires.env`: 依赖环境变量
   - `requires.config`: 依赖配置项
   - `os`: 按平台过滤
   - `install`: 定义安装方式（brew/node/go/uv/download）

4. **ClawHub 注册表**
   - 公共 Skill 注册表 clawhub.com
   - 支持 `clawhub search`, `clawhub install`, `clawhub update`, `clawhub publish`
   - Skill 可被 Agent 动态发现与安装

5. **Token 控制**
   - 注入系统 Prompt 的是紧凑 XML 列表：`<skill name="..." description="..." location="..."/>`
   - 完整 SKILL.md 按需 `read_file` 加载（渐进式）

### 4.2 SecManus 当前做法

- **格式**: YAML frontmatter + Markdown 正文，含 `workflow_steps`、`triggers`、`tags`、`priority` 等
- **Discovery**: `discovery.py` 只解析 frontmatter 的 name、description
- **加载**: SkillsMiddleware 在 SubAgent 运行时从 backend 加载，LLM 按需 read_file SKILL.md
- **位置**: `python-agent-service/skills/` 下若干技能（email-security, binary-analysis, web-security 等）

### 4.3 可参考点

| 方面 | OpenClaw 思路 | SecManus 可借鉴做法 |
|------|---------------|---------------------|
| **Gating** | requires.bins/env/config 控制加载 | 在 frontmatter 中增加 `requires: { bins: [...], env: [...] }`，discovery 时过滤不满足条件的 Skill，避免无效加载和误导 |
| **Install 元数据** | 定义 brew/node/go 等安装方式 | 为需要外部依赖的 Skill（如 VirusTotal）定义 `install` 说明，便于文档和运维 |
| **Skill 注册表** | ClawHub 作为公共 registry | 可建立内部或社区 Skill 注册表（如 API/静态 JSON），支持「搜索 → 安装 → 更新」流程，扩展安全分析能力 |
| **command-dispatch** | 斜杠命令直连工具 | 对部分 Skill 支持 `/skill-name args` 直接调用对应工具， bypass 主 Agent 规划，降低延迟 |
| **Token 优化** | 只注入 name/description 列表 | 已有类似思路，可进一步压缩注入格式，或按「会话类型」选择性注入（如仅安全会话注入安全相关 Skill） |
| **Skill 热更新** | skills.load.watch | 增加文件监听，SKILL.md 变更时刷新 Skill 列表，便于开发调试 |

**建议落地步骤：**

1. 在 SKILL.md frontmatter 中增加 `requires` 和 `install`，在 discovery 中实现 gating 过滤。
2. 新增 `SkillRegistry` 服务，支持从远程 JSON/API 拉取 Skill 列表，并提供 `install`、`update` 接口。
3. 为高频 Skill（如 ioc-extract）增加 `command-dispatch: tool`，支持 `/ioc-extract <content>` 直接调用。
4. 可选：增加 `skills.load.watch` 配置，开发模式下监听 SKILL.md 变更并热更新。

---

## 五、总结

| 领域 | 高价值可借鉴点 | 优先级 |
|------|----------------|--------|
| **意图理解** | 命令/快捷键快速分流、命令注册表、多模态预处理 | 高 |
| **工具使用** | 统一 ToolResult、分层策略、API Key 轮换 | 中 |
| **Skill** | Gating、Install 元数据、Skill 注册表、command-dispatch | 高 |

建议优先落地：**命令分流 + 命令注册表**、**Skill Gating**、**ToolResult 统一格式**，这三项改造成本低、收益明显，且与现有架构兼容。

---

## 参考资料

- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw 架构技术指南](https://www.globalbuilders.club/blog/openclaw-codebase-technical-guide)
- [OpenClaw Skills 文档](https://docs.openclaw.ai/tools/skills)
- [AgentSkills 规范](https://agentskills.io/)
