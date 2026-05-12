"""Middleware for providing subagents to an agent via a `task` tool."""

# =============================================================================
# SECMANUS VENDOR FORK NOTICE (DeepAgents upstream: langchain-ai/deepagents)
# =============================================================================
# This file is vendored from the official DeepAgents package. Local edits are
# wrapped in "SECMANUS PATCH" blocks below.
#
# When upgrading / merging upstream DeepAgents:
#   1. Diff this file against the new upstream `middleware/subagents.py`.
#   2. Re-apply every block marked `# --- SECMANUS PATCH: ... ---`.
#   3. See `SECMANUS_VENDOR_PATCHES.md` in this directory for a patch checklist.
# Related (non-upstream) code: `app/parsers/deepagents_stream_adapter.py` sets
#   `configurable["subagent_sse_event_queue"]` consumed here via `invoke_cfg`.
# =============================================================================

import asyncio
import dataclasses
import json
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NotRequired, TypedDict, cast

import structlog

from app.parsers.final_message_split import subagent_sse_visible_text
from app.parsers.message_content import (
    aimessage_to_handoff_plain_text,
    content_blocks_to_plain_text,
)
from app.billing.llm_usage_per_invoke import LlmUsagePerInvokeCallbackHandler
from app.parsers.llm_invoke_callbacks import (
    LlmInvokeLifecycleCallbackHandler,
    flatten_runnable_callbacks,
)
from app.parsers.llm_invoke_sse import LlmInvokeEmitter
from app.parsers.react_turn import ReactTurnTracker, attach_turn_to_event

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import AgentMiddleware, ContextT, ModelRequest, ModelResponse, ResponseT
from langchain.agents.structured_output import ResponseFormat
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel
# --- SECMANUS PATCH: imports (extend messages/runnables for SSE bridge; asyncio above) ---
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
# --- end SECMANUS PATCH (imports); upstream was: HumanMessage, ToolMessage, Runnable only ---
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from app._vendor.deepagents.backends.protocol import BackendFactory, BackendProtocol
from app._vendor.deepagents.middleware._utils import append_to_system_message
from app._vendor.deepagents.middleware.permissions import FilesystemPermission

_logger = structlog.get_logger(__name__)


def _log_task_tool_invoke_start(
    *,
    subagent_type: str,
    tool_call_id: str,
    invoke_cfg: dict[str, Any],
    description: str,
) -> None:
    """Structured log when ``task()`` / ``atask()`` begins a nested subagent run (grep: binary-analysis)."""
    conf = dict(invoke_cfg.get("configurable") or {})
    preview = (description or "").replace("\n", " ").strip()
    if len(preview) > 200:
        preview = preview[:197] + "..."
    _logger.info(
        "subagent_task_invoke_start",
        subagent_type=subagent_type,
        task_tool_call_id=tool_call_id,
        delegation_depth=conf.get("delegation_depth"),
        delegation_root_tool_call_id=conf.get("delegation_root_tool_call_id"),
        delegation_parent_tool_call_id=conf.get("delegation_parent_tool_call_id"),
        description_preview=preview or None,
    )


class SubAgent(TypedDict):
    """Specification for an agent.

    When using `create_deep_agent`, subagents automatically receive a default middleware
    stack (TodoListMiddleware, FilesystemMiddleware, SummarizationMiddleware, etc.) before
    any custom `middleware` specified in this spec.

    Required fields:
        name: Unique identifier for the subagent.

            The main agent uses this name when calling the `task()` tool.
        description: What this subagent does.

            Be specific and action-oriented. The main agent uses this to decide when to delegate.
        system_prompt: Instructions for the subagent.

            Include tool usage guidance and output format requirements.

    Optional fields:
        tools: Tools the subagent can use.

            If not specified, inherits tools from the main agent via `default_tools`.
        model: Override the main agent's model.

            Use the format `'provider:model-name'` (e.g., `'openai:gpt-4o'`).
        middleware: Additional middleware for custom behavior, logging, or rate limiting.
        interrupt_on: Configure human-in-the-loop for specific tools.

            Requires a checkpointer.
        skills: Skill source paths for SkillsMiddleware.

            List of paths to skill directories (e.g., `["/skills/user/", "/skills/project/"]`).
    """

    name: str
    """Unique identifier for the subagent."""

    description: str
    """What this subagent does. The main agent uses this to decide when to delegate."""

    system_prompt: str
    """Instructions for the subagent."""

    tools: NotRequired[Sequence[BaseTool | Callable | dict[str, Any]]]
    """Tools the subagent can use. If not specified, inherits from main agent."""

    model: NotRequired[str | BaseChatModel]
    """Override the main agent's model. Use `'provider:model-name'` format."""

    middleware: NotRequired[list[AgentMiddleware]]
    """Additional middleware for custom behavior."""

    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]
    """Configure human-in-the-loop for specific tools."""

    skills: NotRequired[list[str]]
    """Skill source paths for SkillsMiddleware."""

    permissions: NotRequired[list[FilesystemPermission]]
    """List of ``FilesystemPermission`` rules for this subagent.

    If omitted, inherits the parent agent's permissions. If specified, replaces
    the parent's permissions entirely for this subagent.

    Rules are evaluated in declaration order; the first match wins.
    ``_PermissionMiddleware`` is appended last in the middleware stack.
    """

    response_format: NotRequired[ResponseFormat[Any] | type | dict[str, Any]]
    """Structured output response format for the subagent.

    When specified, the subagent will produce a `structured_response` conforming to the
    given schema. The structured response is JSON-serialized and returned as the
    ToolMessage content to the parent agent, replacing the default last-message extraction.

    Accepted formats (from `langchain.agents.structured_output`):

    - `ToolStrategy(schema)`: Use tool calling to extract structured output from the model.
    - `ProviderStrategy(schema)`: Use the model provider's native structured output mode.
    - `AutoStrategy(schema)`: Automatically select the best strategy.
    - A bare Python `type`: A Pydantic `BaseModel` subclass, `dataclass`, or `TypedDict`
      class. Equivalent to `AutoStrategy(schema)`.
    - `dict[str, Any]`: A JSON schema dictionary (e.g.,
      `{"type": "object", "properties": {...}, "required": [...]}`).

    Example:
        ```python
        from pydantic import BaseModel

        class Findings(BaseModel):
            findings: str
            confidence: float

        analyzer: SubAgent = {
            "name": "analyzer",
            "description": "Analyzes data and returns structured findings",
            "system_prompt": "Analyze the data and return your findings.",
            "model": "openai:gpt-4o",
            "tools": [],
            "response_format": Findings,
        }
        ```
    """


