# 置信度设置分析

## 当前置信度设置

### 1. 置信度字段

**位置**：`IntentResult.confidence`

```python
@dataclass
class IntentResult:
    confidence: float = 0.8  # 默认值 0.8
```

**来源**：由 LLM 在意图分类时返回（0.0-1.0）

**要求**：在分类提示词中要求 LLM 返回置信度值

```python
"confidence": {"type": "number", "minimum": 0, "maximum": 1}
```

### 2. 置信度阈值

**当前设置**：

```python
# 默认阈值
confidence_threshold = 0.5  # 硬编码默认值

# 尝试从配置读取
try:
    from app.config.intent_config import get_config
    config = get_config()
    confidence_threshold = config.confidence_threshold * 0.7  # 澄清阈值是分类阈值的 70%
except Exception:
    pass
```

**使用场景**：
- **澄清阈值**：`confidence_threshold * 0.7`（如果配置存在）
- **低置信度检查**：`result.confidence < confidence_threshold`

### 3. 低置信度处理

**触发条件**：
```python
if result.confidence < confidence_threshold and not result.enrichment_applied:
    # 请求澄清
    result.task_category = TaskCategory.PARAMETER_NEEDED
```

**处理逻辑**：
1. 如果置信度低于阈值且未应用 enrichment
2. 生成澄清问题
3. 转换为 `PARAMETER_NEEDED` 类别
4. 要求用户提供更多信息

**额外检查**：
```python
if result.confidence < 0.5:
    questions.append(templates["low_confidence"])
```

## 当前设置的局限性

### ❌ 缺失的功能

1. **配置机制不完整**
   - 配置读取有 try-except，但配置可能不存在
   - 没有默认配置值
   - 无法动态调整阈值

2. **置信度计算逻辑缺失**
   - 完全依赖 LLM 返回的置信度
   - 没有验证或校准机制
   - 没有基于上下文的置信度调整

3. **执行策略未关联**
   - 置信度不影响路由决策
   - 置信度不影响执行方式
   - 高置信度和低置信度使用相同的执行路径

4. **置信度分级缺失**
   - 只有"低置信度"和"非低置信度"
   - 没有高/中/低的分级
   - 没有针对不同置信度级别的策略

5. **置信度与路由的关联缺失**
   - SmartRouter 不接收置信度信息
   - 路由决策不考虑置信度
   - 无法根据置信度选择不同的执行策略

## 改进方案

### 方案 1：置信度分级和策略

```python
class ConfidenceLevel(str, Enum):
    """Confidence level classification."""
    VERY_HIGH = "very_high"  # >= 0.9
    HIGH = "high"           # 0.7 - 0.9
    MEDIUM = "medium"        # 0.5 - 0.7
    LOW = "low"             # 0.3 - 0.5
    VERY_LOW = "very_low"   # < 0.3

@dataclass
class IntentResult:
    confidence: float = 0.8
    confidence_level: ConfidenceLevel = field(init=False)
    
    def __post_init__(self):
        """Calculate confidence level."""
        if self.confidence >= 0.9:
            self.confidence_level = ConfidenceLevel.VERY_HIGH
        elif self.confidence >= 0.7:
            self.confidence_level = ConfidenceLevel.HIGH
        elif self.confidence >= 0.5:
            self.confidence_level = ConfidenceLevel.MEDIUM
        elif self.confidence >= 0.3:
            self.confidence_level = ConfidenceLevel.LOW
        else:
            self.confidence_level = ConfidenceLevel.VERY_LOW
```

### 方案 2：置信度配置

```python
@dataclass
class ConfidenceConfig:
    """Confidence threshold configuration."""
    # Classification thresholds
    very_high_threshold: float = 0.9
    high_threshold: float = 0.7
    medium_threshold: float = 0.5
    low_threshold: float = 0.3
    
    # Action thresholds
    clarification_threshold: float = 0.5  # Request clarification below this
    enrichment_threshold: float = 0.6     # Apply enrichment below this
    direct_execution_threshold: float = 0.8  # Direct execution above this
    
    # Routing thresholds
    skill_routing_threshold: float = 0.7   # Use skill routing above this
    research_routing_threshold: float = 0.6  # Use research routing above this
```

