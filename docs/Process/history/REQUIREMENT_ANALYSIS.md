# 需求分析：意图理解到任务规划流程

## 用户需求

### 需求流程
1. **用户输入需求**：包括各种文件和文字
2. **意图理解**：将用户输入转换成专项任务（安全任务和Deep Research任务）
3. **一级任务**：
   - 一个邮件文件 → 一个任务
   - 细粒度分解由专项子智能体完成，**不在意图理解层分解**
4. **复合任务支持**：一次输入可以包含多个一级任务
   - 例如：上传多个不同的邮件文件 → 多个邮件分析任务

---

## 当前实现分析

### ✅ 需求 1：用户输入（文件和文字）

**当前状态**：✅ **完全支持**

**实现**：
- `IntentUnderstandingMiddleware.understand()` 接受 `text` 和 `files` 参数
- `FileParser` 支持多种文件类型（text, email, log, code, binary, image, document）
- 支持多文件上传

**代码位置**：
- `intent_understanding.py:169-176` - `understand` 方法签名

---

### ✅ 需求 2：意图理解转换成专项任务

**当前状态**：✅ **完全支持**

**实现**：
- 意图理解生成 `tasks` 列表（`TaskDescription` 对象）
- 每个任务有 `expertise_needed`（security/research/general）
- 安全任务有 `skill_hint`（如 "email-security", "binary-analysis"）
- 研究任务 `expertise_needed="research"`

**代码位置**：
- `intent_classifier.py:174-187` - `tasks` 字段定义
- `intent_models.py:132-151` - `TaskDescription` 数据模型

---

### ⚠️ 需求 3：一级任务（一个文件一个任务，不细粒度分解）

**当前状态**：⚠️ **部分支持，但可能存在问题**

#### 问题 1：意图理解可能进行细粒度分解

**当前提示词**（`MASTER_AGENT.md:25`）：
```
3. Break down into actionable task descriptions
```

**当前提示词**（`MASTER_AGENT.md:38`）：
```
2. **tasks**: Break down into actionable task descriptions (can be 1 or more)
```

**问题**：
- 提示词要求"分解成可执行的任务描述"
- 但没有明确说明"一个文件对应一个任务"
- LLM 可能会将一个邮件文件分解成多个任务（如：分析邮件头、分析附件、检查链接等）

**示例场景**：
```
用户输入：一个邮件文件
期望：1 个任务（邮件分析）
实际可能：LLM 分解成多个任务（邮件头分析、附件分析、链接检查等）
```

#### 问题 2：任务规划可能进一步分解

**当前实现**（`task_planner.py:281-284`）：
```
## Guidelines
1. **Simple requests** (complexity 1-3): Single task, 2-4 steps
2. **Medium requests** (complexity 4-6): 1-2 tasks, each with 3-5 steps
3. **Complex requests** (complexity 7-10): 2-4 tasks with dependencies
```

**问题**：
- 任务规划的提示词要求生成"步骤"（steps）
- 这可能导致进一步分解，不符合"一级任务"的要求

---

### ⚠️ 需求 4：支持复合多个一级任务

**当前状态**：⚠️ **部分支持，但不够明确**

#### 支持的情况

**提示词**（`MASTER_AGENT.md:144-170`）包含"Compound Task Examples"：
- 示例展示了如何处理多个任务
- 但示例主要是"安全+研究"的组合，不是"多个相同类型文件"

#### 可能的问题

**场景**：用户上传 3 个邮件文件

**期望**：
```
tasks: [
  {description: "Analyze email file 1", skill_hint: "email-security"},
  {description: "Analyze email file 2", skill_hint: "email-security"},
  {description: "Analyze email file 3", skill_hint: "email-security"},
]
```

**实际可能**：
```
tasks: [
  {description: "Analyze all email files", skill_hint: "email-security"},
]
```

**原因**：
- 提示词没有明确说明"一个文件对应一个任务"
- LLM 可能将多个相同类型的文件合并为一个任务

---

## 问题总结

### 🔴 P0 问题（严重）

1. **意图理解可能进行细粒度分解**
   - 提示词要求"分解成可执行的任务"，但没有明确"一个文件一个任务"
   - 可能导致单个文件被分解成多个任务

2. **任务规划可能进一步分解**
   - 任务规划的提示词要求生成"步骤"，可能不符合"一级任务"的要求

### 🟡 P1 问题（重要）

3. **多文件可能被合并**
   - 提示词没有明确说明"一个文件对应一个任务"
   - 多个相同类型文件可能被合并为一个任务

---

## 修复建议

### 修复 1：更新意图理解提示词

**位置**：`MASTER_AGENT.md` - `<intent-understanding>` 部分

