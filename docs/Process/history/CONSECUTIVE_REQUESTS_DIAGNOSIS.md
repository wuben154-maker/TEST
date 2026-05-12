# 连续请求问题诊断结论

## 测试结果

### 1. 后端直接调用（`stream_analyze_request`）

**测试**：`test_consecutive_text_text_file_text_same_session`

- Round 1 (text)、Round 2 (text)、Round 3 (PHP file)、Round 4 (text) 顺序调用
- **结果**：Round 3 正确触发 task/subagent，Round 4 正常返回
- **结论**：后端逻辑在顺序调用时工作正常

### 2. 根因推断（待前端/HTTP 验证）

现象：第 3 次文件请求不触发子 agent，第 4 次才触发。

**推断链条**：

1. **第 3 次请求很快返回旧结论**  
   - adapter 在 graph 未产出新结果时，从 `aget_state` 取到上一轮的 AIMessage 作为 conclusion  
   - 或 graph 未实际运行/提前结束，导致结论来自旧 checkpoint  

2. **用户以为第 3 次已完成**  
   - 看到旧结论（实为第 2 次结果）  
   - 或 persistence 把第 2 次结果展示在 history 中，用户误以为是当前结果  

3. **用户发起第 4 次请求**  
   - 前端 `analyzeInput` 会执行 `abortControllerRef.current.abort()`，**会 abort 仍在进行中的第 3 次请求**  

4. **第 3 次被 abort 前的状态**  
   - 第 3 次请求已把 user3（PHP 文件）merge 进 checkpoint  
   - 但 graph 未跑完或未跑，未产生新 AIMessage  

5. **第 4 次请求执行时**  
   - checkpoint 中已有 `[..., user3, user4]`  
   - graph 按顺序处理，先处理 user3（PHP）→ 触发 subagent  
   - 用户看到的是第 4 次请求的 stream，但内容是对第 3 次 PHP 的分析  

## 核心问题

1. **adapter**：graph 未产出新结果时，不应使用旧 checkpoint 的 AIMessage 作为 conclusion  
2. **前端 abort 策略**：新请求会 abort 前一个请求，若用户误以为前一个已完成而发起新请求，会导致前一个被中断  
3. **后端并发**：同一 session 下多请求并发，会竞态 checkpoint  

## 建议修复（按优先级）

1. **adapter 结论逻辑**：仅使用本次 stream 中产生的 AIMessage 作为 conclusion；若 stream 中无 agent 输出，则报错或提示重试，不返回旧结论  
2. **后端 per-session 锁**：同一 session 串行处理请求，避免并发竞态和“第 4 次触发第 3 次逻辑”的错位  
3. **前端**：可选——在 `isAnalyzing` 时禁止提交，或对新请求做排队/提示，减少误 abort  

## 待验证

- `test_round3_file_only_empty_message`：仅文件、message 为空时的行为  
- `test_concurrent_requests_same_session`：并发请求时的行为  
- 通过 HTTP `/analyze` 端点的完整 E2E 流程  
