# 意图理解硬编码功能检查报告

## 检查结果

经过全面检查，发现以下硬编码内容：

---

## ⚠️ 发现的硬编码内容

### 1. 语言指令硬编码 ⚠️ **需要移除**

**位置**：`python-agent-service/app/middleware/intent_classifier.py` 第307-322行

**硬编码内容**：
```python
lang_instruction_map = {
    "en": "IMPORTANT: You MUST respond in English. All summaries, analysis goals, and approaches must be written in English.",
    "zh": "重要：你必须使用中文进行回复。所有摘要、分析目标和方法都必须使用中文撰写。",
    "ja": "重要：必ず日本語で回答してください。すべての要約、分析目標、アプローチは日本語で記述する必要があります。",
    "ko": "중요: 반드시 한국어로 응답해야 합니다. 모든 요약, 분석 목표 및 접근 방식은 한국어로 작성되어야 합니다.",
}
```

**问题**：
- 语言指令写死在代码中
- 虽然有尝试从 `MASTER_AGENT.md` 加载，但实际使用的是硬编码的fallback

**建议**：
- 应该从 `MASTER_AGENT.md` 的 `language-instructions` 部分加载
- 如果加载失败，应该从 `LABELS.md` 加载，而不是硬编码

---

### 2. Fallback错误消息硬编码 ⚠️ **需要移除**

**位置**：`python-agent-service/app/middleware/intent_classifier.py` 第840-850行

**硬编码内容**：
```python
return {
    "task_category": "unknown",
    "input_type": "text",
    "confidence": 0.2,
    "intent_description": "Unable to understand request due to service error",
    "tasks": [],
    "summary": "Service temporarily unavailable. Please try again.",
    # ...
}
```

**问题**：
- 错误消息写死在代码中
- 不支持多语言

**建议**：
- 应该从 `LABELS.md` 加载错误消息
- 支持多语言

---

### 3. 异常处理错误消息硬编码 ⚠️ **需要移除**

**位置**：`python-agent-service/app/middleware/intent_understanding.py` 第465-470行和第550-555行

**硬编码内容**：
```python
fallback_summary = {
    "en": "I couldn't understand your request. Please add more details and try again.",
    "zh": "我无法理解你的请求，请补充更具体的需求后再试。",
    "ja": "ご要望を理解できませんでした。もう少し詳しく入力して再試行してください。",
    "ko": "요청을 이해하지 못했습니다. 조금 더 자세히 입력한 후 다시 시도해 주세요.",
}.get(language, "I couldn't understand your request. Please add more details and try again.")
```

**问题**：
- 多语言消息写死在代码中
- 应该从 `LABELS.md` 加载

**建议**：
- 使用 `get_intent_label()` 从 `LABELS.md` 加载
- 保持多语言支持的一致性

---

### 4. 系统提示词硬编码 ⚠️ **可接受（但建议改进）**

**位置**：`python-agent-service/app/middleware/intent_understanding.py` 第117-125行

**硬编码内容**：
```python
SYSTEM_PROMPT = """## Intent Understanding

The system automatically analyzes user intent:
- Detects input type (text, email, log, code, files)
- Retrieves relevant context from memory
- Classifies task type (security/research/unknown)
- Requests parameters when needed

Use `understand_intent` to manually trigger intent analysis."""
```

**问题**：
- 系统提示词写死在代码中
- 但这是一个简短的描述性提示词，不是核心功能逻辑

**建议**：
- 可以保留（因为这是工具描述，不是核心意图理解逻辑）
- 或者移到配置文件

---

### 5. 工具Schema硬编码 ⚠️ **可接受（技术定义）**

**位置**：`python-agent-service/app/middleware/intent_classifier.py` 第104-233行

**硬编码内容**：
- `CLASSIFICATION_TOOL` - 工具schema定义
- `PHASE1_TOOL` - Phase 1工具schema定义

**问题**：
- Schema定义写死在代码中
- 但这是技术定义，不是业务逻辑

**建议**：
- 可以保留（因为这是API schema定义，类似于接口定义）
- 如果需要调整，应该通过配置或代码修改

---

### 6. 置信度阈值硬编码 ⚠️ **可接受（有配置支持）**

**位置**：`python-agent-service/app/middleware/intent_classifier.py` 第454-456行

**硬编码内容**：
```python
- High (>= 0.7): Direct execution, no clarification needed
- Medium (0.4-0.7): Smart inference with LLM reasoning
- Low (< 0.4): Clarification needed with LLM reasoning
```

**问题**：
- 置信度阈值在注释中硬编码
- 但实际逻辑使用 `ConfidenceLevel` enum，阈值在 `IntentResult.__post_init__` 中定义

**建议**：
- 检查 `IntentResult` 中的阈值定义
- 如果阈值在代码中硬编码，应该移到配置文件

---

## ✅ 已正确实现（无硬编码）

