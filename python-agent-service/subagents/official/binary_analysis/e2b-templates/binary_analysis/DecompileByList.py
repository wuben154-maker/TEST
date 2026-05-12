"""Ghidra headless postScript — decompile a pre-sorted priority list.

This script is the FR-07 AC-7 / IR-04 / IR-05 work-horse invoked by
``analyzeHeadless`` inside the binary-analysis E2B sandbox. The binary
analysis agent MUST NOT invoke ``analyzeHeadless`` with default
(whole-binary) analysis any more — the decompile budget is controlled by
first writing a priority list (imports × suspicious-string heuristics,
see skill ``ghidra-priority-queue-workflow``) and feeding that list to
this postScript.

Contract:

- Ghidra exposes this file as ``DecompileByList.py`` under
  ``/opt/ghidra/scripts/`` (installed at template build time via
  ``template.py``'s ``.copy(...)`` call).
- The agent invokes::

      analyzeHeadless /workspace/<aid>/ghidra-proj <aid> \
          -import /workspace/<aid>/sample.bin \
          -postScript DecompileByList.py \
          -scriptPath /opt/ghidra/scripts \
          -deleteProject                                           \
          -readOnly                                                \
          [script-args: <priority_list_path> <output_dir> [per_fn_timeout_s]]

- Inputs (read via ``getScriptArgs()``; Ghidra Jython):
    1. ``priority_list_path`` — path to a UTF-8 text file; one function
       reference per line. Lines are parsed in order of descending
       priority as produced by the priority-queue Step 0 skill. Each
       line MAY be either:
           - a hex address (e.g. ``0x401000`` / ``00401000``), or
           - a symbol name (e.g. ``CreateRemoteThread``), or
           - ``<name>@<address>`` (preferred — avoids ambiguous symbols).
       Blank lines and lines starting with ``#`` are skipped.
    2. ``output_dir`` — sandbox path under ``/workspace/<aid>/decompile/``;
       the directory is created if missing. Each decompiled function
       lands at ``<output_dir>/<zero-padded-address>.c``; callers read
       the files via the ``file_read`` tool with offset/limit paging
       (IR-04 semantic chunking).
    3. ``per_fn_timeout_s`` — optional integer, default ``30``. Passed
       verbatim to :class:`DecompInterface`'s timeout argument; enforces
       FR-07 AC-7 per-function timeout.

- Output: one ``<address>.c`` file per successful decompile + a
  ``manifest.json`` at ``<output_dir>/manifest.json`` summarising the
  run (ordered function list, success / timeout / error counts, wall
  time). The agent consumes ``manifest.json`` first to plan
  ``file_read`` pagination.

- Termination: the script NEVER raises back to ``analyzeHeadless`` —
  per-function failures are captured in ``manifest.json`` as
  ``status ∈ {"ok", "timeout", "not_found", "error"}`` so a single bad
  entry cannot poison the whole batch.

This file is executed by Ghidra's Jython 2.7 interpreter (Python 2 +
Java interop); it intentionally avoids Python 3-only syntax and any
third-party imports beyond the ``ghidra.*`` API.
"""

# This file runs under Ghidra's embedded Jython 2.7 interpreter, not the
# host Python 3 that ships BinaryAnalyst. Several modernisation lints are
# actively harmful here: f-strings (UP031) don't exist in Py2; the explicit
# "r" mode on ``open`` (UP015) is still idiomatic for Jython 2.7 clarity;
# and Ghidra's headless script host injects ``getScriptArgs`` /
# ``currentProgram`` / ``println`` as module globals, which ruff's F821
# cannot see. Suppressing at file level keeps the lint signal-to-noise
# ratio high without masking real issues.
# ruff: noqa: I001, E501, F821, N802, N803, N806, N816, UP015, UP031
# pyright: reportMissingImports=false

# Ghidra headless exposes these names in the script's global namespace;
# importing them explicitly keeps the file readable off-line.
from ghidra.app.decompiler import DecompInterface  # type: ignore[import-not-found]
from ghidra.util.task import ConsoleTaskMonitor  # type: ignore[import-not-found]

import json
import os
import re
import time


_HEX_ADDR_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{4,}$")


def _parse_args(args):
    """Extract ``(priority_list_path, output_dir, timeout_s)`` from script args.

    ``analyzeHeadless -postScript DecompileByList.py arg1 arg2 arg3``
    forwards ``arg1/arg2/arg3`` unchanged; validate shape loudly so a
    mis-invocation surfaces in ``analyzeHeadless`` stderr rather than
    producing an empty ``output_dir``.
    """
    if len(args) < 2:
        raise RuntimeError(
            "DecompileByList.py expects at least 2 script args: "
            "<priority_list_path> <output_dir> [per_fn_timeout_s]"
        )
    priority_list_path = args[0]
    output_dir = args[1]
    timeout_s = int(args[2]) if len(args) >= 3 else 30
    return priority_list_path, output_dir, timeout_s


def _load_priority_list(path):
    """Return the ordered list of raw reference tokens from ``path``.

    Comments (``#``-prefixed) and blank lines are dropped; surrounding
    whitespace is stripped. Order is preserved — the caller's priority
    is the script's priority.
    """
    entries = []
    with open(path, "r") as fh:
        for raw in fh.readlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line)
    return entries


