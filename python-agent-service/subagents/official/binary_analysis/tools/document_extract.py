"""DocExtractTool — document structure extraction and macro analysis (FR-03 / ADR-13).

Dispatches to sandbox workers based on ``document_format`` and writes structured
Indicators to four evidence-chain buckets:

- ``document_analysis``  — structure, triggers, DDE, remote templates, PDF objects
- ``macro_analysis``     — VBA / XL4 modules, simulation events and gaps
- ``embedded_payloads``  — OLE objects, PDF embedded files, OneNote FDS
- ``strings_iocs``       — merged document IOC facts (FR-06 AC-2..6)

Format → worker dispatch table:

+------------------------------+---------------------------+
| DocumentFormat               | Workers                   |
+==============================+===========================+
| OOXML_DOCX/XLSX/PPTX_MACRO   | run_olevba + run_vmonkey  |
| OLE2_DOC / OLE2_XLS / OLE2_PPT | run_olevba + run_vmonkey |
| PDF                          | run_peepdf                |
| RTF                          | run_olevba                |
| HTA                          | run_vmonkey               |
| ONENOTE                      | run_onenote               |
| ENCRYPTED_OFFICE             | run_msoffcrypto → recurse |
+------------------------------+---------------------------+

All worker invocations are performed via :meth:`SandboxClient.exec`; the worker
script is uploaded to the sandbox workspace and executed with the JSON input
file.  Total wall-clock budget across all workers is 300 seconds (NFR-02).

Worker crashes are captured as ``document_parser_failed`` Indicators; ``status``
degrades to ``"degraded"`` but the call never raises (FR-03 AC-14).  If every
worker fails ``status`` is ``"failed"``.

Security (ADR-05 / NFR-04)
--------------------------
- All parser imports are confined to sandbox worker scripts; this module never
  imports ``oletools``, ``vipermonkey``, ``peepdf``, or ``msoffcrypto``.
- Sample bytes are uploaded to the sandbox workspace by the preceding
  :class:`~tools.file_identify.FileIdentifyTool` call; this
  tool only passes the *path* to the worker.
- Password plaintext is never written to any log; only ``sha256:XXXXXXXX``
  (8 hex chars) and a length-tagged truncated form are recorded (FR-03 AC-13).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict
from ulid import ULID

from audit import log_indicator_write, log_tool_call
from config import document_settings
from evidence_chain.store import EvidenceChainStore
from sandbox.client import SandboxClient, SandboxSession
from sandbox.registry import get_or_create_session
from schema.document_enums import DocumentFormat
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TOTAL_TIMEOUT_SEC: float = 300.0
_WORKERS_DIR: Path = Path(__file__).parent.parent / "sandbox" / "document_workers"
logger = structlog.get_logger()

# Python interpreter used to launch sandbox workers.
# - subprocess backend: sys.executable is correct — workers run on the host.
# - E2B backend: sys.executable is the *host* Python path, which does not
#   exist inside the Ubuntu 22.04 sandbox VM.  We use "python3.12" instead,
#   which is guaranteed to be on PATH by the E2B template (ADR-17 / ADR-DOC-01).
_SUBPROCESS_PYTHON = sys.executable
_SANDBOX_PYTHON = "python3.12"

# DocumentFormat members that use the olevba worker
_OLEVBA_FORMATS: frozenset[DocumentFormat] = frozenset(
    {
        DocumentFormat.OOXML_DOCX_MACRO,
        DocumentFormat.OOXML_XLSX_MACRO,
        DocumentFormat.OOXML_PPTX_MACRO,
        DocumentFormat.OLE2_DOC,
        DocumentFormat.OLE2_XLS,
        DocumentFormat.OLE2_PPT,
        DocumentFormat.RTF,
    }
)

_OOXML_FORMATS: frozenset[DocumentFormat] = frozenset(
    {
        DocumentFormat.OOXML_DOCX_MACRO,
        DocumentFormat.OOXML_XLSX_MACRO,
        DocumentFormat.OOXML_PPTX_MACRO,
    }
)

# DocumentFormat members that additionally run vmonkey after olevba
_VMONKEY_AFTER_OLEVBA_FORMATS: frozenset[DocumentFormat] = frozenset(
    {
        DocumentFormat.OOXML_DOCX_MACRO,
        DocumentFormat.OOXML_XLSX_MACRO,
        DocumentFormat.OOXML_PPTX_MACRO,
        DocumentFormat.OLE2_DOC,
        DocumentFormat.OLE2_XLS,
        DocumentFormat.OLE2_PPT,
    }
)

# ---------------------------------------------------------------------------
# Input / output schema
# ---------------------------------------------------------------------------


class DocExtractOptions(BaseModel):
    """Optional per-invocation overrides (all fields have safe defaults)."""

    vba_simulation_timeout_sec: int | None = None
    vba_max_instructions: int | None = None
    password_list_path: str | None = None
    enable_pdf_javascript_extract: bool = True

    model_config = ConfigDict(extra="ignore")


EmbeddedPayloadHandler = Callable[
    [str, list[dict[str, Any]]],
    Awaitable[list[dict[str, Any]]] | list[dict[str, Any]],
]
"""Optional host callback invoked after embedded payloads are materialized."""


class DocExtractInput(BaseModel):
    """Input schema for :class:`DocExtractTool`."""

    sample_path: str
    analysis_id: str
    document_format: str
    document_tier: str
    options: dict[str, Any] = {}

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Audit helper (FR-03 AC-13) — no plaintext, within-scope call
# ---------------------------------------------------------------------------


def _log_password_attempt(password: str) -> None:
    """Audit-log one password attempt without storing plaintext (FR-03 AC-13).

    Writes a ``tool_call`` audit entry with:
    - ``hash_prefix``  — first 8 hex characters of the SHA-256 digest
    - ``truncated``    — first two characters + "*" padding + ``[len=N]`` tag

    Args:
        password: The password string that is about to be tried.
    """
    hash_prefix = "sha256:" + hashlib.sha256(password.encode()).hexdigest()[:8]
    visible = password[:2] if len(password) >= 2 else password
    truncated = visible + "*" * max(0, len(password) - 2) + f"[len={len(password)}]"
    log_tool_call(
        tool_name="document_extract_password_attempt",
        args={"hash_prefix": hash_prefix, "truncated": truncated},
        result=None,
        duration_ms=0.0,
    )


# ---------------------------------------------------------------------------
# Worker invocation
# ---------------------------------------------------------------------------


async def _run_worker(
    client: SandboxClient,
    session: SandboxSession,
    worker_filename: str,
    input_payload: dict[str, Any],
    *,
    timeout: float,
) -> tuple[dict[str, Any], bool]:
    """Upload worker script + input JSON to sandbox, execute, parse stdout JSON.

    The worker is uploaded fresh on every call to support both the subprocess
    backend (local tmpdir) and the future E2B backend (remote VM).

    Args:
        client: Active :class:`SandboxClient` backend.
        session: The analysis session whose workspace receives the files.
        worker_filename: Script filename (e.g. ``"run_olevba.py"``).
        input_payload: Dict that will be JSON-serialised and passed as input.
        timeout: Hard wall-clock budget for the worker subprocess in seconds.

    Returns:
        A ``(output_dict, success)`` pair.  ``success`` is ``False`` when the
        worker exited non-zero, timed out, or produced unparseable JSON.
    """
    worker_src = (_WORKERS_DIR / worker_filename).read_bytes()
    worker_sandbox = f"{session.workdir.rstrip('/')}/{worker_filename}"
    await client.upload(session, worker_sandbox, worker_src)

    input_filename = f"input_{worker_filename.replace('.py', '')}.json"
    input_sandbox = f"{session.workdir.rstrip('/')}/{input_filename}"
    await client.upload(session, input_sandbox, json.dumps(input_payload).encode())

    python_exe = (
        _SUBPROCESS_PYTHON if session.backend == "subprocess" else _SANDBOX_PYTHON
    )
    result = await client.exec(
        session,
        [python_exe, worker_filename, "--input", input_filename],
        timeout=timeout,
        cwd=session.workdir,
    )

    if result.timed_out:
        return {"error": f"worker timed out after {timeout:.0f}s"}, False

    stdout = result.stdout.strip()
    try:
        output = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {"error": f"invalid JSON from worker: {stdout[:256]}"}, False

    return output, result.exit_code == 0


# ---------------------------------------------------------------------------
# Password list loading
# ---------------------------------------------------------------------------


def _load_password_list(path_override: str | None) -> list[str]:
    """Load the password dictionary (FR-03 AC-12).

    Resolution order:
    1. ``path_override`` from tool options (e.g. command-line / test fixture).
    2. :attr:`~binary_analysis.config.DocumentSettings.password_list_path`.
    3. Fallback to the bundled ``config/container_password_list.yaml`` in the
       package root (covers offline developer workstations).

    Args:
        path_override: Optional explicit path from caller options.

    Returns:
        Ordered list of plaintext passwords (may be empty on file error).
    """
    candidates: list[Path] = []
    if path_override:
        candidates.append(Path(path_override))
    try:
        candidates.append(document_settings().password_list_path)
    except Exception:  # noqa: BLE001
        pass
    candidates.append(
        Path(__file__).resolve().parent.parent
        / "config"
        / "container_password_list.yaml"
    )

    for candidate in candidates:
        try:
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("passwords"), list):
                return [str(p) for p in raw["passwords"]]
        except Exception:  # noqa: BLE001
            continue
    return []


# ---------------------------------------------------------------------------
# Child sample ID generation (FR-30 AC-3/6)
# ---------------------------------------------------------------------------


def _new_child_sample_id() -> str:
    """Generate a fresh ULID string for a child sample extracted from a document.

    Each embedded payload that may be recursively analysed (PE / ELF / Mach-O)
    is assigned a unique ``child_sample_id`` at extraction time so that the
    parent document analysis and the child :class:`EvidenceChainStore` can
    be correlated without re-hashing the bytes (FR-30 AC-3 / AC-6).
    """
    return str(ULID())


# ---------------------------------------------------------------------------
# Indicator builders
# ---------------------------------------------------------------------------


def _append_indicator(
    store: EvidenceChainStore,
    bucket: Bucket,
    indicator_type: str,
    severity: Severity,
    data: dict[str, Any],
    *,
    source_fr: str = "FR-03",
    confidence: Confidence = Confidence.HIGH,
) -> Indicator:
    """Create a fact Indicator, append it to *store*, emit an audit entry."""
    ind = Indicator(
        source_fr=source_fr,
        indicator_type=indicator_type,
        severity=severity,
        confidence=confidence,
        kind="fact",
        data=data,
    )
    store.append(bucket, ind)
    log_indicator_write(
        indicator_id=ind.id,
        bucket=bucket.value,
        kind=ind.kind,
        severity=ind.severity.value,
        source_fr=ind.source_fr,
    )
    return ind


def _record_parser_failure(
    store: EvidenceChainStore,
    worker: str,
    error: str,
    *,
    fatal: bool = False,
) -> Indicator:
    """Write a ``document_parser_failed`` Indicator for a crashed worker."""
    return _append_indicator(
        store,
        Bucket.document_analysis,
        "document_parser_failed",
        Severity.WARNING,
        {"worker": worker, "error": error, "fatal": fatal},
    )


def _ingest_ooxml_structure(
    output: dict[str, Any],
    store: EvidenceChainStore,
    doc_analysis: dict[str, Any],
    embedded_payloads: list[dict[str, Any]],
    parser_failures: list[dict[str, Any]],
) -> bool:
    """Map OOXML fallback structure output into document evidence buckets."""
    wrote_fact = False

    metadata = output.get("document_metadata")
    if isinstance(metadata, dict) and metadata:
        _append_indicator(
            store,
            Bucket.document_analysis,
            "document_metadata",
            Severity.INFO,
            dict(metadata),
        )
        doc_analysis["metadata"].update(metadata)
        wrote_fact = True

    structure_parts = doc_analysis["structure"].setdefault("ooxml_parts", [])
    for part in output.get("ooxml_parts", []):
        if not isinstance(part, dict):
            continue
        data = {
            "name": str(part.get("name", "")),
            "tag": str(part.get("tag", "part")),
            "content_type": str(part.get("content_type", "")),
            "source": "ooxml_structure",
        }
        _append_indicator(
            store,
            Bucket.document_analysis,
            "ooxml_part",
            Severity.INFO,
            data,
        )
        structure_parts.append(data)
        wrote_fact = True

    for ref in output.get("remote_templates", []):
        if not isinstance(ref, dict):
            continue
        data = {
            "source": str(ref.get("source", "")),
            "target": str(ref.get("target", "")),
            "relationship_type": str(ref.get("relationship_type", "")),
            "target_mode": str(ref.get("target_mode", "")),
            "tag": str(ref.get("tag", "external_relationship")),
        }
        _append_indicator(
            store,
            Bucket.document_analysis,
            "remote_template_ref",
            Severity.WARNING,
            data,
        )
        doc_analysis["remote_template"].append(data)
        wrote_fact = True

    for obj in output.get("embedded_objects", []):
        if not isinstance(obj, dict):
            continue
        data = {
            "name": str(obj.get("name", "")),
            "container_path": str(obj.get("container_path", "")),
            "suggested_format": str(obj.get("suggested_format", "ole_object")),
            "source": str(obj.get("source", "ooxml_structure")),
        }
        _append_indicator(
            store,
            Bucket.embedded_payloads,
            "embedded_ole_object",
            Severity.WARNING,
            data,
        )
        embedded_payloads.append(data)
        wrote_fact = True

    for warning in output.get("warnings", []):
        text = str(warning)
        _record_parser_failure(store, "run_ooxml_structure.py", text, fatal=False)
        parser_failures.append(
            {
                "worker": "run_ooxml_structure.py",
                "error": text,
                "fatal": False,
            }
        )

    return wrote_fact


# ---------------------------------------------------------------------------
# olevba result → Indicators (FR-03 AC-1/2/3/9)
# ---------------------------------------------------------------------------

_AUTO_TRIGGER_NAMES: frozenset[str] = frozenset(
    {
        "autoopen",
        "auto_open",
        "document_open",
        "workbook_open",
        "presentation_open",
        "autoexec",
    }
)
_NORMALIZED_AUTO_TRIGGER_NAMES: frozenset[str] = frozenset(
    re.sub(r"[^a-z0-9]+", "", name) for name in _AUTO_TRIGGER_NAMES
)

_MACRO_LOLBIN_RE = re.compile(
    r"(?i)\b(?:powershell|pwsh|cmd(?:\.exe)?|mshta|certutil|regsvr32|"
    r"rundll32|wscript|cscript|bitsadmin|msiexec)\b"
)
_MACRO_NETWORK_RE = re.compile(
    r"(?i)\b(?:xmlhttp|winhttprequest|urldownloadtofile|webclient|"
    r"internetopen|downloadstring|openurl)\b|https?://"
)
_MACRO_FILE_WRITE_RE = re.compile(
    r"(?i)\b(?:adodb\.stream|savetofile|writeallbytes|writefile|"
    r"createTextFile)\b"
)
_MACRO_COMMAND_RE = re.compile(r"(?i)\b(?:shell|run|exec|createprocess)\b")


def _office_trigger_tag(trigger_type: str) -> str:
    """Return the scoring tag for an Office trigger fact."""
    normalized = re.sub(r"[^a-z0-9]+", "", trigger_type.lower())
    if normalized in _NORMALIZED_AUTO_TRIGGER_NAMES:
        return "auto_trigger"
    return "suspicious_trigger"


def _macro_action_tag(event: dict[str, Any]) -> str:
    """Classify a macro simulation event for deterministic scoring."""
    args = event.get("args_literal", [])
    if isinstance(args, list):
        args_text = " ".join(str(v) for v in args)
    else:
        args_text = str(args)
    haystack = f"{event.get('action', '')} {args_text}"
    if _MACRO_LOLBIN_RE.search(haystack):
        return "lolbin"
    if _MACRO_NETWORK_RE.search(haystack):
        return "network_request"
    if _MACRO_FILE_WRITE_RE.search(haystack):
        return "file_write"
    if _MACRO_COMMAND_RE.search(haystack):
        return "command_invocation"
    return "macro_action"


def _ingest_olevba(
    output: dict[str, Any],
    store: EvidenceChainStore,
    doc_analysis: dict[str, Any],
    macro_analysis: dict[str, Any],
) -> None:
    """Map olevba worker output to evidence-chain Indicators.

    Populates ``doc_analysis["triggers"]`` and ``macro_analysis["vba_modules"]``
    / ``macro_analysis["xl4_macros"]`` as side effects so the caller can
    include them in the tool return value.
    """
    for module in output.get("vba_modules", []):
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "vba_module",
            Severity.INFO,
            {
                "name": module.get("name", ""),
                "source_hash": module.get("source_hash", ""),
                "source_preview": module.get("source_preview", ""),
                "deobfuscated_preview": module.get("deobfuscated_preview", ""),
                "deobfuscated_changed": module.get("deobfuscated_changed", False),
                "code_page": module.get("code_page", "utf-8"),
            },
        )
        macro_analysis["vba_modules"].append(module)

    for xl4 in output.get("xl4_macros", []):
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "xl4_macro",
            Severity.WARNING,
            {"cell": xl4.get("cell", ""), "formula": xl4.get("formula", "")},
        )
        macro_analysis["xl4_macros"].append(xl4)

    for action in output.get("macro_actions", []):
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "macro_action_call",
            Severity.WARNING,
            {
                "action": action.get("action", ""),
                "args_literal": action.get("args_literal", []),
                "source": action.get("source", "olevba_static"),
                "module": action.get("module", ""),
                "tag": _macro_action_tag(action),
            },
        )
        macro_analysis["static_actions"].append(action)

    for ioc in output.get("static_iocs", []):
        if isinstance(ioc, dict):
            macro_analysis["static_iocs"].append(ioc)

    for trigger in output.get("triggers", []):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "trigger",
            Severity.WARNING,
            {
                "type": trigger.get("type", ""),
                "location": trigger.get("location", ""),
                "source": "olevba",
                "tag": _office_trigger_tag(str(trigger.get("type", ""))),
            },
        )
        doc_analysis["triggers"].append(trigger)


def _has_olevba_facts(output: dict[str, Any]) -> bool:
    """Return true when olevba produced document or macro facts worth ingesting."""
    return bool(
        output.get("vba_modules")
        or output.get("xl4_macros")
        or output.get("macro_actions")
        or output.get("static_iocs")
        or output.get("triggers")
    )


async def _run_olevba_and_ingest(
    client: SandboxClient,
    session: SandboxSession,
    sample_path: str,
    *,
    timeout: float,
    store: EvidenceChainStore,
    doc_analysis: dict[str, Any],
    macro_analysis: dict[str, Any],
    parser_failures: list[dict[str, Any]],
    count_empty_success: bool,
) -> bool:
    """Run the olevba worker and ingest usable facts.

    ``count_empty_success`` preserves the historical decrypted-Office behavior:
    an empty but successful post-decryption olevba run still counts as a worker
    success. Protected-OLE fallback uses ``False`` so an empty fallback does not
    mask the password-exhausted downgrade.
    """
    olevba_out, olevba_ok = await _run_worker(
        client,
        session,
        "run_olevba.py",
        {"sample_path": sample_path, "options": {}},
        timeout=timeout,
    )
    has_facts = _has_olevba_facts(olevba_out)
    if has_facts or (count_empty_success and olevba_ok):
        _ingest_olevba(olevba_out, store, doc_analysis, macro_analysis)
        return True
    if olevba_out.get("error"):
        _record_parser_failure(store, "run_olevba.py", olevba_out["error"])
        parser_failures.append(
            {
                "worker": "run_olevba.py",
                "error": olevba_out["error"],
                "fatal": False,
            }
        )
    return False


# ---------------------------------------------------------------------------
# vmonkey result → Indicators (FR-03 AC-4/5)
# ---------------------------------------------------------------------------


def _ingest_vmonkey(
    output: dict[str, Any],
    store: EvidenceChainStore,
    macro_analysis: dict[str, Any],
    *,
    parser_failures: list[dict[str, Any]],
) -> None:
    """Map vmonkey worker output to evidence-chain Indicators."""
    status = output.get("simulation_status", "unavailable")

    for event in output.get("simulation_events", []):
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "macro_action_call",
            Severity.WARNING,
            {
                "action": event.get("action", ""),
                "args_literal": event.get("args_literal", []),
                "source_line": event.get("source_line"),
                "tag": _macro_action_tag(event),
            },
        )
        macro_analysis["simulation_events"].append(event)

    for gap in output.get("simulation_gaps", []):
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "vba_simulation_gap",
            Severity.INFO,
            {
                "statement_type": gap.get("statement_type", ""),
                "source_line": gap.get("source_line"),
                "skip_reason": gap.get("skip_reason", ""),
            },
        )
        macro_analysis["simulation_gaps"].append(gap)

    if status == "timeout":
        _append_indicator(
            store,
            Bucket.macro_analysis,
            "vba_simulation_timeout",
            Severity.WARNING,
            {"simulation_status": "timeout"},
        )
        parser_failures.append(
            {
                "worker": "run_vmonkey.py",
                "error": "simulation timed out",
                "fatal": False,
            }
        )

    _append_indicator(
        store,
        Bucket.macro_analysis,
        "macro_simulation_status",
        Severity.INFO,
        {"simulation_status": status},
    )
    macro_analysis["simulation_status"] = status


# ---------------------------------------------------------------------------
# peepdf result → Indicators (FR-03 AC-6/7/8)
# ---------------------------------------------------------------------------

_PE_EXTENSIONS: frozenset[str] = frozenset({".exe", ".dll", ".scr", ".sys", ".ocx"})
_SCRIPT_EXTENSIONS: frozenset[str] = frozenset(
    {".js", ".jse", ".vbs", ".vbe", ".ps1", ".hta", ".wsf", ".bat", ".cmd"}
)
_ARCHIVE_EXTENSIONS: frozenset[str] = frozenset({".zip", ".rar", ".7z", ".cab", ".iso"})
_RECURSIVE_PAYLOAD_FORMATS: frozenset[str] = frozenset({"pe", "elf", "mach-o"})


def _pdf_action_tag(chain_or_action: Any) -> str:
    """Return the scoring tag for a PDF action chain or trigger."""
    if isinstance(chain_or_action, dict):
        values = list(chain_or_action.values())
    elif isinstance(chain_or_action, list):
        values = chain_or_action
    else:
        values = [chain_or_action]
    text = " ".join(str(v).lower() for v in values)
    if "launch" in text:
        return "launch_action"
    if "/js" in text or "javascript" in text or "js" == text.strip():
        return "js_trigger"
    if "xfa" in text:
        return "xfa_script"
    return "pdf_action"


def _suggest_document_payload_format(name: str) -> str:
    """Infer a lightweight embedded-payload format hint from a filename."""
    normalized = name.strip().lower()
    suffix = Path(normalized).suffix.lower()
    if not suffix and normalized:
        suffix = normalized if normalized.startswith(".") else f".{normalized}"
    if suffix in _PE_EXTENSIONS:
        return "pe"
    if suffix in _SCRIPT_EXTENSIONS:
        return "script"
    if suffix in _ARCHIVE_EXTENSIONS:
        return "archive"
    if suffix in {".dylib", ".bundle", ".kext"}:
        return "mach-o"
    return "unknown"


def _best_effort_child_path(parent_analysis_id: str, child_id: str) -> str:
    """Return a deterministic placeholder path for non-materialized payloads."""
    if parent_analysis_id:
        return f"/workspace/{parent_analysis_id}/children/{child_id}.bin"
    return f"/workspace/children/{child_id}.bin"


def _worker_materialized_path(payload: dict[str, Any]) -> str:
    """Return worker-provided extraction path only when it represents real bytes."""
    extracted_to = str(payload.get("extracted_to") or "")
    if not extracted_to:
        return ""
    materialized_flag = payload.get("materialized")
    if materialized_flag is None:
        return extracted_to
    return extracted_to if bool(materialized_flag) else ""


def _payload_recursive_ready(materialized: bool, suggested_format: str) -> bool:
    """Return whether downstream recursion can safely consume this payload."""
    return materialized and suggested_format in _RECURSIVE_PAYLOAD_FORMATS


def _ingest_peepdf(
    output: dict[str, Any],
    store: EvidenceChainStore,
    doc_analysis: dict[str, Any],
    embedded_payloads: list[dict[str, Any]],
    parent_analysis_id: str = "",
) -> None:
    """Map peepdf worker output to evidence-chain Indicators."""
    keyword_summary = output.get("keyword_summary", {})
    if keyword_summary.get("keywords") or keyword_summary.get("structure"):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "pdf_keyword_summary",
            Severity.WARNING
            if keyword_summary.get("risk_counts", {}).get("high", 0)
            else Severity.INFO,
            keyword_summary,
        )
        doc_analysis["structure"]["pdf_keywords"] = keyword_summary.get("keywords", {})
        doc_analysis["structure"]["pdf_surface"] = keyword_summary.get("structure", {})

    js_analysis = output.get("js_analysis", {})
    if js_analysis.get("blocks") or js_analysis.get("markers"):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "pdf_js_analysis",
            Severity.CRITICAL
            if js_analysis.get("has_shellcode_markers")
            else Severity.WARNING,
            js_analysis,
        )

    if output.get("object_tree"):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "pdf_object_tree",
            Severity.INFO,
            {"objects": output["object_tree"]},
        )
        doc_analysis["structure"]["pdf_object_count"] = len(output["object_tree"])

    for trigger in output.get("triggers", []):
        action_type = trigger.get("action_type", "")
        js_preview = trigger.get("js_preview", "")
        ind_data: dict[str, Any] = {
            "type": trigger.get("type", ""),
            "action_type": action_type,
            "source": "peepdf",
            "tag": _pdf_action_tag(trigger),
        }
        if js_preview:
            # AC-8: pass JS source as embedded_js fact; no AST analysis in C5
            ind_data["embedded_js"] = js_preview
        _append_indicator(
            store,
            Bucket.document_analysis,
            "trigger",
            Severity.WARNING,
            ind_data,
        )
        doc_analysis["triggers"].append(trigger)

    for uri in output.get("uris", []):
        trigger = {
            "type": "URI",
            "action_type": "URI",
            "url": uri,
            "source": "pdf_keyword_scan",
            "tag": "uri_action",
        }
        _append_indicator(
            store,
            Bucket.document_analysis,
            "trigger",
            Severity.INFO,
            trigger,
        )
        doc_analysis["triggers"].append(trigger)

    for target in output.get("submit_targets", []):
        trigger = {
            "type": "SubmitForm",
            "action_type": "SubmitForm",
            "url": target,
            "source": "pdf_keyword_scan",
            "tag": "submit_form",
        }
        _append_indicator(
            store,
            Bucket.document_analysis,
            "trigger",
            Severity.WARNING,
            trigger,
        )
        doc_analysis["triggers"].append(trigger)

    for chain in output.get("action_chains", []):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "pdf_action_chain",
            Severity.INFO,
            {"chain": chain.get("chain", chain), "tag": _pdf_action_tag(chain)},
        )

    xfa = output.get("xfa_form", {})
    if xfa.get("present"):
        _append_indicator(
            store,
            Bucket.document_analysis,
            "xfa_form",
            Severity.WARNING,
            xfa,
        )

    for emb in output.get("embedded_files", []):
        child_id = _new_child_sample_id()
        suggested_format = str(
            emb.get("suggested_format")
            or _suggest_document_payload_format(str(emb.get("name", "")))
        )
        worker_path = _worker_materialized_path(emb)
        materialized = bool(worker_path)
        extracted_to = worker_path or _best_effort_child_path(
            parent_analysis_id, child_id
        )
        recursive_ready = _payload_recursive_ready(materialized, suggested_format)
        materialization_status = (
            "worker_materialized" if materialized else "best_effort_unmaterialized"
        )
        _append_indicator(
            store,
            Bucket.embedded_payloads,
            "pdf_embedded_file",
            Severity.WARNING,
            {
                "name": emb.get("name", ""),
                "sha256": emb.get("sha256", ""),
                "size_bytes": emb.get("size_bytes", 0),
                "source": "peepdf",
                "suggested_format": suggested_format,
                "child_sample_id": child_id,
                "child_analysis_id": child_id,
                "extracted_to": extracted_to,
                "materialized": materialized,
                "recursive_ready": recursive_ready,
                "materialization_status": materialization_status,
            },
        )
        embedded_payloads.append(
            {
                "source": "pdf_embedded_file",
                "sha256": emb.get("sha256", ""),
                "size_bytes": emb.get("size_bytes", 0),
                "name": emb.get("name", ""),
                "suggested_format": suggested_format,
                "child_sample_id": child_id,
                "child_analysis_id": child_id,
                "extracted_to": extracted_to,
                "materialized": materialized,
                "recursive_ready": recursive_ready,
                "materialization_status": materialization_status,
            }
        )


# ---------------------------------------------------------------------------
# onenote result → Indicators (FR-03 AC-11)
# ---------------------------------------------------------------------------


def _ingest_onenote(
    output: dict[str, Any],
    store: EvidenceChainStore,
    embedded_payloads: list[dict[str, Any]],
    parent_analysis_id: str = "",
) -> None:
    """Map onenote worker output to evidence-chain Indicators."""
    _ = parent_analysis_id  # retained for parity with other document ingesters
    for fds in output.get("file_data_stores", []):
        child_id = _new_child_sample_id()
        suggested_format = str(
            fds.get("suggested_format")
            or _suggest_document_payload_format(str(fds.get("extension", "")))
        )
        extracted_to = _worker_materialized_path(fds)
        materialized = bool(extracted_to)
        recursive_ready = _payload_recursive_ready(materialized, suggested_format)
        materialization_status = (
            "worker_materialized" if materialized else "not_materialized"
        )
        indicator_data: dict[str, Any] = {
            "guid": fds.get("guid", ""),
            "extension": fds.get("extension", ""),
            "size_bytes": fds.get("size_bytes", 0),
            "sha256": fds.get("sha256", ""),
            "offset": fds.get("offset"),
            "child_sample_id": child_id,
            "child_analysis_id": child_id,
            "suggested_format": suggested_format,
            "materialized": materialized,
            "recursive_ready": recursive_ready,
            "materialization_status": materialization_status,
        }
        payload_summary: dict[str, Any] = {
            "source": "onenote_file_data_store",
            "guid": fds.get("guid", ""),
            "sha256": fds.get("sha256", ""),
            "size_bytes": fds.get("size_bytes", 0),
            "extension": fds.get("extension", ""),
            "child_sample_id": child_id,
            "child_analysis_id": child_id,
            "suggested_format": suggested_format,
            "materialized": materialized,
            "recursive_ready": recursive_ready,
            "materialization_status": materialization_status,
        }
        if extracted_to:
            indicator_data["extracted_to"] = extracted_to
            payload_summary["extracted_to"] = extracted_to
        _append_indicator(
            store,
            Bucket.embedded_payloads,
            "onenote_file_data_store",
            Severity.WARNING,
            indicator_data,
        )
        embedded_payloads.append(payload_summary)


# ---------------------------------------------------------------------------
# Document IOC extraction (FR-06 AC-2..6, strings_iocs bucket)
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s'\"<>\x00-\x1f]{4,2048}", re.IGNORECASE)
_REMOTE_TMPL_RE = re.compile(
    r"https?://[^\s'\"<>\x00-\x1f]+\.(?:dotm|dotx|dot)\b",
    re.IGNORECASE,
)
_IP_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d{1,3})\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d{1,3})\b",
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_REGISTRY_RE = re.compile(r"\bHKEY_[A-Z_]+(?:\\[^\s,;]+)+", re.IGNORECASE)
_PS_CRADLE_RE = re.compile(
    r"(?i)powershell[^\n]*-(?:enc|e|nop|noprofile|w\s*hidden|ep\s*bypass)",
)
_LOLBIN_RE = re.compile(r"(?i)\b(?:mshta|certutil|regsvr32|rundll32)\b")
_DDE_RE = re.compile(r"(?i)=\s*(?:DDE|DDEAUTO)\s*\(")
_RTF_U_RE = re.compile(r"\\u(-?\d+)\s?")

_CONF_ORDER = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}


def _stronger_confidence(a: Confidence, b: Confidence) -> Confidence:
    return a if _CONF_ORDER[a] >= _CONF_ORDER[b] else b


def _normalize_ioc_value(value: str) -> str:
    return value.strip().lower()


def _decode_rtf_unicode_escapes(text: str) -> list[str]:
    """Decode RTF ``\\uN`` control words into Unicode fragments (FR-06 AC-2)."""
    out: list[str] = []
    for m in _RTF_U_RE.finditer(text):
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        code = n & 0xFFFF
        try:
            out.append(chr(code))
        except ValueError:
            continue
    return out


def _regex_hits(
    pattern: re.Pattern[str],
    chunk: str,
    indicator_type: str,
    confidence: Confidence,
    origin: str,
) -> list[tuple[str, str, Confidence, str]]:
    return [
        (m.group(0), indicator_type, confidence, origin)
        for m in pattern.finditer(chunk)
    ]


def _url_hits(chunk: str, origin: str) -> list[tuple[str, str, Confidence, str]]:
    hits: list[tuple[str, str, Confidence, str]] = []
    for m in _URL_RE.finditer(chunk):
        raw = m.group(0).strip()
        if not raw:
            continue
        if _REMOTE_TMPL_RE.search(raw):
            hits.append((raw, "remote_template_url", Confidence.HIGH, origin))
        else:
            hits.append((raw, "url", Confidence.MEDIUM, origin))
    return hits


def _collect_labeled_corpus(
    doc_analysis: dict[str, Any],
    macro_analysis: dict[str, Any],
    onenote_byte_strings: list[str],
) -> list[tuple[str, str]]:
    """Pair each text chunk with ``static`` or ``simulated`` origin label."""
    out: list[tuple[str, str]] = []

    for mod in macro_analysis.get("vba_modules", []):
        src = mod.get("source") or mod.get("source_preview") or ""
        if src:
            out.append(("static", src))
            out.extend(("static", frag) for frag in _decode_rtf_unicode_escapes(src))
        deobfuscated = mod.get("deobfuscated_preview") or ""
        if deobfuscated:
            out.append(("static_deobfuscated", deobfuscated))
            out.extend(
                ("static_deobfuscated", frag)
                for frag in _decode_rtf_unicode_escapes(deobfuscated)
            )

    for xl in macro_analysis.get("xl4_macros", []):
        formula = xl.get("formula") or ""
        if formula:
            out.append(("static", formula))
            out.extend(
                ("static", frag) for frag in _decode_rtf_unicode_escapes(formula)
            )

    for trig in doc_analysis.get("triggers", []):
        js = trig.get("js_preview") or trig.get("embedded_js") or ""
        if js:
            out.append(("static", js))
        url = trig.get("url", "")
        if isinstance(url, str) and url:
            out.append(("static", url))

    for dde in doc_analysis.get("dde_fields", []):
        if isinstance(dde, dict):
            for _k, val in dde.items():
                if isinstance(val, str) and val:
                    out.append(("static", val))

    for rt in doc_analysis.get("remote_template", []):
        if isinstance(rt, dict):
            for _k, val in rt.items():
                if isinstance(val, str) and val:
                    out.append(("static", val))
        elif isinstance(rt, str) and rt:
            out.append(("static", rt))

    meta = doc_analysis.get("metadata", {})
    for _key, val in meta.items():
        if isinstance(val, str) and val:
            out.append(("static", val))

    for s in onenote_byte_strings:
        if isinstance(s, str) and s:
            out.append(("static", s))

    for ev in macro_analysis.get("simulation_events", []):
        args = ev.get("args_literal", [])
        if isinstance(args, list):
            joined = "\n".join(str(x) for x in args if str(x))
        elif isinstance(args, str):
            joined = args
        else:
            joined = ""
        if joined:
            out.append(("simulated", joined))

    for action in macro_analysis.get("static_actions", []):
        args = action.get("args_literal", [])
        if isinstance(args, list):
            joined = "\n".join(str(x) for x in args if str(x))
        elif isinstance(args, str):
            joined = args
        else:
            joined = ""
        if joined:
            out.append(("static_action", joined))

    for ioc in macro_analysis.get("static_iocs", []):
        if isinstance(ioc, dict):
            val = ioc.get("value", "")
            if isinstance(val, str) and val:
                out.append(("static_ioc", val))

    return out


def _extract_and_append_document_iocs(
    store: EvidenceChainStore,
    doc_analysis: dict[str, Any],
    macro_analysis: dict[str, Any],
    onenote_byte_strings: list[str],
) -> list[dict[str, Any]]:
    """Merge document-derived strings, match IOC patterns, append to ``strings_iocs``."""
    corpus = _collect_labeled_corpus(doc_analysis, macro_analysis, onenote_byte_strings)

    pending: dict[tuple[str, str], set[str]] = {}
    display_val: dict[tuple[str, str], str] = {}
    conf_val: dict[tuple[str, str], Confidence] = {}

    def _add(
        value: str, indicator_type: str, confidence: Confidence, origin: str
    ) -> None:
        raw = value.strip()
        if not raw:
            return
        key = (_normalize_ioc_value(raw), indicator_type)
        display_val.setdefault(key, raw)
        pending.setdefault(key, set()).add(origin)
        prev_c = conf_val.get(key)
        conf_val[key] = (
            _stronger_confidence(prev_c, confidence)
            if prev_c is not None
            else confidence
        )

    for origin, chunk in corpus:
        for val, itype, conf, org in _regex_hits(
            _PS_CRADLE_RE, chunk, "powershell_cradle", Confidence.HIGH, origin
        ):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _regex_hits(
            _LOLBIN_RE, chunk, "lolbin", Confidence.HIGH, origin
        ):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _regex_hits(
            _DDE_RE, chunk, "dde", Confidence.HIGH, origin
        ):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _url_hits(chunk, origin):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _regex_hits(
            _EMAIL_RE, chunk, "email", Confidence.MEDIUM, origin
        ):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _regex_hits(
            _IP_RE, chunk, "ipv4", Confidence.MEDIUM, origin
        ):
            _add(val, itype, conf, org)
        for val, itype, conf, org in _regex_hits(
            _REGISTRY_RE, chunk, "registry_key", Confidence.MEDIUM, origin
        ):
            _add(val, itype, conf, org)

    written: list[dict[str, Any]] = []
    for key in sorted(pending.keys(), key=lambda k: (k[1], k[0])):
        itype = key[1]
        origins = pending[key]
        conf = conf_val[key]
        display = display_val[key]
        data: dict[str, Any] = {"value": display, "source": sorted(origins)}
        _append_indicator(
            store,
            Bucket.strings_iocs,
            itype,
            Severity.WARNING,
            data,
            source_fr="FR-06",
            confidence=conf,
        )
        written.append(
            {"indicator_type": itype, "data": dict(data), "confidence": conf.value},
        )
    return written


# ---------------------------------------------------------------------------
# DocExtractTool
# ---------------------------------------------------------------------------


class DocExtractTool(BaseTool):
    """Document extraction and macro analysis tool (FR-03 / ADR-13).

    Accepts a sandbox ``sample_path`` for a recognised document-format file,
    dispatches to the appropriate sandbox worker(s), and writes structured
    Indicators to the three document evidence-chain buckets.

    Args:
        sandbox_client: Backend implementing :class:`SandboxClient`.
        store: Per-analysis :class:`EvidenceChainStore`.

    Raises:
        ValueError: When ``document_format`` is not a valid
            :class:`~schema.document_enums.DocumentFormat`
            member (non-document formats are rejected here, never silently
            executed).
    """

    name: str = "document_extract"
    description: str = (
        "Extract document structure, macros, embedded payloads and PDF triggers "
        "from a sample already uploaded to the sandbox workspace. "
        "Dispatches to specialised sandbox workers (olevba / vmonkey / peepdf / "
        "onenote / msoffcrypto) and writes structured Indicators to the "
        "'document_analysis', 'macro_analysis', 'embedded_payloads', and "
        "'strings_iocs' (FR-06 document IOC merge) buckets. "
        "Input: sample_path (sandbox path), analysis_id, document_format, "
        "document_tier, options. "
        "MUST NOT be called on PE / ELF / Mach-O binaries."
    )
    args_schema: type[BaseModel] = DocExtractInput
    sandbox_client: Any
    store: EvidenceChainStore
    embedded_payload_handler: EmbeddedPayloadHandler | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        msg = (
            "DocExtractTool is async-only; invoke via .ainvoke(...) / "
            ".arun(...) rather than .invoke(...)."
        )
        raise NotImplementedError(msg)

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """Dispatch workers, write Indicators, return structured summary.

        Args:
            **kwargs: Must satisfy the :class:`DocExtractInput` schema.

        Returns:
            A dict with keys ``status``, ``document_analysis``, ``macro_analysis``,
            ``embedded_payloads``, ``delivery_chain_doc``, ``strings_iocs``,
            ``error_summary``.

        Invalid ``document_format`` values return ``status='failed'`` with
        ``error_code='TOOL_SCHEMA_INVALID'`` so an accidental PE / ELF /
        Mach-O call does not abort the LangGraph run.
        """
        inp = DocExtractInput(**kwargs)
        options = (
            DocExtractOptions(**inp.options) if inp.options else DocExtractOptions()
        )

        # Validate document_format early — non-document formats raise immediately
        try:
            doc_fmt = DocumentFormat(inp.document_format)
        except ValueError:
            msg = (
                f"document_format {inp.document_format!r} is not a valid "
                f"DocumentFormat; DocExtractTool must not be called on "
                f"PE / ELF / Mach-O binaries."
            )
            return {
                "ok": False,
                "status": "failed",
                "error_code": "TOOL_SCHEMA_INVALID",
                "reason": "invalid_document_format",
                "message": msg,
                "details": {
                    "reason": "invalid_document_format",
                    "document_format": inp.document_format,
                    "document_tier": inp.document_tier,
                },
                "document_analysis": {},
                "macro_analysis": {},
                "embedded_payloads": [],
                "delivery_chain_doc": {},
                "strings_iocs": [],
                "error_summary": {
                    "parser_failures": [
                        {
                            "worker": "document_extract",
                            "error": msg,
                            "fatal": True,
                        }
                    ],
                    "simulation_warnings": [],
                    "password_attempts": {"attempted": 0, "succeeded": False},
                },
            }

        session = await self._ensure_session(inp.analysis_id)
        overall_start = time.perf_counter()

        doc_analysis: dict[str, Any] = {
            "structure": {},
            "triggers": [],
            "dde_fields": [],
            "remote_template": [],
            "metadata": {},
        }
        macro_analysis: dict[str, Any] = {
            "vba_modules": [],
            "xl4_macros": [],
            "static_actions": [],
            "static_iocs": [],
            "simulation_events": [],
            "simulation_gaps": [],
            "simulation_status": "not_run",
        }
        embedded_payloads: list[dict[str, Any]] = []
        delivery_chain_doc: dict[str, Any] = {
            "parent_analysis_id": None,
            "children": [],
        }
        parser_failures: list[dict[str, Any]] = []
        simulation_warnings: list[str] = []
        password_attempts: dict[str, Any] = {"attempted": 0, "succeeded": False}
        onenote_fallback_strings: list[str] = []

        successful_workers = 0

        # ------------------------------------------------------------------
        # ENCRYPTED_OFFICE: msoffcrypto → decrypt → recurse
        # ------------------------------------------------------------------
        if doc_fmt == DocumentFormat.ENCRYPTED_OFFICE:
            pw_path = options.password_list_path
            passwords = _load_password_list(pw_path)

            # AC-13: audit-log each attempt before invoking the worker
            for pw in passwords:
                _log_password_attempt(pw)

            remaining = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
            crypto_out, crypto_ok = await _run_worker(
                self.sandbox_client,
                session,
                "run_msoffcrypto.py",
                {
                    "sample_path": inp.sample_path,
                    "password_list": passwords,
                },
                timeout=max(remaining, 10.0),
            )
            password_attempts = {
                "attempted": crypto_out.get("attempted", len(passwords)),
                "succeeded": bool(crypto_out.get("decrypted", False)),
                "succeeded_password_hash": crypto_out.get("succeeded_password_hash"),
            }

            # Count msoffcrypto as a successful worker invocation regardless of
            # decryption outcome — "exhausted dictionary" is a known degraded
            # path (AC-14), not an unhandled crash.  Only a worker error
            # (non-zero exit with an error message) is a true failure.
            if crypto_ok or not crypto_out.get("error"):
                successful_workers += 1

            if crypto_out.get("decrypted"):
                # Record encryption metadata as document_metadata Indicator
                _append_indicator(
                    self.store,
                    Bucket.document_analysis,
                    "document_metadata",
                    Severity.INFO,
                    {
                        "encrypted": True,
                        "cipher_algorithm": crypto_out.get("metadata", {}).get(
                            "cipher_algorithm"
                        ),
                        "key_bits": crypto_out.get("metadata", {}).get("key_bits"),
                        "hash_algorithm": crypto_out.get("metadata", {}).get(
                            "hash_algorithm"
                        ),
                        "password_hash": crypto_out.get("succeeded_password_hash"),
                    },
                )
                doc_analysis["metadata"]["encrypted"] = True
                doc_analysis["metadata"]["cipher"] = crypto_out.get("metadata", {})

                # AC-12: after successful decryption the encrypted outer shell
                # is analysed via a best-effort olevba call on the original path
                # (the decrypted bytes are inside the sandbox only).
                remaining2 = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
                if remaining2 > 5.0:
                    if await _run_olevba_and_ingest(
                        self.sandbox_client,
                        session,
                        inp.sample_path,
                        timeout=min(remaining2 * 0.6, 120.0),
                        store=self.store,
                        doc_analysis=doc_analysis,
                        macro_analysis=macro_analysis,
                        parser_failures=parser_failures,
                        count_empty_success=True,
                    ):
                        successful_workers += 1
            else:
                # AC-14: password dictionary exhausted → degraded report
                _record_parser_failure(
                    self.store,
                    "run_msoffcrypto.py",
                    crypto_out.get("error", "password dictionary exhausted"),
                    fatal=False,
                )
                parser_failures.append(
                    {
                        "worker": "run_msoffcrypto.py",
                        "error": crypto_out.get(
                            "error", "password dictionary exhausted"
                        ),
                        "fatal": False,
                        "unknown_downgrade_reason": "encrypted_office_no_password",
                    }
                )
                _append_indicator(
                    self.store,
                    Bucket.document_analysis,
                    "document_metadata",
                    Severity.WARNING,
                    {
                        "encrypted": True,
                        "cipher_algorithm": crypto_out.get("metadata", {}).get(
                            "cipher_algorithm"
                        ),
                        "decrypted": False,
                    },
                )
                remaining2 = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
                if remaining2 > 5.0:
                    if await _run_olevba_and_ingest(
                        self.sandbox_client,
                        session,
                        inp.sample_path,
                        timeout=min(remaining2 * 0.6, 120.0),
                        store=self.store,
                        doc_analysis=doc_analysis,
                        macro_analysis=macro_analysis,
                        parser_failures=parser_failures,
                        count_empty_success=False,
                    ):
                        successful_workers += 1

        # ------------------------------------------------------------------
        # PDF → peepdf
        # ------------------------------------------------------------------
        elif doc_fmt == DocumentFormat.PDF:
            remaining = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
            peepdf_out, peepdf_ok = await _run_worker(
                self.sandbox_client,
                session,
                "run_peepdf.py",
                {"sample_path": inp.sample_path},
                timeout=max(remaining, 10.0),
            )
            if peepdf_ok or peepdf_out.get("object_tree") is not None:
                _ingest_peepdf(
                    peepdf_out,
                    self.store,
                    doc_analysis,
                    embedded_payloads,
                    inp.analysis_id,
                )
                successful_workers += 1
            if peepdf_out.get("error"):
                _record_parser_failure(self.store, "run_peepdf.py", peepdf_out["error"])
                parser_failures.append(
                    {
                        "worker": "run_peepdf.py",
                        "error": peepdf_out["error"],
                        "fatal": not peepdf_ok,
                    }
                )

        # ------------------------------------------------------------------
        # ONENOTE → run_onenote
        # ------------------------------------------------------------------
        elif doc_fmt == DocumentFormat.ONENOTE:
            remaining = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
            onenote_out, onenote_ok = await _run_worker(
                self.sandbox_client,
                session,
                "run_onenote.py",
                {"sample_path": inp.sample_path},
                timeout=max(remaining, 10.0),
            )
            if onenote_ok or onenote_out.get("file_data_stores") is not None:
                _ingest_onenote(
                    onenote_out, self.store, embedded_payloads, inp.analysis_id
                )
                successful_workers += 1
            fb = onenote_out.get("fallback_strings_ioc")
            if isinstance(fb, list):
                onenote_fallback_strings.extend(str(x) for x in fb if x)
            if onenote_out.get("error"):
                _record_parser_failure(
                    self.store, "run_onenote.py", onenote_out["error"]
                )
                parser_failures.append(
                    {
                        "worker": "run_onenote.py",
                        "error": onenote_out["error"],
                        "fatal": not onenote_ok,
                    }
                )

        # ------------------------------------------------------------------
        # HTA → vmonkey only
        # ------------------------------------------------------------------
        elif doc_fmt == DocumentFormat.HTA:
            dsettings = document_settings()
            vba_timeout = (
                options.vba_simulation_timeout_sec
                or dsettings.vba_simulation_timeout_sec
            )
            vba_max = options.vba_max_instructions or dsettings.vba_max_instructions
            remaining = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
            vmonkey_out, vmonkey_ok = await _run_worker(
                self.sandbox_client,
                session,
                "run_vmonkey.py",
                {
                    "sample_path": inp.sample_path,
                    "source_files": [],
                    "timeout_sec": vba_timeout,
                    "max_instructions": vba_max,
                },
                timeout=max(remaining, 10.0),
            )
            if vmonkey_ok or vmonkey_out.get("simulation_events") is not None:
                _ingest_vmonkey(
                    vmonkey_out,
                    self.store,
                    macro_analysis,
                    parser_failures=parser_failures,
                )
                successful_workers += 1
            else:
                status_val = vmonkey_out.get("simulation_status", "unavailable")
                if status_val not in ("unavailable",):
                    _record_parser_failure(
                        self.store,
                        "run_vmonkey.py",
                        vmonkey_out.get("error", status_val),
                    )
                    parser_failures.append(
                        {
                            "worker": "run_vmonkey.py",
                            "error": vmonkey_out.get("error", status_val),
                            "fatal": False,
                        }
                    )

        # ------------------------------------------------------------------
        # RTF / OOXML / OLE2 → olevba (+ vmonkey for non-RTF)
        # ------------------------------------------------------------------
        else:
            dsettings = document_settings()
            vba_timeout = (
                options.vba_simulation_timeout_sec
                or dsettings.vba_simulation_timeout_sec
            )
            vba_max = options.vba_max_instructions or dsettings.vba_max_instructions

            # Step 1: olevba
            remaining = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
            olevba_out, olevba_ok = await _run_worker(
                self.sandbox_client,
                session,
                "run_olevba.py",
                {"sample_path": inp.sample_path, "options": {}},
                timeout=max(min(remaining * 0.45, 120.0), 10.0),
            )
            _olevba_has_data = bool(
                olevba_out.get("vba_modules")
                or olevba_out.get("xl4_macros")
                or olevba_out.get("triggers")
            )
            if olevba_ok or _olevba_has_data:
                _ingest_olevba(olevba_out, self.store, doc_analysis, macro_analysis)
                successful_workers += 1
            if olevba_out.get("error"):
                _record_parser_failure(self.store, "run_olevba.py", olevba_out["error"])
                parser_failures.append(
                    {
                        "worker": "run_olevba.py",
                        "error": olevba_out["error"],
                        "fatal": not olevba_ok,
                    }
                )

            # Step 2: vmonkey (OOXML/OLE2 only, skip for RTF)
            if doc_fmt in _VMONKEY_AFTER_OLEVBA_FORMATS:
                remaining2 = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
                vmonkey_out, vmonkey_ok = await _run_worker(
                    self.sandbox_client,
                    session,
                    "run_vmonkey.py",
                    {
                        "sample_path": inp.sample_path,
                        "source_files": [],
                        "timeout_sec": vba_timeout,
                        "max_instructions": vba_max,
                    },
                    timeout=max(remaining2, 10.0),
                )
                if vmonkey_ok or vmonkey_out.get("simulation_events") is not None:
                    _ingest_vmonkey(
                        vmonkey_out,
                        self.store,
                        macro_analysis,
                        parser_failures=parser_failures,
                    )
                    successful_workers += 1
                else:
                    status_val = vmonkey_out.get("simulation_status", "unavailable")
                    if vmonkey_out.get("error"):
                        _record_parser_failure(
                            self.store, "run_vmonkey.py", vmonkey_out["error"]
                        )
                        parser_failures.append(
                            {
                                "worker": "run_vmonkey.py",
                                "error": vmonkey_out["error"],
                                "fatal": False,
                            }
                        )

            if doc_fmt in _OOXML_FORMATS:
                remaining3 = _TOTAL_TIMEOUT_SEC - (time.perf_counter() - overall_start)
                ooxml_out, ooxml_ok = await _run_worker(
                    self.sandbox_client,
                    session,
                    "run_ooxml_structure.py",
                    {"sample_path": inp.sample_path},
                    timeout=max(min(remaining3, 30.0), 10.0),
                )
                if ooxml_ok or ooxml_out.get("document_metadata"):
                    if _ingest_ooxml_structure(
                        ooxml_out,
                        self.store,
                        doc_analysis,
                        embedded_payloads,
                        parser_failures,
                    ):
                        successful_workers += 1
                if ooxml_out.get("error"):
                    _record_parser_failure(
                        self.store,
                        "run_ooxml_structure.py",
                        ooxml_out["error"],
                        fatal=not ooxml_ok,
                    )
                    parser_failures.append(
                        {
                            "worker": "run_ooxml_structure.py",
                            "error": ooxml_out["error"],
                            "fatal": not ooxml_ok,
                        }
                    )

        # ------------------------------------------------------------------
        # Determine final status
        # ------------------------------------------------------------------
        if successful_workers == 0:
            status: Literal["ok", "degraded", "failed"] = "failed"
        elif parser_failures:
            status = "degraded"
        else:
            status = "ok"

        strings_iocs_written = _extract_and_append_document_iocs(
            self.store,
            doc_analysis,
            macro_analysis,
            onenote_fallback_strings,
        )
        if embedded_payloads and self.embedded_payload_handler is not None:
            handled = self.embedded_payload_handler(inp.analysis_id, embedded_payloads)
            if inspect.isawaitable(handled):
                embedded_payloads = await handled
            else:
                embedded_payloads = handled

        logger.info(
            "document_extract_complete",
            analysis_id=inp.analysis_id,
            status=status,
            document_format=doc_fmt.value,
            successful_workers=successful_workers,
            parser_failure_count=len(parser_failures),
            password_attempted=int(password_attempts.get("attempted") or 0),
            password_succeeded=bool(password_attempts.get("succeeded", False)),
            vba_module_count=len(macro_analysis["vba_modules"]),
            xl4_macro_count=len(macro_analysis["xl4_macros"]),
            macro_action_count=len(macro_analysis["static_actions"]),
            static_ioc_count=len(macro_analysis["static_iocs"]),
            trigger_count=len(doc_analysis["triggers"]),
            simulation_event_count=len(macro_analysis["simulation_events"]),
            embedded_payload_count=len(embedded_payloads),
            strings_ioc_count=len(strings_iocs_written),
        )

        return {
            "status": status,
            "document_analysis": doc_analysis,
            "macro_analysis": macro_analysis,
            "embedded_payloads": embedded_payloads,
            "delivery_chain_doc": delivery_chain_doc,
            "strings_iocs": strings_iocs_written,
            "error_summary": {
                "parser_failures": parser_failures,
                "simulation_warnings": simulation_warnings,
                "password_attempts": password_attempts,
            },
        }

    async def _ensure_session(self, analysis_id: str) -> SandboxSession:
        """Return or create the sandbox session for ``analysis_id``."""
        return await get_or_create_session(self.sandbox_client, analysis_id)


__all__ = [
    "DocExtractInput",
    "DocExtractOptions",
    "DocExtractTool",
]
