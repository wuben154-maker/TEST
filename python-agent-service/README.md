# Deep Agent Security Service

基于 LangGraph 的深度安全分析 Agent 服务。

## 架构概览

本仓库内**不包含** Supabase Edge Functions；主应用前端通过配置的 Base URL **直连**本服务的 HTTP API（SSE 流式分析走 `POST /analyze`）。Supabase 仅用于认证、项目/消息等数据持久化（见仓库根目录 `supabase/migrations`），与分析计算解耦。

```
┌─────────────────────────────────────────────────────────────────┐
│              前端 (React + Vite，仓库根目录 src/)                 │
│  · Supabase JS：登录、projects / messages / shared_reports 等    │
│  · 分析流：fetch → PYTHON_BACKEND_URL（见 src/config/endpoints）│
├─────────────────────────────────────────────────────────────────┤
│                            │  Bearer + JSON/SSE                  │
│                            ▼                                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        Python FastAPI — python-agent-service (本服务)      │  │
│  │  /health /analyze /api/models /agents /tools               │  │
│  │  /auth /projects /messages /shared-reports …               │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │           LangGraph Deep Agent + Skills / Tools      │  │  │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐              │  │  │
│  │  │  │ Planning │  │  Tools  │  │ Memory  │              │  │  │
│  │  │  └─────────┘  └─────────┘  └─────────┘              │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│         │ 可选：Postgres / Supabase（checkpoint、业务库）        │
│         ▼                                                       │
│              PostgreSQL（本地或 Supabase 托管）                   │
└─────────────────────────────────────────────────────────────────┘
```

## 功能特性

### Deep Agent 核心能力

1. **规划与任务分解** - 将复杂任务分解为可管理的步骤
2. **上下文管理** - 使用文件系统工具管理大上下文
3. **子代理生成** - 为特定任务生成专门的子代理
4. **长期记忆** - 跨会话持久化信息

### 安全分析工具

典型内置工具包括（完整列表以运行实例为准：`GET http://localhost:8000/tools`）：

- **search_virustotal** - 查询 VirusTotal 威胁情报
- **decode_base64** - Base64 解码
- **decode_url** - URL 解码
- **extract_iocs** - 提取 IOC (IP、域名、URL、哈希)

另可通过 `skills/` 与子 Agent（`config/subagents.registry.yaml`）扩展能力。

## 快速开始

### 1. 环境准备

```bash
# 克隆项目后进入目录
cd python-agent-service

# 复制环境配置
cp .env.example .env

# 编辑 .env 文件，填入 API 密钥
```

