---
version: 1.0.0
description: Event visibility configuration - Controls which events are shown to users
---

# Internal Event Types

Event types listed here are always hidden from users.
Add event types that should never be displayed.

## debug
## trace
## internal

---

# Visible Event Types

Event types listed here are always shown to users (cannot be hidden).
These are important user-facing events.

## conclusion
## error
## done
## understanding
## decision_request
## decision_response
## parameter_request
## parameter_response
## task_plan
## task_complete
## plan_complete
## task_summary
## next_actions

---

# Internal Labels

Exact label matches that mark events as internal (hidden from users).
Both Chinese and English labels are supported.

## init_deep_agent_zh
- label: 初始化 DeepAgent 分析引擎

## init_deep_agent_en
- label: Initializing DeepAgent analysis engine

## init_simple_mode_zh
- label: 初始化简单分析模式

## init_simple_mode_en
- label: Initializing simple analysis mode

## simple_mode_ready_zh
- label: 简单分析模式就绪

## simple_mode_ready_en
- label: Simple analysis mode ready

## deep_agent_ready_zh
- label: DeepAgent 分析引擎就绪

## deep_agent_ready_en
- label: DeepAgent analysis engine ready

---

# Internal Label Patterns

Regex patterns for labels that should be hidden.
Use these for flexible matching of similar labels.

## init_engine_zh
- pattern: ^初始化.*分析引擎$

## init_mode_zh
- pattern: ^初始化.*模式$

## mode_ready_zh
- pattern: ^.*模式就绪$

## init_engine_en
- pattern: ^Initializing.*engine$

## init_mode_en
- pattern: ^Initializing.*mode$

## mode_ready_en
- pattern: ^.*mode ready$

## deep_agent_ready_pattern
- pattern: ^DeepAgent.*ready$

## deep_agent_ready_zh_pattern
- pattern: ^DeepAgent.*就绪$

---

# Internal Tool Names

Tool names whose events should always be hidden.
Add tool names here if their execution should not be visible to users.

## internal_debug_tool
## internal_trace_tool
