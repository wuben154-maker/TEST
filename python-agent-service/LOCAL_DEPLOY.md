# SecManus Local Deployment Guide

本指南帮助你在本地部署和运行 Python DeepAgent 服务。

## 快速开始

### 1. 环境准备

```bash
cd python-agent-service

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，配置以下关键项：
```

**.env 配置说明：**

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `AGENT_MODE` | 代理模式 | `deepagent` 或 `simple` |
| `DATABASE_MODE` | 数据库模式 | `local` 或 `supabase` |
| `GOOGLE_API_KEY` | Google Gemini API Key | `your-key` |
| `LOCAL_DB_*` | 本地数据库配置 | 见下文 |

### 3. 本地数据库设置 (可选)

如果你选择 `DATABASE_MODE=local`：

```bash
# 安装 PostgreSQL
# macOS: brew install postgresql
# Ubuntu: sudo apt install postgresql

# 创建数据库
createdb secmanus

# 初始化表结构
psql -U postgres -d secmanus -f scripts/db/init_local_db.sql
```

**数据库配置：**
```env
DATABASE_MODE=local
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=postgres
```

### 4. 运行服务

```bash
# 开发模式 (自动重载)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 或使用默认配置
python -m app.main
```

服务将在 http://localhost:8000 启动。

### 5. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 预期输出：
# {"status":"healthy","version":"2.0.0","framework":"DeepAgents","agent_mode":"deepagent","database_mode":"local"}
```

## 配置切换

### 切换 Agent 模式

```env
# 完整 DeepAgent 模式 (需要 API Key)
AGENT_MODE=deepagent

# 简单模式 (无需 LangGraph，快速 IOC 提取)
AGENT_MODE=simple
```

### 切换数据库

```env
# 本地 PostgreSQL
DATABASE_MODE=local

# Supabase 云数据库
DATABASE_MODE=supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=xxx
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/analyze` | POST | 安全分析 |
| `/agents` | GET | 列出子代理 |
| `/tools` | GET | 列出可用工具 |

### 分析请求示例

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"message": "分析这个IP: 192.168.1.1", "stream": false}'
```

## 常见问题

### Q: 启动时报 API Key 错误？
A: 确保至少配置了一个 AI API Key：`GOOGLE_API_KEY`、`OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY`

### Q: 数据库连接失败？
A: 检查 PostgreSQL 是否运行，用户名密码是否正确：
```bash
psql -U postgres -d secmanus -c "SELECT 1"
```

### Q: 想快速测试不需要数据库？
A: 设置 `AGENT_MODE=simple`，简单模式不需要数据库连接。

## Docker 部署

### 快速启动 (推荐)

使用 `docker-compose.local.yml` 一键部署完整的本地环境：

```bash
cd python-agent-service

# 复制配置文件
cp .env.example .env

# 编辑 .env，添加 AI API Key (任选其一)
# GOOGLE_API_KEY=xxx 或其他 LLM API Key

# 启动所有服务
docker compose -f docker-compose.local.yml up -d

# 查看日志
docker compose -f docker-compose.local.yml logs -f
```

这将启动：
- **Deep Agent** (端口 8000) - 主 AI 代理服务
- **Firecrawl Simple** (端口 3002) - 本地网页抓取服务
- **PostgreSQL** (端口 5432) - 本地数据库
- **Redis** (端口 6379) - 任务队列

### 验证服务

```bash
# 检查 Deep Agent
curl http://localhost:8000/health

# 检查 Firecrawl
curl http://localhost:3002/health

# 测试网页抓取
curl -X POST http://localhost:3002/v1/scrape \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fc-local" \
  -d '{"url": "https://example.com", "formats": ["markdown"]}'
```

### 单独运行 Deep Agent

如果只需要 Agent 服务（使用云端 Firecrawl）：

```bash
# 构建镜像
docker build -t secmanus-agent .

# 运行容器
docker run -p 8000:8000 \
  -e AGENT_MODE=simple \
  -e GOOGLE_API_KEY=your-key \
  secmanus-agent
```

### 资源需求

| 服务 | 内存 | 说明 |
|------|------|------|
| Deep Agent | 512MB | Python 代理服务 |
| Firecrawl | 2GB | 包含 Chromium 浏览器 |
| PostgreSQL | 256MB | 数据库 |
| Redis | 128MB | 任务队列 |

**总计**：建议至少 4GB 可用内存

## 开发调试

```bash
# 启用详细日志
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=your-key

# 使用 reload 模式
python -m uvicorn app.main:app --reload --log-level debug
```

## 本地 Firecrawl 配置

项目集成了 [firecrawl-simple](https://github.com/devflowinc/firecrawl-simple)，完全免费，无需外部 API Key。

**环境变量配置：**
```env
# 本地 Firecrawl
FIRECRAWL_API_URL=http://localhost:3002/v1
FIRECRAWL_API_KEY=fc-local

# 或者使用云端 Firecrawl (需要 API Key)
# FIRECRAWL_API_URL=https://api.firecrawl.dev/v1
# FIRECRAWL_API_KEY=your-firecrawl-key
```

**Firecrawl Simple 功能：**
- ✅ 单页抓取 (Scrape)
- ✅ 网站地图 (Map)
- ✅ 网站爬取 (Crawl)
- ✅ Markdown 输出
- ✅ JavaScript 渲染 (Playwright)
- ❌ AI 功能 (已移除，但我们用 Lovable AI 替代)