def _resolve_function(program, raw_token):
    """Map one priority-list token to a ``ghidra.program.model.listing.Function``.

    Accepts ``<name>@<hex_addr>``, a bare hex address, or a bare symbol
    name. Returns ``None`` when no matching function exists — the
    caller records it as ``status="not_found"``.
    """
    token = raw_token
    name_hint = None
    addr_hint = None
    if "@" in token:
        name_hint, addr_hint = token.split("@", 1)
    elif _HEX_ADDR_RE.match(token):
        addr_hint = token
    else:
        name_hint = token

    fn = None
    fm = program.getFunctionManager()
    addr_factory = program.getAddressFactory()

    if addr_hint is not None:
        stripped = addr_hint[2:] if addr_hint.lower().startswith("0x") else addr_hint
        try:
            addr = addr_factory.getAddress(stripped)
        except Exception:
            addr = None
        if addr is not None:
            fn = fm.getFunctionContaining(addr) or fm.getFunctionAt(addr)

    if fn is None and name_hint:
        # Fall back to the first function with a matching name; ambiguity
        # between overloaded / thunked symbols is tolerated because the
        # priority list is the caller's responsibility.
        it = fm.getFunctions(True)
        while it.hasNext():
            candidate = it.next()
            if candidate.getName() == name_hint:
                fn = candidate
                break
    return fn


def _decompile_one(decomp, fn, timeout_s):
    """Invoke :meth:`DecompInterface.decompileFunction` with per-fn timeout.

    Returns ``(status, pseudo_c, error_message)``:

    - ``status="ok"``:      ``pseudo_c`` is the rendered C; error is None.
    - ``status="timeout"``: decomp hit ``timeout_s``; pseudo_c is "".
    - ``status="error"``:   decomp returned non-complete / exception;
      error contains the reason.
    """
    try:
        result = decomp.decompileFunction(fn, timeout_s, ConsoleTaskMonitor())
    except Exception as exc:  # Ghidra may throw on malformed samples
        return "error", "", "decompile_exception: %s" % exc

    if result is None:
        return "error", "", "null_result"
    if result.isTimedOut():
        return "timeout", "", "per_function_timeout=%ds" % timeout_s
    if not result.decompileCompleted():
        return "error", "", result.getErrorMessage() or "incomplete"

    decompiled = result.getDecompiledFunction()
    if decompiled is None:
        return "error", "", "no_decompiled_function"
    return "ok", decompiled.getC() or "", None


def _addr_filename(fn):
    """Return a stable, sortable filename for ``fn`` using its entry address."""
    addr = fn.getEntryPoint()
    # ``toString()`` emits the canonical zero-padded hex form (e.g.
    # ``00401000``); prefer that over ``getOffset()`` so Mach-O / PE+ 64-bit
    # addresses remain lexicographically sortable.
    return "%s.c" % addr.toString()


def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def _run():
    script_args = list(getScriptArgs())  # type: ignore[name-defined]
    priority_list_path, output_dir, timeout_s = _parse_args(script_args)
    _ensure_dir(output_dir)

    entries = _load_priority_list(priority_list_path)
    program = currentProgram  # type: ignore[name-defined]

    decomp = DecompInterface()
    try:
        decomp.openProgram(program)

        manifest = {
            "program": program.getName(),
            "priority_list_path": priority_list_path,
            "output_dir": output_dir,
            "per_function_timeout_s": timeout_s,
            "total_requested": len(entries),
            "started_at": time.time(),
            "functions": [],
            "counts": {"ok": 0, "timeout": 0, "not_found": 0, "error": 0},
        }

        for idx, token in enumerate(entries):
            fn = _resolve_function(program, token)
            entry = {
                "rank": idx,
                "request": token,
                "resolved_name": None,
                "resolved_addr": None,
                "status": None,
                "output_path": None,
                "error": None,
                "duration_s": None,
            }

            if fn is None:
                entry["status"] = "not_found"
                manifest["counts"]["not_found"] += 1
                manifest["functions"].append(entry)
                continue

            entry["resolved_name"] = fn.getName()
            entry["resolved_addr"] = fn.getEntryPoint().toString()

            t0 = time.time()
            status, pseudo_c, err = _decompile_one(decomp, fn, timeout_s)
            entry["duration_s"] = round(time.time() - t0, 3)
            entry["status"] = status
            manifest["counts"][status] = manifest["counts"].get(status, 0) + 1

            if status == "ok":
                filename = _addr_filename(fn)
                out_path = os.path.join(output_dir, filename)
                with open(out_path, "w") as fh:
                    fh.write(pseudo_c)
                entry["output_path"] = out_path
            else:
                entry["error"] = err

            manifest["functions"].append(entry)

        manifest["finished_at"] = time.time()
        manifest["wall_s"] = round(manifest["finished_at"] - manifest["started_at"], 3)

        with open(os.path.join(output_dir, "manifest.json"), "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)

        # ``println`` goes to analyzeHeadless stdout — keep it minimal
        # because BashTool truncates to 64 KiB. Agents consume
        # ``manifest.json`` via ``file_read`` instead.
        println(  # type: ignore[name-defined]
            "DecompileByList: requested=%d ok=%d timeout=%d not_found=%d error=%d wall=%.2fs"
            % (
                manifest["total_requested"],
                manifest["counts"]["ok"],
                manifest["counts"]["timeout"],
                manifest["counts"]["not_found"],
                manifest["counts"]["error"],
                manifest["wall_s"],
            )
        )
    finally:
        decomp.dispose()


_run()
