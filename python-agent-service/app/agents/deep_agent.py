"""DeepAgent Security Analysis - Based on LangChain DeepAgents Architecture.

This is the main entry point for security analysis using the DeepAgents framework
with skill-based sub-agents for progressive disclosure and token efficiency.

Now includes:
- Layered context management (short-term/long-term)
- Main DeepAgent loop handles routing, planning, and synthesis (see MASTER_AGENT.md);
  open_deep_research is reachable only via task(deep-research) subagent, not a pre-route.

Reference:
- https://blog.langchain.com/using-skills-with-deep-agents/
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
"""

import asyncio
from typing import Any, AsyncGenerator

import structlog
from app.agents.subagent_registry import compute_skill_backend_routes
from app.backends import create_layered_backend, create_middleware_backend
from app.config import get_settings
from app.datetime_support import get_app_tz
from app.prompts.skills.discovery import resolve_main_skills_route_plan
from app.llm_gateway import get_model as get_model_from_gateway
from app.llm_gateway.registry import get_registry
from app.middleware.context_retriever import ContextRetriever
from app.middleware.deep_research_synthesis_skip import DeepResearchSynthesisSkipMiddleware
from app.middleware.normalize_tool_call_names import NormalizeToolCallNamesMiddleware
from app.middleware.file_parser import FileInfo, FileParser
from app.parsers.labels import get_intent_label
from app.prompts import MASTER_SYSTEM_PROMPT
from app.prompts.loader import load_prompt
from langchain_core.messages import AIMessage, HumanMessage

logger = structlog.get_logger()


def _detect_language(text: str) -> str:
    """Detect language from user input text using Unicode heuristics.

    Returns: Language code (en, zh, ja, ko).
    """
    if not text:
        return "en"
    # Japanese: contains Hiragana or Katakana
    if any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text):
        return "ja"
    # Chinese: CJK Unified Ideographs
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        return "zh"
    # Korean: Hangul syllables
    if any('\uac00' <= c <= '\ud7a3' for c in text):
        return "ko"
    return "en"


_ALLOWED_RESPONSE_LANG = frozenset({"en", "zh", "ja", "ko"})


