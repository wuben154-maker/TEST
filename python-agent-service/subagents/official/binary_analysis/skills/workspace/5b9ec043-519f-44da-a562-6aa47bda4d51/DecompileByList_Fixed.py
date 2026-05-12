# -*- coding: utf-8 -*-
"""Ghidra headless postScript - decompile a pre-sorted priority list.

This script is the FR-07 AC-7 / IR-04 / IR-05 work-horse invoked by
analyzeHeadless inside the binary-analysis E2B sandbox.
"""

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

import json
import os
import re
import time

_HEX_ADDR_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{4,}$")

def _parse_args(args):
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
    entries = []
    with open(path, "r") as fh:
        for raw in fh.readlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line)
    return entries

def _resolve_function(program, raw_token):
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
        it = fm.getFunctions(True)
        while it.hasNext():
            candidate = it.next()
            if candidate.getName() == name_hint:
                fn = candidate
                break
    return fn

def _decompile_one(decomp, fn, timeout_s):
    try:
        result = decomp.decompileFunction(fn, timeout_s, ConsoleTaskMonitor())
    except Exception as exc:
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
    addr = fn.getEntryPoint()
    return "%s.c" % addr.toString()

def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def _run():
    script_args = list(getScriptArgs())
    priority_list_path, output_dir, timeout_s = _parse_args(script_args)
    _ensure_dir(output_dir)

    entries = _load_priority_list(priority_list_path)
    program = currentProgram

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

        println(
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
