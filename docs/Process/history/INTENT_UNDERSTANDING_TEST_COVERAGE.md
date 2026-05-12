# Intent Understanding 单元测试覆盖报告

## 测试文件

`python-agent-service/tests/test_intent_understanding.py`

## 测试覆盖范围

### 1. IntentClassifier 测试 (TestIntentClassifier)

#### 初始化测试
- ✅ `test_init`: 测试基本初始化
- ✅ `test_init_with_two_phase`: 测试启用两阶段理解
- ✅ `test_get_phase1_prompt`: 测试 Phase 1 提示词加载
- ✅ `test_get_phase2_prompt`: 测试 Phase 2 提示词加载

#### 分类测试
- ✅ `test_classify_high_confidence`: 测试高置信度分类（>= 0.7）
- ✅ `test_classify_medium_confidence`: 测试中置信度分类（0.4-0.7）
- ✅ `test_classify_low_confidence`: 测试低置信度分类（< 0.4）
- ✅ `test_classify_with_files`: 测试带文件输入的分类
- ✅ `test_classify_llm_failure`: 测试 LLM 调用失败的处理
- ✅ `test_classify_malformed_json`: 测试格式错误的 JSON 响应处理
- ✅ `test_classify_multiple_languages`: 测试多语言支持（en/zh/ja/ko）

#### JSON 处理测试
- ✅ `test_extract_json_direct`: 测试直接 JSON 提取
- ✅ `test_extract_json_code_block`: 测试代码块中的 JSON 提取
- ✅ `test_extract_json_embedded`: 测试嵌入文本中的 JSON 提取
- ✅ `test_extract_json_invalid`: 测试无效 JSON 处理
- ✅ `test_normalize_json_keys`: 测试 JSON 键规范化
- ✅ `test_normalize_query_dict`: 测试查询字典规范化

#### 结果解析测试
- ✅ `test_parse_result_complete`: 测试完整结果解析
- ✅ `test_parse_result_minimal`: 测试最小结果解析
- ✅ `test_parse_result_invalid_category`: 测试无效类别处理
- ✅ `test_parse_result_with_intent_description_only`: 测试仅有 intent_description 的情况

#### Fallback 和错误处理测试
- ✅ `test_get_fallback_result`: 测试 Fallback 结果生成
- ✅ `test_generate_clarification_questions_high_confidence`: 测试高置信度澄清问题生成（不应生成）
- ✅ `test_generate_clarification_questions_no_llm`: 测试无 LLM 时的澄清问题生成
- ✅ `test_generate_clarification_questions_llm_failure`: 测试 LLM 失败时的澄清问题生成

#### LLM 调用测试
- ✅ `test_call_llm_success`: 测试成功 LLM 调用
- ✅ `test_call_llm_retry`: 测试 LLM 调用重试机制
- ✅ `test_call_llm_all_retries_fail`: 测试所有重试都失败的情况
- ✅ `test_call_llm_with_api_key`: 测试使用 API Key 的 LLM 调用

#### 上下文增强测试
- ✅ `test_enrich_context_no_tool`: 测试无增强工具时的上下文增强
- ✅ `test_enrich_context_with_tool`: 测试有增强工具时的上下文增强
- ✅ `test_enrich_context_multiple_queries`: 测试多个查询的上下文增强
- ✅ `test_enrich_context_query_failure`: 测试查询失败时的上下文增强

---

### 2. IntentUnderstandingMiddleware 测试 (TestIntentUnderstandingMiddleware)

#### 初始化测试
- ✅ `test_init`: 测试基本初始化
- ✅ `test_init_with_config_path`: 测试使用自定义配置路径初始化

#### 理解测试
- ✅ `test_understand_simple_text`: 测试简单文本理解
- ✅ `test_understand_with_files`: 测试带文件的理解
- ✅ `test_understand_with_context`: 测试带上下文的理解
- ✅ `test_understand_clarification_resubmission`: 测试澄清重新提交的理解
- ✅ `test_understand_exception_handling`: 测试异常处理
- ✅ `test_understand_parameter_request_callback`: 测试参数请求回调
- ✅ `test_understand_performance_monitoring`: 测试性能监控
- ✅ `test_understand_multiple_languages`: 测试多语言理解

#### 参数保存测试
- ✅ `test_save_parameter`: 测试参数保存到长期记忆

#### 工具创建测试
- ✅ `test_create_tools`: 测试 LangGraph 工具创建
- ✅ `test_understand_intent_tool`: 测试 understand_intent 工具执行
- ✅ `test_understand_intent_tool_exception`: 测试工具异常处理
- ✅ `test_understand_intent_tool_invalid_files_json`: 测试无效文件 JSON 处理

#### 系统提示词测试
- ✅ `test_get_system_prompt`: 测试系统提示词获取

---

### 3. 边界情况和错误处理测试 (TestIntentUnderstandingEdgeCases)

- ✅ `test_empty_text_input`: 测试空文本输入
- ✅ `test_very_long_text_input`: 测试超长文本输入（> 3000 字符）
- ✅ `test_multiple_files`: 测试多个文件输入
- ✅ `test_no_llm_no_api_key`: 测试无 LLM 和 API Key 的情况
- ✅ `test_context_retrieval_failure`: 测试上下文检索失败
- ✅ `test_file_parsing_failure`: 测试文件解析失败

