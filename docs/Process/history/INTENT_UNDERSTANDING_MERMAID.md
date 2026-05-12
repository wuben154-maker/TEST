# Intent Understanding - Mermaid 流程图

本文档包含使用 Mermaid 语法绘制的流程图，可在支持 Mermaid 的 Markdown 查看器中渲染。

## 主流程图

```mermaid
flowchart TD
    Start([用户输入<br/>text, files, session_id]) --> Step1[Step 1: File Parsing<br/>解析上传的文件]
    Step1 --> Step2[Step 2: Build UserInput<br/>构建用户输入对象]
    Step2 --> Step3[Step 3: Detect Input Type<br/>检测输入类型]
    Step3 --> Step4[Step 4: Context Loading<br/>加载会话上下文]
    Step4 --> Step5[Step 5: Two-Phase Classification<br/>两阶段意图理解]
    Step5 --> Step6[Step 6: Save to Short-term Memory<br/>保存到短期记忆]
    Step6 --> Step7{是否有参数请求?}
    Step7 -->|是| Step7a[Step 7: Parameter Request Callback<br/>触发参数请求回调]
    Step7 -->|否| Step8[Step 8: Performance Monitoring<br/>性能监控和日志]
    Step7a --> Step8
    Step8 --> End([返回 IntentResult])
    
    style Start fill:#e1f5ff
    style End fill:#c8e6c9
    style Step5 fill:#fff9c4
    style Step7 fill:#ffccbc
```

## Phase 1 详细流程

```mermaid
flowchart TD
    Start([IntentClassifier.classify<br/>开始 Phase 1]) --> RegFiles[注册文件<br/>register_files]
    RegFiles --> BuildFiles[构建文件信息字符串]
    BuildFiles --> LoadPrompt1[加载 Phase 1 提示词<br/>get_phase1_prompt]
    LoadPrompt1 --> FormatPrompt1[格式化提示词<br/>填充 context, text, files]
    FormatPrompt1 --> CallLLM1[调用 LLM<br/>_call_llm with PHASE1_TOOL]
    CallLLM1 --> ExtractJSON1[提取和规范化 JSON<br/>_extract_json + _normalize_json_keys]
    ExtractJSON1 --> CheckPhase2{需要 Phase 2?<br/>needs_more_context?}
    
    CheckPhase2 -->|否| ParseResult1[解析结果<br/>_parse_result]
    CheckPhase2 -->|是| Phase2[进入 Phase 2]
    
    ParseResult1 --> CheckClarify1{需要澄清?<br/>confidence < threshold?}
    CheckClarify1 -->|是| GenQuestions[生成澄清问题<br/>_generate_clarification_questions]
    CheckClarify1 -->|否| Return1[返回 Phase 1 结果]
    GenQuestions --> Return1
    
    Phase2 --> Return2[返回 Phase 2 结果]
    
    style Start fill:#e1f5ff
    style CheckPhase2 fill:#fff9c4
    style CheckClarify1 fill:#ffccbc
    style Phase2 fill:#f3e5f5
    style Return1 fill:#c8e6c9
    style Return2 fill:#c8e6c9
```

## Phase 2 详细流程

```mermaid
flowchart TD
    Start([Phase 2: Context Enrichment<br/>开始上下文增强]) --> ExtractQueries[提取上下文查询<br/>从 phase1_result.context_queries]
    ExtractQueries --> LoopQueries{遍历查询<br/>最多5个}
    
    LoopQueries -->|web_search| WebSearch[执行网络搜索<br/>enrichment_tool.web_search]
    LoopQueries -->|scrape_url| ScrapeURL[抓取 URL<br/>enrichment_tool.scrape_url]
    LoopQueries -->|read_file| ReadFile[读取文件<br/>enrichment_tool.read_file]
    LoopQueries -->|analyze_file_structure| AnalyzeFile[分析文件结构<br/>enrichment_tool.analyze_file_structure]
    
    WebSearch --> CombineResults[合并增强结果<br/>用 \n\n---\n\n 分隔]
    ScrapeURL --> CombineResults
    ReadFile --> CombineResults
    AnalyzeFile --> CombineResults
    
    CombineResults --> LoadPrompt2[加载 Phase 2 提示词<br/>get_phase2_prompt]
    LoadPrompt2 --> FormatPrompt2[格式化 Phase 2 提示词<br/>填充 additional_context]
    FormatPrompt2 --> CallLLM2[调用 LLM<br/>_call_llm with CLASSIFICATION_TOOL]
    CallLLM2 --> ExtractJSON2[提取和规范化 JSON]
    ExtractJSON2 --> ParseResult2[解析结果<br/>标记 enrichment_applied=True]
    ParseResult2 --> CheckClarify2{需要澄清?}
    CheckClarify2 -->|是| GenQuestions2[生成澄清问题]
    CheckClarify2 -->|否| Return2[返回增强结果]
    GenQuestions2 --> Return2
    
    style Start fill:#f3e5f5
    style LoopQueries fill:#fff9c4
    style CombineResults fill:#e1f5ff
    style Return2 fill:#c8e6c9
```

