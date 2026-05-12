"""Web-security subagent tools: structured web threat analysis."""

import base64
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.sse.tool_presentation import WEB_SECURITY_TOOL_ORDER, get_tool_rule

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class DetectWebAttackInput(BaseModel):
    """Input for detect_web_attack tool."""

    request_data: str | None = Field(
        default=None,
        description=(
            "HTTP request data, log fragment, URL, or web source to analyze"
        ),
    )
    file_path: str | None = Field(
        default=None,
        description=(
            "Virtual workspace file path to analyze, e.g. /workspace/shell.php"
        ),
    )
    hint: str = Field(
        default="auto",
        description=(
            "Classification hint: auto (default), http (traffic), or code "
            "(hosted source/webshell)"
        ),
    )


# ---------------------------------------------------------------------------
# Implementation functions
# ---------------------------------------------------------------------------

_WEB_TOOL_DESCRIPTION_FALLBACKS: dict[str, str] = {
    "detect_web_attack": "Detect web attack patterns (SQLi, XSS, RCE, etc.)",
}


def _registry_tool_description(tool_name: str, code_fallback: str) -> str:
    rule = get_tool_rule(tool_name)
    if rule and rule.description:
        return rule.description
    return code_fallback


def _runtime_backend(runtime: Any) -> Any:
    backend = getattr(runtime, "backend", None)
    if backend is not None:
        return backend
    from app.backends.composite import create_layered_backend

    return create_layered_backend()(runtime)


def _normalize_workspace_file_path(file_path: str) -> str | None:
    """Canonicalize workspace virtual paths (same rules as PathAliasBackend / SReadFile)."""
    from app.backends.path_aliases import canonicalize_agent_path

    cleaned = (file_path or "").strip().replace("\\", "/")
    if not cleaned:
        return None
    low = cleaned.lower()
    if low in ("/workspace", "workspace"):
        return None
    if not (low.startswith("workspace/") or low.startswith("/workspace")):
        return None
    out = canonicalize_agent_path(cleaned)
    if out == "/workspace" or not out.startswith("/workspace/"):
        return None
    return out


def _is_decode_error(error: str) -> bool:
    lowered = error.lower()
    return "codec can't decode" in lowered or "unicodedecodeerror" in lowered


def _decode_file_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _download_workspace_file(backend: Any, normalized_path: str) -> tuple[str | None, str | None]:
    try:
        responses = backend.download_files([normalized_path])
    except Exception as exc:
        return None, f"file_read_failed:{exc}"
    if not responses:
        return None, "file_read_failed"
    response = responses[0]
    error = getattr(response, "error", None)
    if error:
        return None, str(error)
    content = getattr(response, "content", None)
    if not isinstance(content, bytes):
        return None, "unsupported_file_type"
    return _decode_file_bytes(content), None


def _read_workspace_file(
    file_path: str,
    runtime: Any,
) -> tuple[str | None, str | None]:
    normalized_path = _normalize_workspace_file_path(file_path)
    if normalized_path is None:
        return None, "path_out_of_scope"
    if runtime is None:
        return None, "backend_unavailable"
    try:
        backend = _runtime_backend(runtime)
        result = backend.read(
            normalized_path,
            offset=0,
            limit=200000,
        )
    except Exception as exc:
        return None, f"file_read_failed:{exc}"
    if isinstance(result, str):
        if result.startswith("Error:"):
            error = result.removeprefix("Error:").strip() or "file_read_failed"
            if _is_decode_error(error):
                return _download_workspace_file(backend, normalized_path)
            return None, error
        return result, None
    error = getattr(result, "error", None)
    if error:
        if _is_decode_error(str(error)):
            return _download_workspace_file(backend, normalized_path)
        return None, str(error)
    file_data = getattr(result, "file_data", None) or {}
    content = file_data.get("content") if isinstance(file_data, dict) else None
    encoding = file_data.get("encoding") if isinstance(file_data, dict) else None
    if encoding == "base64" and isinstance(content, str):
        try:
            return _decode_file_bytes(base64.b64decode(content)), None
        except Exception as exc:
            return None, f"file_read_failed:{exc}"
    if not isinstance(content, str):
        return None, "unsupported_file_type"
    return content, None


def detect_web_attack(
    request_data: str | None = None,
    hint: str = "auto",
    file_path: str | None = None,
    runtime: ToolRuntime = None,
) -> dict[str, Any]:
    """Detect web threats with schema v2 plus legacy fields."""
    from .models import SourceInfo
    from .pipeline import analyze_web_threat, error_report

    if request_data and file_path:
        return error_report(
            "ambiguous_input",
            "Provide request_data or file_path, not both.",
        )
    if not request_data and not file_path:
        return error_report(
            "missing_input",
            "Provide request_data or file_path.",
        )
    if file_path:
        normalized_path = _normalize_workspace_file_path(file_path)
        source = SourceInfo(kind="file", path=normalized_path or file_path)
        content, error = _read_workspace_file(file_path, runtime)
        if error:
            error_code = (
                error
                if error in {"backend_unavailable", "path_out_of_scope"}
                else "file_read_failed"
            )
            return error_report(
                error_code,
                error,
                source=source,
            )
        return analyze_web_threat(content or "", hint=hint, source=source)

    return analyze_web_threat(request_data or "", hint=hint)


# ---------------------------------------------------------------------------
# Tool assembly
# ---------------------------------------------------------------------------


def _append_web_tool(tool_name: str, out: list[StructuredTool]) -> None:
    rule = get_tool_rule(tool_name)
    if rule is not None and not rule.enabled:
        return
    desc = _registry_tool_description(
        tool_name,
        _WEB_TOOL_DESCRIPTION_FALLBACKS[tool_name],
    )
    if tool_name == "detect_web_attack":
        out.append(
            StructuredTool.from_function(
                func=detect_web_attack,
                name="detect_web_attack",
                description=desc,
                infer_schema=False,
                args_schema=DetectWebAttackInput,
            )
        )


def create_web_tools() -> list[StructuredTool]:
    """Create web security tools.

    Enabled flags and descriptions come from ``config/tool_presentation.yaml``
    (keys under ``WEB_SECURITY_TOOL_ORDER``).
    """
    out: list[StructuredTool] = []
    for name in WEB_SECURITY_TOOL_ORDER:
        _append_web_tool(name, out)
    return out