---

### 4. 集成测试 (TestIntentUnderstandingIntegration)

- ✅ `test_complete_flow_security_analysis`: 测试完整的安全分析流程
- ✅ `test_complete_flow_research_task`: 测试完整的研究任务流程
- ✅ `test_complete_flow_with_parameter_request`: 测试带参数请求的完整流程

---

## 测试统计

### 测试类数量
- **4 个测试类**
  - `TestIntentClassifier`: 30+ 个测试
  - `TestIntentUnderstandingMiddleware`: 15+ 个测试
  - `TestIntentUnderstandingEdgeCases`: 6 个测试
  - `TestIntentUnderstandingIntegration`: 3 个测试

### 总测试数量
- **约 54+ 个测试用例**

### 覆盖的功能模块
1. ✅ **IntentClassifier** - 核心分类逻辑
2. ✅ **IntentUnderstandingMiddleware** - 主入口点
3. ✅ **JSON 解析和规范化** - 数据提取和清理
4. ✅ **LLM 调用和重试** - API 交互和错误处理
5. ✅ **置信度管理** - 高/中/低置信度处理
6. ✅ **澄清问题生成** - LLM 驱动的澄清
7. ✅ **上下文增强** - 工具集成
8. ✅ **多语言支持** - en/zh/ja/ko
9. ✅ **文件处理** - 文件解析和类型检测
10. ✅ **参数管理** - 参数保存和请求
11. ✅ **工具集成** - LangGraph 工具创建
12. ✅ **错误处理** - 异常和 Fallback
13. ✅ **性能监控** - 性能指标收集

---

## 测试特点

### 1. Mock 策略
- **LLM Mock**: 使用 `AsyncMock` 模拟 LLM 调用
- **Store Mock**: 使用 `InMemoryStore` 进行内存存储测试
- **响应 Mock**: 模拟各种 LLM 响应场景（成功、失败、格式错误）

### 2. 测试场景覆盖
- ✅ **正常流程**: 高/中/低置信度分类
- ✅ **错误处理**: LLM 失败、JSON 解析错误、文件解析错误
- ✅ **边界情况**: 空输入、超长输入、多文件、无 LLM
- ✅ **多语言**: 支持 en/zh/ja/ko
- ✅ **集成测试**: 完整流程验证

### 3. 断言覆盖
- ✅ 任务类别验证
- ✅ 置信度验证
- ✅ 置信度级别验证（HIGH/MEDIUM/LOW）
- ✅ 任务描述验证
- ✅ 参数请求验证
- ✅ 输入类型验证
- ✅ 错误处理验证

---

## 运行测试

### 运行所有测试
```bash
cd python-agent-service
pytest tests/test_intent_understanding.py -v
```

### 运行特定测试类
```bash
pytest tests/test_intent_understanding.py::TestIntentClassifier -v
pytest tests/test_intent_understanding.py::TestIntentUnderstandingMiddleware -v
```

### 运行特定测试
```bash
pytest tests/test_intent_understanding.py::TestIntentClassifier::test_classify_high_confidence -v
```

### 生成覆盖率报告
```bash
pytest tests/test_intent_understanding.py --cov=app.middleware.intent_classifier --cov=app.middleware.intent_understanding --cov-report=html
```

---

## 测试依赖

### 必需依赖
- `pytest`: 测试框架
- `pytest-asyncio`: 异步测试支持
- `unittest.mock`: Mock 支持

### 可选依赖（用于覆盖率报告）
- `pytest-cov`: 覆盖率报告

---

## 待补充的测试（可选）

### 1. 性能测试
- [ ] 大量并发请求测试
- [ ] 响应时间基准测试
- [ ] 内存使用测试

### 2. 压力测试
- [ ] 超长上下文测试
- [ ] 大量文件处理测试
- [ ] 长时间运行测试

### 3. 真实场景测试
- [ ] 真实 LLM API 调用测试（需要 API Key）
- [ ] 真实文件解析测试
- [ ] 真实上下文检索测试

---

## 注意事项

1. **Mock LLM**: 所有测试使用 Mock LLM，不进行真实 API 调用
2. **异步测试**: 所有异步方法使用 `@pytest.mark.asyncio` 装饰器
3. **测试隔离**: 每个测试都是独立的，不依赖其他测试的状态
4. **错误处理**: 测试覆盖了各种错误场景，确保系统健壮性
5. **多语言**: 测试验证了多语言标签加载，但不验证翻译质量

---

## 总结

✅ **完整的单元测试覆盖** - 覆盖了意图理解模块的所有核心功能
✅ **错误处理测试** - 覆盖了各种异常和边界情况
✅ **集成测试** - 验证了完整的工作流程
✅ **Mock 策略** - 使用适当的 Mock 策略，避免外部依赖
✅ **可维护性** - 测试代码结构清晰，易于维护和扩展

测试文件已创建，可以运行 `pytest tests/test_intent_understanding.py -v` 来执行所有测试。
