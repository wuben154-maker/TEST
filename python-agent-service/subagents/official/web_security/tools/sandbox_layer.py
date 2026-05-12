"""L3 interpreter syntax checks (no arbitrary code execution)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .layer_env import sandbox_timeout_sec
from .models import Evidence, Finding, Signal

logger = logging.getLogger(__name__)


def run_syntax_sandbox(text: str, language: str) -> tuple[list[Finding], str, str]:
    """
    Run php -l or python -m py_compile on a temp file.

    Returns:
        findings, status, detail
    """
    lang = (language or "").strip().lower()
    if lang not in ("php", "python"):
        return [], "unsupported_lang", language or "unknown"

    timeout = sandbox_timeout_sec()
    tmp: Path | None = None
    try:
        suffix = ".php" if lang == "php" else ".py"
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="webthreat_")
        os.close(fd)
        tmp = Path(path)
        tmp.write_text(text, encoding="utf-8", errors="replace")

        if lang == "php":
            exe = shutil.which("php")
            if not exe:
                return [], "skipped_no_interpreter", "php not in PATH"
            proc = subprocess.run(
                [exe, "-l", str(tmp)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PHP_OPENBASEDIR": ""},
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0:
                return (
                    [
                        Finding(
                            id="sandbox-php-syntax-error",
                            category="webshell",
                            severity="medium",
                            confidence=0.55,
                            layer="L3",
                            evidence=Evidence(
                                snippet=out.strip()[:400],
                                start=0,
                                end=min(400, len(out)),
                                location="L3:sandbox:php_lint",
                            ),
                            signals=[Signal(type="sandbox_trace", name="php_l_failed", weight=1.0)],
                        )
                    ],
                    "syntax_error",
                    out.strip()[:500],
                )
            return [], "clean", out.strip()[:200]

        # python
        py = shutil.which("python3") or shutil.which("python")
        if not py:
            return [], "skipped_no_interpreter", "python not in PATH"
        proc = subprocess.run(
            [py, "-m", "py_compile", str(tmp)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return (
                [
                    Finding(
                        id="sandbox-python-syntax-error",
                        category="webshell",
                        severity="medium",
                        confidence=0.55,
                        layer="L3",
                        evidence=Evidence(
                            snippet=out.strip()[:400],
                            start=0,
                            end=min(400, len(out)),
                            location="L3:sandbox:py_compile",
                        ),
                        signals=[Signal(type="sandbox_trace", name="py_compile_failed", weight=1.0)],
                    )
                ],
                "syntax_error",
                out.strip()[:500],
            )
        return [], "clean", "py_compile ok"
    except subprocess.TimeoutExpired:
        logger.warning("sandbox_timeout lang=%s", lang)
        return (
            [],
            "error",
            f"timeout after {timeout}s",
        )
    except Exception as e:
        logger.warning("sandbox_failed: %s", str(e))
        return [], "error", str(e)
    finally:
        if tmp and tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass
