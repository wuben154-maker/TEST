# 理解导向 + 专业子智能体架构实施计划

## 当前完成状态

### ✅ 已完成（阶段 1 部分）

1. **IntentResult 增强**
   - ✅ 添加了 `intent_description` 字段（自然语言描述）
   - ✅ 添加了 `tasks: list[TaskDescription]` 字段
   - ✅ 添加了 `TaskDescription` 数据类
   - ✅ 简化了置信度分级为 3 个级别（HIGH/MEDIUM/LOW）

2. **提示词改进**
   - ✅ 提示词移到 `MASTER_AGENT.md`，统一管理
   - ✅ 改为理解导向的提示词
   - ✅ 添加了 `clarification-reasoning` section，使用 LLM 推理生成澄清问题

3. **代码质量**
   - ✅ 移除了硬编码的提示词 fallback
   - ✅ 使用 LLM 推理生成澄清问题，而非模板

### ✅ P2 可选增强（已完成）

1. **澄清后再次意图理解**
   - ✅ 检测用户提交澄清参数后的重新提交
   - ✅ 提取原始输入和澄清参数
   - ✅ 将澄清参数整合到新的意图理解中
   - ✅ 标记为重新理解结果（`enrichment_applied=True`, `understanding_phases=2`）
   - ✅ 更新推理信息以反映澄清上下文

### ❌ 未完成

1. **SmartRouter 类** - 完全未实现
2. **ExecutionEngine 类** - 完全未实现
3. **主流程集成** - 仍基于 `task_category` 路由，未使用 `tasks` 列表
4. **移除强制分类** - `IntentResult` 仍保留 `task_category`，需要弱化或移除

---

## 详细实施计划

### 阶段 2：实现智能路由层（SmartRouter）

**优先级：高 | 预计时间：2-3 天**

#### 任务 2.1：创建 SmartRouter 类
- [ ] 创建 `python-agent-service/app/middleware/smart_router.py`
- [ ] 实现 `SmartRouter` 类，包含：
  - `__init__(skill_registry: SkillRegistry)`
  - `route_intent(intent_result: IntentResult) -> ExecutionPlan`
  - `_determine_execution_type(task_desc: TaskDescription) -> str`
  - `_match_skill(task_desc: TaskDescription) -> SkillSpec | None`

#### 任务 2.2：实现 ExecutionPlan 数据类
- [ ] 创建 `ExecutionPlan` 数据类
- [ ] 包含 `tasks: list[ExecutionTask]`
- [ ] `ExecutionTask` 包含：
  - `type: str` (skill/research/direct)
  - `skill_name: str | None`
  - `task_description: str`
  - `context: list[str]`

#### 任务 2.3：实现 Skill 匹配逻辑
- [ ] 优先使用 `task_desc.skill_hint`（如果提供）
- [ ] 基于任务描述查询匹配的 skill（使用 `registry.find_by_query()`）
- [ ] 基于关键实体匹配（文件扩展名等）
- [ ] 基于关键词匹配（email/malware/web 等）
- [ ] 默认回退到 `general-security` skill

#### 任务 2.4：确定执行方式
- [ ] `expertise_needed == "security"` → `"skill"`
- [ ] `expertise_needed == "research"` → `"research"`
- [ ] 其他 → `"direct"`

---

### 阶段 3：实现执行引擎（ExecutionEngine）

**优先级：高 | 预计时间：2-3 天**

#### 任务 3.1：创建 ExecutionEngine 类
- [ ] 创建 `python-agent-service/app/middleware/execution_engine.py`
- [ ] 实现 `ExecutionEngine` 类，包含：
  - `__init__(subagent_middleware, research_agent, direct_executor)`
  - `execute_plan(plan: ExecutionPlan) -> ExecutionResult`
  - `_execute_skill_task(task: ExecutionTask) -> dict`
  - `_execute_research_task(task: ExecutionTask) -> dict`
  - `_execute_direct_task(task: ExecutionTask) -> dict`

#### 任务 3.2：实现 ExecutionResult 数据类
- [ ] 创建 `ExecutionResult` 数据类
- [ ] 包含 `results: list[dict]`，每个结果包含：
  - `type: str` (skill/research/direct)
  - `skill: str | None`
  - `result: Any`
  - `success: bool`
  - `error: str | None`

#### 任务 3.3：集成现有组件
- [ ] 使用 `SubAgentMiddleware.run_skill()` 执行 skill 任务
- [ ] 使用 `DeepResearchAgent.research()` 执行研究任务
- [ ] 实现直接执行逻辑（通用任务处理）

#### 任务 3.4：支持并行执行
- [ ] 对于独立的多个任务，支持并行执行
- [ ] 对于有依赖关系的任务，按顺序执行

---

### 阶段 4：集成到主流程

**优先级：高 | 预计时间：2-3 天**

#### 任务 4.1：修改 DeepAgentWithIntent
- [ ] 在 `__init__()` 中初始化 `SmartRouter` 和 `ExecutionEngine`
- [ ] 修改 `analyze_stream()` 方法：
  - 保留意图理解步骤
  - **替换**基于 `task_category` 的路由逻辑
  - **改为**使用 `SmartRouter.route_intent()` 生成执行计划
  - **改为**使用 `ExecutionEngine.execute_plan()` 执行计划

