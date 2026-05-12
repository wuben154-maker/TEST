---
# Compiled subgraph: open_deep_research. Execution is graph-driven; this file is optional context.
---

Deep research is executed by the compiled LangGraph pipeline (search, synthesis, report). Use global `/skills/deep-research/` documentation when the model reads SKILL.md for user-facing guidance.

## Human-in-the-loop (when enabled)

- **`interrupt_on`**: Pauses on operator-configured tool calls for human approve/edit/reject before execution.
- **`request_user_input`**: Use for custom structured prompts (choices, form, text); not a substitute for standard tool-review flows unless the product maps them the same way.
