"""Contract tests for in-progress analysis persistence/recovery.

These tests help diagnose whether refresh-loss comes from:
1) backend not persisting running progress rows, or
2) frontend restore/render logic.
"""

from uuid import uuid4

import pytest

from app.api.projects import get_analysis_progress
from app.config import get_settings
from app.db import close_db_connections, get_pg_pool
from app.services.progress_service import clear_progress, upsert_progress


def _skip_if_not_local_db() -> None:
    settings = get_settings()
    if settings.database_mode != "local":
        pytest.skip("Contract test requires local Postgres mode")


async def _ensure_progress_timeline_column(pool) -> None:
    """Older local DBs may lack project_analysis_progress.timeline."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            ALTER TABLE project_analysis_progress
            ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb
            """
        )


async def _ensure_progress_ui_language_column(pool) -> None:
    """Older local DBs may lack project_analysis_progress.ui_language."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            ALTER TABLE project_analysis_progress
            ADD COLUMN IF NOT EXISTS ui_language TEXT
            """
        )


@pytest.fixture(autouse=True)
async def _reset_db_pool_per_test():
    """Avoid stale asyncpg pool when switching asyncio loop implementations."""
    await close_db_connections()
    yield
    await close_db_connections()


@pytest.mark.asyncio
async def test_progress_persistence_api_and_clear_progress_two_phase_local_db():
    """Backend contract: upsert + GET analysis-progress (incl. timeline), clear, two-phase semantics."""
    _skip_if_not_local_db()
    pool = await get_pg_pool()
    await _ensure_progress_timeline_column(pool)
    await _ensure_progress_ui_language_column(pool)

    # --- A: persist running row, API reads it, clear removes from API ---
    project_a = str(uuid4())
    user_a = str(uuid4())
    req_a = f"req-{uuid4()}"

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, user_id, title) VALUES ($1, $2, $3)",
            project_a,
            user_a,
            "diagnostic",
        )

    try:
        await upsert_progress(
            project_id=project_a,
            user_id=user_a,
            request_id=req_a,
            status="running",
            user_input="analyze sample file",
            ui_language="zh",
            thinking_steps=[{"id": "s1", "label": "running", "status": "running"}],
            task_summary="summary",
            conclusion="details",
        )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT project_id, user_id, request_id, status, user_input
                FROM project_analysis_progress
                WHERE project_id = $1
                """,
                project_a,
            )
        assert row is not None, "Expected running progress row to be persisted"
        assert str(row["project_id"]) == project_a
        assert str(row["user_id"]) == user_a
        assert row["request_id"] == req_a
        assert row["status"] == "running"
        assert row["user_input"] == "analyze sample file"

        running = await get_analysis_progress(project_a, current_user={"id": user_a})
        assert running is not None
        assert running["is_analyzing"] is True
        assert running["user_input"] == "analyze sample file"
        assert running.get("ui_language") == "zh"
        assert isinstance(running["thinking_steps"], list)
        assert running.get("timeline") == []

        await clear_progress(project_a)
        none_now = await get_analysis_progress(project_a, current_user={"id": user_a})
        assert none_now is None
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM projects WHERE id = $1", project_a)

    # --- B: completed status hides row from API; clear_progress deletes ---
    project_b = str(uuid4())
    user_b = str(uuid4())
    req_b = f"req-{uuid4()}"

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, user_id, title) VALUES ($1, $2, $3)",
            project_b, user_b, "two-phase-test",
        )

    try:
        await upsert_progress(
            project_id=project_b,
            user_id=user_b,
            request_id=req_b,
            status="running",
            user_input="test input",
        )

        running_b = await get_analysis_progress(project_b, current_user={"id": user_b})
        assert running_b is not None
        assert running_b["is_analyzing"] is True

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE project_analysis_progress SET status = 'completed' WHERE project_id = $1",
                project_b,
            )

        after_update = await get_analysis_progress(project_b, current_user={"id": user_b})
        assert after_update is None, (
            "After status='completed', API should return None (query filters status='running')"
        )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM project_analysis_progress WHERE project_id = $1",
                project_b,
            )
        assert row is not None, "Row should still exist before Phase 2 DELETE"
        assert row["status"] == "completed"

        await clear_progress(project_b)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM project_analysis_progress WHERE project_id = $1",
                project_b,
            )
        assert row is None, "Row should be fully deleted after clear_progress"
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM project_analysis_progress WHERE project_id = $1", project_b,
            )
            await conn.execute("DELETE FROM projects WHERE id = $1", project_b)
