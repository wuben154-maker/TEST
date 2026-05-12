"""FastAPI main application for the DeepAgent Security Service.

Based on LangChain DeepAgents architecture with streaming support.
"""

# NOTE: Python 3.13 may eagerly evaluate annotations in some contexts.
# This keeps forward references (e.g. -> AnalyzeAttachment) from breaking module import.
from __future__ import annotations

# Load .env into os.environ so ModelRegistry (os.environ.get) can read API keys
from pathlib import Path

from dotenv import load_dotenv

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_SERVICE_ROOT / ".env")

# google-genai reads os.environ and logs a WARNING on every call to get_env_api_key() when both
# GOOGLE_API_KEY and GEMINI_API_KEY are set. Drop GEMINI_API_KEY for this process once at startup
# (precedence matches the SDK: GOOGLE_API_KEY). See config/env.md.
def _normalize_google_genai_api_key_env() -> None:
    import os

    g = (os.environ.get("GOOGLE_API_KEY") or "").strip()
    m = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if g and m:
        os.environ.pop("GEMINI_API_KEY", None)


_normalize_google_genai_api_key_env()

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Optional
from uuid import uuid4

import structlog
from app.agents.deep_agent import (
    MASTER_SYSTEM_PROMPT,
    create_deep_security_agent,
    get_deep_agent,
    get_model,
    stream_analyze_request,
    stream_resume_request,
)
from app.sse.tool_presentation import get_all_workspace_tab_configs
from app.api.auth import get_current_user
from app.billing import assert_analyze_billing_allowed
from app.config import get_settings
from app.catalog.registry_catalog import build_global_skills_catalog, build_subagents_catalog
from app.prompts.skills import get_skill_registry
from app.sse.framing import create_sse_message
from app.tools.common.tools import create_common_tools
from subagents.official.soc_alert.tools.soc_alert.auth.service import get_vendor_auth_service
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Structured logging configuration
# ---------------------------------------------------------------------------
# Two-stage pipeline (structlog best practice with stdlib LoggerFactory):
#   Stage 1 (_shared_processors): runs inside structlog AND on foreign stdlib logs.
#   Stage 2 (_formatter processors): runs once in ProcessorFormatter → JSON output.
# This prevents double-JSON-encoding that occurs when JSONRenderer is in both stages.
import logging as _stdlib_logging