**添加明确规则**：
```markdown
### Task Granularity Rules

**CRITICAL: One File = One Task (Level 1 Task)**

1. **Single File Input**:
   - One file → One task
   - Do NOT break down a single file into multiple tasks
   - Example: One email file → One task: "Analyze email file [filename]"
   - The sub-agent will handle detailed decomposition (header analysis, attachment analysis, etc.)

2. **Multiple Files Input**:
   - Multiple files → Multiple tasks (one task per file)
   - Example: 3 email files → 3 tasks:
     - Task 1: "Analyze email file [filename1]"
     - Task 2: "Analyze email file [filename2]"
     - Task 3: "Analyze email file [filename3]"
   - Do NOT combine multiple files into one task

3. **Mixed Input (Text + Files)**:
   - Text-only → One task based on text content
   - Text + Files → One task for text + One task per file
   - Example: "Analyze these files and check IP 1.2.3.4" + 2 files
     - Task 1: "Check IP 1.2.3.4 reputation"
     - Task 2: "Analyze file [filename1]"
     - Task 3: "Analyze file [filename2]"

4. **Task Description Format**:
   - For file-based tasks: "Analyze [file_type] file [filename]"
   - Keep descriptions at Level 1 (high-level), not detailed steps
   - Sub-agents will handle detailed decomposition

**What NOT to Do**:
- ❌ Do NOT break down a single file into multiple tasks (e.g., "Analyze header", "Analyze attachment", "Check links")
- ❌ Do NOT combine multiple files into one task (e.g., "Analyze all email files")
- ❌ Do NOT create detailed step-by-step tasks (that's the sub-agent's job)
```

---

### 修复 2：更新任务规划提示词

**位置**：`task_planner.py:215-291` - `PLANNING_PROMPT`

**修改**：
```python
PLANNING_PROMPT = """...
## Task Granularity Rules

**CRITICAL: Use tasks from intent understanding as-is (Level 1 Tasks)**

1. **If intent understanding has identified tasks**:
   - Use them directly, do NOT further decompose
   - Each task is a Level 1 task (e.g., "Analyze email file [filename]")
   - Do NOT create detailed steps - sub-agents will handle that

2. **If intent understanding has NOT identified tasks** (rare):
   - Create Level 1 tasks based on files and text
   - One file = One task
   - Multiple files = Multiple tasks

3. **Task Structure**:
   - Level 1 tasks are high-level (e.g., "Analyze email file")
   - Do NOT create detailed steps (header analysis, attachment analysis, etc.)
   - Sub-agents will decompose Level 1 tasks into detailed steps

**Response Format**:
- If intent understanding has tasks: Use them as-is
- If not: Create Level 1 tasks (one per file, one for text if applicable)
- Do NOT add detailed "steps" - that's handled by sub-agents
"""
```

---

### 修复 3：移除任务规划中的步骤生成

**位置**：`task_planner.py:270-276` - 步骤定义

**修改**：
```python
# 移除 steps 字段，因为子智能体会处理
"tasks": [
  {
    "id": "task-1",
    "title": "Concise task title",
    "description": "What this task will accomplish",
    "task_type": "security|research",
    "skill_name": "skill-name-or-null",
    "priority": 1,
    "depends_on": [],
    # 移除 steps 字段
  }
]
```

---

## 验证检查点

### 检查点 1：单个文件 → 单个任务
- [ ] 一个邮件文件 → 1 个任务
- [ ] 一个二进制文件 → 1 个任务
- [ ] 一个日志文件 → 1 个任务

### 检查点 2：多个文件 → 多个任务
- [ ] 3 个邮件文件 → 3 个任务
- [ ] 2 个邮件 + 1 个二进制 → 3 个任务
- [ ] 混合类型文件 → 每个文件一个任务

### 检查点 3：不进行细粒度分解
- [ ] 单个文件不会被分解成多个任务
- [ ] 任务描述是高级别的（"分析邮件文件"），不是详细的步骤

### 检查点 4：任务规划不进一步分解
- [ ] 任务规划直接使用意图理解的任务
- [ ] 不生成详细的步骤（由子智能体处理）

---

## 总结

### 当前状态
- ✅ 需求 1 和 2：完全支持
- ⚠️ 需求 3：部分支持，但可能进行细粒度分解
- ⚠️ 需求 4：部分支持，但多文件可能被合并

### 需要修复
1. **更新意图理解提示词** - 明确"一个文件一个任务"规则
2. **更新任务规划提示词** - 明确使用 Level 1 任务，不进一步分解
3. **移除步骤生成** - 任务规划不应生成详细步骤

### 预期效果
修复后，系统将：
- ✅ 一个文件 → 一个任务（Level 1）
- ✅ 多个文件 → 多个任务（每个文件一个）
- ✅ 不进行细粒度分解（由子智能体处理）
- ✅ 任务规划直接使用意图理解的任务