## 上下文增强工具调用流程

```mermaid
flowchart LR
    EnrichContext[_enrich_context] --> Normalize[规范化查询字典<br/>_normalize_query_dict]
    Normalize --> CheckType{查询类型}
    
    CheckType -->|web_search| WebSearch[DuckDuckGoSearchProvider<br/>.search]
    CheckType -->|scrape_url| ScrapeURL[UrlScraper<br/>.scrape]
    CheckType -->|read_file| ReadFile[FileParser<br/>.parse_file]
    CheckType -->|analyze_file_structure| AnalyzeFile[FileParser<br/>.parse_file + 结构分析]
    
    WebSearch --> Combine[合并结果]
    ScrapeURL --> Combine
    ReadFile --> Combine
    AnalyzeFile --> Combine
    
    Combine --> Return[返回 additional_context]
    
    style EnrichContext fill:#e1f5ff
    style CheckType fill:#fff9c4
    style Combine fill:#c8e6c9
```

## 函数调用关系图

```mermaid
graph TD
    DeepAgent[DeepAgentWithIntent<br/>.understand_intent] --> Middleware[IntentUnderstandingMiddleware<br/>.understand]
    
    Middleware --> FileParse[FileParser<br/>.parse_file]
    Middleware --> DetectType[FileParser<br/>.detect_input_type]
    Middleware --> ContextSummary[ContextRetriever<br/>.get_context_summary]
    Middleware --> Classify[IntentClassifier<br/>.classify]
    
    ContextSummary --> ShortTerm[get_short_term_context]
    ContextSummary --> ExtractEntities[_extract_entities]
    ContextSummary --> ExtractFiles[_extract_files]
    ContextSummary --> ExtractPrefs[_extract_preferences]
    ContextSummary --> ExtractSummaries[_extract_recent_summaries]
    
    Classify --> Phase1Prompt[get_phase1_prompt]
    Classify --> CallLLM1[_call_llm Phase 1]
    Classify --> EnrichContext[_enrich_context]
    Classify --> Phase2Prompt[get_phase2_prompt]
    Classify --> CallLLM2[_call_llm Phase 2]
    Classify --> ParseResult[_parse_result]
    Classify --> CheckClarify[_check_clarification_needed]
    
    CallLLM1 --> ExtractJSON[_extract_json]
    CallLLM1 --> NormalizeKeys[_normalize_json_keys]
    CallLLM2 --> ExtractJSON
    CallLLM2 --> NormalizeKeys
    
    EnrichContext --> EnrichTool[ContextEnrichmentTool]
    EnrichTool --> WebSearch[web_search]
    EnrichTool --> ScrapeURL[scrape_url]
    EnrichTool --> ReadFile[read_file]
    EnrichTool --> AnalyzeFile[analyze_file_structure]
    
    CheckClarify --> GenQuestions[_generate_clarification_questions]
    
    style DeepAgent fill:#e1f5ff
    style Middleware fill:#fff9c4
    style Classify fill:#f3e5f5
    style EnrichContext fill:#ffccbc
```

## 数据流图

```mermaid
flowchart LR
    UserInput[用户输入<br/>text + files] --> FileParse[文件解析]
    FileParse --> ParsedFiles[FileInfo<br/>parsed_content]
    
    UserInput --> ContextLoad[上下文加载]
    ContextLoad --> ContextSummary[上下文摘要<br/>entities, files, preferences]
    
    ParsedFiles --> Combined[合并内容<br/>get_combined_content]
    Combined --> DetectType[检测输入类型]
    
    ContextSummary --> Phase1Prompt[Phase 1 提示词]
    UserInput --> Phase1Prompt
    Phase1Prompt --> LLM1[LLM 调用]
    LLM1 --> Phase1Result[Phase 1 结果<br/>needs_more_context?]
    
    Phase1Result -->|是| EnrichQueries[上下文查询<br/>context_queries]
    EnrichQueries --> EnrichContext[执行增强查询]
    EnrichContext --> AdditionalContext[增强上下文<br/>additional_context]
    
    AdditionalContext --> Phase2Prompt[Phase 2 提示词]
    UserInput --> Phase2Prompt
    ContextSummary --> Phase2Prompt
    Phase2Prompt --> LLM2[LLM 调用]
    LLM2 --> Phase2Result[Phase 2 结果]
    
    Phase1Result -->|否| FinalResult[最终结果]
    Phase2Result --> FinalResult
    
    FinalResult --> IntentResult[IntentResult<br/>task_category, confidence, summary]
    
    style UserInput fill:#e1f5ff
    style Phase1Result fill:#fff9c4
    style EnrichContext fill:#ffccbc
    style FinalResult fill:#c8e6c9
```