#### 任务 4.2：弱化 task_category 依赖
- [ ] 检查所有使用 `task_category` 的地方
- [ ] 改为基于 `tasks` 列表和 `intent_description` 的逻辑
- [ ] 保留 `task_category` 字段用于向后兼容，但不再作为主要路由依据

#### 任务 4.3：更新事件流
- [ ] 更新 SSE 事件，包含执行计划信息
- [ ] 添加 `execution_plan` 事件类型
- [ ] 添加 `execution_result` 事件类型

#### 任务 4.4：处理边界情况
- [ ] 处理 `tasks` 为空的情况
- [ ] 处理多个任务的情况（并行/顺序）
- [ ] 处理任务执行失败的情况

---

### 阶段 5：优化和测试

**优先级：中 | 预计时间：1 周**

#### 任务 5.1：优化 Skill 匹配算法
- [ ] 改进关键词匹配逻辑
- [ ] 添加匹配置信度评分
- [ ] 优化匹配性能

#### 任务 5.2：处理边界情况
- [ ] 测试复杂混合任务（安全 + 研究）
- [ ] 测试边界情况（历史查询、结果合并等）
- [ ] 测试未知任务类型

#### 任务 5.3：性能优化
- [ ] 优化并行执行性能
- [ ] 优化 Skill 匹配性能
- [ ] 添加缓存机制（如适用）

#### 任务 5.4：文档更新
- [ ] 更新架构文档
- [ ] 更新 API 文档
- [ ] 添加使用示例

---

## 关键设计决策

### 1. task_category 的处理

**选项 A：完全移除**
- 优点：彻底理解导向，无分类限制
- 缺点：破坏向后兼容性，需要大量重构

**选项 B：弱化为辅助字段（推荐）**
- 优点：保持向后兼容，逐步迁移
- 缺点：代码中仍需要处理两种逻辑

**建议：采用选项 B**
- 保留 `task_category` 字段，但不再作为主要路由依据
- 路由逻辑完全基于 `tasks` 列表
- `task_category` 仅用于日志、统计等辅助用途

### 2. 执行计划的生成时机

**选项 A：在意图理解后立即生成**
- 优点：流程清晰，易于调试
- 缺点：无法利用任务规划的结果

**选项 B：在任务规划后生成（推荐）**
- 优点：可以利用任务规划的细化结果
- 缺点：流程稍复杂

**建议：采用选项 B**
- 意图理解 → 任务规划 → 智能路由 → 执行

### 3. 多任务执行策略

**选项 A：全部并行**
- 优点：性能最优
- 缺点：可能浪费资源，无法处理依赖

**选项 B：智能调度（推荐）**
- 优点：处理依赖关系，优化资源使用
- 缺点：实现复杂

**建议：采用选项 B**
- 分析任务依赖关系
- 独立任务并行执行
- 有依赖的任务顺序执行

---

## 实施优先级

### P0（必须完成）
1. ✅ 阶段 1：增强意图理解（已完成）
2. ⏳ 阶段 2：实现智能路由层（SmartRouter）
3. ⏳ 阶段 3：实现执行引擎（ExecutionEngine）
4. ⏳ 阶段 4：集成到主流程

### P1（重要但可延后）
5. ⏳ 阶段 5：优化和测试

---

## 预计时间线

- **阶段 2**：2-3 天
- **阶段 3**：2-3 天
- **阶段 4**：2-3 天
- **阶段 5**：1 周

**总计：约 2-3 周**

---

## 风险与挑战

1. **向后兼容性**
   - 风险：现有代码依赖 `task_category`
   - 缓解：保留字段，逐步迁移

2. **Skill 匹配准确性**
   - 风险：匹配错误导致执行失败
   - 缓解：实现回退机制，默认使用 `general-security`

3. **性能影响**
   - 风险：增加路由和执行引擎可能影响性能
   - 缓解：优化匹配算法，支持并行执行

4. **测试覆盖**
   - 风险：新架构需要大量测试
   - 缓解：分阶段实施，每个阶段充分测试

---

## P2 可选增强：澄清后再次意图理解

### 实现说明

**功能**：当用户提交澄清参数后，系统会检测到这是澄清后的重新提交，并进行再次意图理解。

**检测机制**：
- 检测前端构建的 `resumeInput` 格式（包含 "Continue analyzing" 或 "继续分析" 关键词）
- 提取原始输入和澄清参数
- 将澄清参数整合到新的意图理解中

**实现位置**：
- `python-agent-service/app/middleware/intent_understanding.py`
- `IntentUnderstandingMiddleware.understand()` 方法

**标记机制**：
- `enrichment_applied = True`：标记为增强理解
- `understanding_phases = 2`：标记为第二阶段理解
- `enrichment_summary`：记录澄清参数数量
- `reasoning`：更新推理信息以包含澄清上下文

**日志记录**：
- 记录检测到的澄清重新提交
- 记录重新理解的结果（置信度、类别等）

## 下一步行动

1. **立即开始**：阶段 2 - 实现 SmartRouter
2. **准备**：阶段 3 - 实现 ExecutionEngine
3. **规划**：阶段 4 - 集成到主流程
