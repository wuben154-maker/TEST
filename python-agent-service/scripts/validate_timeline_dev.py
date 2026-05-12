#!/usr/bin/env python3
"""Dev helper: validate persisted or exported analysis timeline rows (schemaVersion 1).

Use this to verify acceptance criteria for nested subagents (e.g. ``binary-analysis``):
see ``docs/SSE_EVENT_CATALOG.md`` — look for ``task`` tool_call with ``subagent_type`` and/or
``subagentName`` on subagent-scoped stream rows.

Run from ``python-agent-service`` directory::

  python scripts/validate_timeline_dev.py path/to/timeline.json
  python scripts/validate_timeline_dev.py -
  type timeline.json | python scripts/validate_timeline_dev.py --stdin

Load timeline from DB (requires ``.env`` with DATABASE_MODE and credentials)::

  python scripts/validate_timeline_dev.py --latest
  python scripts/validate_timeline_dev.py --latest --scan-limit 500
  python scripts/validate_timeline_dev.py --message-id <uuid>
  python scripts/validate_timeline_dev.py --latest --dump out/timeline.json

Slice (strict attribution between two tool_call boundaries; UI ``Thought brief`` is not tagged):: 

  python scripts/validate_timeline_dev.py msg.json \\
    --segment-after-tool analyze_attachment --segment-before-tool run_enrich_phase

Write machine-readable artifacts for agent/IDE (no copy-paste; default dir is gitignored)::

  python scripts/validate_timeline_dev.py --latest --scan-limit 5000 --snapshot \\
    --segment-after-tool analyze_attachment --segment-before-tool run_enrich_phase
  # -> .artifacts/dev_validate/{timeline,meta,analysis}.json

Strict exit codes (optional)::

  python scripts/validate_timeline_dev.py --expect-binary-analysis timeline.json
  python scripts/validate_timeline_dev.py --expect-task-delegation timeline.json

Exit code:
  0 — ok (or strict expectations met)
  1 — invalid JSON / empty timeline / strict expectations not met
  2 — file not found or read error / DB error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = SCRIPT_DIR.parent
DEFAULT_SNAPSHOT_DIR = SERVICE_ROOT / ".artifacts" / "dev_validate"


def _load_json_raw(text: str) -> Any:
    return json.loads(text)


def _normalize_timeline_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        tl = data.get("timeline")
        if isinstance(tl, list):
            return [x for x in tl if isinstance(x, dict)]
        # Single assistant message shape
        if "timeline" in data and isinstance(data["timeline"], list):
            return [x for x in data["timeline"] if isinstance(x, dict)]
    return []


def _read_input(path: str | None, use_stdin: bool) -> str:
    if use_stdin or path == "-":
        return sys.stdin.read()
    if not path:
        raise ValueError("path or --stdin required")
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_text(encoding="utf-8")


def _coerce_timeline_list(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def load_timeline_from_database(
    *,
    message_id: str | None,
    latest: bool,
    scan_limit: int = 200,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """Load timeline rows from Supabase or local Postgres.

    Returns ``(rows, meta_line, db_message_id)``. ``db_message_id`` is set when loaded from DB.
    """
    from dotenv import load_dotenv

    load_dotenv(SERVICE_ROOT / ".env")
    from app.config.settings import get_settings

    settings = get_settings()
    mode = getattr(settings, "database_mode", None) or ""

    def _row_meta(row: dict[str, Any]) -> str:
        return (
            f"db message id={row.get('id')} type={row.get('type')} "
            f"created={row.get('created_at')} project_id={row.get('project_id')}"
        )

    if message_id:
        mid = str(message_id).strip()
        if mode == "supabase":
            from app.db import get_supabase_client

            client = get_supabase_client()
            result = (
                client.table("messages")
                .select("id,timeline,created_at,project_id,type")
                .eq("id", mid)
                .limit(1)
                .execute()
            )
            rows_data = result.data or []
            if not rows_data:
                raise RuntimeError(f"No message with id={mid}")
            row = rows_data[0]
        elif mode == "local":

            async def _fetch_one() -> Any:
                from app.db import get_pg_pool

                pool = await get_pg_pool()
                async with pool.acquire() as conn:
                    return await conn.fetchrow(
                        """
                        SELECT id, timeline, created_at, project_id, type
                        FROM messages
                        WHERE id = $1::uuid
                        """,
                        mid,
                    )

            r = asyncio.run(_fetch_one())
            if not r:
                raise RuntimeError(f"No message with id={mid}")
            row = dict(r)
        else:
            raise RuntimeError(f"Unsupported DATABASE_MODE: {mode!r} (need supabase or local)")

        tl = _coerce_timeline_list(row.get("timeline"))
        mid_out = str(row.get("id") or "").strip() or mid
        return tl, _row_meta(row), mid_out

    if latest:
        n = max(1, min(int(scan_limit), 5000))
        if mode == "supabase":
            from app.db import get_supabase_client

            client = get_supabase_client()
            result = (
                client.table("messages")
                .select("id,timeline,created_at,project_id,type")
                .eq("type", "assistant")
                .order("created_at", desc=True)
                .limit(n)
                .execute()
            )
            for row in result.data or []:
                tl = _coerce_timeline_list(row.get("timeline"))
                if tl:
                    mid_out = str(row.get("id") or "").strip() or None
                    return (
                        tl,
                        _row_meta(row) + f" (latest non-empty timeline, scanned {n})",
                        mid_out,
                    )
            raise RuntimeError(
                f"No assistant message with non-empty timeline (checked last {n} assistant rows)"
            )
        if mode == "local":

            async def _fetch_recent() -> list[Any]:
                from app.db import get_pg_pool

                pool = await get_pg_pool()
                async with pool.acquire() as conn:
                    return await conn.fetch(
                        """
                        SELECT id, timeline, created_at, project_id, type
                        FROM messages
                        WHERE type = 'assistant'
                        ORDER BY created_at DESC
                        LIMIT $1
                        """,
                        n,
                    )

            for r in asyncio.run(_fetch_recent()):
                row = dict(r)
                tl = _coerce_timeline_list(row.get("timeline"))
                if tl:
                    mid_out = str(row.get("id") or "").strip() or None
                    return (
                        tl,
                        _row_meta(row) + f" (latest non-empty timeline, scanned {n})",
                        mid_out,
                    )
            raise RuntimeError(
                f"No assistant message with non-empty timeline (checked last {n} assistant rows)"
            )
        raise RuntimeError(f"Unsupported DATABASE_MODE: {mode!r} (need supabase or local)")

    raise RuntimeError("internal: specify message_id or latest")


def _task_subagent_types(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ev in rows:
        if str(ev.get("type")) != "tool_call":
            continue
        if str(ev.get("toolName") or "") != "task":
            continue
        inp = ev.get("toolInput")
        if not isinstance(inp, dict):
            continue
        st = inp.get("subagent_type") or inp.get("subagentType")
        if st is not None:
            out.append(str(st).strip())
    return out


def _rows_between_tool_calls(
    rows: list[dict[str, Any]],
    after_tool: str,
    before_tool: str,
) -> tuple[list[dict[str, Any]], int | None, int | None, str | None]:
    """Rows **after** the first ``tool_call`` with ``toolName == after_tool`` and **before**
    the first ``tool_call`` with ``toolName == before_tool`` that appears later.
    Returns ``(segment, start_idx, end_idx, err)``; ``end_idx`` is index of *before* tool, or
    ``None`` if *before* never appears (segment is tail after *after*; still an error string).
    """
    start_i: int | None = None
    for i, ev in enumerate(rows):
        if str(ev.get("type")) == "tool_call" and str(ev.get("toolName") or "") == after_tool:
            start_i = i
            break
    if start_i is None:
        return [], None, None, f"no tool_call with toolName={after_tool!r}"

    end_i: int | None = None
    for j in range(start_i + 1, len(rows)):
        if str(rows[j].get("type")) == "tool_call" and str(rows[j].get("toolName") or "") == before_tool:
            end_i = j
            break
    if end_i is None:
        return (
            rows[start_i + 1 :],
            start_i,
            None,
            f"no tool_call with toolName={before_tool!r} after index {start_i}",
        )
    return rows[start_i + 1 : end_i], start_i, end_i, None


def _tool_calls_in_order(rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for ev in rows:
        if str(ev.get("type")) == "tool_call":
            out.append(str(ev.get("toolName") or ""))
    return out


def _print_segment_report(
    seg: list[dict[str, Any]],
    *,
    after_tool: str,
    before_tool: str,
    after_idx: int | None,
    before_idx: int | None,
    err: str | None,
    st_pre: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Print human-readable segment report. Returns segment stats (for ``--snapshot``)."""
    print()
    print("--- segment (S4 -> S4.5 gap) ---")
    print(
        f"bounds: after first {after_tool!r} tool_call"
        + (f" @ row {after_idx}" if after_idx is not None else "")
        + f", before first {before_tool!r} tool_call"
        + (f" @ row {before_idx}" if before_idx is not None else "")
    )
    if err:
        print(f"warning: {err}")
    print(
        "note: UI label 'Thought brief' = thinking duration with no visible reasoning/text "
        "(see src/lib/thinkingDurationLabel.ts); it does not name a subagent."
    )
    print(f"segment row count: {len(seg)}")
    if not seg and not err:
        print("  (empty segment — tools are adjacent in timeline order)")
    tools_here = _tool_calls_in_order(seg)
    if tools_here:
        print("tool_call toolName order inside segment:")
        for tn in tools_here:
            print(f"  - {tn!r}")
    else:
        print("tool_call toolName order inside segment: (none)")
    st = st_pre if st_pre is not None else _analyze(seg)
    bn = st["binary_analysis_subagent_name_indices"]
    bt = st["binary_analysis_task_tool_indices"]
    off = (after_idx + 1) if after_idx is not None else 0
    bn_full = [off + i for i in bn]
    bt_full = [off + i for i in bt]
    ok = len(bn) > 0 or len(bt) > 0
    print()
    print(
        "binary-analysis in this segment (strict A): "
        + ("YES - task(binary-analysis) and/or subagentName binary-analysis rows here" if ok else "NO")
    )
    if ok:
        print(f"  subagentName hits (full timeline indices): {bn_full}")
        print(f"  task(binary-analysis) hits (full timeline indices): {bt_full}")
    # Per-stream attribution inside segment (still strict: only names prove nested binary agent)
    names_seg = Counter()
    for ev in seg:
        sn = ev.get("subagentName")
        if sn is not None:
            names_seg[str(sn)] += 1
    if names_seg:
        print("subagentName row counts inside segment (any nested stream tags):")
        for n, c in sorted(names_seg.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {n!r}: {c}")
    return st


def _analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    types = Counter(str(r.get("type") or "") for r in rows)
    names = Counter()
    subagent_scoped = 0
    delegation_with_depth = 0
    binary_name_hits: list[int] = []
    binary_task_hits: list[int] = []

    for i, ev in enumerate(rows):
        sn = ev.get("subagentName")
        if sn is not None:
            names[str(sn)] += 1
        sc = ev.get("scope") or ("subagent" if ev.get("subagentStream") else "main")
        if sc == "subagent" or ev.get("subagentStream") is True:
            subagent_scoped += 1
        if isinstance(ev.get("delegationDepth"), (int, float)):
            delegation_with_depth += 1
        if str(sn or "").strip() == "binary-analysis":
            binary_name_hits.append(i)

    for i, ev in enumerate(rows):
        if str(ev.get("type")) != "tool_call":
            continue
        if str(ev.get("toolName") or "") != "task":
            continue
        inp = ev.get("toolInput") if isinstance(ev.get("toolInput"), dict) else {}
        st = str((inp or {}).get("subagent_type") or (inp or {}).get("subagentType") or "").strip()
        if st == "binary-analysis":
            binary_task_hits.append(i)

    task_types = _task_subagent_types(rows)

    return {
        "row_count": len(rows),
        "type_counts": dict(types),
        "subagent_name_counts": dict(names),
        "subagent_scoped_rows": subagent_scoped,
        "rows_with_delegation_depth": delegation_with_depth,
        "binary_analysis_subagent_name_indices": binary_name_hits,
        "binary_analysis_task_tool_indices": binary_task_hits,
        "task_subagent_types": task_types,
    }


def _print_report(stats: dict[str, Any], *, source: str | None = None) -> None:
    print("=== timeline validate (dev) ===")
    if source:
        print(f"source: {source}")
    print(f"rows: {stats['row_count']}")
    print(f"subagent-scoped or subagentStream rows: {stats['subagent_scoped_rows']}")
    print(f"rows with delegationDepth: {stats['rows_with_delegation_depth']}")
    print()
    print("event types (top):")
    for t, c in sorted(stats["type_counts"].items(), key=lambda x: (-x[1], x[0]))[:25]:
        print(f"  {t}: {c}")
    if len(stats["type_counts"]) > 25:
        print(f"  ... ({len(stats['type_counts'])} distinct types)")
    print()
    print("subagentName counts:")
    if not stats["subagent_name_counts"]:
        print("  (none)")
    else:
        for n, c in sorted(stats["subagent_name_counts"].items(), key=lambda x: (-x[1], x[0])):
            print(f"  {n!r}: {c}")
    print()
    print("task() delegations (subagent_type from toolInput):")
    if not stats["task_subagent_types"]:
        print("  (no task tool_call rows found)")
    else:
        for st in stats["task_subagent_types"]:
            print(f"  - {st!r}")
    print()
    idx_bn = stats["binary_analysis_subagent_name_indices"]
    idx_bt = stats["binary_analysis_task_tool_indices"]
    print(f"binary-analysis evidence: subagentName rows -> {len(idx_bn)} (indices: {idx_bn[:20]}{'...' if len(idx_bn) > 20 else ''})")
    print(f"binary-analysis evidence: task tool_call    -> {len(idx_bt)} (indices: {idx_bt[:20]}{'...' if len(idx_bt) > 20 else ''})")
    print()
    ok_a = len(idx_bn) > 0 or len(idx_bt) > 0
    print(
        "acceptance A (protocol): "
        + (
            "PASS - found task(binary-analysis) and/or subagentName binary-analysis"
            if ok_a
            else "FAIL - no binary-analysis in timeline"
        )
    )


def _dump_timeline(path: str, rows: list[dict[str, Any]]) -> None:
    outp = Path(path)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_dev_snapshot(
    out_dir: Path,
    *,
    rows: list[dict[str, Any]],
    source_line: str | None,
    message_id: str | None,
    stats: dict[str, Any],
    segment: dict[str, Any] | None,
) -> None:
    """Write machine-readable artifacts for local dev (gitignored under ``.artifacts/`` by default)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timeline.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    meta: dict[str, Any] = {
        "message_id": message_id,
        "source": source_line,
        "utc_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    analysis: dict[str, Any] = {
        "stats": stats,
        "segment": segment,
    }
    (out_dir / "analysis.json").write_text(
        json.dumps(analysis, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate analysis timeline JSON (dev).")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to JSON file, or '-' for stdin",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read JSON from stdin (same as path '-')",
    )
    db_src = parser.add_mutually_exclusive_group()
    db_src.add_argument(
        "--latest",
        action="store_true",
        help="Load timeline from DB: latest assistant message with non-empty timeline",
    )
    db_src.add_argument(
        "--message-id",
        metavar="UUID",
        help="Load timeline from DB for this messages.id",
    )
    parser.add_argument(
        "--dump",
        metavar="PATH",
        help="Write normalized timeline rows as JSON array to this file",
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=200,
        metavar="N",
        help="With --latest: scan up to N recent assistant rows for a non-empty timeline (default 200, max 5000)",
    )
    parser.add_argument(
        "--expect-binary-analysis",
        action="store_true",
        help="Exit 1 if no binary-analysis task call and no subagentName binary-analysis",
    )
    parser.add_argument(
        "--expect-task-delegation",
        action="store_true",
        help="Exit 1 if no tool_call with toolName task at all",
    )
    parser.add_argument(
        "--segment-after-tool",
        metavar="TOOL",
        help="With --segment-before-tool: analyze rows strictly between these tool_call toolNames",
    )
    parser.add_argument(
        "--segment-before-tool",
        metavar="TOOL",
        help="See --segment-after-tool (e.g. email_security S4→S4.5: analyze_attachment → run_enrich_phase)",
    )
    parser.add_argument(
        "--segment-expect-binary-analysis",
        action="store_true",
        help="Exit 1 if segment has no binary-analysis evidence (requires segment bounds)",
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help=f"Write timeline.json, meta.json, analysis.json under snapshot dir (default: {DEFAULT_SNAPSHOT_DIR})",
    )
    parser.add_argument(
        "--snapshot-dir",
        metavar="DIR",
        help=f"Directory for --snapshot (default: {DEFAULT_SNAPSHOT_DIR})",
    )
    args = parser.parse_args()

    if (args.segment_after_tool or args.segment_before_tool) and not (
        args.segment_after_tool and args.segment_before_tool
    ):
        parser.error("--segment-after-tool and --segment-before-tool must be used together")

    has_file = bool(args.stdin or args.path)
    has_db = bool(args.latest or args.message_id)
    if has_file and has_db:
        parser.error("use either file/stdin or --latest / --message-id, not both")
    if not has_file and not has_db:
        parser.error("provide a JSON path, --stdin, --latest, or --message-id")

    source_line: str | None = None
    rows: list[dict[str, Any]] = []
    db_message_id: str | None = None

    if has_db:
        try:
            rows, meta, db_message_id = load_timeline_from_database(
                message_id=args.message_id,
                latest=args.latest,
                scan_limit=args.scan_limit,
            )
            source_line = f"database ({meta})"
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"error loading from database: {e}", file=sys.stderr)
            return 2
        if not rows:
            print("error: no timeline rows in message.timeline", file=sys.stderr)
            return 1
    else:
        text = ""
        try:
            text = _read_input(args.path, args.stdin)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"error reading input: {e}", file=sys.stderr)
            return 2

        try:
            raw = _load_json_raw(text)
        except json.JSONDecodeError as e:
            print(f"error: invalid JSON: {e}", file=sys.stderr)
            return 1

        rows = _normalize_timeline_rows(raw)
        if not rows:
            print("error: no timeline rows (expect JSON array or object.timeline array)", file=sys.stderr)
            return 1
        if args.stdin or args.path == "-":
            source_line = "stdin"
        elif args.path:
            source_line = f"file:{Path(args.path).resolve()}"

    if args.dump:
        try:
            _dump_timeline(args.dump, rows)
        except OSError as e:
            print(f"error: cannot write --dump: {e}", file=sys.stderr)
            return 2

    stats = _analyze(rows)
    _print_report(stats, source=source_line)

    segment_payload: dict[str, Any] | None = None
    if args.segment_after_tool and args.segment_before_tool:
        seg, ai, bi, serr = _rows_between_tool_calls(
            rows, args.segment_after_tool, args.segment_before_tool
        )
        st_seg = _analyze(seg)
        _print_segment_report(
            seg,
            after_tool=args.segment_after_tool,
            before_tool=args.segment_before_tool,
            after_idx=ai,
            before_idx=bi,
            err=serr,
            st_pre=st_seg,
        )
        ok_seg = bool(
            st_seg["binary_analysis_subagent_name_indices"] or st_seg["binary_analysis_task_tool_indices"]
        )
        segment_payload = {
            "after_tool": args.segment_after_tool,
            "before_tool": args.segment_before_tool,
            "after_row_index": ai,
            "before_row_index": bi,
            "bounds_error": serr,
            "segment_row_count": len(seg),
            "tools_in_segment": _tool_calls_in_order(seg),
            "stats": st_seg,
            "binary_analysis_in_segment_strict_a": ok_seg,
        }
        if args.segment_expect_binary_analysis:
            if not ok_seg:
                print("", file=sys.stderr)
                print(
                    "strict: --segment-expect-binary-analysis not satisfied in segment",
                    file=sys.stderr,
                )
                return 1

    if args.snapshot:
        snap_dir = Path(args.snapshot_dir) if args.snapshot_dir else DEFAULT_SNAPSHOT_DIR
        try:
            _write_dev_snapshot(
                snap_dir,
                rows=rows,
                source_line=source_line,
                message_id=db_message_id,
                stats=stats,
                segment=segment_payload,
            )
            print("", file=sys.stderr)
            print(f"snapshot: wrote {snap_dir / 'timeline.json'} analysis.json meta.json", file=sys.stderr)
        except OSError as e:
            print(f"error: --snapshot write failed: {e}", file=sys.stderr)
            return 2

    if args.expect_binary_analysis:
        if not stats["binary_analysis_subagent_name_indices"] and not stats["binary_analysis_task_tool_indices"]:
            print("", file=sys.stderr)
            print("strict: --expect-binary-analysis not satisfied", file=sys.stderr)
            return 1

    if args.expect_task_delegation:
        if not stats["task_subagent_types"]:
            print("", file=sys.stderr)
            print("strict: --expect-task-delegation not satisfied (no task tool_call)", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(SERVICE_ROOT))
    raise SystemExit(main())