### 方案 3：置信度感知的路由

```python
class SmartRouter:
    def route_intent(
        self,
        intent_description: str,
        tasks: list[TaskDescription],
        confidence: float,  # 添加置信度参数
        confidence_level: ConfidenceLevel,
    ) -> ExecutionPlan:
        """Route with confidence awareness."""
        
        plan = ExecutionPlan()
        
        # 根据置信度调整路由策略
        if confidence_level == ConfidenceLevel.VERY_HIGH:
            # 高置信度：直接执行，使用最佳匹配的 skill
            strategy = "direct_best_match"
        elif confidence_level == ConfidenceLevel.HIGH:
            # 高置信度：正常路由
            strategy = "normal"
        elif confidence_level == ConfidenceLevel.MEDIUM:
            # 中等置信度：使用通用 skill，或请求确认
            strategy = "conservative"
        elif confidence_level in [ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW]:
            # 低置信度：请求澄清或使用最保守的策略
            strategy = "clarification_or_fallback"
        
        # 根据策略路由
        for task in tasks:
            if strategy == "clarification_or_fallback":
                # 低置信度：请求澄清
                plan.add_task(ExecutionTask(
                    type="clarification",
                    task_description=task.description,
                ))
            elif strategy == "conservative":
                # 中等置信度：使用通用 skill
                plan.add_task(ExecutionTask(
                    type="skill",
                    skill_name="general-security",
                    task_description=task.description,
                ))
            else:
                # 正常路由
                skill = self._match_skill(task)
                plan.add_task(ExecutionTask(
                    type="skill",
                    skill_name=skill.name if skill else "general-security",
                    task_description=task.description,
                ))
        
        return plan
```

### 方案 4：置信度验证和校准

```python
class ConfidenceValidator:
    """Validate and calibrate confidence scores."""
    
    def validate(
        self,
        confidence: float,
        context: dict,
    ) -> tuple[float, str]:
        """Validate confidence score based on context.
        
        Returns:
            (adjusted_confidence, reason)
        """
        adjusted = confidence
        reasons = []
        
        # 检查上下文完整性
        if not context.get("key_entities"):
            adjusted *= 0.9  # 降低 10%
            reasons.append("missing_entities")
        
        # 检查输入长度
        input_length = len(context.get("text", ""))
        if input_length < 10:
            adjusted *= 0.8  # 降低 20%
            reasons.append("input_too_short")
        
        # 检查历史上下文
        if not context.get("has_history"):
            adjusted *= 0.95  # 降低 5%
            reasons.append("no_history")
        
        return adjusted, "; ".join(reasons)
```

### 方案 5：完整的置信度配置

```python
# app/config/intent_config.py
@dataclass
class IntentConfig:
    """Intent understanding configuration."""
    
    # Confidence thresholds
    confidence_thresholds: ConfidenceConfig = field(default_factory=ConfidenceConfig)
    
    # Behavior flags
    enable_confidence_validation: bool = True
    enable_confidence_based_routing: bool = True
    enable_confidence_calibration: bool = True
    
    # Default values
    default_confidence: float = 0.8
    min_confidence_for_execution: float = 0.3
    max_confidence_for_clarification: float = 0.5
```

## 实施建议

### 阶段 1：基础改进（1-2 天）

1. ✅ 添加置信度分级枚举
2. ✅ 完善配置机制
3. ✅ 添加置信度验证

### 阶段 2：路由集成（2-3 天）

1. ✅ 将置信度传递给 SmartRouter
2. ✅ 实现置信度感知的路由策略
3. ✅ 测试不同置信度级别的行为

### 阶段 3：高级功能（3-5 天）

1. ✅ 置信度校准机制
2. ✅ 基于上下文的置信度调整
3. ✅ 置信度监控和日志

## 总结

**当前状态**：
- ✅ 有基本的置信度字段和阈值检查
- ❌ 配置机制不完整
- ❌ 执行策略未关联置信度
- ❌ 路由决策不考虑置信度

**改进方向**：
1. 置信度分级（高/中/低）
2. 置信度配置（可配置阈值）
3. 置信度感知的路由（根据置信度调整策略）
4. 置信度验证和校准（提高准确性）
