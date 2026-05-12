# Proposal: Common tool registry + ToolSpec (python-agent-service)

## Problem

- `create_common_tools()` used a long `if/elif` chain for tiered YAML assembly, making new tools easy to miss (`common_tools_no_impl`) and mixing policy with mounting logic.
- No single place for tool metadata (risk category) to support future truncation or sub-agent policy.

## Goals

- Introduce **`COMMON_TOOL_MOUNTERS`**: `tool_name -> callable` that appends `StructuredTool` instances, preserving YAML order and existing behavior.
- Introduce **`ToolSpec`** with minimal fields (`name`, `category`, `risk`) for documentation and future policy hooks.
- Keep **`tool_presentation.yaml`** as the source of enabled/description/order for tiered mode; no breaking change to SSE or LangChain tool names.

## Non-goals

- Changing email/web standalone factories (`create_email_tools` / `create_web_tools`) in this slice (optional follow-up).
- Implementing result truncation or permission pipelines (future).

## Success metrics

- All existing tests for `create_common_tools` / `create_research_tools` pass.
- New test: registered common tool names cover security + `search_history` + research trio.
- `docs/TOOLS_AND_REGISTRY.md` documents the add-tool checklist.

## Dependencies

- `app/sse/tool_presentation.py` (`COMMON_SECURITY_TOOL_ORDER`, `RESEARCH_TOOL_ORDER`, tiered YAML).
