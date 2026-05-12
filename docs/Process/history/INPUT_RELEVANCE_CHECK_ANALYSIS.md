# 输入相关性检查实现分析

## 当前实现状态

### 问题
`_check_input_relevance()` 方法在 `classify()` 中被调用（第298行），但**方法定义缺失**，这会导致运行时错误。

### 当前实现方式

**是的，目前是写死在代码中的规则**：

1. **关键词列表硬编码在 `__init__` 方法中**（第256-275行）：
   ```python
   self._security_keywords = [
       "analyze", "analysis", "detect", "scan", "check", "investigate", "examine",
       "malware", "virus", "threat", "attack", "vulnerability", "exploit", "cve",
       "email", "phishing", "spam", "header", "smtp",
       # ... 更多关键词
   ]
   
   self._unrelated_keywords = [
       "weather", "temperature", "forecast", "rain", "sunny",
       "poem", "poetry", "story", "novel", "write a story",
       # ... 更多关键词
   ]
   ```

2. **基于规则的匹配逻辑**：
   - 简单的字符串包含检查（`keyword in text_lower`）
   - 没有语义理解
   - 没有配置化支持

---

## 问题分析

### 1. 硬编码的问题

**当前问题**：
- ❌ 关键词列表写死在代码中
- ❌ 无法通过配置文件调整
- ❌ 添加新关键词需要修改代码
- ❌ 不同环境无法使用不同的规则集

**影响**：
- 维护困难：每次调整都需要修改代码并重新部署
- 灵活性差：无法根据实际使用情况快速调整
- 扩展性差：无法支持多语言关键词（目前只支持英文）

### 2. 方法缺失的问题

**当前状态**：
- `_check_input_relevance()` 方法被调用但未定义
- 会导致 `AttributeError` 运行时错误

**需要实现**：
```python
def _check_input_relevance(self, text: str, language: str = "en") -> dict:
    """Check if input is relevant to system capabilities."""
    # 实现逻辑
```

---

## 改进建议

### 方案1：配置文件化（推荐）

**将关键词列表移到配置文件**：

1. **在 `intent_config.yaml` 中添加**：
   ```yaml
   # Input relevance check configuration
   relevance_check:
     enabled: true
     
     # Security-related keywords
     security_keywords:
       - analyze
       - analysis
       - detect
       - scan
       - malware
       - virus
       # ... 更多关键词
     
     # Unrelated keywords (out of scope)
     unrelated_keywords:
       - weather
       - temperature
       - poem
       - poetry
       # ... 更多关键词
     
     # Multi-language support
     multilingual_keywords:
       zh:
         security_keywords:
           - 分析
           - 检测
           - 恶意软件
         unrelated_keywords:
           - 天气
           - 诗歌
   ```

2. **在代码中加载配置**：
   ```python
   from app.config.intent_config import get_config
   
   config = get_config()
   self._security_keywords = config.relevance_check.security_keywords
   self._unrelated_keywords = config.relevance_check.unrelated_keywords
   ```

**优点**：
- ✅ 无需修改代码即可调整关键词
- ✅ 支持多语言关键词
- ✅ 不同环境可以使用不同配置
- ✅ 易于维护和扩展

### 方案2：混合方案（LLM + 规则）

**结合LLM和规则**：

1. **快速规则检查**（当前实现）：
   - 明显的无关输入（如"天气"）直接拒绝
   - 明显的安全相关输入（如"分析恶意软件"）直接通过

2. **LLM辅助判断**（边界情况）：
   - 如果规则检查无法确定，使用LLM进行判断
   - 只对边界情况使用LLM，减少延迟

**实现**：
```python
def _check_input_relevance(self, text: str, language: str = "en") -> dict:
    """Check if input is relevant using rules + LLM."""
    text_lower = text.lower()
    
    # 1. 快速规则检查：明显的无关输入
    for keyword in self._unrelated_keywords:
        if keyword in text_lower:
            return {
                "is_relevant": False,
                "reason": "unrelated_keyword",
                "message": self._get_relevance_message("intent_unrelated_input", language),
            }
    
    # 2. 快速规则检查：明显的安全相关输入
    has_security_keyword = any(kw in text_lower for kw in self._security_keywords)
    if has_security_keyword:
        return {"is_relevant": True, "reason": "security_keyword_found"}
    
    # 3. 边界情况：使用LLM判断（可选）
    if self._use_llm_for_relevance_check:
        return await self._check_relevance_with_llm(text, language)
    
    # 4. 默认：让LLM决定（不在这里拒绝）
    return {"is_relevant": True, "reason": "passed_to_llm"}
```

**优点**：
- ✅ 快速拒绝明显无关的输入
- ✅ 对边界情况使用LLM，更准确
- ✅ 平衡性能和准确性

### 方案3：完全LLM驱动（不推荐）

**完全依赖LLM判断**：
- 所有输入都通过LLM判断相关性
- 不使用规则

**缺点**：
- ❌ 增加延迟（每个请求都需要LLM调用）
- ❌ 增加成本
- ❌ 对明显无关的输入浪费资源

---

## 推荐实施方案

### 立即修复（P0）

1. **实现缺失的 `_check_input_relevance()` 方法**：
   ```python
   def _check_input_relevance(self, text: str, language: str = "en") -> dict:
       """Check if input is relevant to system capabilities."""
       if not text or len(text.strip()) < 3:
           return {
               "is_relevant": False,
               "reason": "input_too_short",
               "message": self._get_relevance_message("intent_cannot_understand", language),
           }
       
       text_lower = text.lower()
       
       # Check for unrelated keywords
       for keyword in self._unrelated_keywords:
           if keyword in text_lower:
               return {
                   "is_relevant": False,
                   "reason": "unrelated_keyword",
                   "message": self._get_relevance_message("intent_unrelated_input", language),
               }
       
       # If we have security keywords or reasonable length, assume relevant
       # Let LLM make the final decision
       return {
           "is_relevant": True,
           "reason": "passed_relevance_check",
           "message": "",
       }
   ```

2. **实现 `_get_relevance_message()` 方法**：
   ```python
   def _get_relevance_message(self, label_key: str, language: str) -> str:
       """Get relevance check message from labels."""
       try:
           from app.parsers.labels import get_intent_label
           return get_intent_label(label_key, language)
       except Exception:
           # Fallback messages
           fallback = {
               "intent_cannot_understand": {
                   "en": "Unable to understand your request. Please provide more details.",
                   "zh": "无法理解您的请求，请提供更多详细信息。",
               },
               "intent_unrelated_input": {
                   "en": "I couldn't find any security-related content in your request.",
                   "zh": "我在您的请求中找不到任何与安全相关的内容。",
               },
           }
           return fallback.get(label_key, {}).get(language, fallback.get(label_key, {}).get("en", ""))
   ```

### 后续优化（P1）

3. **将关键词列表移到配置文件**：
   - 在 `intent_config.yaml` 中添加 `relevance_check` 部分
   - 在 `intent_config.py` 中添加配置类
   - 在 `IntentClassifier.__init__` 中从配置加载关键词

4. **支持多语言关键词**：
   - 在配置文件中添加多语言关键词列表
   - 根据用户语言选择对应的关键词列表

---

## 总结

### 当前状态
- ✅ 关键词列表已定义（硬编码）
- ❌ `_check_input_relevance()` 方法缺失（需要实现）
- ❌ 关键词列表未配置化（需要改进）

### 建议
1. **立即**：实现缺失的方法，修复运行时错误
2. **近期**：将关键词列表移到配置文件，提升灵活性
3. **长期**：考虑混合方案（规则 + LLM），提升准确性