def _safe_filter_by_level(
    logger: _stdlib_logging.Logger | None,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """stdlib/ProcessorFormatter can pass logger=None; filter_by_level needs a Logger."""
    if logger is None:
        logger = _stdlib_logging.root
    return structlog.stdlib.filter_by_level(logger, method_name, event_dict)


_shared_processors: list = [
    structlog.contextvars.merge_contextvars,
    _safe_filter_by_level,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]

structlog.configure(
    processors=_shared_processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Single formatter for all handlers — renders to JSON exactly once.
# ProcessorFormatter defaults logger=None; foreign/vendor logs (httpx, etc.) then
# pass None into foreign_pre_chain and filter_by_level crashes on logger.disabled.
_formatter = structlog.stdlib.ProcessorFormatter(
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.JSONRenderer(),
    ],
    foreign_pre_chain=_shared_processors,
    logger=_stdlib_logging.getLogger(),
)

# Suppress Uvicorn's duplicate access log (our RequestLoggingMiddleware handles it).
_stdlib_logging.getLogger("uvicorn.access").handlers.clear()
_stdlib_logging.getLogger("uvicorn.access").propagate = False

_log_settings = get_settings()
_log_sink = _log_settings.log_sink  # "stdout" | "file" | "both"

if _log_sink in ("stdout", "both"):
    _stream_handler = _stdlib_logging.StreamHandler()
    _stream_handler.setFormatter(_formatter)
    _stdlib_logging.root.addHandler(_stream_handler)

if _log_sink in ("file", "both"):
    from logging.handlers import RotatingFileHandler as _RotatingFileHandler

    _log_file = Path(_log_settings.log_file_path)
    if not _log_file.is_absolute():
        _log_file = _SERVICE_ROOT / _log_file
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    _file_handler = _RotatingFileHandler(
        str(_log_file),
        maxBytes=_log_settings.log_file_max_bytes,
        backupCount=_log_settings.log_file_backup_count,
        encoding="utf-8",
    )
    _file_handler.setFormatter(_formatter)
    _stdlib_logging.root.addHandler(_file_handler)

_stdlib_logging.root.setLevel(_stdlib_logging.INFO)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Running-producer registry: request_id → asyncio.Task
# Allows explicit cancellation when the client disconnects or calls /analyze/cancel.
# ---------------------------------------------------------------------------
_running_producers: dict[str, asyncio.Task] = {}


def _register_producer(request_id: str, task: asyncio.Task) -> None:
    if request_id:
        _running_producers[request_id] = task


def _unregister_producer(request_id: str) -> None:
    _running_producers.pop(request_id, None)


def cancel_producer_by_request_id(request_id: str) -> bool:
    """Cancel a running producer task. Returns True if a task was found and cancelled."""
    task = _running_producers.get(request_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(
        "Starting DeepAgent Security Service",
        agent_mode=settings.agent_mode,
        database_mode=settings.database_mode,
        default_model=settings.default_model,
    )

    # Log database configuration
    if settings.is_local_database:
        logger.info(
            f"Using local database: {settings.local_db_host}:{settings.local_db_port}/{settings.local_db_name}"
        )
    else:
        logger.info(f"Using Supabase: {settings.supabase_url}")

    logger.info("DeepAgent mode enabled - using LangGraph with full tool support")

    # Create AsyncPostgresSaver for astream (agent.astream requires aget_tuple, not get_tuple)
    app.state.checkpointer = None
    # NOTE: Supabase project URL (https://<ref>.supabase.co) is not a PostgreSQL DSN.
    # Only initialise Postgres checkpointing when running in local Postgres mode.
    postgres_conninfo: str | None = None
    if settings.database_mode == "local":
        postgres_conninfo = (
            f"postgresql://{settings.local_db_user}:{settings.local_db_password}"
            f"@{settings.local_db_host}:{settings.local_db_port}/{settings.local_db_name}"
        )
    if (
        settings.is_deepagent_mode
        and settings.enable_checkpointing
        and settings.checkpoint_backend == "postgres"
        and postgres_conninfo
    ):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from psycopg.rows import dict_row
            from psycopg_pool import AsyncConnectionPool

            pool = AsyncConnectionPool(
                conninfo=postgres_conninfo,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                open=False,
            )
            await pool.open()
            checkpointer = AsyncPostgresSaver(conn=pool)
            await checkpointer.setup()
            app.state.checkpointer = checkpointer
            app.state._checkpoint_pool = pool
            logger.info("AsyncPostgresSaver initialized for streaming")
        except Exception as e:
            logger.warning(
                "Failed to create AsyncPostgresSaver, using MemorySaver",
                error=str(e),
            )

    if (
        app.state.checkpointer is None
        and settings.is_deepagent_mode
        and settings.enable_checkpointing
    ):
        if (
            settings.checkpoint_backend == "postgres"
            and settings.database_mode == "supabase"
            and not settings.database_url
        ):
            logger.info(
                "Supabase mode without SUPABASE_DB_URL: using MemorySaver for LangGraph "
                "checkpoints (graph state is lost on process restart). "
                "Set SUPABASE_DB_URL to the postgresql:// URI from Supabase Dashboard → "
                "Settings → Database, or set CHECKPOINT_BACKEND=memory to make this explicit."
            )
        from langgraph.checkpoint.memory import MemorySaver

        app.state.checkpointer = MemorySaver()
        logger.info("Using MemorySaver for checkpointing")

    yield

    # Cleanup checkpoint pool
    pool = getattr(app.state, "_checkpoint_pool", None)
    if pool is not None:
        await pool.close()
    logger.info("Shutting down DeepAgent Security Service")


# Version info - imported from app.version (single source of truth)
from app.version import APP_VERSION, BUILD_DATE

BUILD_NOTES = "Structured conclusion report with task grouping and summary header"
FEATURE_FLAGS = {
    "workflow_steps": False,  # YAML workflow_steps removed from SKILL.md; LLM follows ## Workflow (mandatory SOP) via progressive disclosure
    "skill_events": True,  # Show skill_start/skill_complete events
    "parallel_tasks": True,  # Enable parallel task execution
}

# Create FastAPI app
app = FastAPI(
    title="DeepAgent Security Service",
    description="LangGraph-powered security analysis with DeepAgents framework",
    version=APP_VERSION,
    lifespan=lifespan,
)


# Configure CORS - use allow_origins=["*"] with allow_credentials=False so
# error responses (e.g. 500) always get CORS headers; API uses Bearer token, not cookies
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.middleware.client_timezone import ClientTimezoneMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware

app.add_middleware(ClientTimezoneMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# Include API routers
from app.api import (
    account_router,
    auth_router,
    billing_router,
    client_errors_router,
    messages_router,
    projects_router,
    shared_reports_router,
    uploads_router,
    knowledge_router,
)
from starlette.requests import Request
from starlette.responses import JSONResponse

app.include_router(auth_router)
app.include_router(account_router)
app.include_router(billing_router)
app.include_router(client_errors_router)
app.include_router(projects_router)
app.include_router(messages_router)
app.include_router(shared_reports_router)
app.include_router(uploads_router)
app.include_router(knowledge_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure all errors return JSON with CORS-friendly response."""
    logger.error(
        "Unhandled exception", error=str(exc), path=request.url.path, exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )


# Request/Response Models
class AnalyzeAttachment(BaseModel):
    """Attachment payload for analysis requests."""

    filename: str
    content_type: str = "application/octet-stream"
    content: str | bytes | None = None
    size: int = 0
    file_path: Optional[str] = None
    virtual_path: Optional[str] = None
    sha256: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_path_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("file_path") is None and data.get("filePath"):
                data["file_path"] = data["filePath"]
            if data.get("virtual_path") is None and data.get("virtualPath"):
                data["virtual_path"] = data["virtualPath"]
        return data

    @model_validator(mode="after")
    def _merge_virtual_into_file_path(self) -> "AnalyzeAttachment":
        if self.file_path is None and self.virtual_path:
            self.file_path = self.virtual_path
        return self


class AnalyzeRequest(BaseModel):
    """Request model for security analysis."""

    message: str
    attachments: list[AnalyzeAttachment] | None = None
    analysis_scope: str = "all_input"  # Deprecated: ignored; kept for client compatibility
    stream: bool = True
    session_id: Optional[str] = None
    project_id: Optional[str] = (
        None  # For persistence when client disconnects (same as session_id)
    )
    request_id: Optional[str] = None  # Client request ID for event scoping
    # Omitted must mean None so ``language`` (legacy) can supply locale; default zh only after merge.
    ui_language: Optional[str] = None  # Non-LLM UI/event language: en, zh, ja, ko
    input_language: str = (
        "auto"  # LLM generation language, "auto" detects from user text
    )
    language: Optional[str] = None  # Deprecated alias for ui_language
    client_timezone: Optional[str] = None  # IANA timezone string e.g. "Asia/Shanghai"
    model_id: Optional[str] = None  # Optional model id e.g. "anthropic/claude-sonnet-4"


class AnalyzeResumeRequest(BaseModel):
    """Resume a paused LangGraph run after human-in-the-loop interrupt."""

    session_id: str
    resume: Any  # Passed to Command(resume=...) — dict or scalar per LangGraph 1.x
    project_id: Optional[str] = None
    # Correlation id for this HTTP/SSE resume leg (defaults to a new UUID on the server).
    request_id: Optional[str] = None
    # Stable id for project_analysis_progress rows (original POST /analyze request_id).
    progress_request_id: Optional[str] = None
    # SSE / step labels locale (app chrome). Model reply language follows checkpoint + input_language.
    ui_language: str = "zh"
    # Same semantics as POST /analyze: auto = detect from first user message in checkpoint.
    input_language: str = "auto"
    model_id: Optional[str] = None
    # UI-only: persisted to project_analysis_progress.timeline as decision_response (not sent to LangGraph).
    hitl_decision_ui_id: Optional[str] = None
    hitl_selected_options: Optional[list[str]] = None


class ThinkingEvent(BaseModel):
    """SSE event for thinking chain."""

    type: str  # step, tool_call, tool_result, reasoning, conclusion, error, done
    id: str
    turn: Optional[int] = None  # ReAct cycle (think+act share turn; next think increments)
    label: Optional[str] = None
    status: Optional[str] = None  # pending, running, success, warning, error
    detail: Optional[str] = None
    content: Optional[str] = None
    toolName: Optional[str] = None
    toolInput: Optional[dict] = None
    toolOutput: Optional[Any] = None
    timestamp: Optional[int] = None
    internal: Optional[bool] = None  # If True, frontend will not display this event


class CancelAnalysisRequest(BaseModel):
    """Cancel a running analysis by request_id."""

    request_id: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    framework: str
    agent_mode: str
    database_mode: str



# Import labels and event visibility from parsers module
from app.parsers.labels import (
    get_analysis_phases_list,
    get_intent_label,
    get_phase_label,
    get_stream_adapter_label,
    get_tool_label,
    get_tool_labels_dict,
)

# Backward-compatible aliases
TOOL_STEP_LABELS = get_tool_labels_dict("zh")
ANALYSIS_PHASES = get_analysis_phases_list("zh")


def _validate_analyze_attachments(
    attachments: list[AnalyzeAttachment] | None,
    *,
    user_id: str | None,
    session_id: str,
    project_id: str | None = None,
) -> None:
    """Reject oversized inline payloads and unauthorized virtual paths."""
    from pathlib import Path

    from app.services.upload_path_auth import (
        authorize_virtual_path,
        total_inline_attachment_bytes,
    )

    settings = get_settings()
    rows = [a.model_dump() for a in (attachments or [])]
    ib = total_inline_attachment_bytes(rows)
    if ib > settings.attachment_inline_max_total_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                "Inline attachment payload too large "
                f"({ib} bytes; max {settings.attachment_inline_max_total_bytes}); "
                "use POST /uploads and pass virtual_path only"
            ),
        )
    upload_dir = Path(settings.upload_dir)
    for att in attachments or []:
        vp = (att.file_path or att.virtual_path or "").strip()
        if not vp:
            continue
        ok, _, msg = authorize_virtual_path(
            vp,
            upload_dir=upload_dir,
            user_id=user_id,
            session_id=session_id,
            project_id=project_id,
            allow_legacy_flat=settings.allow_legacy_flat_upload_paths,
        )
        if not ok:
            logger.warning(
                "attachment_path_unauthorized",
                detail=msg,
                virtual_path=vp,
            )
            raise HTTPException(status_code=403, detail=msg or "Forbidden")


def _parse_running_step_whitelist(raw: str | None) -> set[str]:
    """Parse comma-separated step IDs for running-step allowlist."""
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _should_emit_event(
    event: dict[str, Any],
    *,
    running_step_whitelist: set[str],
) -> bool:
    """Temporary bypass: emit all events without running-step filtering."""
    # Filtering is intentionally disabled for now so task-running/subagent start
    # signals always reach UI and debug panels.
    _ = event
    _ = running_step_whitelist

    # Legacy filter kept for quick restore:
    # if (
    #     event.get("type") == "step"
    #     and event.get("status") == "running"
    #     and str(event.get("id") or "") not in running_step_whitelist
    # ):
    #     return False
    return True


def _stream_ended_awaiting_human(events: list[dict[str, Any]]) -> bool:
    """True if the last ``done`` event in the stream marks a LangGraph HITL pause."""
    for ev in reversed(events):
        if isinstance(ev, dict) and ev.get("type") == "done":
            return ev.get("awaitingHuman") is True
    return False


def _should_flush_progress_upsert(
    now: float,
    last_flush_at: float,
    event_index_in_stream: int,
    min_interval_s: float,
    force_every_n: int,
) -> bool:
    """Throttle progress row writes during SSE so auth/light APIs keep pool headroom."""
    if min_interval_s <= 0:
        return True
    if event_index_in_stream <= 0:
        return True
    if force_every_n > 0 and event_index_in_stream % force_every_n == 0:
        return True
    return (now - last_flush_at) >= min_interval_s


@app.get("/api/models")
async def list_models():
    """Return available LLM models for UI model selector."""
    from app.llm_gateway import list_models as gateway_list_models

    return {"models": gateway_list_models()}


@app.get("/health")
async def health_check():
    """Health check endpoint with skills diagnostics and version info."""
    from app.prompts.skills import SKILLS_DIR, get_skills_info
    from app.version import APP_VERSION, BUILD_DATE

    settings = get_settings()
    skills_info = get_skills_info()

    return {
        "status": "healthy",
        "version": APP_VERSION,
        "build_date": BUILD_DATE,
        "framework": "DeepAgents",
        "agent_mode": settings.agent_mode,
        "database_mode": settings.database_mode,
        "feature_flags": FEATURE_FLAGS,
        "skills": skills_info,
        "skills_dir": str(SKILLS_DIR),
    }


@app.post("/analyze")
async def analyze(
    http_request: Request,
    request: AnalyzeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Analyze security input using DeepAgent with streaming."""
    session_id = request.session_id or request.project_id or str(uuid4())
    project_id = request.project_id or session_id
    effective_request_id = request.request_id or str(uuid4())
    user_id = current_user.get("id")
    settings = get_settings()

    await assert_analyze_billing_allowed(str(user_id))

    logger.info(
        "Received analysis request",
        message_length=len(request.message),
        session_id=session_id,
        project_id=project_id,
        stream=request.stream,
        agent_mode=settings.agent_mode,
    )

    ui_language = (request.ui_language or request.language or "zh").strip()
    input_language = request.input_language or "auto"

    _validate_analyze_attachments(
        request.attachments,
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
    )

    if request.stream:
        checkpointer = getattr(http_request.app.state, "checkpointer", None)
        return StreamingResponse(
            stream_deep_analysis(
                request.message,
                request.attachments,
                session_id,
                ui_language=ui_language,
                input_language=input_language,
                checkpointer=checkpointer,
                request_id=effective_request_id,
                client_timezone=request.client_timezone,
                project_id=project_id,
                user_id=user_id,
                model_id=request.model_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming fallback
    try:
        from app.agents.deep_agent import analyze_with_deep_agent

        checkpointer = getattr(http_request.app.state, "checkpointer", None)
        result = await asyncio.wait_for(
            analyze_with_deep_agent(
                request.message, session_id, checkpointer=checkpointer
            ),
            timeout=settings.timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timed out")
    except Exception as e:
        logger.error("Analysis failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/resume")
async def analyze_resume(
    http_request: Request,
    body: AnalyzeResumeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Resume DeepAgent after HITL interrupt (SSE)."""
    settings = get_settings()
    if not settings.is_deepagent_mode:
        raise HTTPException(status_code=400, detail="DeepAgent mode required")

    session_id = body.session_id.strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    user_id = current_user.get("id")
    await assert_analyze_billing_allowed(str(user_id))
    effective_request_id = body.request_id or str(uuid4())

    return StreamingResponse(
        stream_deep_resume(
            resume=body.resume,
            session_id=session_id,
            ui_language=body.ui_language or "zh",
            input_language=body.input_language or "auto",
            checkpointer=getattr(http_request.app.state, "checkpointer", None),
            request_id=effective_request_id,
            progress_row_request_id=(body.progress_request_id or "").strip() or None,
            project_id=body.project_id or session_id,
            user_id=user_id,
            model_id=body.model_id,
            hitl_decision_ui_id=(body.hitl_decision_ui_id or "").strip() or None,
            hitl_selected_options=body.hitl_selected_options,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/analyze/cancel")
async def cancel_analysis(
    body: CancelAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """Cancel a running analysis by request_id.

    Cancels the background producer task so LLM calls stop promptly.
    The producer's finally block still persists partial results.
    """
    cancelled = cancel_producer_by_request_id(body.request_id)
    logger.info(
        "Cancel analysis requested",
        request_id=body.request_id,
        producer_found=cancelled,
    )
    return {"message": "cancelled", "producer_cancelled": cancelled}


async def stream_deep_resume(
    resume: Any,
    session_id: str,
    ui_language: str = "zh",
    input_language: str = "auto",
    checkpointer: Any = None,
    request_id: str = "",
    progress_row_request_id: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    model_id: str | None = None,
    hitl_decision_ui_id: str | None = None,
    hitl_selected_options: list[str] | None = None,
):
    """SSE producer for POST /analyze/resume (same envelope as stream_deep_analysis)."""
    import time

    from app.services.message_persistence import (
        format_user_message_for_persistence,
        persist_analysis_result,
    )
    from app.services.progress_service import (
        build_decision_response_timeline_event,
        build_parameter_response_timeline_event,
        clear_progress,
        fetch_running_progress_for_merge,
        merge_resume_progress_state,
        upsert_progress,
    )

    rid_for_progress = (progress_row_request_id or "").strip() or request_id

    async def _persist_background(
        pid: str, uid: str, msg: str, events: list, rid: str | None, lang: str
    ) -> None:
        try:
            await persist_analysis_result(
                pid, uid, msg, events, request_id=rid, ui_language=lang
            )
        except Exception as e:
            logger.error("Background persist retry failed (resume)", error=str(e), exc_info=True)
        finally:
            if not _stream_ended_awaiting_human(events):
                await clear_progress(pid)

    settings = get_settings()
    prog_min_iv = settings.progress_upsert_min_interval_seconds
    prog_force_n = settings.progress_upsert_force_every_n_events
    running_step_whitelist = _parse_running_step_whitelist(
        settings.step_running_whitelist
    )

    base_snapshot: dict | None = None
    if project_id and user_id:
        base_snapshot = await fetch_running_progress_for_merge(project_id, user_id)

    # Recover original user input from the first-leg progress row instead of
    # the "[HITL resume]" placeholder.  This ensures progress & message
    # persistence both store the real question the user asked.
    original_user_input = (base_snapshot or {}).get("user_input", "").strip()
    user_input_for_store = (
        original_user_input
        or format_user_message_for_persistence("[HITL resume]", [])
    )

    queue: asyncio.Queue = asyncio.Queue()
    collected_events: list[dict] = []

    async def producer() -> None:
        nonlocal collected_events
        collected_events = []
        dec_ev = build_decision_response_timeline_event(
            decision_ui_id=hitl_decision_ui_id,
            selected_options=hitl_selected_options,
        )
        if dec_ev:
            collected_events.append(dec_ev)
        else:
            param_ev = build_parameter_response_timeline_event(resume)
            if param_ev:
                collected_events.append(param_ev)

        def _merged_resume_progress() -> dict:
            return merge_resume_progress_state(base_snapshot, collected_events)

        last_progress_flush = time.monotonic()
        progress_stream_idx = 0
        if project_id and user_id:
            await upsert_progress(
                project_id,
                user_id,
                rid_for_progress,
                status="running",
                user_input=user_input_for_store,
                ui_language=ui_language,
                **_merged_resume_progress(),
            )
            last_progress_flush = time.monotonic()
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async for event in stream_resume_request(
                    resume=resume,
                    session_id=session_id,
                    request_id=request_id,
                    ui_language=ui_language,
                    input_language=input_language,
                    checkpointer=checkpointer,
                    model_id=model_id,
                    user_id=user_id,
                    project_id=project_id,
                ):
                    collected_events.append(event)
                    await queue.put(event)
                    if project_id and user_id:
                        progress_stream_idx += 1
                        now = time.monotonic()
                        if not _should_flush_progress_upsert(
                            now,
                            last_progress_flush,
                            progress_stream_idx,
                            prog_min_iv,
                            prog_force_n,
                        ):
                            continue
                        last_progress_flush = now
                        await upsert_progress(
                            project_id,
                            user_id,
                            rid_for_progress,
                            status="running",
                            user_input=user_input_for_store,
                            ui_language=ui_language,
                            **_merged_resume_progress(),
                        )
        except asyncio.CancelledError:
            logger.info(
                "Resume cancelled by user",
                session_id=session_id,
                request_id=request_id,
            )
        except asyncio.TimeoutError:
            err_ev = {
                "type": "error",
                "id": "timeout",
                "label": get_intent_label("stream_error_label", ui_language),
                "detail": f"Resume timed out after {settings.timeout_seconds} seconds.",
                "status": "error",
                "timestamp": int(time.time() * 1000),
            }
            collected_events.append(err_ev)
            await queue.put(err_ev)
        except Exception as e:
            err_msg = str(e).strip() or type(e).__name__
            logger.error("Resume stream failed", error=err_msg, exc_info=True)
            err_ev = {
                "type": "error",
                "id": "error",
                "label": get_intent_label("stream_error_label", ui_language),
                "detail": err_msg,
                "status": "error",
                "timestamp": int(time.time() * 1000),
            }
            collected_events.append(err_ev)
            await queue.put(err_ev)
        finally:
            _unregister_producer(request_id)
            persist_done = False
            if project_id and user_id:
                # Merge first-leg timeline into the events so
                # persist_analysis_result sees the full picture.
                base_timeline = (
                    list((base_snapshot or {}).get("timeline") or [])
                    if isinstance((base_snapshot or {}).get("timeline"), list)
                    else []
                )
                merged_events_for_persist = base_timeline + list(collected_events)

                # Use first-leg request_id so ON CONFLICT updates the
                # existing messages row rather than creating a second pair.
                persist_rid = rid_for_progress or request_id or None

                try:
                    await asyncio.shield(
                        asyncio.wait_for(
                            persist_analysis_result(
                                project_id,
                                user_id,
                                user_input_for_store,
                                merged_events_for_persist,
                                request_id=persist_rid,
                                ui_language=ui_language,
                            ),
                            timeout=30.0,
                        )
                    )
                    persist_done = True
                except asyncio.TimeoutError:
                    asyncio.create_task(
                        _persist_background(
                            project_id,
                            user_id,
                            user_input_for_store,
                            list(merged_events_for_persist),
                            persist_rid,
                            ui_language,
                        )
                    )
                    persist_done = True
                except (asyncio.CancelledError, Exception) as e:
                    logger.error("Resume persist failed", error=str(e), exc_info=True)
                    persist_done = True
                if persist_done and not _stream_ended_awaiting_human(collected_events):
                    try:
                        await asyncio.shield(clear_progress(project_id))
                    except (asyncio.CancelledError, Exception):
                        pass
            await queue.put(None)

    task = asyncio.create_task(producer())
    _register_producer(request_id, task)

    yield create_sse_message(
        {
            "type": "step",
            "id": "stream-init-resume",
            "label": get_stream_adapter_label("stream_analysis_start", ui_language),
            "status": "running",
            "timestamp": int(time.time() * 1000),
        }
    )

    try:
        while True:
            ev = await queue.get()
            if ev is None:
                break
            if _should_emit_event(ev, running_step_whitelist=running_step_whitelist):
                yield create_sse_message(ev)
    except (asyncio.CancelledError, GeneratorExit):
        cancel_producer_by_request_id(request_id)


async def stream_deep_analysis(
    message: str,
    attachments: list[AnalyzeAttachment] | None,
    session_id: str,
    ui_language: str = "zh",
    input_language: str = "auto",
    checkpointer: Any = None,
    request_id: str = "",
    client_timezone: str | None = None,
    project_id: str | None = None,
    user_id: str | None = None,
    model_id: str | None = None,
):
    """Stream DeepAgent analysis with cooperative cancellation.

    Producer runs in a background task. When the client disconnects or calls
    /analyze/cancel, the producer is cancelled; partial results are still persisted.
    """
    import time

    from app.services.message_persistence import (
        format_user_message_for_persistence,
        persist_analysis_result,
    )
    from app.services.progress_service import clear_progress, upsert_progress

    async def _persist_background(
        pid: str, uid: str, msg: str, events: list, rid: str | None, lang: str
    ) -> None:
        try:
            await persist_analysis_result(
                pid, uid, msg, events, request_id=rid, ui_language=lang
            )
        except Exception as e:
            logger.error("Background persist retry failed", error=str(e), exc_info=True)
        finally:
            if not _stream_ended_awaiting_human(events):
                await clear_progress(pid)

    start_time = time.time()
    settings = get_settings()
    prog_min_iv = settings.progress_upsert_min_interval_seconds
    prog_force_n = settings.progress_upsert_force_every_n_events
    running_step_whitelist = _parse_running_step_whitelist(
        settings.step_running_whitelist
    )
    from app.middleware.user_input_unwrap import unwrap_structured_user_prompt

    message = unwrap_structured_user_prompt(message)
    files_payload = [
        a.model_dump(exclude_none=True) for a in (attachments or [])
    ]
    user_input_for_store = format_user_message_for_persistence(message, files_payload)

    queue: asyncio.Queue = asyncio.Queue()
    collected_events: list[dict] = []

    # Register sandbox SSE emitter so sandbox tools can push real-time output.
    # Must be called BEFORE asyncio.create_task(producer()) so the producer task
    # inherits the ContextVar value in its copied execution context.
    try:
        from app.tools.sandbox_sse import set_sse_emitter as _set_sandbox_emitter

        async def _sandbox_queue_emitter(event: dict) -> None:
            await queue.put(event)

        _set_sandbox_emitter(_sandbox_queue_emitter)
    except Exception:  # noqa: BLE001
        pass  # sandbox SSE is optional — never block the main stream

    def _state() -> dict:
        from app.services.progress_service import _state_from_events

        return _state_from_events(collected_events)

    async def producer() -> None:
        nonlocal collected_events
        cancelled = False
        last_progress_flush = time.monotonic()
        progress_stream_idx = 0
        if project_id and user_id:
            await upsert_progress(
                project_id,
                user_id,
                request_id,
                status="running",
                user_input=user_input_for_store,
                ui_language=ui_language,
            )
            last_progress_flush = time.monotonic()
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                async for event in stream_analyze_request(
                    text=message,
                    files=files_payload,
                    session_id=session_id,
                    ui_language=ui_language,
                    input_language=input_language,
                    checkpointer=checkpointer,
                    request_id=request_id,
                    client_timezone=client_timezone,
                    model_id=model_id,
                    user_id=user_id,
                    project_id=project_id,
                ):
                    collected_events.append(event)
                    await queue.put(event)
                    if project_id and user_id:
                        progress_stream_idx += 1
                        now = time.monotonic()
                        if not _should_flush_progress_upsert(
                            now,
                            last_progress_flush,
                            progress_stream_idx,
                            prog_min_iv,
                            prog_force_n,
                        ):
                            continue
                        last_progress_flush = now
                        st = _state()
                        await upsert_progress(
                            project_id,
                            user_id,
                            request_id,
                            status="running",
                            user_input=user_input_for_store,
                            ui_language=ui_language,
                            **st,
                        )
        except asyncio.CancelledError:
            cancelled = True
            logger.info(
                "Analysis cancelled by user",
                session_id=session_id,
                request_id=request_id,
                events_collected=len(collected_events),
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Analysis timed out",
                session_id=session_id,
                timeout_seconds=settings.timeout_seconds,
            )
            err_ev = {
                "type": "error",
                "id": "timeout",
                "label": get_intent_label("stream_error_label", ui_language),
                "detail": f"Analysis timed out after {settings.timeout_seconds} seconds.",
                "status": "error",
                "timestamp": int(time.time() * 1000),
            }
            collected_events.append(err_ev)
            await queue.put(err_ev)
            if project_id and user_id:
                await upsert_progress(
                    project_id,
                    user_id,
                    request_id,
                    status="failed",
                    user_input=user_input_for_store,
                    ui_language=ui_language,
                    error_detail=err_ev.get("detail", ""),
                )
        except Exception as e:
            err_msg = str(e).strip() if e else ""
            if not err_msg:
                err_msg = f"{type(e).__name__}: {get_intent_label('stream_error_unknown', ui_language)}"
            logger.error("Streaming analysis failed", error=err_msg, exc_info=True)
            err_ev = {
                "type": "error",
                "id": "error",
                "label": get_intent_label("stream_error_label", ui_language),
                "detail": err_msg,
                "status": "error",
                "timestamp": int(time.time() * 1000),
            }
            collected_events.append(err_ev)
            await queue.put(err_ev)
            if project_id and user_id:
                await upsert_progress(
                    project_id,
                    user_id,
                    request_id,
                    status="failed",
                    user_input=user_input_for_store,
                    ui_language=ui_language,
                    error_detail=err_ev.get("detail", ""),
                )
        finally:
            _unregister_producer(request_id)
            awaiting_human = _stream_ended_awaiting_human(collected_events)
            # Throttled loop upserts can omit tail SSE. On HITL pause we skip
            # persist until resume; merge uses project_analysis_progress.timeline.
            # Without this flush, base_timeline may lack parameter_request while
            # the resume leg still adds parameter_response (broken replay).
            if project_id and user_id and awaiting_human and collected_events:
                try:
                    st = _state()
                    await upsert_progress(
                        project_id,
                        user_id,
                        request_id,
                        status="running",
                        user_input=user_input_for_store,
                        ui_language=ui_language,
                        **st,
                    )
                except Exception as e:
                    logger.warning(
                        "analyze_hitl_pause_progress_flush_failed",
                        project_id=project_id,
                        error=str(e),
                    )
            persist_done = False
            if project_id and user_id and not awaiting_human:
                try:
                    await asyncio.shield(
                        asyncio.wait_for(
                            persist_analysis_result(
                                project_id,
                                user_id,
                                user_input_for_store,
                                collected_events,
                                request_id=request_id or None,
                                ui_language=ui_language,
                            ),
                            timeout=30.0,
                        )
                    )
                    persist_done = True
                except asyncio.TimeoutError:
                    logger.warning(
                        "Persist timed out, retrying in background (progress row kept for frontend)",
                        project_id=project_id,
                    )
                    asyncio.create_task(
                        _persist_background(
                            project_id,
                            user_id,
                            user_input_for_store,
                            list(collected_events),
                            request_id or None,
                            ui_language,
                        )
                    )
                except (asyncio.CancelledError, Exception) as e:
                    logger.error("Producer persist failed", error=str(e), exc_info=True)
                    persist_done = True
                if persist_done:
                    try:
                        await asyncio.shield(clear_progress(project_id))
                    except (asyncio.CancelledError, Exception):
                        pass
            await queue.put(None)

    task = asyncio.create_task(producer())
    _register_producer(request_id, task)

    yield create_sse_message(
        {
            "type": "step",
            "id": "stream-init",
            "label": get_stream_adapter_label("stream_analysis_start", ui_language),
            "status": "running",
            "timestamp": int(time.time() * 1000),
        }
    )

    try:
        while True:
            ev = await queue.get()
            if ev is None:
                break
            if _should_emit_event(ev, running_step_whitelist=running_step_whitelist):
                yield create_sse_message(ev)
    except (asyncio.CancelledError, GeneratorExit):
        cancel_producer_by_request_id(request_id)


@app.get("/agents")
async def list_agents():
    """List available sub-agents (from skill registry)."""
    registry = get_skill_registry()
    return {
        "agents": [
            {"name": skill.name, "description": skill.description}
            for skill in registry.list_skills()
        ],
    }


@app.get("/registry/subagents")
async def list_registry_subagents():
    """Catalog: official subagents from ``config/subagents.registry.yaml`` plus skill metadata."""
    return build_subagents_catalog()


@app.get("/registry/skills")
async def list_registry_skills():
    """Catalog: global skill packages under the runtime ``skills/`` directory."""
    return build_global_skills_catalog()


@app.get("/tool-tab-config")
async def get_tool_tab_config():
    """Return workspace_tab config for all tools that declare one.

    Frontend reads this once at startup to initialize ToolTabRegistry.
    Response shape: { tools: { [toolName]: { workspace_tab: WorkspaceTabConfig } } }
    """
    return {"tools": get_all_workspace_tab_configs()}


@app.get("/tools")
async def list_tools():
    """List available tools."""
    common_tools = create_common_tools()
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in common_tools
        ],
    }


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.reload,
    )