class CompiledSubAgent(TypedDict):
    """A pre-compiled agent spec.

    !!! note

        The runnable's state schema must include a 'messages' key.

        This is required for the subagent to communicate results back to the main agent.

    When the subagent completes, the final message in the 'messages' list will be
    extracted and returned as a `ToolMessage` to the parent agent.
    """

    name: str
    """Unique identifier for the subagent."""

    description: str
    """What this subagent does."""

    runnable: Runnable
    """A custom agent implementation.

    Create a custom agent using either:

    1. LangChain's [`create_agent()`](https://docs.langchain.com/oss/python/langchain/quickstart)
    2. A custom graph using [`langgraph`](https://docs.langchain.com/oss/python/langgraph/quickstart)

    If you're creating a custom graph, make sure the state schema includes a 'messages' key.
    This is required for the subagent to communicate results back to the main agent.
    """


DEFAULT_SUBAGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."

# State keys that are excluded when passing state to subagents and when returning
# updates from subagents.
#
# When returning updates:
# 1. The messages key is handled explicitly to ensure only the final message is included
# 2. The todos and structured_response keys are excluded as they do not have a defined reducer
#    and no clear meaning for returning them from a subagent to the main agent.
# 3. The skills_metadata and memory_contents keys are automatically excluded from subagent output
#    via PrivateStateAttr annotations on their respective state schemas. However, they must ALSO
#    be explicitly filtered from runtime.state when invoking a subagent to prevent parent state
#    from leaking to child agents (e.g., the general-purpose subagent loads its own skills via
#    SkillsMiddleware).
_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response", "skills_metadata", "memory_contents"}


class TaskToolSchema(BaseModel):
    """Input schema for the `task` tool."""

    description: str = Field(
        description=(
            "A detailed description of the task for the subagent to perform autonomously. "
            "Include all necessary context and specify the expected output format."
        )
    )
    subagent_type: str = Field(description=("The type of subagent to use. Must be one of the available agent types listed in the tool description."))


TASK_TOOL_DESCRIPTION = """Launch an ephemeral subagent to handle complex, multi-step independent tasks with isolated context windows.

Available agent types and the tools they have access to:
{available_agents}

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

## Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to create content, perform analysis, or just do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
6. If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
7. When only the general-purpose agent is provided, you should use it for all tasks. It is great for isolating context and token usage, and completing specific, complex tasks, as it has all the same capabilities as the main agent.

### Example usage of the general-purpose agent:

<example_agent_descriptions>
"general-purpose": use this agent for general purpose tasks, it has access to all tools as the main agent.
</example_agent_descriptions>

<example>
User: "I want to conduct research on the accomplishments of Lebron James, Michael Jordan, and Kobe Bryant, and then compare them."
Assistant: *Uses the task tool in parallel to conduct isolated research on each of the three players*
Assistant: *Synthesizes the results of the three isolated research tasks and responds to the User*
<commentary>
Research is a complex, multi-step task in it of itself.
The research of each individual player is not dependent on the research of the other players.
The assistant uses the task tool to break down the complex objective into three isolated tasks.
Each research task only needs to worry about context and tokens about one player, then returns synthesized information about each player as the Tool Result.
This means each research task can dive deep and spend tokens and context deeply researching each player, but the final result is synthesized information, and saves us tokens in the long run when comparing the players to each other.
</commentary>
</example>

<example>
User: "Analyze a single large code repository for security vulnerabilities and generate a report."
Assistant: *Launches a single `task` subagent for the repository analysis*
Assistant: *Receives report and integrates results into final summary*
<commentary>
Subagent is used to isolate a large, context-heavy task, even though there is only one. This prevents the main thread from being overloaded with details.
If the user then asks followup questions, we have a concise report to reference instead of the entire history of analysis and tool calls, which is good and saves us time and money.
</commentary>
</example>

<example>
User: "Schedule two meetings for me and prepare agendas for each."
Assistant: *Calls the task tool in parallel to launch two `task` subagents (one per meeting) to prepare agendas*
Assistant: *Returns final schedules and agendas*
<commentary>
Tasks are simple individually, but subagents help silo agenda preparation.
Each subagent only needs to worry about the agenda for one meeting.
</commentary>
</example>

<example>
User: "I want to order a pizza from Dominos, order a burger from McDonald's, and order a salad from Subway."
Assistant: *Calls tools directly in parallel to order a pizza from Dominos, a burger from McDonald's, and a salad from Subway*
<commentary>
The assistant did not use the task tool because the objective is super simple and clear and only requires a few trivial tool calls.
It is better to just complete the task directly and NOT use the `task` tool.
</commentary>
</example>

### Example usage with custom agents:

<example_agent_descriptions>
"content-reviewer": use this agent after you are done creating significant content or documents
"greeting-responder": use this agent when to respond to user greetings with a friendly joke
"research-analyst": use this agent to conduct thorough research on complex topics
</example_agent_descriptions>

<example>
user: "Please write a function that checks if a number is prime"
assistant: Sure let me write a function that checks if a number is prime
assistant: First let me use the Write tool to write a function that checks if a number is prime
assistant: I'm going to use the Write tool to write the following code:
<code>
function isPrime(n) {{
  if (n <= 1) return false
  for (let i = 2; i * i <= n; i++) {{
    if (n % i === 0) return false
  }}
  return true
}}
</code>
<commentary>
Since significant content was created and the task was completed, now use the content-reviewer agent to review the work
</commentary>
assistant: Now let me use the content-reviewer agent to review the code
assistant: Uses the Task tool to launch with the content-reviewer agent
</example>

<example>
user: "Can you help me research the environmental impact of different renewable energy sources and create a comprehensive report?"
<commentary>
This is a complex research task that would benefit from using the research-analyst agent to conduct thorough analysis
</commentary>
assistant: I'll help you research the environmental impact of renewable energy sources. Let me use the research-analyst agent to conduct comprehensive research on this topic.
assistant: Uses the Task tool to launch with the research-analyst agent, providing detailed instructions about what research to conduct and what format the report should take
</example>

<example>
user: "Hello"
<commentary>
Since the user is greeting, use the greeting-responder agent to respond with a friendly joke
</commentary>
assistant: "I'm going to use the Task tool to launch with the greeting-responder agent"
</example>"""  # noqa: E501

TASK_SYSTEM_PROMPT = """## `task` (subagent spawner)

You have access to a `task` tool to launch short-lived subagents that handle isolated tasks. These agents are ephemeral — they live only for the duration of the task and return a single result.

When to use the task tool:
- When a task is complex and multi-step, and can be fully delegated in isolation
- When a task is independent of other tasks and can run in parallel
- When a task requires focused reasoning or heavy token/context usage that would bloat the orchestrator thread
- When sandboxing improves reliability (e.g. code execution, structured searches, data formatting)
- When you only care about the output of the subagent, and not the intermediate steps (ex. performing a lot of research and then returned a synthesized report, performing a series of computations or lookups to achieve a concise, relevant answer.)

Subagent lifecycle:
1. **Spawn** → Provide clear role, instructions, and expected output
2. **Run** → The subagent completes the task autonomously
3. **Return** → The subagent provides a single structured result
4. **Reconcile** → Incorporate or synthesize the result into the main thread

When NOT to use the task tool:
- If you need to see the intermediate reasoning or steps after the subagent has completed (the task tool hides them)
- If the task is trivial (a few tool calls or simple lookup)
- If delegating does not reduce token usage, complexity, or context switching
- If splitting would add latency without benefit

## Important Task Tool Usage Notes to Remember
- Whenever possible, parallelize the work that you do. This is true for both tool_calls, and for tasks. Whenever you have independent steps to complete - make tool_calls, or kick off tasks (subagents) in parallel to accomplish them faster. This saves time for the user, which is incredibly important.
- Remember to use the `task` tool to silo independent tasks within a multi-part objective.
- You should use the `task` tool whenever you have a complex task that will take multiple steps, and is independent from other tasks that the agent needs to complete. These agents are highly competent and efficient."""  # noqa: E501


DEFAULT_GENERAL_PURPOSE_DESCRIPTION = "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent."  # noqa: E501

# Base spec for general-purpose subagent (caller adds model, tools, middleware)
GENERAL_PURPOSE_SUBAGENT: SubAgent = {
    "name": "general-purpose",
    "description": DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
    "system_prompt": DEFAULT_SUBAGENT_PROMPT,
}


# --- SECMANUS PATCH: subagent response language via LangGraph configurable ---
def _normalize_subagent_language_code(raw: str | None) -> str:
    """Map configurable language string to en | zh | ja | ko."""
    if not raw:
        return "en"
    s = str(raw).strip().lower()
    if s.startswith("zh-hant") or s in {"zh-tw", "zh-hk"}:
        return "zh-hant"
    base = s.split("-", 1)[0]
    if base == "zh":
        return "zh"
    if base in {"ja", "jp"}:
        return "ja"
    if base in {"ko", "kr"}:
        return "ko"
    if base == "en":
        return "en"
    return "en"


def _subagent_language_system_content(lang: str) -> str:
    """Short system directive so subagent prose matches the session/user language."""
    if lang == "zh":
        return (
            "Response language: Write all natural-language content (WRAPUP and FULL_REPORT "
            "**bodies**, reasoning, tool narration, and conclusions) in **Simplified Chinese (简体中文)**. "
            "Keep the required markdown heading lines for SM_SUBAGENT_* exactly as your system "
            "prompt specifies (those heading tokens stay in English). "
            "Structured data, file paths, IOCs, and code identifiers may stay as-is."
        )
    if lang == "zh-hant":
        return (
            "Response language: Write all natural-language prose (WRAPUP/FULL_REPORT **bodies**, "
            "reasoning, conclusions) in **Traditional Chinese (繁體中文)**. "
            "Keep SM_SUBAGENT_* heading lines exactly as specified in English. "
            "Paths, IOCs, and code may stay as-is."
        )
    if lang == "ja":
        return (
            "Response language: Write all natural-language prose (WRAPUP/FULL_REPORT **bodies**, "
            "reasoning, conclusions) in **Japanese**. Keep SM_SUBAGENT_* heading lines exactly "
            "as specified in English. Paths, IOCs, and code may stay as-is."
        )
    if lang == "ko":
        return (
            "Response language: Write all natural-language prose (WRAPUP/FULL_REPORT **bodies**, "
            "reasoning, conclusions) in **Korean**. Keep SM_SUBAGENT_* heading lines exactly "
            "as specified in English. Paths, IOCs, and code may stay as-is."
        )
    return (
        "Response language: Write all natural-language content (WRAPUP and FULL_REPORT **bodies**, "
        "reasoning, tool narration, and conclusions) in **English**. "
        "Keep required SM_SUBAGENT_* heading lines exactly as specified. "
        "Paths, IOCs, and code identifiers may stay as-is."
    )


def build_subagent_task_messages(description: str, runtime: ToolRuntime) -> list:
    """Build initial messages for a task() subagent (language directive + task payload).

    Prefers ``configurable['subagent_response_language']`` (user/input language from parent);
    falls back to ``configurable['sse_ui_language']`` (UI labels locale).
    """
    cfg = (getattr(runtime, "config", None) or {}).get("configurable") or {}
    raw = cfg.get("subagent_response_language") or cfg.get("sse_ui_language")
    lang = _normalize_subagent_language_code(raw if raw is not None else None)
    return [
        SystemMessage(content=_subagent_language_system_content(lang)),
        HumanMessage(content=description),
    ]


# --- end SECMANUS PATCH (subagent response language) ---


# --- SECMANUS PATCH: subagent -> main SSE bridge (start) ---
#
# Purpose: Forward subagent progress events (tool_call, tool_result, reasoning)
# into the main SSE stream for real-time frontend display.
#
# Delivery mechanism (preferred → fallback):
#   1. stream_writer (LangGraph StreamWriter): writes directly into the parent
#      graph's "custom" stream channel, yielded in real-time while the task()
#      tool is executing — eliminates the queue-flush timing problem where the
#      main astream() loop is blocked during tool execution.
#   2. subagent_sse_event_queue (asyncio.Queue): legacy side-channel kept for
#      the open_deep_research RunnableLambda path, which manages its own
#      internal queue writes. Events are flushed by adapt_astream_to_sse at
#      the start of each main-loop iteration (batch delivery after tool ends).
#
# Upstream merge checklist (run when rebasing against new deepagents release):
#   [ ] _tool_output_text_for_sse         — new helper; safe to keep as-is
#   [ ] _extract_subagent_thinking_and_text — new helper; safe to keep as-is
#   [ ] _ainvoke_subagent_with_sse_queue  — entirely new function; keep block
#         Signature change vs. original: added `stream_writer` kwarg (None OK)
#   [ ] atask() patch inside _build_task_tool:
#         + reads runtime.stream_writer
#         + passes it to _ainvoke_subagent_with_sse_queue
#         (search for "SECMANUS PATCH: async path" below)
#
# Remove this entire block (and the atask patch) when dropping the feature.


def _tool_output_text_for_sse(content: Any) -> str:
    """Normalize tool result content to a string for SSE (no bridge truncation)."""
    if isinstance(content, str):
        text = content
    else:
        text = str(content) if content is not None else ""
    return text.strip()


def _derive_tool_status(content: Any) -> str:
    """Proxy to ``app.parsers.tool_status.derive_tool_status``.

    Kept here so callers within the vendor middleware don't need to import
    from ``app.parsers`` directly (avoids circular imports at module level).
    The real implementation lives in ``app/parsers/tool_status.py``.
    """
    from app.parsers.tool_status import derive_tool_status
    return derive_tool_status(content)