def _human_message_content_as_text(content: Any) -> str:
    """Normalize HumanMessage content to plain text (string or LC content blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content else ""


def _first_human_request_text(messages: list[Any] | None) -> str:
    """First non-empty HumanMessage in thread (original user request for language)."""
    if not messages:
        return ""
    for m in messages:
        if isinstance(m, HumanMessage):
            t = _human_message_content_as_text(m.content).strip()
            if t:
                return t
    return ""


def resolve_subagent_language_for_resume(
    snap_values: dict[str, Any] | None,
    *,
    input_language: str = "auto",
) -> str:
    """Language for subagent/LLM output after HITL resume (match first /analyze user text).

    ``input_language`` mirrors POST /analyze: explicit en/zh/ja/ko or ``auto`` (detect from
    checkpoint messages). ``ui_language`` must not be used here — it is for SSE labels only.
    """
    raw = (input_language or "auto").strip().lower()
    if raw in _ALLOWED_RESPONSE_LANG:
        return raw
    text = _first_human_request_text((snap_values or {}).get("messages"))
    return _detect_language(text) if text else "en"


def get_model(model_id: str | None = None):
    """Get the configured LLM model via LLM Gateway.

    Args:
        model_id: Optional model id (e.g. "anthropic/claude-sonnet-4"). Uses default if None.
    """
    return get_model_from_gateway(model_id)


class DeepAgentWithIntent:
    """Session-scoped DeepAgent wrapper (checkpointer, backend, streaming).

    Historical name retains ``WithIntent``. All requests enter the main agent graph;
    deep-research runs only when the model delegates via task(deep-research).
    """

    @property
    def settings(self):
        """App settings; lazy if the instance skipped ``__init__`` (e.g. test doubles)."""
        s = getattr(self, "_settings", None)
        if s is None:
            s = get_settings()
            self._settings = s
        return s

    def __init__(
        self,
        session_id: str = "default",
        model_id: str | None = None,
        checkpointer: Any = None,
    ):
        self.session_id = session_id
        self._settings = get_settings()
        self._model_id = model_id if model_id is not None else get_registry().get_default_model()
        self.model = get_model_from_gateway(model_id)
        self._checkpointer_context = None
        
        # ============================================
        # Backend Setup
        # ============================================

        _skill_routes = compute_skill_backend_routes()
        _main_skills = resolve_main_skills_route_plan()
        self._main_skills_middleware_sources: list[str] | None = (
            _main_skills.middleware_sources if _main_skills.middleware_sources else None
        )

        # Backend factory for create_deep_agent (receives ToolRuntime at runtime)
        self.backend_factory = create_layered_backend(
            bundle_skill_routes=_skill_routes["bundle"],
            skills_subset_routes=_skill_routes["subset"],
            main_skills_filtered_dirs=_main_skills.filtered_dir_names,
        )
        # Middleware backend (no ToolRuntime - uses StandaloneStateBackend for default)
        self.composite_backend = create_middleware_backend(
            bundle_skill_routes=_skill_routes["bundle"],
            skills_subset_routes=_skill_routes["subset"],
            main_skills_filtered_dirs=_main_skills.filtered_dir_names,
        )

        # ============================================
        # Context Retriever (official-style: no store_backend)
        # ============================================
        # Short-term: _session_history (in-memory) + checkpointer for conversation.
        # Long-term: disabled (store=None). Extend later when agent_store is needed.
        self.context_retriever = ContextRetriever(store_backend=None)
        self.context_retriever._short_term_limit = 20

        # ============================================
        # Checkpointer Setup (LangGraph State Persistence)
        # Must use AsyncPostgresSaver for agent.astream (aget_tuple); PostgresSaver only has get_tuple.
        # ============================================
        self.checkpointer = checkpointer if checkpointer is not None else self._create_checkpointer()

        # Inject checkpointer so context retriever can query conversation history
        if self.checkpointer:
            self.context_retriever._checkpointer = self.checkpointer

        # TodoList, Filesystem, Summarization: built into official create_deep_agent

        # Build the main agent
        self.agent = self._build_official_agent()

    def __del__(self):
        """Best-effort cleanup for entered checkpointer contexts."""
        ctx = getattr(self, "_checkpointer_context", None)
        if ctx and hasattr(ctx, "__exit__"):
            try:
                ctx.__exit__(None, None, None)
            except Exception as _cleanup_exc:
                logger.debug("checkpointer_context_cleanup_failed", error=str(_cleanup_exc))
    
    def _create_checkpointer(self):
        """Create checkpointer for state persistence.
        
        Returns:
            Checkpointer instance (MemorySaver or PostgresSaver)
        """
        if not self.settings.enable_checkpointing:
            logger.info("checkpointing_disabled")
            return None
        
        if self.settings.checkpoint_backend == "postgres":
            # PostgresSaver only implements get_tuple (sync); agent.astream needs aget_tuple.
            # AsyncPostgresSaver is created in app lifespan and passed to get_deep_agent.
            # When called from sync context (tests, create_deep_security_agent), use MemorySaver.
            logger.warning(
                "checkpointer_postgres_sync_fallback",
                detail="PostgresSaver lacks aget_tuple; falling back to MemorySaver for sync context",
            )
            from langgraph.checkpoint.memory import MemorySaver
            return MemorySaver()
        else:
            # Memory checkpointer (for development/testing)
            from langgraph.checkpoint.memory import MemorySaver
            logger.info("checkpointer_memory_mode")
            return MemorySaver()
    
    def _build_official_agent(self):
        """Build the main agent using official create_deep_agent.

        Sub-agent specs are raw SubAgent dicts; create_deep_agent fills in the
        model, builds the full middleware stack (including SkillsMiddleware from
        the 'skills' key), and compiles them via SubAgentMiddleware internally.

        Intent understanding, routing, and task planning are handled natively by
        the main LLM in its first round, guided by MASTER_AGENT.md prompt rules.
        The task() tool is injected automatically by SubAgentMiddleware.
        """
        from app._vendor.deepagents import create_deep_agent
        from app.agents.official_subagents import build_subagent_specs
        from app.tools.common.tools import create_common_tools

        s = self.settings
        main_hitl_tools = True
        main_agent_tools = create_common_tools(include_hitl=main_hitl_tools)
        intr_on = s.main_agent_interrupt_on

        prompt = MASTER_SYSTEM_PROMPT
        if main_hitl_tools:
            prompt = prompt + "\n" + load_prompt("clarify_gate")

        _subagent_specs = build_subagent_specs(
            backend_factory=self.backend_factory,
            default_subagent_model=self.model,
        )

        return create_deep_agent(
            model=self.model,
            tools=main_agent_tools,
            system_prompt=prompt,
            backend=self.backend_factory,
            subagents=_subagent_specs,  # raw specs, framework compiles
            checkpointer=self.checkpointer,
            middleware=[
                DeepResearchSynthesisSkipMiddleware(),
                NormalizeToolCallNamesMiddleware(),
            ],
            skills=self._main_skills_middleware_sources,
            interrupt_on=intr_on,
        )

    async def analyze_stream(
        self,
        text: str,
        files: list[dict] | None = None,
        request_id: str = "",
        ui_language: str = "en",
        input_language: str = "auto",
        client_timezone: str | None = None,
        project_id: str | None = None,
        user_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream analysis events for frontend SSE consumption.

        The main agent's LLM handles intent understanding, routing, task planning,
        sub-agent dispatch, and synthesis in its natural graph loop.  This method:
        1. Detects language (pure heuristic, no LLM)
        2. Validates input (rejects empty requests before any LLM call)
        3. Parses file content (builds files dict for FilesystemMiddleware)
        4. Injects session context summary (pure DB query, no LLM)
        5. Builds initial state and streams the agent
        """
        from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse

        # Step 1: Language detection (heuristic, no LLM)
        effective_input_language = (
            input_language
            if input_language and input_language != "auto"
            else _detect_language(text)
        )

        # Step 2: Input validity gate — reject obviously invalid requests before any LLM call
        has_text = bool(text and text.strip())
        has_files = bool(
            files
            and any(
                f.get("content")
                or f.get("fullContent")
                or f.get("file_path")
                or f.get("filePath")
                or f.get("virtual_path")
                for f in files
            )
        )
        if not has_text and not has_files:
            yield {
                "type": "error",
                "id": "empty-input",
                "requestId": request_id,
                "label": get_intent_label("intent_analysis_failed", ui_language),
                "status": "error",
                "detail": "No text or file content provided.",
            }
            yield {"type": "done", "id": "done", "requestId": request_id}
            return

        # Step 3: Parse files — two modes:
        #
        # A) file_path / virtual_path (preferred): on-disk under upload_dir; manifest
        #    for main-agent routing + optional bounded sniff; never load full file into
        #    state["files"].
        # B) inline content (legacy): state["files"] FileData; budgeted preview in message.
        _FILE_TOTAL_BUDGET = 6_000
        _FILE_MAX_PER_FILE = 2_000

        from pathlib import Path as _Path

        from app._vendor.deepagents.backends.utils import create_file_data
        from app.backends.upload_scope import get_upload_stripped_root
        from app.services.upload_path_auth import (
            owner_segment,
            resolve_upload_disk_path,
            sniff_preview,
            strip_uploads_virtual_path,
        )

        _upload_dir = _Path(get_settings().upload_dir)
        _settings = get_settings()
        _scope_root = get_upload_stripped_root()
        if not _scope_root:
            _scope_root = "/" + owner_segment(
                user_id=user_id,
                session_id=self.session_id,
                project_id=project_id,
            )
        _owner_segment = _scope_root.strip("/")

        def _agent_file_path(virtual_path: str) -> str:
            try:
                rel = strip_uploads_virtual_path(virtual_path).replace("\\", "/")
            except ValueError:
                return virtual_path
            owner_prefix = _owner_segment.strip("/")
            if rel == owner_prefix:
                return virtual_path
            if not rel.startswith(owner_prefix + "/"):
                fallback_name = _Path(rel.replace("\\", "/")).name
                return f"/workspace/{fallback_name}" if fallback_name else virtual_path
            tail = rel[len(owner_prefix) + 1:].strip("/")
            return f"/workspace/{tail}" if tail else virtual_path

        inline_files_dict: dict[str, str] = {}
        manifest_rows: list[str] = []
        file_sections: list[str] = []
        file_parser = FileParser(language=effective_input_language)
        total_file_chars = 0
        sniff_bytes_used = 0

        for f in files or []:
            content_type = (
                str(f.get("content_type") or f.get("contentType") or "").strip()
                or "application/octet-stream"
            )
            vp_raw = f.get("file_path") or f.get("filePath") or f.get("virtual_path")
            virtual_path: str | None = str(vp_raw).strip() if vp_raw else None
            filename = str(f.get("filename") or "").strip()
            if virtual_path and not filename:
                filename = _Path(virtual_path.replace("\\", "/")).name or "attachment"
            if not filename:
                continue

            if virtual_path:
                file_path = _agent_file_path(virtual_path)
                try:
                    disk = resolve_upload_disk_path(_upload_dir, virtual_path)
                except ValueError:
                    manifest_rows.append(
                        f"| {filename} | `{file_path}` | — | {content_type} | (invalid path) | — |"
                    )
                    continue
                exists = disk.is_file()
                size_b = disk.stat().st_size if exists else 0
                sha = f.get("sha256") or ""
                sha_cell = sha[:16] + "…" if len(sha) > 16 else (sha or "—")
                manifest_rows.append(
                    f"| {filename} | `{file_path}` | "
                    f"{content_type} | {size_b} | {sha_cell} |"
                )
                if exists:
                    remain = (
                        _settings.main_agent_manifest_sniff_bytes_total
                        - sniff_bytes_used
                    )
                    cap = min(
                        _settings.main_agent_manifest_sniff_bytes_per_file,
                        max(0, remain),
                    )
                    if cap >= 32:
                        sn = sniff_preview(disk, per_file_cap=cap)
                        sniff_bytes_used += len(sn.encode("utf-8", errors="replace"))
                        file_sections.append(
                            f"### {filename}\n"
                            f"(virtual workspace path: `{file_path}`)\n{sn}"
                        )
                else:
                    file_sections.append(
                        f"### {filename}\n"
                        f"(virtual workspace path: `{file_path}`)\n(file not on disk)"
                    )
                continue

            raw_content = f.get("content") or f.get("fullContent") or ""
            inline_files_dict[filename] = str(raw_content)

            try:
                file_info = FileInfo(
                    filename=filename,
                    content_type=content_type,
                    size=len(str(raw_content)),
                    content=raw_content,
                )
                parsed = file_parser.parse_file(file_info)
            except Exception as _parse_exc:
                logger.debug("file_parse_fallback", filename=filename, error=str(_parse_exc))
                parsed = str(raw_content)[:500]

            section_header = f"### {filename}"
            remaining_budget = _FILE_TOTAL_BUDGET - total_file_chars
            per_file_cap = min(_FILE_MAX_PER_FILE, remaining_budget)

            if per_file_cap <= 100:
                file_sections.append(f"{section_header}\n(omitted — token budget reached)")
            else:
                summary = parsed[:per_file_cap]
                if len(parsed) > per_file_cap:
                    summary += f"\n... (truncated, {len(parsed)} chars total)"
                file_sections.append(f"{section_header}\n{summary}")
                total_file_chars += len(summary)

        # Step 4: Build user message parts (context comes from checkpoint messages)
        parts: list[str] = []
        if text and text.strip():
            parts.append(text.strip())
        if manifest_rows:
            table = (
                "| filename | file_path | content_type | size_bytes | sha256 (prefix) |\n"
                "| --- | --- | --- | --- | --- |\n"
                + "\n".join(manifest_rows)
            )
            parts.append(
                "[Attached files - For read_file/glob uses the virtual workspace path "
                "in ``file_path``. For **binary-analysis** subagent delegations, "
                "pass **`file_path`** to `file_identify`; the tool resolves "
                "authorized workspace uploads internally. Do not request or "
                "construct host filesystem paths.] "
                "Use detect_web_attack(file_path=...) on file_path for web/security "
                "files. Do not construct paths from filename.\n"
                + table
            )
        if file_sections:
            parts.append(
                "[File previews]\n" + "\n\n".join(file_sections)
                if manifest_rows
                else "[Uploaded Files]\n" + "\n\n".join(file_sections)
            )

        # Inject client local time so the LLM can answer time-related questions accurately.
        from datetime import datetime

        try:
            if client_timezone:
                import zoneinfo

                tz_obj = zoneinfo.ZoneInfo(client_timezone)
                now_str = datetime.now(tz_obj).strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
                parts.append(f"[System Time]\nCurrent time in user's timezone ({client_timezone}): {now_str}")
            else:
                tz_obj = get_app_tz()
                now_str = datetime.now(tz_obj).strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
                parts.append(
                    f"[System Time]\nCurrent time in app timezone ({tz_obj.key}): {now_str}"
                )
        except Exception as _tz_exc:
            logger.debug("client_timezone_fallback", client_timezone=client_timezone, error=str(_tz_exc))
            tz_obj = get_app_tz()
            now_str = datetime.now(tz_obj).strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)")
            parts.append(
                f"[System Time]\nCurrent time in app timezone ({tz_obj.key}): {now_str}"
            )

        from app.services.context_memory.pipeline import (
            build_injection_prefix,
            fetch_hydration_prefix,
        )

        prefix_chunks: list[str] = []
        hydrate = await fetch_hydration_prefix(project_id, user_id)
        if hydrate:
            prefix_chunks.append(hydrate)
        inject = await build_injection_prefix(project_id, user_id)
        if inject:
            prefix_chunks.append(inject)
        if prefix_chunks:
            parts = prefix_chunks + parts

        user_message = "\n\n".join(parts) if parts else text

        # Step 5: Build initial agent state and stream
        initial_state = {
            "messages": [HumanMessage(content=user_message)],
            "todos": [],
            "files": {
                (k if k.startswith("/") else f"/{k}"): create_file_data(str(v))
                for k, v in inline_files_dict.items()
            },
            "current_step": "analyzing",
            "iteration_count": 0,
            "session_id": self.session_id,
            "request_id": request_id,
            "context_token_count": 0,
            "summarization_applied": False,
        }
        config = {
            "configurable": {
                "thread_id": self.session_id,
                "subagent_response_language": effective_input_language,
                "llm_gateway_model_id": self._model_id,
            }
        }

        # HITL pending guard — MUST run before any aupdate_state, otherwise
        # aupdate_state creates a new checkpoint that silently clears the
        # pending interrupt and the guard below would never fire.
        s_hitl = self.settings
        if getattr(s_hitl, "agent_hitl_block_analyze_when_pending", False):
            try:
                pending_snap = await asyncio.wait_for(
                    self.agent.aget_state(config), timeout=10.0
                )
                if pending_snap.interrupts:
                    logger.warning(
                        "hitl_interrupt_pending_block_analyze",
                        session_id=self.session_id,
                        interrupts_count=len(pending_snap.interrupts),
                    )
                    yield {
                        "type": "error",
                        "id": "hitl-pending",
                        "requestId": request_id,
                        "label": "Pending human input",
                        "status": "error",
                        "detail": (
                            "This session is waiting for human-in-the-loop input. "
                            "Call POST /analyze/resume with the same session_id before "
                            "sending a new message."
                        ),
                    }
                    yield {"type": "done", "id": "done", "requestId": request_id}
                    return
            except Exception as _hitl_guard_exc:
                logger.debug("hitl_pending_guard_check_failed", error=str(_hitl_guard_exc))

        try:
            await asyncio.wait_for(
                self.agent.aupdate_state(config, {"todos": []}),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "aupdate_state_timeout",
                detail="checkpointer may be slow/unreachable, continuing without clearing todos",
            )
        except Exception as _clear_exc:
            logger.debug("aupdate_state_clear_todos_failed", error=str(_clear_exc))

        if not has_files:
            try:
                state = await asyncio.wait_for(
                    self.agent.aget_state(config), timeout=10.0
                )
                _vals = state.values if isinstance(state.values, dict) else {}
                existing_files = _vals.get("files") or {}
                if existing_files:
                    clear_updates = {k: None for k in existing_files}
                    await asyncio.wait_for(
                        self.agent.aupdate_state(config, {"files": clear_updates}),
                        timeout=5.0,
                    )
                    logger.debug(
                        "checkpoint_files_cleared",
                        session_id=self.session_id,
                        cleared_keys=list(existing_files.keys()),
                    )
            except asyncio.TimeoutError:
                logger.warning(
                    "checkpoint_file_clear_timeout",
                    detail="aget_state/aupdate_state timed out when clearing files, continuing",
                )
            except Exception as _clear_files_exc:
                logger.debug("checkpoint_file_clear_failed", error=str(_clear_files_exc))

        seen_sigs: frozenset[str] = frozenset()
        try:
            from app.parsers.deepagents_stream_adapter import _message_signature
            state = await asyncio.wait_for(self.agent.aget_state(config), timeout=10.0)
            _vals = state.values if isinstance(state.values, dict) else {}
            msgs = _vals.get("messages") or []
            sigs = []
            for m in msgs:
                if isinstance(m, AIMessage):
                    s = _message_signature(m)
                    if s:
                        sigs.append(s)
            seen_sigs = frozenset(sigs)
        except Exception as _sig_exc:
            logger.debug("seen_signatures_preload_failed", error=str(_sig_exc))

        hitl_paused = False
        try:
            async for event in adapt_astream_to_sse(
                self.agent,
                initial_state,
                config,
                language=ui_language,
                seen_message_signatures=seen_sigs,
            ):
                if event.get("awaitingHuman"):
                    hitl_paused = True
                if request_id:
                    event = {**event, "requestId": request_id}
                yield event
        finally:
            if hitl_paused:
                logger.info(
                    "hitl_guard_awaiting_human_skip_todos_reset",
                    session_id=self.session_id,
                )
            else:
                # Double-check: even if the SSE flag was missed, verify the
                # checkpoint directly before writing a state update that would
                # wipe a pending interrupt.
                _has_pending_interrupt = False
                try:
                    _snap = await asyncio.wait_for(
                        self.agent.aget_state(config), timeout=5.0
                    )
                    _has_pending_interrupt = bool(
                        _snap and getattr(_snap, "interrupts", None)
                    )
                except Exception as _snap_exc:
                    logger.debug("hitl_guard_post_stream_check_failed", error=str(_snap_exc))

                if _has_pending_interrupt:
                    logger.info(
                        "hitl_guard_pending_interrupt_skip_todos_reset",
                        session_id=self.session_id,
                    )
                else:
                    try:
                        await asyncio.wait_for(
                            self.agent.aupdate_state(config, {"todos": []}),
                            timeout=5.0,
                        )
                    except Exception as _reset_exc:
                        logger.debug("post_stream_todos_reset_failed", error=str(_reset_exc))

    async def resume_stream(
        self,
        resume: Any,
        *,
        request_id: str = "",
        ui_language: str = "zh",
        subagent_response_language: str = "en",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Continue after LangGraph interrupt (HITL).

        ``ui_language`` drives SSE/tool step labels; ``subagent_response_language`` must match
        the user's request text (same as analyze_stream when input_language is auto).
        """
        from langgraph.types import Command

        from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse

        cmd = resume if isinstance(resume, Command) else Command(resume=resume)
        config = {
            "configurable": {
                "thread_id": self.session_id,
                "subagent_response_language": subagent_response_language,
                "llm_gateway_model_id": self._model_id,
            }
        }
        seen_sigs: frozenset[str] = frozenset()
        try:
            from app.parsers.deepagents_stream_adapter import _message_signature
            state = await asyncio.wait_for(self.agent.aget_state(config), timeout=10.0)
            _vals = state.values if isinstance(state.values, dict) else {}
            msgs = _vals.get("messages") or []
            sigs = []
            for m in msgs:
                if isinstance(m, AIMessage):
                    s = _message_signature(m)
                    if s:
                        sigs.append(s)
            seen_sigs = frozenset(sigs)
        except Exception as _resume_sig_exc:
            logger.debug("resume_seen_signatures_preload_failed", error=str(_resume_sig_exc))
        async for event in adapt_astream_to_sse(
            self.agent,
            {},
            config,
            language=ui_language,
            seen_message_signatures=seen_sigs,
            stream_input=cmd,
        ):
            if request_id:
                event = {**event, "requestId": request_id}
            yield event

    async def submit_parameters(self, parameters: dict[str, str]):
        """Save user-submitted parameters to encrypted storage."""
        for name, value in parameters.items():
            await self.context_retriever.save_to_long_term(
                self.session_id,
                name,
                value,
                encrypted=True,
            )

        logger.info(
            "session_parameters_saved",
            session_id=self.session_id,
            param_count=len(parameters),
        )
    
# ============================================
# Legacy Functions (for backward compatibility)
# ============================================

def create_deep_security_agent(session_id: str = "default"):
    """Create a DeepAgent for security analysis with skill-based sub-agents.
    
    The agent uses progressive disclosure for skills:
    - Only skill metadata is loaded initially (token efficient)
    - Full skill instructions are loaded on-demand when skill is used
    
    Now includes layered context management:
    - SummarizationMiddleware for automatic context compression
    - CompositeBackend for path-based storage routing
    """
    agent_wrapper = DeepAgentWithIntent(session_id)
    return agent_wrapper.agent


_agent_cache: dict[tuple[str, str], DeepAgentWithIntent] = {}
_session_locks: dict[str, asyncio.Lock] = {}


def _get_session_lock(session_id: str) -> asyncio.Lock:
    """Get per-session lock to serialize same-session requests."""
    existing = _session_locks.get(session_id)
    if existing is not None:
        return existing
    created = asyncio.Lock()
    _session_locks[session_id] = created
    return created


def _cache_key(session_id: str, model_id: str | None) -> tuple[str, str]:
    """Cache key: (session_id, effective_model_id)."""
    from app.llm_gateway import get_registry
    effective = model_id or get_registry().get_default_model()
    return (session_id, effective)


def get_deep_agent(
    session_id: str = "default",
    model_id: str | None = None,
    checkpointer: Any = None,
) -> DeepAgentWithIntent:
    """Get or create a DeepAgent for a session and model.

    When *model_id* is ``None`` (e.g. HITL resume) and the exact cache key
    misses, fall back to any cached agent for *session_id* so that the resume
    reuses the same checkpointer / graph that holds the pending interrupt.
    """
    key = _cache_key(session_id, model_id)
    if key in _agent_cache:
        return _agent_cache[key]

    if model_id is None:
        for (sid, _mid), agent in _agent_cache.items():
            if sid == session_id:
                logger.info(
                    "get_deep_agent session-fallback hit",
                    session_id=session_id,
                    cached_model=_mid,
                )
                return agent

    agent = DeepAgentWithIntent(
        session_id, model_id=model_id, checkpointer=checkpointer
    )
    _agent_cache[key] = agent
    return agent


async def analyze_with_deep_agent(input_text: str, session_id: str = "default", checkpointer: Any = None) -> dict:
    """Analyze security input using the DeepAgent with skill-based sub-agents.
    
    The agent will automatically select appropriate skills based on the input
    and use progressive disclosure to minimize token usage.
    """
    from app.middleware.user_input_unwrap import unwrap_structured_user_prompt

    input_text = unwrap_structured_user_prompt(input_text)
    agent = get_deep_agent(session_id, checkpointer=checkpointer)
    
    # Collect all events
    events = []
    async for event in agent.analyze_stream(input_text):
        events.append(event)
    
    # Extract final response from conclusion event
    final_response = None
    for event in reversed(events):
        if event.get("type") == "conclusion":
            final_response = event.get("content")
            break
    
    return {
        "analysis": final_response,
        "events": events,
    }


async def stream_analyze_request(
    text: str,
    files: list[dict] | None = None,
    session_id: str = "default",
    request_id: str = "",
    ui_language: str = "zh",
    input_language: str = "auto",
    checkpointer: Any = None,
    client_timezone: str | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
) -> AsyncGenerator[dict, None]:
    """HTTP/SSE entry: per-session lock, upload scope, request-scoped LLM id, then ``analyze_stream``."""
    from app.middleware.user_input_unwrap import unwrap_structured_user_prompt

    text = unwrap_structured_user_prompt(text)
    agent = get_deep_agent(session_id, model_id=model_id, checkpointer=checkpointer)
    lock = _get_session_lock(session_id)

    # Try to acquire the per-session lock within 30 s.  If a previous request for the
    # same session is genuinely stuck (e.g. the blocking subagent.invoke path), we
    # unblock the waiting request instead of deadlocking the event loop indefinitely.
    try:
        await asyncio.wait_for(lock.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning(
            "session_lock_timeout",
            session_id=session_id,
        )
        yield {
            "type": "error",
            "id": "session-busy",
            "label": "Session busy",
            "detail": "A previous request for this session is still processing. Please wait a moment and retry.",
            "status": "error",
        }
        return

    from app.backends.upload_scope import reset_upload_stripped_root, set_upload_stripped_root
    from app.services.upload_path_auth import owner_segment
    from app.request_context.user_id import reset_request_user_id, set_request_user_id

    scope_tok = set_upload_stripped_root(
        f"/{owner_segment(user_id=user_id, session_id=session_id, project_id=project_id)}"
    )
    from app.llm_gateway.registry import get_registry
    from app.llm_gateway.request_context import reset_request_llm_model_id, set_request_llm_model_id
    from app.analyze_request_context import (
        reset_analyze_request_context,
        set_analyze_request_context,
    )

    effective_model_id = model_id or getattr(agent, "_model_id", None) or get_registry().get_default_model()
    llm_ctx_tok = set_request_llm_model_id(effective_model_id)
    uid_ctx_tok = set_request_user_id(user_id)
    tenant_toks = set_analyze_request_context(
        user_id=user_id,
        project_id=project_id or session_id,
        request_id=request_id,
        session_id=session_id,
    )
    import structlog as _sl_ctx
    _sl_ctx.contextvars.bind_contextvars(
        request_id=request_id,
        user_id=user_id or "",
        project_id=project_id or session_id,
        session_id=session_id,
    )
    try:
        async for event in agent.analyze_stream(
            text,
            files,
            request_id=request_id,
            ui_language=ui_language,
            input_language=input_language,
            client_timezone=client_timezone,
            project_id=project_id or session_id,
            user_id=user_id,
        ):
            yield event
    finally:
        _sl_ctx.contextvars.unbind_contextvars(
            "request_id", "user_id", "project_id", "session_id",
        )
        reset_analyze_request_context(
            tenant_toks[0],
            tenant_toks[1],
            tenant_toks[2],
            tenant_toks[3],
        )
        reset_request_user_id(uid_ctx_tok)
        reset_request_llm_model_id(llm_ctx_tok)
        reset_upload_stripped_root(scope_tok)
        lock.release()


async def stream_resume_request(
    resume: Any,
    session_id: str = "default",
    request_id: str = "",
    ui_language: str = "zh",
    input_language: str = "auto",
    checkpointer: Any = None,
    model_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """HTTP/SSE entry for HITL resume: same session lock and upload scope as ``stream_analyze_request``."""
    agent = get_deep_agent(session_id, model_id=model_id, checkpointer=checkpointer)
    lock = _get_session_lock(session_id)
    try:
        await asyncio.wait_for(lock.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning(
            "session_lock_timeout_resume",
            session_id=session_id,
        )
        yield {
            "type": "error",
            "id": "session-busy",
            "label": "Session busy",
            "detail": "A previous request for this session is still processing.",
            "status": "error",
        }
        return

    from app.backends.upload_scope import reset_upload_stripped_root, set_upload_stripped_root
    from app.services.upload_path_auth import owner_segment
    from app.request_context.user_id import reset_request_user_id, set_request_user_id

    scope_tok = set_upload_stripped_root(
        f"/{owner_segment(user_id=user_id, session_id=session_id, project_id=project_id)}"
    )
    config = {"configurable": {"thread_id": session_id}}
    try:
        snap = await asyncio.wait_for(agent.agent.aget_state(config), timeout=15.0)
        logger.info(
            "hitl_resume_checkpoint_state",
            session_id=session_id,
            agent_id=id(agent),
            checkpointer_type=type(agent.checkpointer).__name__ if agent.checkpointer else "None",
            has_interrupts=bool(snap.interrupts) if snap else False,
            interrupts_count=len(snap.interrupts) if snap and snap.interrupts else 0,
            next_nodes=list(snap.next) if snap and snap.next else [],
            tasks_count=len(snap.tasks) if snap and hasattr(snap, "tasks") and snap.tasks else 0,
            has_values=bool(snap.values) if snap else False,
            checkpoint_id=(snap.config or {}).get("configurable", {}).get("checkpoint_id") if snap else None,
        )
        if not snap.interrupts:
            yield {
                "type": "error",
                "id": "hitl-nothing-pending",
                "requestId": request_id,
                "label": "No pending interrupt",
                "status": "error",
                "detail": "There is no human-in-the-loop interrupt to resume for this session.",
            }
            yield {"type": "done", "id": "done", "requestId": request_id}
            return

        snap_values = snap.values if isinstance(getattr(snap, "values", None), dict) else None
        subagent_response_language = resolve_subagent_language_for_resume(
            snap_values,
            input_language=input_language,
        )
    except Exception as e:
        logger.warning("aget_state failed before resume", error=str(e))
        yield {
            "type": "error",
            "id": "hitl-state-error",
            "requestId": request_id,
            "label": "State error",
            "status": "error",
            "detail": "Could not read graph state before resume.",
        }
        yield {"type": "done", "id": "done", "requestId": request_id}
        return

    from app.llm_gateway.registry import get_registry
    from app.llm_gateway.request_context import reset_request_llm_model_id, set_request_llm_model_id
    from app.analyze_request_context import (
        reset_analyze_request_context,
        set_analyze_request_context,
    )

    effective_model_id = model_id or getattr(agent, "_model_id", None) or get_registry().get_default_model()
    llm_ctx_tok = set_request_llm_model_id(effective_model_id)
    uid_ctx_tok = set_request_user_id(user_id)
    tenant_toks = set_analyze_request_context(
        user_id=user_id,
        project_id=project_id or session_id,
        request_id=request_id,
        session_id=session_id,
    )
    import structlog as _sl_ctx
    _sl_ctx.contextvars.bind_contextvars(
        request_id=request_id,
        user_id=user_id or "",
        project_id=project_id or session_id,
        session_id=session_id,
    )
    try:
        async for event in agent.resume_stream(
            resume,
            request_id=request_id,
            ui_language=ui_language,
            subagent_response_language=subagent_response_language,
        ):
            yield event
    finally:
        _sl_ctx.contextvars.unbind_contextvars(
            "request_id", "user_id", "project_id", "session_id",
        )
        reset_analyze_request_context(
            tenant_toks[0],
            tenant_toks[1],
            tenant_toks[2],
            tenant_toks[3],
        )
        reset_request_user_id(uid_ctx_tok)
        reset_request_llm_model_id(llm_ctx_tok)
        reset_upload_stripped_root(scope_tok)
        lock.release()