### 1. 提示词加载 ✅
- 从 `MASTER_AGENT.md` 加载意图理解提示词
- 从 `MASTER_AGENT.md` 加载澄清推理提示词
- 使用 `load_prompt_section()` 动态加载

### 2. 多语言标签 ✅
- 从 `LABELS.md` 加载多语言消息
- 使用 `get_intent_label()` 获取标签
- 支持 en/zh/ja/ko 四种语言

### 3. 配置加载 ✅
- 从 `intent_config.yaml` 加载配置
- 使用 `get_config()` 动态加载
- 支持配置文件路径参数

---

## 需要修复的硬编码

### 优先级 P0（必须修复）

1. **语言指令硬编码**（第307-322行）
   - 应该从 `MASTER_AGENT.md` 或 `LABELS.md` 加载
   - 移除硬编码的 `lang_instruction_map`

2. **Fallback错误消息硬编码**（第840-850行）
   - 应该从 `LABELS.md` 加载
   - 支持多语言

3. **异常处理错误消息硬编码**（第465-470行和第550-555行）
   - 应该使用 `get_intent_label()` 从 `LABELS.md` 加载
   - 移除硬编码的多语言字典

---

## 建议修复方案

### 1. 修复语言指令硬编码

**当前代码**：
```python
lang_instruction_map = {
    "en": "IMPORTANT: You MUST respond in English...",
    "zh": "重要：你必须使用中文进行回复...",
    # ...
}
```

**修复方案**：
```python
# 从 MASTER_AGENT.md 加载语言指令
try:
    lang_instruction_section = load_prompt_section("master-agent", "language-instructions")
    # 解析语言指令（需要实现解析逻辑）
    lang_instruction = parse_language_instruction(lang_instruction_section, language)
except Exception:
    # Fallback: 从 LABELS.md 加载
    lang_instruction = get_intent_label("intent_language_instruction", language)
```

### 2. 修复Fallback错误消息硬编码

**当前代码**：
```python
"intent_description": "Unable to understand request due to service error",
"summary": "Service temporarily unavailable. Please try again.",
```

**修复方案**：
```python
from app.parsers.labels import get_intent_label

"intent_description": get_intent_label("intent_service_error", language),
"summary": get_intent_label("intent_service_unavailable", language),
```

### 3. 修复异常处理错误消息硬编码

**当前代码**：
```python
fallback_summary = {
    "en": "I couldn't understand your request...",
    "zh": "我无法理解你的请求...",
    # ...
}.get(language, "...")
```

**修复方案**：
```python
from app.parsers.labels import get_intent_label

fallback_summary = get_intent_label("intent_cannot_understand", language)
```

---

## 需要在 LABELS.md 中添加的标签

### 1. 语言指令标签
```markdown
## intent_language_instruction
- en: IMPORTANT: You MUST respond in English. All summaries, analysis goals, and approaches must be written in English.
- zh: 重要：你必须使用中文进行回复。所有摘要、分析目标和方法都必须使用中文撰写。
- ja: 重要：必ず日本語で回答してください。すべての要約、分析目標、アプローチは日本語で記述する必要があります。
- ko: 중요: 반드시 한국어로 응답해야 합니다. 모든 요약, 분석 목표 및 접근 방식은 한국어로 작성되어야 합니다.
```

### 2. 服务错误标签
```markdown
## intent_service_error
- en: Unable to understand request due to service error
- zh: 由于服务错误，无法理解请求
- ja: サービスエラーのため、リクエストを理解できませんでした
- ko: 서비스 오류로 인해 요청을 이해할 수 없습니다

## intent_service_unavailable
- en: Service temporarily unavailable. Please try again.
- zh: 服务暂时不可用，请稍后重试。
- ja: サービスが一時的に利用できません。後でもう一度お試しください。
- ko: 서비스가 일시적으로 사용할 수 없습니다. 나중에 다시 시도해 주세요.
```

---

## 总结

### 发现的硬编码
1. ⚠️ 语言指令硬编码（需要修复）
2. ⚠️ Fallback错误消息硬编码（需要修复）
3. ⚠️ 异常处理错误消息硬编码（需要修复）
4. ⚠️ 系统提示词硬编码（可接受，但建议改进）
5. ⚠️ 工具Schema硬编码（可接受，技术定义）
6. ⚠️ 置信度阈值硬编码（需要检查 `IntentResult` 中的定义）

### 已正确实现
1. ✅ 提示词加载（从 `MASTER_AGENT.md`）
2. ✅ 多语言标签加载（从 `LABELS.md`）
3. ✅ 配置加载（从 `intent_config.yaml`）

### 建议
- **立即修复**：语言指令、Fallback错误消息、异常处理错误消息
- **后续优化**：系统提示词可以移到配置文件
- **保持不变**：工具Schema定义（技术定义，合理）