def _extract_subagent_thinking_and_text(msg: AIMessage) -> tuple[str, str]:
    """Extract chain-of-thought (thinking) and visible text from an AIMessage.

    Inline variant of deepagents_stream_adapter._extract_thinking_and_text kept
    here to avoid a circular import between vendor code and app parsers. Handles
    Anthropic thinking blocks, OpenAI reasoning_content, and Gemini thought parts.

    Returns:
        (thinking, text) — either may be an empty string.
    """
    thinking_parts: list[str] = []
    text_parts: list[str] = []

    additional = getattr(msg, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        rc = additional.get("reasoning_content")
        if rc:
            thinking_parts.append(rc if isinstance(rc, str) else str(rc))

    content = getattr(msg, "content", None)
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "thinking":
                thinking_parts.append(str(block.get("thinking", "")))
            elif block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("thought") is True:
                thinking_parts.append(str(block.get("text", "")))
            elif "text" in block:
                text_parts.append(str(block.get("text", "")))

    return ("".join(thinking_parts), "".join(text_parts))


# --- SECMANUS PATCH: per-tick message order for subagent SSE (final AIMessage vs ToolMessage) ---
def _stable_subagent_message_delivery_order(messages: list[Any]) -> list[Any]:
    """Reorder one ``values``-tick message slice for stable SSE mirroring."""

    def phase(m: Any) -> int:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            return 0
        if isinstance(m, ToolMessage):
            return 1
        if isinstance(m, AIMessage):
            return 2
        return 3

    indexed = list(enumerate(messages))
    indexed.sort(key=lambda iv: (phase(iv[1]), iv[0]))
    return [m for _, m in indexed]


# --- end SECMANUS PATCH (subagent message delivery order) ---

class _SubagentEagerStartCallback(AsyncCallbackHandler):
    """Emit ``llm_invoke_start`` in real-time when a subagent's LLM call begins."""

    def __init__(self, emitter: LlmInvokeEmitter) -> None:
        super().__init__()
        self._emitter = emitter

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[Any],
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> Any:
        iid = run_id.hex[:12] if hasattr(run_id, "hex") else str(run_id)[:12]
        ts = int(time.time() * 1000)
        self._emitter.pre_open(iid, ts)

    async def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> Any:
        pass

    async def on_llm_error(
        self, error: BaseException, *, run_id: Any, **kwargs: Any
    ) -> Any:
        pass


def _merge_task_delegation_into_invoke_cfg(
    invoke_cfg: dict[str, Any],
    *,
    current_task_tool_call_id: str,
) -> dict[str, Any]:
    """Append delegation chain into Runnable ``configurable`` for nested ``task()`` SSE tagging.

    First hop from an agent that has no ``delegation_root_tool_call_id``: depth=1, root=id.
    Nested hop: depth+=1, parent=id (the nested ``task`` tool_call id starting this subrun).
    """
    cfg = dict(invoke_cfg or {})
    conf = dict(cfg.get("configurable") or {})
    existing_root = conf.get("delegation_root_tool_call_id")
    if not existing_root:
        conf["delegation_root_tool_call_id"] = current_task_tool_call_id
        conf["delegation_depth"] = 1
        conf.pop("delegation_parent_tool_call_id", None)
    else:
        conf["delegation_depth"] = int(conf.get("delegation_depth") or 1) + 1
        conf["delegation_parent_tool_call_id"] = current_task_tool_call_id
    cfg["configurable"] = conf
    return cfg


def _delegation_tags_from_configurable(conf: dict[str, Any]) -> dict[str, Any]:
    """Map configurable delegation_* keys to camelCase SSE envelope fields."""
    out: dict[str, Any] = {}
    dep_depth = conf.get("delegation_depth")
    dep_root = conf.get("delegation_root_tool_call_id")
    dep_parent = conf.get("delegation_parent_tool_call_id")
    if dep_depth is not None:
        try:
            out["delegationDepth"] = int(dep_depth)
        except (TypeError, ValueError):
            pass
    if dep_root:
        out["rootDelegationId"] = str(dep_root)
    if dep_parent and out.get("delegationDepth", 0) >= 2:
        out["parentToolCallId"] = str(dep_parent)
    return out


async def _ainvoke_subagent_with_sse_queue(
    subagent: Runnable,
    subagent_state: dict[str, Any],
    invoke_cfg: dict[str, Any],
    subagent_type: str,
    stream_writer: Any | None = None,
) -> dict[str, Any]:
    """Run subagent once; mirror progress events into the main SSE stream."""
    cfg_in = invoke_cfg or {}
    configurable = cfg_in.get("configurable") or {}
    _deleg_ctx = _delegation_tags_from_configurable(configurable)
    queue = configurable.get("subagent_sse_event_queue")
    sub_turn = ReactTurnTracker() if (stream_writer is not None or queue) else None

    def _tag_delegation(ev: dict[str, Any]) -> None:
        if not _deleg_ctx:
            return
        for k, v in _deleg_ctx.items():
            ev.setdefault(k, v)

    # True when this subagent is nested inside another subagent (depth >= 2).
    # LangGraph propagates stream_writer writes up to the outermost astream that
    # includes "custom" mode (the main adapter).  At depth >= 2, using BOTH
    # stream_writer AND queue delivers every event twice: once via t_chunk
    # (stream_writer, lower seq) and once via t_sub (queue, higher seq).
    # Email-security events (depth=1) arrive between the two copies via their
    # own stream_writer, causing delegationStreamKey to alternate and producing
    # repeated delegation banners in the UI.  Queue-only at depth >= 2 avoids
    # duplicates while still reliably delivering all events (main adapter's t_sub
    # drains the queue in real-time while t_chunk is blocked on the tool node).
    _nested_subagent = _deleg_ctx.get("delegationDepth", 0) >= 2

    def _push(ev: dict[str, Any]) -> None:
        _tag_delegation(ev)
        if _nested_subagent:
            # depth >= 2: queue-only to prevent duplicate / interleaved delivery.
            if queue is not None:
                try:
                    queue.put_nowait(ev)
                except asyncio.QueueFull:
                    pass
            elif stream_writer is not None:  # fallback when no queue
                try:
                    stream_writer(ev)
                except Exception:
                    pass
            return
        if stream_writer is not None:
            try:
                stream_writer(ev)
            except Exception:
                pass
        elif queue is not None:
            try:
                queue.put_nowait(ev)
            except asyncio.QueueFull:
                pass

    def _emit_sa(ev: dict[str, Any]) -> dict[str, Any]:
        t = ev.get("type")
        if t in ("llm_invoke_start", "llm_delta", "llm_invoke_end"):
            ev.setdefault("subagentName", subagent_type)
            ev.setdefault("scope", "subagent")
            ev.setdefault("subagentStream", True)
        if sub_turn:
            attach_turn_to_event(ev, sub_turn)
        _push(ev)
        return ev

    # --- SECMANUS PATCH: nested subagent lifecycle step events (start) ---
    # Emits visible ``step`` events bracketing this nested subagent's run so
    # the UI timeline shows clear "binary-analysis running / done" boundaries
    # instead of an unattributed stream of "Thought brief" entries.
    # phaseId enables frontend mergePhaseIdMilestoneStepsAtMinSeq: the
    # "running" event appears at first, then "done" overlays it in-place.
    _lifecycle_phase_id = (
        f"sa-lifecycle-{subagent_type}-"
        f"{_deleg_ctx.get('rootDelegationId', '') or 'default'}"
    )

    def _push_lifecycle_step(status: str, detail: str | None = None) -> None:
        """Push a ``step`` SSE event for this nested subagent's lifecycle.

        Unlike ``_push`` (which prefers stream_writer and silently skips queue
        when stream_writer is set), this helper fans out to BOTH channels so the
        event reaches the main adapter regardless of whether the stream_writer
        here writes to a captured or uncaptured LangGraph custom channel.
        Duplicate-suppression is handled by the frontend's phaseId merge.
        """
        if stream_writer is None and not queue:
            return
        ev: dict[str, Any] = {
            "type": "step",
            "id": f"sa-lifecycle-{subagent_type}",
            "label": subagent_type,
            "status": status,
            "scope": "subagent",
            "subagentName": subagent_type,
            "subagentStream": True,
            "phaseId": _lifecycle_phase_id,
        }
        if detail:
            ev["detail"] = detail
        _tag_delegation(ev)
        # Use the same delivery strategy as _push: queue-only at depth >= 2 to
        # avoid duplicate delivery (phaseId deduplication handles the depth=1
        # fan-out case where both stream_writer and queue are used).
        if _nested_subagent:
            if queue is not None:
                try:
                    queue.put_nowait(ev)
                except asyncio.QueueFull:
                    pass
            elif stream_writer is not None:
                try:
                    stream_writer(ev)
                except Exception:
                    pass
            return
        # depth=1: fan-out for reliability (phaseId deduplicates at frontend)
        if stream_writer is not None:
            try:
                stream_writer(ev)
            except Exception:
                pass
        if queue is not None:
            try:
                queue.put_nowait(ev)
            except asyncio.QueueFull:
                pass
    # --- SECMANUS PATCH: nested subagent lifecycle step events (end) ---

    def _merge_cfg_with_usage_callback(cfg: dict[str, Any]) -> dict[str, Any]:
        cbs = flatten_runnable_callbacks(cfg.get("callbacks"))
        if any(isinstance(h, LlmUsagePerInvokeCallbackHandler) for h in cbs):
            return {**cfg, "callbacks": cbs}
        return {**cfg, "callbacks": [*cbs, LlmUsagePerInvokeCallbackHandler()]}

    llm_sa = LlmInvokeEmitter(_emit_sa, emit_boundaries=True)

    _cfg_callbacks = (
        flatten_runnable_callbacks(cfg_in.get("callbacks")) if isinstance(cfg_in, dict) else []
    )
    _callbacks_without_lifecycle = [
        h for h in _cfg_callbacks
        if not isinstance(h, LlmInvokeLifecycleCallbackHandler)
    ]
    if len(_callbacks_without_lifecycle) != len(_cfg_callbacks):
        cfg_in = {**cfg_in, "callbacks": _callbacks_without_lifecycle}

    def _close_llm_sa_with_subagent_invoke_end(
        usage: Any | None = None,
    ) -> None:
        # SECMANUS PATCH: forward AIMessage.usage_metadata so the realtime
        # context-usage indicator can attribute tokens to this subagent.
        for _ in llm_sa.close(usage=usage):
            pass

    # SECMANUS PATCH (Path A): When stream_writer is available, inject it into
    # the configurable dict so the RunnableLambda implementation can retrieve it
    # as "subagent_stream_writer" and write events in real-time.
    def _wrap_subagent_stream_writer(sw: Any | None) -> Any | None:
        if sw is None:
            return None

        def _inner(ev: dict[str, Any]) -> None:
            _tag_delegation(ev)
            try:
                sw(ev)
            except Exception:
                pass

        return _inner

    if isinstance(subagent, RunnableLambda):
        _push_lifecycle_step("running")
        try:
            if stream_writer is not None:
                _lambda_cfg = _merge_cfg_with_usage_callback(dict(cfg_in))
                _lambda_cfgable = dict(_lambda_cfg.get("configurable") or {})
                _lambda_cfgable["subagent_stream_writer"] = _wrap_subagent_stream_writer(stream_writer)
                _lambda_cfg["configurable"] = _lambda_cfgable
                return await subagent.ainvoke(subagent_state, config=_lambda_cfg)
            return await subagent.ainvoke(
                subagent_state, config=_merge_cfg_with_usage_callback(dict(cfg_in))
            )
        finally:
            _push_lifecycle_step("done")

    if stream_writer is None and not queue:
        return await subagent.ainvoke(
            subagent_state, config=_merge_cfg_with_usage_callback(dict(cfg_in))
        )

    if not hasattr(subagent, "astream"):
        _push_lifecycle_step("running")
        try:
            return await subagent.ainvoke(
                subagent_state, config=_merge_cfg_with_usage_callback(dict(cfg_in))
            )
        finally:
            _push_lifecycle_step("done")

    _eager_cb = _SubagentEagerStartCallback(llm_sa)
    _base_cbs = list(_callbacks_without_lifecycle)
    if not any(isinstance(h, LlmUsagePerInvokeCallbackHandler) for h in _base_cbs):
        _base_cbs.append(LlmUsagePerInvokeCallbackHandler())
    cfg_in = {**cfg_in, "callbacks": [*_base_cbs, _eager_cb]}

    astream_kw: dict[str, Any] = {"stream_mode": "values"}
    try:
        import langgraph  # noqa: PLC0415
        if hasattr(langgraph, "__version__") and langgraph.__version__ >= "1.1":
            astream_kw["version"] = "v2"
    except Exception:
        pass

    # --- SECMANUS PATCH: subagent total-duration timeout ---
    from app.config import get_settings as _get_sa_settings  # noqa: PLC0415
    _sa_timeout = getattr(_get_sa_settings(), "subagent_timeout_seconds", 0) or None

    last_state: dict[str, Any] | None = None
    prev_msg_len = 0
    tick = 0
    _push_lifecycle_step("running")
    try:
        try:
            async with asyncio.timeout(_sa_timeout):
                async for chunk in subagent.astream(subagent_state, config=cfg_in, **astream_kw):
                    tick += 1
                    if not isinstance(chunk, dict):
                        continue
                    last_state = chunk
                    msgs = chunk.get("messages")
                    if isinstance(msgs, list) and len(msgs) > prev_msg_len:
                        new_msgs = _stable_subagent_message_delivery_order(msgs[prev_msg_len:])
                        for msg in new_msgs:
                            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                                _thinking, _vis_tc = _extract_subagent_thinking_and_text(msg)
                                if _thinking:
                                    for _ in llm_sa.delta("reasoning", _thinking):
                                        pass
                                if _vis_tc.strip():
                                    for _ in llm_sa.delta("text", _vis_tc.strip()):
                                        pass
                                _close_llm_sa_with_subagent_invoke_end(
                                    usage=getattr(msg, "usage_metadata", None),
                                )
                                for tc in msg.tool_calls or []:
                                    tc_id = str(tc.get("id", "") or "")
                                    _tc_ev: dict[str, Any] = {
                                        "type": "tool_call",
                                        "id": tc_id or f"tc-{tick}",
                                        "toolName": tc.get("name", ""),
                                        "toolInput": tc.get("args", {}) or {},
                                        "status": "running",
                                        "subagentName": subagent_type,
                                    }
                                    if sub_turn:
                                        attach_turn_to_event(_tc_ev, sub_turn)
                                    _push(_tc_ev)
                            elif isinstance(msg, AIMessage):
                                _thinking, _vis_final = _extract_subagent_thinking_and_text(msg)
                                if _thinking:
                                    for _ in llm_sa.delta("reasoning", _thinking):
                                        pass
                                _sse_visible = subagent_sse_visible_text(_vis_final)
                                if _sse_visible.strip():
                                    for _ in llm_sa.delta("text", _sse_visible.strip()):
                                        pass
                                _close_llm_sa_with_subagent_invoke_end(
                                    usage=getattr(msg, "usage_metadata", None),
                                )
                            elif isinstance(msg, ToolMessage):
                                tc_id = str(getattr(msg, "tool_call_id", "") or "")
                                tool_name = str(getattr(msg, "name", None) or "")
                                _raw_content = getattr(msg, "content", "")
                                _tr_ev: dict[str, Any] = {
                                    "type": "tool_result",
                                    "id": tc_id,
                                    "toolName": tool_name,
                                    "toolOutput": _tool_output_text_for_sse(_raw_content),
                                    "status": _derive_tool_status(_raw_content),
                                    "subagentName": subagent_type,
                                }
                                if sub_turn:
                                    attach_turn_to_event(_tr_ev, sub_turn)
                                _push(_tr_ev)
                        prev_msg_len = len(msgs)
        except TimeoutError:
            import structlog as _sl  # noqa: PLC0415
            _sl.get_logger().warning(
                "subagent_timeout", subagent=subagent_type,
                timeout=_sa_timeout,
            )
            if last_state is not None:
                return last_state
            return {"messages": [AIMessage(content=f"[Subagent '{subagent_type}' timed out after {_sa_timeout}s]")]}
        except Exception:
            return await subagent.ainvoke(subagent_state, config=cfg_in)

        if last_state is not None:
            return last_state
        return await subagent.ainvoke(subagent_state, config=cfg_in)
    finally:
        _push_lifecycle_step("done")


# --- SECMANUS PATCH: subagent -> main SSE bridge (end) ---


class _SubagentSpec(TypedDict):
    """Internal spec for building the task tool."""

    name: str
    description: str
    runnable: Runnable


def _build_task_tool(  # noqa: C901
    subagents: list[_SubagentSpec],
    task_description: str | None = None,
) -> BaseTool:
    """Create a task tool from pre-built subagent graphs.

    Args:
        subagents: List of subagent specs containing name, description, and runnable.
        task_description: Custom description for the task tool. If `None`,
            uses default template. Supports `{available_agents}` placeholder.

    Returns:
        A StructuredTool that can invoke subagents by type.
    """
    # Build the graphs dict and descriptions from the unified spec list
    subagent_graphs: dict[str, Runnable] = {spec["name"]: spec["runnable"] for spec in subagents}
    subagent_description_str = "\n".join(f"- {s['name']}: {s['description']}" for s in subagents)

    # Use custom description if provided, otherwise use default template
    if task_description is None:
        description = TASK_TOOL_DESCRIPTION.format(available_agents=subagent_description_str)
    elif "{available_agents}" in task_description:
        description = task_description.format(available_agents=subagent_description_str)
    else:
        description = task_description

    def _return_command_with_state_update(result: dict, tool_call_id: str) -> Command:
        # Validate that the result contains a 'messages' key
        if "messages" not in result:
            error_msg = (
                "CompiledSubAgent must return a state containing a 'messages' key. "
                "Custom StateGraphs used with CompiledSubAgent should include 'messages' "
                "in their state schema to communicate results back to the main agent."
            )
            raise ValueError(error_msg)

        state_update = {k: v for k, v in result.items() if k not in _EXCLUDED_STATE_KEYS}

        structured = result.get("structured_response")
        if structured is not None:
            if hasattr(structured, "model_dump_json"):
                content: str = structured.model_dump_json()
            elif dataclasses.is_dataclass(structured) and not isinstance(structured, type):
                content = json.dumps(dataclasses.asdict(structured))
            else:
                content = json.dumps(structured)
        else:
            # Include thinking/reasoning blocks — AIMessage.text is text-channel only and
            # would drop SM_SUBAGENT_FULL_REPORT if the model put it in thinking blocks.
            last_msg = result["messages"][-1]
            if isinstance(last_msg, AIMessage):
                message_text = aimessage_to_handoff_plain_text(last_msg).rstrip()
            else:
                message_text = content_blocks_to_plain_text(
                    getattr(last_msg, "content", None)
                ).rstrip()
                if not message_text:
                    message_text = (getattr(last_msg, "text", None) or "").rstrip()
            content = message_text

        return Command(
            update={
                **state_update,
                "messages": [ToolMessage(content, tool_call_id=tool_call_id)],
            }
        )

    def _validate_and_prepare_state(subagent_type: str, description: str, runtime: ToolRuntime) -> tuple[Runnable, dict]:
        """Prepare state for invocation."""
        subagent = subagent_graphs[subagent_type]
        # Create a new state dict to avoid mutating the original
        subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
        # SECMANUS: language directive from parent configurable (see build_subagent_task_messages)
        subagent_state["messages"] = build_subagent_task_messages(description, runtime)
        return subagent, subagent_state

    def task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)
        subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
        # --- SECMANUS PATCH: sync task() must not use subagent.invoke — async-only tools ---
        # Binary subagent tools (bash/python_exec/...) raise NotImplementedError on
        # .invoke; mirror atask() via _ainvoke_subagent_with_sse_queue.
        invoke_cfg = _merge_task_delegation_into_invoke_cfg(
            dict(getattr(runtime, "config", None) or {}),
            current_task_tool_call_id=str(runtime.tool_call_id),
        )
        _log_task_tool_invoke_start(
            subagent_type=subagent_type,
            tool_call_id=str(runtime.tool_call_id),
            invoke_cfg=invoke_cfg,
            description=description,
        )
        _stream_writer = getattr(runtime, "stream_writer", None)
        coro_main = _ainvoke_subagent_with_sse_queue(
            subagent,
            subagent_state,
            invoke_cfg,
            subagent_type,
            stream_writer=_stream_writer,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(coro_main)
        else:
            # Sync task() entered while the main loop is running: cannot asyncio.run here.
            _loop_for_sw: asyncio.AbstractEventLoop | None
            try:
                _loop_for_sw = asyncio.get_running_loop()
            except RuntimeError:
                _loop_for_sw = None

            def _threadsafe_stream_writer(base: Any) -> Any | None:
                """Marshals writes onto the loop thread so LangGraph ``stream_writer`` stays safe."""
                if base is None:
                    return None
                if _loop_for_sw is None or not callable(base):
                    return base

                def _forward(ev: dict[str, Any]) -> None:
                    def _call() -> None:
                        try:
                            base(ev)
                        except Exception:
                            pass

                    try:
                        _loop_for_sw.call_soon_threadsafe(_call)
                    except Exception:
                        try:
                            base(ev)
                        except Exception:
                            pass

                return _forward

            cfg_offthread = dict(invoke_cfg or {})
            _cfg_off = dict(cfg_offthread.get("configurable") or {})
            _cfg_off.pop("subagent_sse_event_queue", None)
            cfg_offthread["configurable"] = _cfg_off
            _sw_offthread = _threadsafe_stream_writer(_stream_writer)
            coro_off = _ainvoke_subagent_with_sse_queue(
                subagent,
                subagent_state,
                cfg_offthread,
                subagent_type,
                stream_writer=_sw_offthread,
            )
            import concurrent.futures as _cf  # noqa: PLC0415

            with _cf.ThreadPoolExecutor(max_workers=1) as ex:
                result = ex.submit(lambda: asyncio.run(coro_off)).result()
        # --- end SECMANUS PATCH (sync task) ---
        return _return_command_with_state_update(result, runtime.tool_call_id)

    async def atask(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)
        subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
        # --- SECMANUS PATCH: async path uses _ainvoke_subagent_with_sse_queue instead of bare ainvoke ---
        invoke_cfg = _merge_task_delegation_into_invoke_cfg(
            dict(getattr(runtime, "config", None) or {}),
            current_task_tool_call_id=str(runtime.tool_call_id),
        )
        _log_task_tool_invoke_start(
            subagent_type=subagent_type,
            tool_call_id=str(runtime.tool_call_id),
            invoke_cfg=invoke_cfg,
            description=description,
        )
        _stream_writer = getattr(runtime, "stream_writer", None)
        result = await _ainvoke_subagent_with_sse_queue(
            subagent, subagent_state, invoke_cfg, subagent_type,
            stream_writer=_stream_writer,
        )
        # --- end SECMANUS PATCH (atask) ---
        return _return_command_with_state_update(result, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=description,
        infer_schema=False,
        args_schema=TaskToolSchema,
    )


class SubAgentMiddleware(AgentMiddleware[Any, ContextT, ResponseT]):
    """Middleware for providing subagents to an agent via a `task` tool.

    This middleware adds a `task` tool to the agent that can be used to invoke subagents.
    Subagents are useful for handling complex tasks that require multiple steps, or tasks
    that require a lot of context to resolve.

    A chief benefit of subagents is that they can handle multi-step tasks, and then return
    a clean, concise response to the main agent.

    Subagents are also great for different domains of expertise that require a narrower
    subset of tools and focus.

    Args:
        backend: Backend for file operations and execution.
        subagents: List of fully-specified subagent configs. Each SubAgent
            must specify `model` and `tools`. Optional `interrupt_on` on
            individual subagents is respected.
        system_prompt: Instructions appended to main agent's system prompt
            about how to use the task tool.
        task_description: Custom description for the task tool.

    Example:
        ```python
        from app._vendor.deepagents.middleware import SubAgentMiddleware
        from langchain.agents import create_agent

        agent = create_agent(
            "openai:gpt-4o",
            middleware=[
                SubAgentMiddleware(
                    backend=my_backend,
                    subagents=[
                        {
                            "name": "researcher",
                            "description": "Research agent",
                            "system_prompt": "You are a researcher.",
                            "model": "openai:gpt-4o",
                            "tools": [search_tool],
                        }
                    ],
                )
            ],
        )
        ```

    """

    def __init__(
        self,
        *,
        backend: BackendProtocol | BackendFactory,
        subagents: Sequence[SubAgent | CompiledSubAgent],
        system_prompt: str | None = TASK_SYSTEM_PROMPT,
        task_description: str | None = None,
    ) -> None:
        """Initialize the `SubAgentMiddleware`."""
        super().__init__()

        if not subagents:
            msg = "At least one subagent must be specified"
            raise ValueError(msg)
        self._backend = backend
        self._subagents = subagents
        subagent_specs = self._get_subagents()

        task_tool = _build_task_tool(subagent_specs, task_description)

        # Build system prompt with available agents
        if system_prompt and subagent_specs:
            agents_desc = "\n".join(f"- {s['name']}: {s['description']}" for s in subagent_specs)
            self.system_prompt = system_prompt + "\n\nAvailable subagent types:\n" + agents_desc
        else:
            self.system_prompt = system_prompt

        self.tools = [task_tool]

    def _get_subagents(self) -> list[_SubagentSpec]:
        """Create runnable agents from specs.

        Returns:
            List of subagent specs with name, description, and runnable.
        """
        specs: list[_SubagentSpec] = []

        for spec in self._subagents:
            if "runnable" in spec:
                # CompiledSubAgent - use as-is
                compiled = cast("CompiledSubAgent", spec)
                specs.append({"name": compiled["name"], "description": compiled["description"], "runnable": compiled["runnable"]})
                continue

            # SubAgent - validate required fields
            if "model" not in spec:
                msg = f"SubAgent '{spec['name']}' must specify 'model'"
                raise ValueError(msg)
            if "tools" not in spec:
                msg = f"SubAgent '{spec['name']}' must specify 'tools'"
                raise ValueError(msg)

            # Resolve model if string
            from app._vendor.deepagents._models import resolve_model  # noqa: PLC0415

            model = resolve_model(spec["model"])

            # Use middleware as provided (caller is responsible for building full stack)
            middleware: list[AgentMiddleware] = list(spec.get("middleware", []))

            interrupt_on = spec.get("interrupt_on")
            if interrupt_on:
                middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

            specs.append(
                {
                    "name": spec["name"],
                    "description": spec["description"],
                    "runnable": create_agent(
                        model,
                        system_prompt=spec["system_prompt"],
                        tools=spec["tools"],
                        middleware=middleware,
                        name=spec["name"],
                        response_format=spec.get("response_format"),
                    ),
                }
            )

        return specs

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        """Update the system message to include instructions on using subagents."""
        if self.system_prompt is not None:
            new_system_message = append_to_system_message(request.system_message, self.system_prompt)
            return handler(request.override(system_message=new_system_message))
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """(async) Update the system message to include instructions on using subagents."""
        if self.system_prompt is not None:
            new_system_message = append_to_system_message(request.system_message, self.system_prompt)
            return await handler(request.override(system_message=new_system_message))
        return await handler(request)
