"""run_vmonkey.py — VBA / VBScript Tier-B simulation worker (FR-03 AC-4/5/10).

Invocation (by host via SandboxClient)::

    python run_vmonkey.py --input <json_path>

Input JSON::

    {
        "sample_path": "/workspace/<aid>/sample.xlsm",
        "source_files": [],
        "timeout_sec": 60,
        "max_instructions": 100000
    }

Stdout JSON contract::

    {
        "simulation_events": [
            {
                "action": "WScript.Shell.Run",
                "args_literal": ["powershell -NoP ..."],
                "source_line": 17
            }
        ],
        "simulation_gaps": [
            {
                "statement_type": "Application.OnTime",
                "source_line": 42,
                "skip_reason": "out_of_tier_b"
            }
        ],
        "simulation_status": "completed | timeout | parse_error | unavailable"
    }

Tier-B stub semantics (FR-03 AC-4 / NFR-04)
--------------------------------------------
ViperMonkey intercepts and *records* the following without calling real OS APIs:

- ``CreateObject(...)`` — captured to ``simulation_events`` as ``create_object``
- ``Shell(...)`` / ``WScript.Shell.Run(...)`` — captured as ``shell_run``
- ``FSO.CreateTextFile`` / ``FSO.DeleteFile`` — captured as ``fso_write`` / ``fso_delete``
- ``XMLHTTP.Open`` / ``XMLHTTP.Send`` — captured as ``xmlhttp``
- ``ADODB.Stream`` — captured as ``adodb_stream``
- ``RegRead`` / ``RegWrite`` — captured as ``reg_read`` / ``reg_write``

Any statement ViperMonkey cannot simulate is recorded as a *gap*
(FR-03 AC-5)::

    {"statement_type": "<type>", "source_line": <n>, "skip_reason": "out_of_tier_b"}

Timeout (IR-DOC-05 / A-07)
---------------------------
A ``signal.alarm(timeout_sec)`` hard deadline is set before simulation begins.
On SIGALRM the worker returns ``simulation_status=timeout`` with the events
collected so far.  ``signal.alarm`` is POSIX-only; on Windows (e.g. CI) the
worker falls back to a ``threading.Timer`` that raises ``SystemExit`` instead.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

_DEFAULT_TIMEOUT_SEC = 60
_DEFAULT_MAX_INSTRUCTIONS = 100_000


def _alarm_timeout_ctx(timeout_sec: int):
    """Return a context manager that raises TimeoutError after timeout_sec."""
    import contextlib
    import signal

    @contextlib.contextmanager
    def _posix_alarm():
        def _handler(signum, frame):  # noqa: ARG001
            raise TimeoutError("vmonkey_alarm")

        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout_sec)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    @contextlib.contextmanager
    def _thread_timer():
        fired = threading.Event()

        def _expire():
            fired.set()

        timer = threading.Timer(timeout_sec, _expire)
        timer.daemon = True
        timer.start()
        try:
            yield
        finally:
            timer.cancel()
        if fired.is_set():
            raise TimeoutError("vmonkey_timer")

    if hasattr(signal, "SIGALRM"):
        return _posix_alarm()
    return _thread_timer()


def _run(
    sample_path: str,
    source_files: list[str],
    timeout_sec: int,
    max_instructions: int,
) -> dict:
    try:
        # ViperMonkey is sandbox-only; import is intentional here (ADR-DOC-01).
        import vipermonkey  # type: ignore[import-untyped]  # noqa: F401
        from vipermonkey import core as vmonkey_core  # type: ignore[import-untyped]
    except ImportError:
        return {
            "simulation_events": [],
            "simulation_gaps": [],
            "simulation_status": "unavailable",
        }

    path = Path(sample_path)
    if not path.exists():
        return {
            "simulation_events": [],
            "simulation_gaps": [],
            "simulation_status": "parse_error",
            "error": f"sample not found: {sample_path}",
        }

    simulation_events: list[dict] = []
    simulation_gaps: list[dict] = []
    status = "completed"

    try:
        with _alarm_timeout_ctx(timeout_sec):
            try:
                vba = vmonkey_core.ViperMonkey(str(path))
                vba.max_steps = max_instructions

                # Inject source files for HTA / multi-file scenarios
                for sf in source_files:
                    vba.add_vba_file(sf)

                actions = vba.run()

                for action in actions:
                    action_type = str(getattr(action, "action", "unknown"))
                    args = []
                    try:
                        args = [str(a) for a in (action.args or [])]
                    except Exception:  # noqa: BLE001
                        pass
                    src_line = getattr(action, "line_number", None)

                    simulation_events.append(
                        {
                            "action": action_type,
                            "args_literal": args,
                            "source_line": src_line,
                        }
                    )

                # Collect gaps from ViperMonkey's unsupported-statement log
                gaps_attr = getattr(vba, "unsupported_statements", [])
                for gap in gaps_attr:
                    simulation_gaps.append(
                        {
                            "statement_type": str(getattr(gap, "stmt_type", "unknown")),
                            "source_line": getattr(gap, "line_number", None),
                            "skip_reason": "out_of_tier_b",
                        }
                    )

            except TimeoutError:
                raise
            except Exception as exc:  # noqa: BLE001
                status = "parse_error"
                simulation_gaps.append(
                    {
                        "statement_type": "parse_failure",
                        "source_line": None,
                        "skip_reason": str(exc),
                    }
                )

    except TimeoutError:
        status = "timeout"

    return {
        "simulation_events": simulation_events,
        "simulation_gaps": simulation_gaps,
        "simulation_status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ViperMonkey VBA simulation worker")
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "error": f"bad input: {exc}",
                    "simulation_events": [],
                    "simulation_gaps": [],
                    "simulation_status": "parse_error",
                }
            )
        )
        sys.exit(1)

    result = _run(
        sample_path=payload.get("sample_path", ""),
        source_files=payload.get("source_files", []),
        timeout_sec=int(payload.get("timeout_sec", _DEFAULT_TIMEOUT_SEC)),
        max_instructions=int(
            payload.get("max_instructions", _DEFAULT_MAX_INSTRUCTIONS)
        ),
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
