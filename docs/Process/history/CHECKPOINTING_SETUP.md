# LangGraph Checkpointing 设置指南

## 概述

LangGraph Checkpointing 已集成到系统中，用于持久化对话状态和历史记录。

---

## 功能特性

✅ **对话历史持久化**：所有对话状态自动保存到数据库  
✅ **跨会话连续性**：服务器重启后可以恢复之前的对话  
✅ **状态恢复**：中断的任务可以从最后一个检查点恢复  
✅ **历史查询**：可以查询和访问之前的对话历史  

---

## 配置

### 环境变量

在 `.env` 文件中配置：

```bash
# 启用 checkpointing（默认：true）
ENABLE_CHECKPOINTING=true

# Checkpoint 后端：memory（开发）或 postgres（生产）
CHECKPOINT_BACKEND=postgres

# 数据库配置（用于 PostgreSQL checkpointing）
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=postgres
```

### 配置选项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enable_checkpointing` | `true` | 是否启用 checkpointing |
| `checkpoint_backend` | `postgres` | 存储后端：`memory` 或 `postgres` |
| `checkpoint_table_name` | `langgraph_checkpoints` | PostgreSQL 表名 |

---

## 后端选择

### 1. Memory Checkpointer（开发/测试）

**特点**：
- ✅ 无需数据库配置
- ✅ 快速启动
- ❌ 状态易失（重启后丢失）
- 📝 适用于开发和测试

**配置**：
```bash
CHECKPOINT_BACKEND=memory
```

### 2. PostgreSQL Checkpointer（生产环境）

**特点**：
- ✅ 持久化存储
- ✅ 支持查询历史状态
- ✅ 支持并发访问
- 📝 适用于生产环境

**配置**：
```bash
CHECKPOINT_BACKEND=postgres
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=postgres
```

**数据库表**：
- 表名：`langgraph_checkpoints`
- 自动创建：首次使用时自动创建（如果不存在）
- 手动创建：运行迁移脚本 `supabase/migrations/20250121000000_create_checkpoint_table.sql`

---

## 使用方式

### 自动使用

Checkpointing 已集成到 `DeepAgentWithIntent` 类中，**无需额外代码**。

每次执行图时，状态会自动保存：

```python
# 状态自动保存
config = {"configurable": {"thread_id": self.session_id}}
async for event in self.agent.astream(initial_state, config):
    # 每个节点执行后自动保存 checkpoint
    ...
```

### 查询历史状态

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(database_url)

# 获取所有检查点
checkpoints = await checkpointer.list(
    thread_id="session-123"
)

# 获取特定检查点
checkpoint = await checkpointer.get(
    thread_id="session-123",
    checkpoint_id="checkpoint-456"
)
```

### 从检查点恢复

```python
# 从最后一个检查点恢复
config = {
    "configurable": {
        "thread_id": "session-123",
        # checkpoint_id 可选，不指定则使用最新的
    }
}

# 继续执行
result = await agent.ainvoke(new_input, config)
```

---

## 数据库迁移

### 自动创建（推荐）

PostgresSaver 会在首次使用时自动创建表，无需手动操作。

### 手动创建

如果需要手动创建表，运行迁移脚本：

```bash
# PostgreSQL
psql -U postgres -d secmanus -f supabase/migrations/20250121000000_create_checkpoint_table.sql
```

或使用 Supabase：

```bash
# Supabase CLI
supabase migration up
```

---

## 表结构

```sql
CREATE TABLE langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    checkpoint JSONB NOT NULL,
    parent_checkpoint_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
```

**字段说明**：
- `thread_id`：会话ID（对应 `session_id`）
- `checkpoint_ns`：命名空间（用于多租户场景）
- `checkpoint_id`：检查点ID（唯一标识）
- `checkpoint`：序列化的状态（JSONB）
- `parent_checkpoint_id`：父检查点引用（构建状态历史链）
- `metadata`：元数据（时间戳、版本等）

---

## 性能考虑

### 存储开销

- **每个检查点大小**：取决于状态大小（messages、files等）
- **检查点数量**：每个节点执行后创建一个检查点
- **建议**：定期清理旧的检查点

### 清理策略

```sql
-- 删除 30 天前的检查点
DELETE FROM langgraph_checkpoints
WHERE created_at < NOW() - INTERVAL '30 days';

-- 只保留每个 thread_id 的最新 100 个检查点
WITH ranked AS (
    SELECT checkpoint_id,
           ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY created_at DESC) as rn
    FROM langgraph_checkpoints
)
DELETE FROM langgraph_checkpoints
WHERE checkpoint_id IN (
    SELECT checkpoint_id FROM ranked WHERE rn > 100
);
```

---

## 故障排除

### 问题 1：Checkpointing 未启用

**症状**：状态未保存，重启后丢失

**解决**：
1. 检查 `ENABLE_CHECKPOINTING=true`
2. 检查日志中的 checkpointing 初始化消息

### 问题 2：PostgreSQL 连接失败

**症状**：日志显示 "Failed to create PostgreSQL checkpointer"

**解决**：
1. 检查数据库连接配置
2. 确保数据库服务运行
3. 检查数据库用户权限
4. 系统会自动回退到 MemorySaver

### 问题 3：表不存在

**症状**：首次使用时出错

**解决**：
1. 运行迁移脚本手动创建表
2. 或让 PostgresSaver 自动创建（默认行为）

### 问题 4：依赖缺失

**症状**：`ImportError: No module named 'langgraph.checkpoint.postgres'`

**解决**：
```bash
pip install langgraph-checkpoint-postgres>=2.0.0
```

---

## 最佳实践

1. **生产环境使用 PostgreSQL**：确保状态持久化
2. **开发环境使用 Memory**：快速迭代，无需数据库
3. **定期清理旧检查点**：避免存储膨胀
4. **监控检查点数量**：避免过多检查点影响性能
5. **使用有意义的 thread_id**：便于管理和查询

---

## 示例场景

### 场景 1：跨会话对话

```
第1次对话：
- 用户："分析 malware.exe"
- AI："正在分析..."

服务器重启

第2次对话：
- 用户："之前的分析结果是什么？"
- AI："根据之前的分析，malware.exe..." ✅ 可以访问历史
```

### 场景 2：中断恢复

```
任务执行到 50% → 网络中断
恢复后 → 从最后一个检查点继续 ✅
```

### 场景 3：历史查询

```
用户："把前3次分析结果合并成一个报告"
→ AI 可以查询历史检查点，合并结果 ✅
```

---

## 参考资料

- [LangGraph Checkpointing 官方文档](https://langchain-ai.github.io/langgraph/how-tos/persistence/)
- [LangGraph Checkpointing 详解](./LANGGRAPH_CHECKPOINTING_GUIDE.md)
- 实现代码：`python-agent-service/app/agents/deep_agent.py`
