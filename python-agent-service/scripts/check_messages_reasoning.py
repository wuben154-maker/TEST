#!/usr/bin/env python3
"""Check if reasoning is persisted in messages table.

Run from python-agent-service dir:
  python scripts/check_messages_reasoning.py
  python scripts/check_messages_reasoning.py --limit 10

Requires .env with DATABASE_MODE and corresponding DB config (Supabase or local).
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _trunc(s: str | None, max_len: int = 80) -> str:
    if s is None:
        return "(null)"
    s = str(s).strip()
    if not s:
        return "(empty)"
    return (s[: max_len] + "...") if len(s) > max_len else s


def main_sync():
    from app.config.settings import get_settings

    settings = get_settings()
    limit = getattr(main_sync, "_limit", 5)

    if settings.database_mode == "supabase":
        from app.db import get_supabase_client

        client = get_supabase_client()
        result = (
            client.table("messages")
            .select("id,project_id,type,content,reasoning,thinking_steps,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = result.data or []
    elif settings.database_mode == "local":
        import asyncpg

        async def _query():
            from app.db import get_pg_pool

            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                return await conn.fetch(
                    """
                    SELECT id, project_id, type, content, reasoning, thinking_steps, created_at
                    FROM messages
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit,
                )

        rows_raw = asyncio.run(_query())
        rows = [
            {
                "id": str(r["id"]),
                "project_id": str(r["project_id"]),
                "type": r["type"],
                "content": r["content"],
                "reasoning": r["reasoning"],
                "thinking_steps": r["thinking_steps"],
                "created_at": r["created_at"],
            }
            for r in rows_raw
        ]
    else:
        print("DATABASE_MODE must be 'supabase' or 'local'. Current:", settings.database_mode)
        sys.exit(1)

    print(f"Database mode: {settings.database_mode}")
    print(f"Latest {len(rows)} messages:\n")
    for r in rows:
        ts = r.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        steps = r.get("thinking_steps") or []
        steps_len = len(steps) if isinstance(steps, list) else 0
        print(f"  id={r.get('id')} project={r.get('project_id')} type={r.get('type')} created={ts}")
        print(f"    content:   {_trunc(r.get('content'))}")
        print(f"    reasoning: {_trunc(r.get('reasoning'))}")
        print(f"    thinking_steps: {steps_len} items")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", "-n", type=int, default=5, help="Number of messages to show")
    args = ap.parse_args()
    main_sync._limit = args.limit
    main_sync()