### 2. 本地运行

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m app.main
```

### 3. Docker 运行

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## Subagent registry（官方子 Agent）

- **主 Agent 全局技能白名单**：`config/main_agent_skills.yaml` — 字段 `main_agent_skill_packages` 列出 **`skills/` 下目录名**；仅这些包会由主 Agent 的 SkillsMiddleware 从全局根加载。子 Agent 的 bundle 内技能不受此文件约束。文件不存在或省略该列表键时，视为「全部允许」（便于本地开发）。
- **注册表（schema v3）**：`config/subagents.registry.yaml` — 声明启用的子 Agent、`bundle_path`、`runtime`（`standard` | `compiled`）、`tools`、`tool_profile`（兼容回退）、`description` / `routing_hints`（写入 **task** 工具目录，与 `AGENT.md` 解耦）。
- **tools 声明**：
  - 兼容旧格式：`tools: ["tool_name", ...]`
  - 推荐新格式：`tools: [{name: "tool_name", backend_binding: "none|required", enabled: true, description_override: "...", provider?: "common|email_security"}]`（省略 `backend_binding` 时视为 `none`）
  - 优先级：`tools` > `tool_profile`；`tool_profile` 仅作为未声明 `tools` 时的兼容兜底。
  - `backend_binding: required` 需要可用 `backend_factory`，否则在构建 subagent specs 时 fail-fast。
- **Bundle 目录**：`subagents/official/<id>/` — 必填 `AGENT.md`（标准子 Agent 系统提示词）；`deep-research` 可为简短说明。每个子 Agent 的 **`skills/<包名>/SKILL.md`** 挂在虚拟路径 **`/subagent-skills/<id>/`**（`include_shared_skills: false` 时仅使用 bundle 内技能；全局 `skills/` 仅保留未注册为子 Agent 的包，如通用分析模板）。
- **编译型子 Agent**：`deep-research` 由 `app/agents/subagent_registry.py` 中 `COMPILED_SUBAGENT_BUILDERS` 分派；`RESEARCH_AGENT_MODE=compiled_subagent`（默认）时使用编译子图。
- **用户自定义**：`source: user` 的条目当前会跳过并打日志；未来与 `subagents/user/` 同构扩展。
- **配置刷新**：修改注册表或 `AGENT.md` 后，若使用进程内 Agent 缓存，需**新会话**（新 `session_id`/`project_id`）或**重启**；`SKILL.md` 正文在渐进披露下通常下次读取即更新。

## Streaming SSE envelope (schemaVersion 1)

Each JSON object on the `POST /analyze` stream includes:

| Field | Meaning |
|--------|---------|
| `schemaVersion` | Protocol version; currently `1`. |
| `seq` | Monotonic integer per HTTP connection (ordering). |
| `scope` | `main` or `subagent` (events merged from `task()` sub-agents). |
| `type` | Event kind (`reasoning`, `tool_call`, `tool_result`, `conclusion`, …). |

`adapt_subagent_astream_to_skill_events` accepts optional `sse_seq_counter` (the same mutable `list[int]` `adapt_astream_to_sse` uses internally) so task-tool subruns can share monotonic `seq` and `scope: subagent` with the main response.

The web app persists non-internal events on the assistant message as `messages.timeline` (JSONB). Apply the repo migration `supabase/migrations/20260324120000_messages_timeline.sql` (or equivalent `ALTER`) before using this column. See `docs/DEV_DB_RESET.md` for dev reset options.

## API 接口

### 健康检查

```bash
curl http://localhost:8000/health
```

### 安全分析

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": "分析以下安全日志: [2024-01-15 10:23:45] Failed login attempt from 192.168.1.100"
  }'
```

### 模型列表（供前端选择器）

```bash
curl http://localhost:8000/api/models
```

## 与前端集成

与 monorepo 主前端对齐的配置方式：

1. **`src/config/endpoints.ts`**：`VITE_PYTHON_BACKEND_URL`（云端默认）、`VITE_LOCAL_API_URL`（本地默认 `http://127.0.0.1:8000`）。
2. **`VITE_API_MODE`**：`local` 时使用 `localApiUrl`，否则使用 `pythonBackendUrl`（见 `src/lib/config.ts` 中 `analysisEndpoints.stream` → `{base}/analyze`）。
3. 认证：请求头可带 `Authorization: Bearer <access_token>`（与 `app/api/auth.py` 签发的 JWT 一致时，`/analyze` 会解析可选用户上下文）。

直接调用示例（开发）：

```typescript
const response = await fetch('http://127.0.0.1:8000/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: '分析这个日志...',
    stream: true,
    session_id: '...',
    project_id: '...',
    request_id: '...',
  }),
});
// stream: true 时响应为 text/event-stream，需按 SSE 解析
```

若生产环境需要将 Python 服务藏在网关之后，可在 **任意反向代理 / API 网关** 后暴露同一路径（例如 `/analyze`），无需本仓库提供 Edge Function 源码。

## 部署选项

### Railway

```bash
railway login
railway init
railway up
```

### Fly.io

```bash
fly auth login
fly launch
fly deploy
```

### AWS Lambda (通过 Mangum)

参考 [Mangum 文档](https://mangum.io/) 配置 Lambda 适配器。

## 扩展开发

### 添加新工具

```python
# app/tools/my_tools.py
from langchain_core.tools import tool

@tool("my_tool")
def my_tool(param: str) -> dict:
    """工具描述"""
    # 实现逻辑
    return {"result": "..."}
```

### 自定义 Agent

```python
# app/agents/custom_agent.py
from langgraph.graph import StateGraph

def create_custom_agent():
    graph = StateGraph(YourState)
    # 配置节点和边
    return graph.compile()
```

## 许可证

MIT License
