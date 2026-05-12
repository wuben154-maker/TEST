# Checkpointing 快速开始指南

## 1. 安装依赖

```bash
pip install langgraph-checkpoint-postgres>=2.0.0
```

## 2. 配置数据库

在 `.env` 文件中配置 PostgreSQL 连接：

```bash
# 启用 checkpointing
ENABLE_CHECKPOINTING=true

# 使用 PostgreSQL（生产）或 memory（开发）
CHECKPOINT_BACKEND=postgres

# PostgreSQL 配置
DATABASE_MODE=local
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=your_password
```

## 3. 验证配置

运行配置检查脚本：

```bash
python scripts/check_checkpointing_config.py
```

脚本会检查：
- ✅ 依赖是否安装
- ✅ 配置是否正确
- ✅ 数据库连接是否正常

## 4. 测试 Checkpointing

### 方法 1：使用测试脚本

```bash
python scripts/test_checkpointing.py
```

### 方法 2：手动测试

1. **启动应用**：
   ```bash
   python -m uvicorn app.main:app --reload
   ```

2. **执行一次分析**：
   - 发送请求到 `/analyze` 端点
   - 状态会自动保存到数据库

3. **重启服务器**：
   - 停止服务器
   - 重新启动

4. **验证状态恢复**：
   - 使用相同的 `session_id` 发送新请求
   - AI 应该能够访问之前的对话历史

## 5. 检查数据库

### 查看检查点表

```sql
-- 连接到数据库
psql -U postgres -d secmanus

-- 查看检查点
SELECT thread_id, checkpoint_id, created_at 
FROM langgraph_checkpoints 
ORDER BY created_at DESC 
LIMIT 10;

-- 查看特定会话的检查点
SELECT checkpoint_id, created_at 
FROM langgraph_checkpoints 
WHERE thread_id = 'your-session-id' 
ORDER BY created_at DESC;
```

### 检查表是否存在

```sql
-- 检查表是否存在
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'langgraph_checkpoints'
);
```

## 6. 故障排除

### 问题 1：依赖未安装

**错误**：`ModuleNotFoundError: No module named 'langgraph.checkpoint.postgres'`

**解决**：
```bash
pip install langgraph-checkpoint-postgres>=2.0.0
```

### 问题 2：数据库连接失败

**错误**：`Failed to create PostgreSQL checkpointer`

**检查**：
1. PostgreSQL 服务是否运行？
   ```bash
   # Windows
   services.msc  # 查找 PostgreSQL 服务
   
   # Linux/Mac
   sudo systemctl status postgresql
   ```

2. 连接信息是否正确？
   ```bash
   # 测试连接
   psql -h localhost -U postgres -d secmanus
   ```

3. 数据库是否存在？
   ```sql
   CREATE DATABASE secmanus;
   ```

### 问题 3：表不存在

**解决**：PostgresSaver 会自动创建表。如果失败，可以手动运行迁移：

```bash
psql -U postgres -d secmanus -f supabase/migrations/20250121000000_create_checkpoint_table.sql
```

### 问题 4：回退到 MemorySaver

**原因**：
- PostgreSQL 连接失败
- 依赖未安装
- 配置错误

**检查日志**：
- 查看应用启动日志
- 查找 "falling back to memory checkpointer" 消息

## 7. 生产环境建议

1. **使用 PostgreSQL**：确保状态持久化
2. **定期备份**：备份 `langgraph_checkpoints` 表
3. **监控存储**：监控检查点数量，避免存储膨胀
4. **清理策略**：定期清理旧的检查点

```sql
-- 清理 30 天前的检查点
DELETE FROM langgraph_checkpoints
WHERE created_at < NOW() - INTERVAL '30 days';
```

## 8. 验证 Checklist

- [ ] 依赖已安装
- [ ] 数据库配置正确
- [ ] 数据库连接正常
- [ ] 检查点表已创建
- [ ] 应用启动无错误
- [ ] 状态可以保存
- [ ] 状态可以恢复

## 9. 下一步

- 查看 [详细文档](./CHECKPOINTING_SETUP.md)
- 查看 [实现说明](./CHECKPOINTING_IMPLEMENTATION_SUMMARY.md)
- 查看 [Checkpointing 详解](./LANGGRAPH_CHECKPOINTING_GUIDE.md)
