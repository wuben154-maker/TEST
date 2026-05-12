# 增补需求分析：文件去重和关联任务处理

## 增补需求

### 需求 1：相同文件去重
**要求**：如果两个文件是一样的（内容相同），只生成一个任务

### 需求 2：关联任务处理
**要求**：如果多个文件之间有关联性，或者文件和描述需求文字产生的任务有关联性，应该如何处理？
- **选项 A**：合并成一个任务
- **选项 B**：独立任务执行后，再有一个合并结果的任务

---

## 当前实现分析

### ✅ 需求 1：文件去重 - 基础设施已具备

**当前状态**：✅ **基础设施已具备，但未实现去重逻辑**

**已有功能**：
- `FileInfo` 类包含 `hash_md5` 和 `hash_sha256` 字段
- `FileParser` 会自动计算文件哈希（`compute_hashes()`）
- 文件哈希在文件解析时已计算

**缺失功能**：
- 意图理解层没有检测重复文件
- 没有基于哈希值去重的逻辑

**代码位置**：
- `file_parser.py:29-38` - `FileInfo.compute_hashes()`
- `intent_understanding.py:169-176` - `understand()` 方法处理文件列表

---

### ⚠️ 需求 2：关联任务处理 - 部分支持

**当前状态**：⚠️ **部分支持，但不够明确**

**已有功能**：
1. **任务依赖**：
   - `TaskDescription.context_needed` - 表示任务需要其他任务的上下文
   - `PlannedTask.depends_on` - 表示任务依赖关系
   - `TaskPlan.get_ready_tasks()` - 支持依赖管理

2. **关联任务识别**：
   - 意图理解可以识别关联任务（通过 `context_needed`）
   - 任务规划可以设置依赖关系（通过 `depends_on`）

**缺失功能**：
- 没有明确的"合并结果任务"机制
- 没有自动识别文件关联性的逻辑
- 没有自动生成合并任务的逻辑

**代码位置**：
- `intent_models.py:142` - `TaskDescription.context_needed`
- `task_planner.py:86` - `PlannedTask.depends_on`
- `task_planner.py:146-155` - `TaskPlan.get_ready_tasks()`

---

## 方案设计

### 方案 1：文件去重

#### 实现位置
在 `IntentUnderstandingMiddleware.understand()` 中，文件解析后、意图理解前进行去重。

#### 实现逻辑
```python
async def understand(self, text: str, files: list[dict], ...):
    # 1. 解析所有文件
    file_infos = []
    for file in files:
        file_info = self.file_parser.parse_file(...)
        file_info.compute_hashes()  # 计算哈希
        file_infos.append(file_info)
    
    # 2. 基于哈希值去重
    seen_hashes = {}
    unique_files = []
    duplicate_map = {}  # 记录重复关系
    
    for file_info in file_infos:
        file_hash = file_info.hash_sha256  # 使用 SHA256
        if file_hash in seen_hashes:
            # 发现重复文件
            original_file = seen_hashes[file_hash]
            duplicate_map[file_info.filename] = original_file.filename
            logger.info(
                "Duplicate file detected",
                duplicate=file_info.filename,
                original=original_file.filename,
                hash=file_hash[:16] + "..."
            )
        else:
            seen_hashes[file_hash] = file_info
            unique_files.append(file_info)
    
    # 3. 使用去重后的文件列表进行意图理解
    # ... 后续处理
```

#### 处理重复文件的策略
1. **只保留第一个文件**：后续重复文件被忽略
2. **记录重复关系**：在 `IntentResult.metadata` 中记录重复文件映射
3. **用户提示**：在 `summary` 或 `reasoning` 中提示用户有重复文件

---

### 方案 2：关联任务处理

#### 方案对比

##### 选项 A：合并成一个任务
**优点**：
- 简单直接
- 减少任务数量
- 一次性处理所有关联内容

**缺点**：
- 可能违反"一个文件一个任务"的原则
- 如果关联文件很多，任务会变得复杂
- 不利于并行执行

**适用场景**：
- 关联文件数量少（2-3个）
- 关联性非常强（如：邮件+附件）
- 需要综合分析

##### 选项 B：独立任务 + 合并结果任务（推荐）
**优点**：
- 保持"一个文件一个任务"的原则
- 支持并行执行独立任务
- 合并任务可以综合所有结果
- 更灵活，可以单独查看每个任务的结果

**缺点**：
- 任务数量增加
- 需要额外的合并逻辑

**适用场景**：
- 关联文件数量多（>3个）
- 需要分别分析每个文件
- 需要综合报告

---

## 推荐方案

### 推荐：选项 B（独立任务 + 合并结果任务）

