# Intent Understanding Flow - 详细流程图和函数调用图

## 目录
1. [主流程图](#主流程图)
2. [Phase 1 详细流程](#phase-1-详细流程)
3. [Phase 2 详细流程](#phase-2-详细流程)
4. [函数调用关系图](#函数调用关系图)
5. [数据流图](#数据流图)

---

## 主流程图

```
┌─────────────────────────────────────────────────────────────────┐
│  IntentUnderstandingMiddleware.understand()                    │
│  入口点：用户输入 (text, files, session_id, language)          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 1: File Parsing              │
        │ - 遍历 files 列表                 │
        │ - 创建 FileInfo 对象              │
        │ - 调用 file_parser.parse_file()   │
        │   解析文件内容                     │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 2: Build UserInput          │
        │ - UserInput(text, files,         │
        │            session_id)           │
        │ - 合并文本和文件内容              │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 3: Detect Input Type        │
        │ - file_parser.detect_input_type() │
        │ - 检测: TEXT/EMAIL/LOG/CODE/     │
        │   BINARY/IMAGE/DOCUMENT/MIXED    │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 4: Context Loading          │
        │ - context_retriever.              │
        │   get_context_summary()           │
        │ - 获取短期记忆（会话历史）         │
        │ - 提取：实体、文件、偏好、摘要     │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 5: Two-Phase Classification  │
        │ - classifier.classify()           │
        │   ┌─────────────────────────┐    │
        │   │ Phase 1: Initial        │    │
        │   │ Classification           │    │
        │   └─────────────────────────┘    │
        │   ┌─────────────────────────┐    │
        │   │ Phase 2: Context         │    │
        │   │ Enrichment (if needed)   │    │
        │   └─────────────────────────┘    │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 6: Save to Short-term       │
        │ Memory                           │
        │ - context_retriever.             │
        │   add_to_short_term()            │
        │ - 保存意图理解结果到会话历史      │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 7: Parameter Request        │
        │ Callback                          │
        │ - 如果有 parameter_requests       │
        │ - 调用 on_parameter_request()    │
        │   触发用户交互                    │
        └───────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────┐
        │ Step 8: Performance Monitoring   │
        │ - 记录各阶段耗时                  │
        │ - 慢操作告警                      │
        │ - 日志记录                        │
        └───────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │ Return Result │
                    │ IntentResult  │
                    └───────────────┘
```

---

## Phase 1 详细流程

```
┌─────────────────────────────────────────────────────────────┐
│  IntentClassifier.classify()                                │
│  Phase 1: Initial Classification + Context Sufficiency Check │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 1. Register Files                    │
        │ - enrichment_tool.register_files()   │
        │ - 注册上传的文件供后续 read_file 使用 │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 2. Build Files Info String          │
        │ - 格式化文件信息                     │
        │ - 添加到提示词中                     │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 3. Load Phase 1 Prompt               │
        │ - get_phase1_prompt()                │
        │   ├─ 从文件加载（延迟加载）          │
        │   └─ 或使用 fallback prompt         │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 4. Format Prompt                     │
        │ - 填充上下文 (context)               │
        │ - 填充用户文本 (text[:3000])          │
        │ - 填充文件信息 (files_str)            │
        │ - 添加语言指令                       │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 5. Call LLM (Phase 1)               │
        │ - _call_llm(prompt, PHASE1_TOOL)     │
        │   ├─ 使用 LangChain LLM 或          │
        │   └─ Lovable AI Gateway             │
        │ - 工具：classify_intent_phase1       │
        │ - 返回 JSON 结果                     │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 6. Extract & Normalize JSON         │
        │ - _extract_json()                    │
        │   ├─ 直接解析 JSON                   │
        │   ├─ 提取 ```json 代码块            │
        │   └─ 提取任何 JSON 对象            │
        │ - _normalize_json_keys()             │
        │   清理键名中的引号                   │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 7. Check Phase 2 Need                │
        │ - needs_more_context == True?         │
        │ - context_queries 非空?              │
        │ - enable_two_phase == True?          │
        └──────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
    ┌───────────────┐              ┌──────────────────┐
    │ 不需要 Phase 2 │              │ 需要 Phase 2      │
    │                │              │                  │
    │ 8a. Parse      │              │ 8b. 进入 Phase 2  │
    │    Result      │              │    (见下方)      │
    │ - _parse_result│              │                  │
    │    (phase1)    │              │                  │
    └───────────────┘              └──────────────────┘
            │
            ▼
    ┌──────────────────────┐
    │ 9. Check Clarification│
    │ - _check_clarification│
    │   _needed()          │
    │ - 置信度 < 阈值?      │
    │ - 生成澄清问题        │
    └──────────────────────┘
            │
            ▼
    ┌──────────────────────┐
    │ 10. Return Result     │
    │ - IntentResult        │
    │   (from Phase 1)      │
    └──────────────────────┘
```

---

## Phase 2 详细流程

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Context Enrichment + Re-classification            │
│  (仅在 Phase 1 判断需要更多上下文时执行)                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 1. Extract Context Queries           │
        │ - 从 phase1_result 获取              │
        │   context_queries[]                  │
        │ - 最多处理 5 个查询                   │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 2. Execute Enrichment Queries       │
        │ - _enrich_context(queries,          │
        │                  session_id)       │
        │                                     │
        │   对每个查询：                       │
        │   ├─ web_search                    │
        │   │  └─ enrichment_tool.            │
        │   │     web_search(query)          │
        │   │                                │
        │   ├─ scrape_url                    │
        │   │  └─ enrichment_tool.            │
        │   │     scrape_url(url)           │
        │   │                                │
        │   ├─ read_file                     │
        │   │  └─ enrichment_tool.           │
        │   │     read_file(filename,       │
        │   │               session_id,      │
        │   │               max_lines,      │
        │   │               search_pattern) │
        │   │                                │
        │   └─ analyze_file_structure        │
        │      └─ enrichment_tool.          │
        │        analyze_file_structure(     │
        │          filename, session_id)     │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 3. Combine Enrichment Results       │
        │ - 合并所有查询结果                   │
        │ - 格式：\n\n---\n\n 分隔            │
        │ - 限制总长度（5000 字符）           │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 4. Load Phase 2 Prompt              │
        │ - get_phase2_prompt()               │
        │   ├─ 从文件加载（延迟加载）          │
        │   └─ 或使用 fallback prompt         │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 5. Format Phase 2 Prompt            │
        │ - 填充原始请求 (text, files)        │
        │ - 填充增强上下文                    │
        │   (additional_context[:5000])        │
        │ - 填充会话上下文 (context)          │
        │ - 添加语言指令                       │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 6. Call LLM (Phase 2)               │
        │ - _call_llm(prompt,                 │
        │            CLASSIFICATION_TOOL)     │
        │ - 工具：classify_intent              │
        │ - 返回 JSON 结果                     │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 7. Extract & Parse Result            │
        │ - _extract_json()                    │
        │ - _normalize_json_keys()             │
        │ - _parse_result(phase2_result)       │
        │ - 标记 enrichment_applied = True      │
        │ - 保存 enrichment_sources             │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 8. Check Clarification               │
        │ - _check_clarification_needed()     │
        │ - 即使 Phase 2 后也可能需要澄清      │
        └──────────────────────────────────────┘
                            │
                            ▼
        ┌──────────────────────────────────────┐
        │ 9. Return Enhanced Result           │
        │ - IntentResult                      │
        │   (from Phase 2, with enrichment)    │
        │ - understanding_phases = 2           │
        └──────────────────────────────────────┘
```

---

## 函数调用关系图

### 顶层调用链

```
DeepAgentWithIntent.understand_intent()
    │
    └─► IntentUnderstandingMiddleware.understand()
            │
            ├─► FileParser.parse_file()              [Step 1]
            │
            ├─► FileParser.detect_input_type()       [Step 3]
            │
            ├─► ContextRetriever.get_context_summary() [Step 4]
            │       │
            │       ├─► ContextRetriever.get_short_term_context()
            │       │
            │       ├─► ContextRetriever._extract_entities()
            │       │
            │       ├─► ContextRetriever._extract_files()
            │       │
            │       ├─► ContextRetriever._extract_preferences()
            │       │
            │       └─► ContextRetriever._extract_recent_summaries()
            │
            └─► IntentClassifier.classify()            [Step 5]
                    │
                    ├─► IntentClassifier.get_phase1_prompt()
                    │
                    ├─► IntentClassifier._call_llm()
                    │       │
                    │       ├─► IntentClassifier._extract_json()
                    │       │
                    │       └─► IntentClassifier._normalize_json_keys()
                    │
                    ├─► IntentClassifier._enrich_context()  [Phase 2]
                    │       │
                    │       ├─► ContextEnrichmentTool.web_search()
                    │       │
                    │       ├─► ContextEnrichmentTool.scrape_url()
                    │       │
                    │       ├─► ContextEnrichmentTool.read_file()
                    │       │
                    │       └─► ContextEnrichmentTool.analyze_file_structure()
                    │
                    ├─► IntentClassifier.get_phase2_prompt()
                    │
                    ├─► IntentClassifier._parse_result()
                    │
                    └─► IntentClassifier._check_clarification_needed()
                            │
                            └─► IntentClassifier._generate_clarification_questions()
```

### 详细函数调用树

```
IntentUnderstandingMiddleware
│
├── __init__()
│   ├── FileParser()
│   ├── ContextRetriever(store_backend)
│   └── IntentClassifier(llm, api_key, enable_two_phase, file_parser)
│
├── understand(text, files, session_id, language)
│   │
│   ├── [Step 1] FileParser.parse_file(file_info)
│   │   └── (在 file_parser.py 中实现)
│   │
│   ├── [Step 2] UserInput(text, files, session_id)
│   │   └── UserInput.get_combined_content()
│   │
│   ├── [Step 3] FileParser.detect_input_type(content)
│   │   └── (在 file_parser.py 中实现)
│   │
│   ├── [Step 4] ContextRetriever.get_context_summary(session_id, language)
│   │   ├── ContextRetriever.get_short_term_context(session_id)
│   │   ├── ContextRetriever._extract_entities(history)
│   │   │   └── re.findall() [IP, domain, hash patterns]
│   │   ├── ContextRetriever._extract_files(history)
│   │   │   └── re.findall() [file patterns]
│   │   ├── ContextRetriever._extract_preferences(history, language)
│   │   │   └── get_intent_label() [from labels.py]
│   │   └── ContextRetriever._extract_recent_summaries(history, language)
│   │       └── get_intent_label() [from labels.py]
│   │
│   └── [Step 5] IntentClassifier.classify(user_input, context, language)
│       │
│       ├── ContextEnrichmentTool.register_files(session_id, files)
│       │
│       ├── IntentClassifier.get_phase1_prompt()
│       │   ├── get_intent_phase1_prompt() [from prompts/loader.py]
│       │   └── IntentClassifier._get_fallback_phase1_prompt()
│       │
│       ├── IntentClassifier._call_llm(prompt, PHASE1_TOOL)
│       │   ├── llm.ainvoke() [LangChain] 或
│       │   └── httpx.AsyncClient.post() [Lovable AI Gateway]
│       │   ├── IntentClassifier._extract_json(content)
│       │   │   ├── json.loads() [直接解析]
│       │   │   ├── re.search() [提取 ```json 代码块]
│       │   │   └── re.search() [提取 JSON 对象]
│       │   └── IntentClassifier._normalize_json_keys(data)
│       │       └── (递归处理嵌套字典和列表)
│       │
│       ├── [Phase 2] IntentClassifier._enrich_context(queries, session_id)
│       │   ├── IntentClassifier._normalize_query_dict(q)
│       │   │
│       │   ├── ContextEnrichmentTool.web_search(query)
│       │   │   └── DuckDuckGoSearchProvider.search()
│       │   │
│       │   ├── ContextEnrichmentTool.scrape_url(url)
│       │   │   └── UrlScraper.scrape()
│       │   │
│       │   ├── ContextEnrichmentTool.read_file(filename, session_id, ...)
│       │   │   ├── FileParser.parse_file(file_info)
│       │   │   └── re.compile() [如果 search_pattern 存在]
│       │   │
│       │   └── ContextEnrichmentTool.analyze_file_structure(filename, session_id)
│       │       ├── FileInfo.compute_hashes()
│       │       └── FileParser.parse_file(file_info)
│       │
│       ├── IntentClassifier.get_phase2_prompt()
│       │   ├── get_intent_phase2_prompt() [from prompts/loader.py]
│       │   └── IntentClassifier._get_fallback_phase2_prompt()
│       │
│       ├── IntentClassifier._call_llm(prompt, CLASSIFICATION_TOOL)
│       │   └── (同上)
│       │
│       ├── IntentClassifier._parse_result(data)
│       │   ├── TaskCategory(category_str)
│       │   ├── InputType(input_type_str)
│       │   ├── SecuritySubType(security_subtype_str)
│       │   └── ParameterRequest() [for each param]
│       │
│       └── IntentClassifier._check_clarification_needed(user_input, result, language)
│           ├── get_config() [from intent_config.py]
│           └── IntentClassifier._generate_clarification_questions(...)
│               └── get_intent_label() [from labels.py]
│
├── [Step 6] ContextRetriever.add_to_short_term(session_id, entry)
│
├── [Step 7] on_parameter_request(parameter_requests) [callback]
│
└── [Step 8] Performance monitoring & logging
    └── get_config() [from intent_config.py]
```

---

## 数据流图

### 输入数据流

```
用户输入
│
├─ text: str
│  └─► UserInput.text
│
├─ files: list[dict]
│  ├─ filename: str
│  ├─ content_type: str
│  ├─ content: bytes/str
│  └─ size: int
│     └─► FileInfo
│         └─► UserInput.files
│
├─ session_id: str
│  └─► UserInput.session_id
│     └─► ContextRetriever (用于记忆检索)
│
└─ language: str
   └─► 多语言消息和标签
```

### 处理数据流

```
UserInput
│
├─► FileParser.parse_file()
│   └─► FileInfo.parsed_content
│
├─► UserInput.get_combined_content()
│   └─► combined_content: str
│
├─► FileParser.detect_input_type()
│   └─► InputType enum
│
└─► ContextRetriever.get_context_summary()
    ├─► get_short_term_context()
    │   └─► history: list[dict]
    │
    ├─► _extract_entities()
    │   └─► entities: list[str]  [IPs, domains, hashes]
    │
    ├─► _extract_files()
    │   └─► files: list[str]
    │
    ├─► _extract_preferences()
    │   └─► preferences: str
    │
    └─► _extract_recent_summaries()
        └─► summaries: list[str]
```

### Phase 1 数据流

```
Phase 1 Prompt
│
├─ context: str (from get_context_summary)
├─ text: str (user input, truncated to 3000)
├─ files: str (formatted file info)
└─ language_instruction: str
   │
   └─► _call_llm(prompt, PHASE1_TOOL)
       │
       └─► phase1_result: dict
           ├─ task_category: str
           ├─ input_type: str
           ├─ confidence: float
           ├─ summary: str
           ├─ key_entities: list[str]
           ├─ analysis_goals: list[str]
           ├─ suggested_approach: str
           ├─ security_subtype: str | None
           ├─ research_topic: str
           ├─ reasoning: str
           ├─ needs_more_context: bool  ⭐
           ├─ context_queries: list[dict]  ⭐
           │   ├─ type: str  [web_search/scrape_url/read_file/analyze_file_structure]
           │   ├─ query: str  [for web_search]
           │   ├─ url: str  [for scrape_url]
           │   ├─ filename: str  [for read_file/analyze_file_structure]
           │   ├─ search_pattern: str  [for read_file]
           │   └─ max_lines: int  [for read_file]
           └─ context_reasoning: str
```

### Phase 2 数据流

```
context_queries: list[dict]
│
└─► _enrich_context(queries, session_id)
    │
    ├─► web_search(query)
    │   └─► "[Web Search: {query}]\n{results}"
    │
    ├─► scrape_url(url)
    │   └─► "[URL Content: {url}]\n{content}"
    │
    ├─► read_file(filename, session_id, ...)
    │   └─► "[File: {filename}] ...\n{content}"
    │
    └─► analyze_file_structure(filename, session_id)
        └─► "[File Structure Analysis: {filename}] ..."
        │
        └─► additional_context: str
            (combined with \n\n---\n\n separator)
            │
            └─► Phase 2 Prompt
                ├─ text: str (original)
                ├─ files: str (original)
                ├─ additional_context: str  ⭐ (enriched)
                └─ context: str (original)
                   │
                   └─► _call_llm(prompt, CLASSIFICATION_TOOL)
                       │
                       └─► phase2_result: dict
                           ├─ (same fields as phase1_result)
                           ├─ enrichment_summary: str  ⭐
                           └─ enrichment_applied: bool = True  ⭐
```

### 输出数据流

```
IntentResult
│
├─ task_category: TaskCategory
├─ input_type: InputType
├─ confidence: float
├─ summary: str
├─ key_entities: list[str]
├─ analysis_goals: list[str]
├─ suggested_approach: str
├─ security_subtype: SecuritySubType | None
├─ research_topic: str
├─ reasoning: str
├─ parameter_requests: list[ParameterRequest]
│   ├─ id: str
│   ├─ name: str
│   ├─ description: str
│   ├─ param_type: str
│   ├─ required: bool
│   └─ encrypted: bool
├─ enrichment_applied: bool
├─ enrichment_summary: str
├─ enrichment_sources: list[str]
├─ understanding_phases: int  [1 or 2]
└─ timestamp: datetime
   │
   └─► to_event_dict()
       └─► dict (for SSE events)
```

---

## 关键决策点

### 1. Phase 2 触发条件

```
needs_more_context == True
    AND
context_queries is not empty
    AND
enable_two_phase == True
    ↓
进入 Phase 2
```

### 2. 澄清请求触发条件

```
confidence < confidence_threshold
    AND
enrichment_applied == False
    ↓
生成澄清问题
    ↓
task_category = PARAMETER_NEEDED
```

### 3. 异常处理策略

```
任何异常发生
    ↓
捕获异常
    ↓
记录错误日志
    ↓
返回安全的回退结果
    ↓
IntentResult(
    task_category=UNKNOWN,
    confidence=0.3,
    summary="无法理解请求..."
)
```

---

## 性能监控点

```
perf_metrics = {
    "file_parsing": float,          # Step 1 耗时
    "context_loading": float,       # Step 4 耗时
    "phase1_classification": float,  # Phase 1 LLM 调用耗时
    "phase2_enrichment": float,      # Phase 2 上下文增强耗时
    "phase2_classification": float, # Phase 2 LLM 调用耗时
    "total": float                  # 总耗时
}
```

---

## 总结

这个意图理解系统采用了**两阶段理解策略**：

1. **Phase 1**: 快速初步分类，判断是否需要更多上下文
2. **Phase 2**: 仅在需要时执行上下文增强，提高理解准确性

关键特性：
- ✅ 异常安全：所有方法都有异常保护
- ✅ 性能监控：记录各阶段耗时
- ✅ 多语言支持：支持 en/zh/ja/ko
- ✅ 智能澄清：低置信度时自动请求用户澄清
- ✅ 上下文管理：短期记忆 + 长期记忆
- ✅ 文件处理：支持多种文件类型和智能解析
