"""L4 E2B dynamic analysis — triggered only when L1-L3 are inconclusive.

Trigger conditions (see should_escalate):
  A. Language is jsp / aspx / unknown — L3 has no interpreter, any finding warrants dynamic check.
  B. Language is php / python — findings exist but confidence < threshold or severity < high (gray zone).

Execution strategy per language:
  - php, python, javascript  → actually execute the file in E2B (timeout 8s), capture output.
  - jsp, aspx                → strings + grep for dangerous Java/.NET patterns (no runtime needed).
  - unknown                  → file(1) type detection + strings extraction.

Feature toggle: WEB_THREAT_E2B_ESCALATION_ENABLED (default false).
Confidence threshold: WEB_THREAT_E2B_CONFIDENCE_THRESHOLD (default 0.80).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from .layer_env import e2b_escalation_confidence_threshold, e2b_escalation_enabled
from .models import Evidence, Finding, Signal

logger = logging.getLogger(__name__)

# Singleton thread pool — each submitted task runs asyncio.run() in its own thread,
# creating an isolated event loop that is safe even when FastAPI's loop is running.
_POOL: ThreadPoolExecutor | None = None


def _get_pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="web_e2b")
    return _POOL


# ---------------------------------------------------------------------------
# Language profiles
# ---------------------------------------------------------------------------

_LANG_EXT: dict[str, str] = {
    "php": ".php",
    "python": ".py",
    "javascript": ".js",
    "jsp": ".jsp",
    "aspx": ".aspx",
}

# Commands run inside E2B per language.  {path} is substituted before sending.
_LANG_COMMANDS: dict[str, list[str]] = {
    "php": [
        "timeout 8 php {path} 2>&1 | head -200 || true",
    ],
    "python": [
        "timeout 8 python3 {path} 2>&1 | head -200 || true",
    ],
    "javascript": [
        "timeout 8 node {path} 2>&1 | head -200 || true"
        " || strings {path} | grep -Ei 'child_process|exec|spawn|eval' | head -30",
    ],
    "jsp": [
        r"strings {path} | grep -Ei 'runtime\.exec|ProcessBuilder|exec\(|/bin/sh|cmd\.exe|shell_exec' | head -50 || true",
        r"strings {path} | grep -Ei 'base64|gzinflate|fromCharCode' | head -20 || true",
    ],
    "aspx": [
        r"strings {path} | grep -Ei 'Process\.Start|Invoke|cmd\.exe|powershell|eval\(' | head -50 || true",
    ],
}

_DEFAULT_COMMANDS: list[str] = [
    "file {path}",
    "strings {path} | head -100 || true",
]

# ---------------------------------------------------------------------------
# Output pattern matching → findings
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, severity, confidence, finding_id, signal_name)
_OUTPUT_RULES: list[tuple[re.Pattern[str], str, float, str, str]] = [
    (re.compile(r"uid=\d+\("), "critical", 0.92, "e2b-rce-confirmed", "rce_confirmed_dynamic"),
    (re.compile(r"root:x:0:0"), "critical", 0.90, "e2b-passwd-read", "sensitive_file_read"),
    (re.compile(r"/etc/shadow"), "critical", 0.90, "e2b-shadow-read", "sensitive_file_read"),
    (re.compile(r"runtime\.exec|ProcessBuilder", re.I), "high", 0.78, "e2b-java-exec", "java_exec_string"),
    (re.compile(r"Process\.Start|powershell", re.I), "high", 0.78, "e2b-dotnet-exec", "dotnet_exec_string"),
    (re.compile(r"\beval\s*\(|\bexec\s*\(|\bsystem\s*\(", re.I), "high", 0.75, "e2b-dyn-exec", "dyn_exec_observed"),
    (re.compile(r"base64_decode|gzinflate|fromCharCode", re.I), "medium", 0.60, "e2b-obfuscation", "obfuscation_string"),
]

_SEVERITY_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_RANK_MEDIUM = 2
_RANK_HIGH = 3


def _max_severity_rank(findings: list[Finding]) -> int:
    return max((_SEVERITY_RANK.get(f.severity, 0) for f in findings), default=0)


# ---------------------------------------------------------------------------
# Trigger decision
# ---------------------------------------------------------------------------


def should_escalate(
    findings: list[Finding],
    lang: str,
    artifact_type: str,
) -> tuple[bool, str]:
    """Decide whether L4 E2B dynamic analysis is warranted.

    Returns (escalate: bool, reason: str).
    """
    if not e2b_escalation_enabled():
        return False, "disabled"

    if not os.environ.get("E2B_API_KEY"):
        return False, "no_api_key"

    # Only code artifacts go to dynamic analysis
    if artifact_type == "http_traffic":
        return False, "http_traffic"

    if not findings:
        return False, "no_findings"

    norm_lang = (lang or "").strip().lower()

    # JSP / ASPX / unknown: L3 cannot lint these → escalate on any finding
    if norm_lang in ("jsp", "aspx", "unknown", ""):
        return True, f"l3_blind:{norm_lang or 'unknown'}"

    # PHP / Python: compare against confidence threshold
    threshold = e2b_escalation_confidence_threshold()
    max_conf = max(f.confidence for f in findings)
    max_rank = _max_severity_rank(findings)

    if max_rank >= _RANK_HIGH and max_conf >= threshold:
        return False, "definitive_result"

    if max_rank >= _RANK_MEDIUM:
        return True, f"gray_zone:rank={max_rank},conf={max_conf:.2f}"

    return False, "low_severity"


# ---------------------------------------------------------------------------
# E2B execution (async core)
# ---------------------------------------------------------------------------


async def _run_e2b_async(
    text: str,
    lang: str,
    reason: str,
) -> tuple[list[Finding], str, str]:
    """Upload file to E2B, run language-appropriate commands, analyse output."""
    try:
        from e2b import AsyncSandbox  # type: ignore[import-untyped]
    except ImportError:
        return [], "e2b_not_installed", "e2b package not installed"

    api_key = os.environ.get("E2B_API_KEY")
    if not api_key:
        return [], "skipped:no_api_key", ""

    norm_lang = (lang or "").strip().lower()
    ext = _LANG_EXT.get(norm_lang, ".txt")
    remote_path = f"/tmp/webthreat_target{ext}"
    commands = _LANG_COMMANDS.get(norm_lang, _DEFAULT_COMMANDS)

    sandbox = None
    try:
        sandbox = await AsyncSandbox.create(
            template_id="base",
            api_key=api_key,
            timeout=35,
        )
        await sandbox.files.write(remote_path, text.encode("utf-8", errors="replace"))

        combined_output: list[str] = []
        for cmd_template in commands:
            cmd = cmd_template.format(path=remote_path)
            try:
                result = await sandbox.commands.run(cmd, timeout=12)
                out = ((result.stdout or "") + (result.stderr or "")).strip()
                if out:
                    combined_output.append(out)
            except Exception as cmd_exc:
                logger.debug("e2b_cmd_failed cmd=%r error=%s", cmd, cmd_exc)

        output = "\n".join(combined_output)[:1000]
        findings = _analyse_output(output, norm_lang, remote_path)
        status = "suspicious" if findings else "clean"
        return findings, status, output[:500]

    except Exception as exc:
        logger.warning("e2b_dynamic_failed lang=%s reason=%s error=%s", lang, reason, exc)
        return [], "error", str(exc)[:300]
    finally:
        if sandbox is not None:
            try:
                await sandbox.kill()
            except Exception:
                pass


def _analyse_output(output: str, lang: str, remote_path: str) -> list[Finding]:
    """Match dynamic output against known suspicious patterns."""
    findings: list[Finding] = []
    seen_ids: set[str] = set()

    for pattern, severity, confidence, finding_id, signal_name in _OUTPUT_RULES:
        if finding_id in seen_ids:
            continue
        if not pattern.search(output):
            continue
        seen_ids.add(finding_id)
        snippet = output[:400]
        findings.append(
            Finding(
                id=finding_id,
                category="rce" if "rce" in finding_id or "exec" in signal_name else "webshell",
                severity=severity,  # type: ignore[arg-type]
                confidence=confidence,
                layer="L4",
                evidence=Evidence(
                    snippet=snippet,
                    start=0,
                    end=len(snippet),
                    location=f"L4:e2b:dynamic:{lang}",
                ),
                signals=[Signal(type="sandbox_trace", name=signal_name, weight=confidence)],
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Sync entry point for pipeline.py
# ---------------------------------------------------------------------------


def run_e2b_dynamic(
    text: str,
    lang: str,
    reason: str,
) -> tuple[list[Finding], str, str]:
    """Synchronous wrapper: runs async E2B call in an isolated thread event loop.

    Safe when FastAPI's own event loop is running (uses a separate thread + asyncio.run).
    Returns (findings, status, detail).
    """
    def _in_thread() -> tuple[list[Finding], str, str]:
        return asyncio.run(_run_e2b_async(text, lang, reason))

    future = _get_pool().submit(_in_thread)
    try:
        return future.result(timeout=40)
    except Exception as exc:
        logger.warning("e2b_dynamic_sync_wrapper_failed error=%s", exc)
        return [], "error", str(exc)[:200]