**理由**：
1. ✅ 保持"一个文件一个任务"的原则
2. ✅ 支持并行执行，提高效率
3. ✅ 更灵活，可以单独查看每个任务的结果
4. ✅ 合并任务可以生成综合报告

### 实现设计

#### 1. 关联任务识别

**在意图理解阶段**：
- LLM 识别文件之间的关联性
- 识别文件和文字描述之间的关联性
- 在 `TaskDescription.context_needed` 中标记关联关系

**示例**：
```json
{
  "tasks": [
    {
      "description": "Analyze email file email1.eml",
      "expertise_needed": "security",
      "skill_hint": "email-security",
      "key_entities": ["email1.eml"],
      "context_needed": []  // 独立任务
    },
    {
      "description": "Analyze email file email2.eml",
      "expertise_needed": "security",
      "skill_hint": "email-security",
      "key_entities": ["email2.eml"],
      "context_needed": ["email1_analysis"]  // 关联任务
    },
    {
      "description": "Merge analysis results from email1.eml and email2.eml",
      "expertise_needed": "security",
      "skill_hint": "general-security",
      "key_entities": ["email1.eml", "email2.eml"],
      "context_needed": ["email1_analysis", "email2_analysis"]  // 合并任务
    }
  ]
}
```

#### 2. 合并任务生成

**在任务规划阶段**：
- 检测有关联关系的任务
- 自动生成合并任务（如果需要）
- 设置依赖关系（`depends_on`）

**实现逻辑**：
```python
def _create_merge_task_if_needed(
    self,
    tasks: list[PlannedTask],
    intent_result: IntentResult
) -> Optional[PlannedTask]:
    """Create a merge task if there are related tasks."""
    
    # 检测是否有多个关联任务
    related_tasks = [t for t in tasks if t.context_needed]
    if len(related_tasks) < 2:
        return None  # 不需要合并任务
    
    # 检查是否已有合并任务
    merge_tasks = [
        t for t in tasks 
        if "merge" in t.description.lower() or "合并" in t.description
    ]
    if merge_tasks:
        return None  # 已有合并任务
    
    # 生成合并任务
    merge_task = PlannedTask(
        title="Merge Analysis Results",
        description=f"Merge analysis results from {len(related_tasks)} related tasks",
        task_type=TaskType.SECURITY,
        skill_name="general-security",
        depends_on=[t.id for t in related_tasks],  # 依赖所有关联任务
        priority=len(related_tasks) + 1,  # 最后执行
    )
    
    return merge_task
```

#### 3. 合并任务执行

**在任务执行阶段**：
- 等待所有关联任务完成
- 读取所有任务的结果
- 生成综合报告

**实现位置**：
- `TaskExecutor` 或 `DeepAgent` 中实现合并逻辑
- 或者创建专门的 `MergeTaskExecutor`

---

## 实现计划

### Phase 1：文件去重（P0）

**任务**：
1. 在 `IntentUnderstandingMiddleware.understand()` 中添加文件去重逻辑
2. 基于 `hash_sha256` 检测重复文件
3. 记录重复文件映射到 `IntentResult.metadata`
4. 在用户提示中告知重复文件

**代码位置**：
- `intent_understanding.py:169-250` - `understand()` 方法

---

### Phase 2：关联任务识别（P1）

**任务**：
1. 更新 `MASTER_AGENT.md` 提示词，指导 LLM 识别关联任务
2. 在 `TaskDescription` 中使用 `context_needed` 标记关联关系
3. 在任务规划中处理关联关系

**代码位置**：
- `MASTER_AGENT.md` - 添加关联任务识别指南
- `intent_classifier.py` - 处理 `context_needed`
- `task_planner.py` - 处理关联任务

---

### Phase 3：合并任务生成（P1）

**任务**：
1. 在 `TaskPlanner` 中添加合并任务生成逻辑
2. 检测关联任务，自动生成合并任务
3. 设置依赖关系

**代码位置**：
- `task_planner.py` - 添加 `_create_merge_task_if_needed()` 方法

---

### Phase 4：合并任务执行（P2）

**任务**：
1. 实现合并任务执行逻辑
2. 读取所有关联任务的结果
3. 生成综合报告

**代码位置**：
- `task_executor.py` 或 `deep_agent.py` - 实现合并逻辑

---

## 总结

### 当前状态
- ✅ 文件去重：基础设施已具备（哈希计算），但未实现去重逻辑
- ⚠️ 关联任务：部分支持（依赖关系），但缺少合并任务机制

### 推荐方案
1. **文件去重**：基于 `hash_sha256` 在意图理解前进行去重
2. **关联任务**：选项 B（独立任务 + 合并结果任务）

### 实施优先级
- **P0**：文件去重（简单，立即实施）
- **P1**：关联任务识别和合并任务生成（重要，近期实施）
- **P2**：合并任务执行（优化，长期实施）