## 决策流程图

```mermaid
flowchart TD
    Start([开始意图理解]) --> Phase1[Phase 1: 初步分类]
    Phase1 --> CheckContext{needs_more_context<br/>== True?}
    
    CheckContext -->|否| CheckConfidence1{confidence<br/>< threshold?}
    CheckContext -->|是| Phase2[Phase 2: 上下文增强]
    
    Phase2 --> EnrichQueries[执行上下文查询<br/>web_search/scrape_url/read_file]
    EnrichQueries --> ReClassify[重新分类]
    ReClassify --> CheckConfidence2{confidence<br/>< threshold?}
    
    CheckConfidence1 -->|是| RequestClarify[请求澄清<br/>PARAMETER_NEEDED]
    CheckConfidence1 -->|否| ReturnResult[返回结果]
    
    CheckConfidence2 -->|是| RequestClarify
    CheckConfidence2 -->|否| ReturnResult
    
    RequestClarify --> ReturnResult
    
    style Start fill:#e1f5ff
    style CheckContext fill:#fff9c4
    style Phase2 fill:#f3e5f5
    style CheckConfidence1 fill:#ffccbc
    style CheckConfidence2 fill:#ffccbc
    style ReturnResult fill:#c8e6c9
```

## 异常处理流程

```mermaid
flowchart TD
    Start([方法执行]) --> Try{执行操作}
    Try -->|成功| Success[返回正常结果]
    Try -->|异常| Catch[捕获异常]
    
    Catch --> LogError[记录错误日志<br/>logger.error]
    LogError --> CheckMethod{方法类型}
    
    CheckMethod -->|understand| Fallback[返回安全回退结果<br/>UNKNOWN, confidence=0.3]
    CheckMethod -->|classify| FallbackClassify[返回基础结果<br/>UNKNOWN, confidence=0.3]
    CheckMethod -->|其他| ReturnEmpty[返回空值或默认值]
    
    Fallback --> EmitError[发送错误事件<br/>on_phase_update]
    EmitError --> ReturnFallback[返回回退结果]
    
    FallbackClassify --> ReturnFallback
    ReturnEmpty --> ReturnFallback
    
    Success --> End([正常结束])
    ReturnFallback --> End
    
    style Start fill:#e1f5ff
    style Catch fill:#ffccbc
    style Fallback fill:#ffcdd2
    style End fill:#c8e6c9
```

## 性能监控流程

```mermaid
flowchart TD
    Start([开始 understand]) --> InitMetrics[初始化性能指标<br/>perf_metrics]
    InitMetrics --> StartTime[记录开始时间]
    
    StartTime --> Step1[Step 1: File Parsing<br/>记录耗时]
    Step1 --> Step4[Step 4: Context Loading<br/>记录耗时]
    Step4 --> Step5[Step 5: Classification<br/>提取阶段耗时]
    
    Step5 --> ExtractPerf[从结果中提取性能指标<br/>_perf_phase1<br/>_perf_phase2_enrichment<br/>_perf_phase2]
    ExtractPerf --> CalcTotal[计算总耗时]
    CalcTotal --> CheckConfig{监控启用?}
    
    CheckConfig -->|是| LogMetrics[记录性能日志<br/>logger.info]
    CheckConfig -->|否| CheckSlow{总耗时 > 阈值?}
    
    LogMetrics --> CheckSlow
    CheckSlow -->|是| WarnSlow[警告慢操作<br/>logger.warning]
    CheckSlow -->|否| StoreMetrics[存储到结果元数据]
    
    WarnSlow --> StoreMetrics
    StoreMetrics --> End([结束])
    
    style Start fill:#e1f5ff
    style CheckConfig fill:#fff9c4
    style WarnSlow fill:#ffccbc
    style End fill:#c8e6c9
```

---

## 使用说明

这些 Mermaid 图表可以在以下环境中查看：
- GitHub/GitLab（原生支持）
- VS Code（安装 Mermaid Preview 扩展）
- 在线编辑器：https://mermaid.live/
- 文档工具：MkDocs、Docusaurus 等

## 图表说明

1. **主流程图**：展示从用户输入到返回结果的完整流程
2. **Phase 1 详细流程**：展示第一阶段分类的详细步骤
3. **Phase 2 详细流程**：展示上下文增强和第二阶段分类
4. **上下文增强工具调用流程**：展示各种增强工具的调用方式
5. **函数调用关系图**：展示主要函数之间的调用关系
6. **数据流图**：展示数据在各个组件之间的流动
7. **决策流程图**：展示关键决策点的判断逻辑
8. **异常处理流程**：展示异常处理策略
9. **性能监控流程**：展示性能监控的实现方式
