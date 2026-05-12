# Local PostgreSQL 数据库配置指南

使用本地 PostgreSQL 替代 Supabase，前后端均连接本地数据库。

## 前置条件

- PostgreSQL 12+ 已安装并运行
- `psql`、`createdb` 在 PATH 中

## 快速开始

### 1. 创建数据库并初始化表

**Windows (PowerShell):**
```powershell
cd python-agent-service
.\scripts\setup_local_db.ps1
```

**Linux/macOS:**
```bash
cd python-agent-service
chmod +x scripts/setup_local_db.sh
./scripts/setup_local_db.sh
```

**或手动执行:**
```bash
createdb -U postgres secmanus
psql -U postgres -d secmanus -f python-agent-service/scripts/db/init_local_db.sql
```

### 2. 配置后端 .env

`python-agent-service/.env` 中设置：

```
DATABASE_MODE=local
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=postgres
```

按需修改 `LOCAL_DB_*` 以匹配你的 PostgreSQL 配置。

### 3. 配置前端 .env

根目录 `.env` 中设置（本地模式）：

```
VITE_API_MODE=local
VITE_LOCAL_API_URL=http://localhost:8000
```

### 4. 启动服务

**后端:**
```bash
cd python-agent-service
python -m uvicorn app.main:app --reload --port 8000
```

**前端:**
```bash
npm run dev
```

### 5. 注册用户

打开前端 (http://localhost:5173)，在登录页点击「注册」，创建第一个账号。本地模式无需 Supabase。

## 表结构说明

| 表名 | 用途 |
|------|------|
| profiles | 用户账号 (email + password_hash) |
| projects | 对话/项目 |
| messages | 消息与分析结果 |
| shared_reports | 分享报告 |
| langgraph_checkpoints | Agent 会话状态 |
| session_parameters | 会话参数与长期记忆 |
| parameter_callbacks | 参数回调队列 |

## 历史库升级：`messages.timeline`

若早期本地库在增加「分析时间线」列之前就已初始化，加载项目时可能出现 **`column "timeline" does not exist`**（前端提示「加载历史项目失败」）。执行一次：

```bash
psql -U postgres -d secmanus -h localhost -p <端口> -f python-agent-service/scripts/db/patch_messages_timeline.sql
```

或重新跑 `scripts/db/init_local_db.sql` 末尾的兼容块（`DO $$ ...` 会为已存在的 `messages` 表补列）。新环境直接使用当前版 `scripts/db/init_local_db.sql` 建库即可，已包含 `timeline`。

## 切换回 Supabase

- 后端: `DATABASE_MODE=supabase` 并配置 `SUPABASE_*`
- 前端: `VITE_API_MODE=cloud` 并配置 `VITE_SUPABASE_*`
