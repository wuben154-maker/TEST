# 简单问题统一回复问题修复总结

## 问题现象

用户输入以下三个不同问题，均返回相同的固定回复：
- 问题1：我是谁
- 问题2：你能做哪些安全工作
- 问题3：你是谁

统一返回：**"除了安全事件处理外，我还可以帮你做深度研究工作，你可以输入更详细的需求。"**

## 根因分析

**结论：属于后台服务问题，不是界面显示问题。**

### 流程说明

1. **意图理解**：LLM 将上述问题均分类为 `task_category=unknown`（正确，因非安全/研究任务）
2. **关键缺失**：LLM 未设置 `is_simple_question=true` 和 `direct_response=true`
3. **错误分支**：代码进入 `unknown-task` 分支，返回固定提示文案
4. **正确分支**：应进入 `is_simple_question && direct_response` 分支，由 LLM 直接生成针对性回答

### 代码路径

```
deep_agent.py analyze_stream:
├─ is_simple_question && direct_response → 直接 LLM 回答（期望路径）
├─ task_category==UNKNOWN && suggested_alternatives → 显示引导选项
└─ task_category==UNKNOWN → 固定文案「除了安全事件处理外...」（实际命中）
```

## 修复内容

### 1. MASTER_AGENT.md 提示词强化

在「Simple Questions (Direct Response)」章节中新增：

- **中文示例**：明确列出「你是谁」「你能做哪些安全工作」「我是谁」「你有什么功能」等
- **CRITICAL 指令**：要求对上述元问题/能力类问题必须设置 `is_simple_question=true` 和 `direct_response=true`
- **禁止行为**：不得对上述问题返回通用「除了安全事件处理外...」文案

### 2. loader.py Return Format 补充

在 `get_intent_phase1_prompt()` 的 Return Format 中新增：

- `is_simple_question`: true|false
- `direct_response`: true|false
- `suggested_alternatives`: []

并增加说明：对简单问题（如「你是谁」「你能做哪些安全工作」等）必须设置 `is_simple_question=true` 和 `direct_response=true`，且 `tasks` 为空。

## 预期效果

修复后，上述问题应分别得到不同回答：

| 问题 | 预期行为 |
|------|----------|
| 你是谁 | 直接回答 Agent 身份与能力（如 MASTER_AGENT 中的角色描述） |
| 你能做哪些安全工作 | 直接列举安全分析、威胁情报、深度研究等能力 |
| 我是谁 | 根据会话上下文回答，或说明需要更多信息 |

## 验证建议

1. 重启 python-agent-service 使提示词生效
2. 依次输入「你是谁」「你能做哪些安全工作」「我是谁」进行测试
3. 确认不再出现统一的「除了安全事件处理外...」回复
