# Intent Understanding 代码重构计划

## 当前状态

`python-agent-service/app/middleware/intent_understanding.py` 文件有 **2453行**，包含以下组件：

1. **数据模型**（第1-239行，约240行）
   - Enums: TaskCategory, InputType, SecuritySubType, ConfidenceLevel
   - DataClasses: UserInput, ParameterRequest, TaskDescription, IntentResult

2. **ContextRetriever**（第245-904行，约660行）
   - 上下文检索和管理功能
   - 短长期记忆管理
   - 模糊搜索、实体提取等

3. **ContextEnrichmentTool**（第910-1083行，约173行）
   - 上下文增强工具
   - web_search, scrape_url, read_file, analyze_file_structure

4. **IntentClassifier**（第1086-1993行，约907行）
   - 意图分类器
   - 两阶段理解逻辑
   - LLM调用、结果解析

5. **IntentUnderstandingMiddleware**（第2000-2453行，约453行）
   - 主中间件
   - 整合所有组件

## 拆分方案

### 1. `intent_models.py` - 数据模型
**内容**：
- 所有 Enums（TaskCategory, InputType, SecuritySubType, ConfidenceLevel）
- 所有 DataClasses（UserInput, ParameterRequest, TaskDescription, IntentResult）

**依赖**：
- `app.middleware.file_parser.FileInfo`
- 标准库（dataclasses, datetime, enum, uuid）

**导出**：
- 所有 Enums 和 DataClasses

---

### 2. `context_retriever.py` - 上下文检索器
**内容**：
- `ContextRetriever` 类及其所有方法

**依赖**：
- `app.middleware.intent_models`（用于类型注解）
- `app.parsers.labels`（用于多语言标签）
- `app.config.intent_config`（用于配置）

**导出**：
- `ContextRetriever`

---

### 3. `context_enrichment_tool.py` - 上下文增强工具
**内容**：
- `ContextEnrichmentTool` 类及其所有方法

**依赖**：
- `app.middleware.file_parser.FileParser, FileInfo`
- `app.tools.research_tools`（DuckDuckGoSearchProvider, UrlScraper）

**导出**：
- `ContextEnrichmentTool`

---

### 4. `intent_classifier.py` - 意图分类器
**内容**：
- `IntentClassifier` 类及其所有方法

**依赖**：
- `app.middleware.intent_models`（所有数据模型）
- `app.middleware.context_enrichment_tool.ContextEnrichmentTool`
- `app.middleware.file_parser.FileParser`
- `app.prompts.loader`（用于加载prompts）
- `app.parsers.labels`（用于多语言标签）

**导出**：
- `IntentClassifier`

---

### 5. `intent_understanding.py` - 主中间件（保留）
**内容**：
- `IntentUnderstandingMiddleware` 类
- 必要的导入和整合逻辑

**依赖**：
- `app.middleware.intent_models`（所有数据模型）
- `app.middleware.context_retriever.ContextRetriever`
- `app.middleware.intent_classifier.IntentClassifier`
- `app.middleware.file_parser.FileParser`

**导出**：
- `IntentUnderstandingMiddleware`
- 重新导出所有数据模型（向后兼容）

---

## 拆分后的文件大小预估

- `intent_models.py`: ~240行
- `context_retriever.py`: ~660行
- `context_enrichment_tool.py`: ~173行
- `intent_classifier.py`: ~907行
- `intent_understanding.py`: ~500行（主文件）

**总计**: ~2480行（略有增加，因为需要导入语句）

---

## 实施步骤

1. ✅ 创建 `intent_models.py`，移动所有数据模型
2. ✅ 创建 `context_retriever.py`，移动 `ContextRetriever`
3. ✅ 创建 `context_enrichment_tool.py`，移动 `ContextEnrichmentTool`
4. ✅ 创建 `intent_classifier.py`，移动 `IntentClassifier`
5. ✅ 更新 `intent_understanding.py`，移除已拆分的代码，添加导入
6. ✅ 更新 `__init__.py`，确保向后兼容
7. ✅ 测试编译和导入

---

## 向后兼容性

为了保持向后兼容，`intent_understanding.py` 应该重新导出所有数据模型：

```python
# Re-export for backward compatibility
from app.middleware.intent_models import (
    TaskCategory,
    InputType,
    SecuritySubType,
    ConfidenceLevel,
    UserInput,
    ParameterRequest,
    TaskDescription,
    IntentResult,
)
```

这样现有的导入 `from app.middleware.intent_understanding import IntentResult` 仍然有效。
