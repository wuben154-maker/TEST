"""Contract tests for ``context_usage`` persistence on ``projects``.

Backs acceptance ids A-09 / A-10 / A-11 in
``docs/Process/realtime-context-usage-indicator/acceptance.md``.

These tests exercise the REST-layer handler directly (``update_project`` /
``get_project`` from ``app.api.projects``) against a local Postgres so the
DB side-effects are genuinely verified. They skip cleanly in ``memory`` or
``supabase`` mode because the former doesn't persist and the latter needs
network credentials.

NOTE: we deliberately pack multiple sub-cases inside each async test to
avoid the asyncpg pool / pytest-asyncio event-loop interaction that causes
``Event loop is closed`` when a fresh pool is spun up per test. This mirrors
``test_progress_persistence_contract.py`` in this codebase.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from uuid import uuid4

import pytest

from app.api.projects import (
    ProjectUpdate,
    get_project,
    update_project,
)
from app.config import get_settings
from app.db import close_db_connections, get_pg_pool


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _skip_if_not_local_db() -> None:
    settings = get_settings()
    if settings.database_mode != "local":
        pytest.skip(
            "projects.context_usage contract tests require local Postgres mode"
        )


async def _ensure_context_usage_columns(pool) -> None:
    """Older local DBs may pre-date the 2026-04-19 migration."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS context_usage JSONB
            """
        )
        await conn.execute(
            """
            ALTER TABLE projects
            ADD COLUMN IF NOT EXISTS context_usage_updated_at TIMESTAMPTZ
            """
        )


@pytest.fixture(autouse=True)
async def _reset_db_pool_per_test():
    await close_db_connections()
    yield
    await close_db_connections()


async def _create_project(user_id: str, title: str = "ctx-usage-test") -> str:
    pool = await get_pg_pool()
    project_id = str(uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, user_id, title) VALUES ($1, $2, $3)",
            project_id,
            user_id,
            title,
        )
    return project_id


def _sample_payload(ts_ms: int = 1_700_000_000_000) -> Dict[str, Any]:
    return {
        "v": 1,
        "state": {
            "latest": {
                "invokeId": "abc",
                "modelId": "anthropic/claude-sonnet-4",
                "subagent": None,
                "inputTokens": 12_345,
                "outputTokens": 678,
                "at": ts_ms,
            },
            "cumulative": {
                "inputTokens": 12_345,
                "outputTokens": 678,
                "invocations": 1,
            },
            "bySubagent": [
                {
                    "subagentName": "__main__",
                    "inputTokens": 12_345,
                    "outputTokens": 678,
                    "invocations": 1,
                }
            ],
            "lastSummarizedAt": None,
        },
        "updatedAt": ts_ms,
    }


# ---------------------------------------------------------------------------
# A-09 · round-trip, back-compat, clear, validation (one async test)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_usage_full_contract():
    """All A-09 / A-10 / A-11 sub-cases in a single async test.

    Packed into one function to share a single asyncpg pool under pytest-
    asyncio's per-function event-loop scope (mirrors the approach used by
    ``test_progress_persistence_contract.py``). Splitting into multiple
    async tests reliably hits ``Event loop is closed`` on Windows.

    Sub-cases:
        (a) PATCH persists payload verbatim; GET returns the same payload.
        (b) Title-only PATCH leaves context_usage + its timestamp untouched.
        (c) Explicit null clears the column AND bumps the timestamp.
        (d) Empty body → 400.
        (e) Non-object context_usage → 400.
        (f) Cross-user PATCH → 404 and target row untouched.
        (g) Two sequential PATCHes → later payload wins (last-write-wins).
    """
    _skip_if_not_local_db()
    pool = await get_pg_pool()
    await _ensure_context_usage_columns(pool)

    from fastapi import HTTPException

    user_id = str(uuid4())
    project_id = await _create_project(user_id)
    current_user = {"id": user_id}
    payload = _sample_payload()

    # (a) Round-trip --------------------------------------------------------
    resp = await update_project(
        project_id,
        ProjectUpdate(context_usage=payload),
        current_user=current_user,
    )
    assert resp["context_usage"] == payload
    assert resp["context_usage_updated_at"] is not None

    got = await get_project(project_id, current_user=current_user)
    assert got["context_usage"] == payload
    assert got["context_usage_updated_at"] == resp["context_usage_updated_at"]

    seeded_ts = got["context_usage_updated_at"]

    # (b) Title-only PATCH --------------------------------------------------
    resp2 = await update_project(
        project_id,
        ProjectUpdate(title="renamed"),
        current_user=current_user,
    )
    assert resp2["title"] == "renamed"
    assert resp2["context_usage"] == payload
    assert resp2["context_usage_updated_at"] == seeded_ts

    # (c) Explicit-null clear bumps timestamp ------------------------------
    # ``format_api_datetime`` only serialises to second precision, so we
    # must sleep long enough to cross a second boundary deterministically.
    await asyncio.sleep(1.1)
    cleared = await update_project(
        project_id,
        ProjectUpdate(context_usage=None),
        current_user=current_user,
    )
    assert cleared["context_usage"] is None
    assert cleared["context_usage_updated_at"] is not None
    assert cleared["context_usage_updated_at"] != seeded_ts

    # (d) Empty body -------------------------------------------------------
    with pytest.raises(HTTPException) as exc_empty:
        await update_project(
            project_id,
            ProjectUpdate(),
            current_user=current_user,
        )
    assert exc_empty.value.status_code == 400

    # (e) Non-object context_usage -----------------------------------------
    with pytest.raises(HTTPException) as exc_bad:
        await update_project(
            project_id,
            ProjectUpdate(context_usage="not a dict"),
            current_user=current_user,
        )
    assert exc_bad.value.status_code == 400

    # (f) Cross-user PATCH ------------------------------------------------
    other_user = {"id": str(uuid4())}
    with pytest.raises(HTTPException) as exc_xuser:
        await update_project(
            project_id,
            ProjectUpdate(context_usage=_sample_payload()),
            current_user=other_user,
        )
    assert exc_xuser.value.status_code == 404
    # Row still holds the cleared value from step (c) — not the attempt.
    still = await get_project(project_id, current_user=current_user)
    assert still["context_usage"] is None

    # (g) Last-write-wins -------------------------------------------------
    first = _sample_payload(ts_ms=1_700_000_000_000)
    second = _sample_payload(ts_ms=1_700_000_000_500)
    second["state"]["cumulative"]["invocations"] = 2

    await update_project(
        project_id,
        ProjectUpdate(context_usage=first),
        current_user=current_user,
    )
    # Short sleep sufficient: we only compare the jsonb payload body here,
    # not the stamped timestamp, so sub-second ordering of two UPDATEs is
    # determined by monotonic SQL execution order.
    await asyncio.sleep(0.05)
    await update_project(
        project_id,
        ProjectUpdate(context_usage=second),
        current_user=current_user,
    )

    final = await get_project(project_id, current_user=current_user)
    assert final["context_usage"] == second
    assert final["context_usage"]["state"]["cumulative"]["invocations"] == 2
