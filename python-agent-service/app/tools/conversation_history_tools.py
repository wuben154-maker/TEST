"""Read-only tools over persisted conversation rows (messages table)."""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field

from app.analyze_request_context import (
    get_analyze_project_id,
    get_analyze_user_id,
)
from app.services.context_memory.repository import search_project_messages

logger = structlog.get_logger(__name__)


class SearchHistoryInput(BaseModel):
    """Arguments for ``search_history``."""

    query: str | None = Field(
        default=None,
        description=(
            "Optional case-insensitive substring to match against message "
            "content. Omit to list the most recent messages only."
        ),
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=50,
        description=(
            "Max rows to return (newest first). Default 8, max 50."
        ),
    )
    request_id: str | None = Field(
        default=None,
        description=(
            "Optional filter: only messages for this analysis request_id."
        ),
    )


async def search_history(
    query: str | None = None,
    limit: int = 8,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Search persisted chat for the current project (read-only, tenant-scoped)."""
    user_id = get_analyze_user_id()
    project_id = get_analyze_project_id()
    if not user_id or not project_id:
        return {
            "ok": False,
            "error": "no_request_context",
            "matches": [],
            "detail": (
                "Requires an authenticated analyze request with project scope."
            ),
        }

    result = await search_project_messages(
        project_id,
        user_id,
        query=query,
        limit=limit,
        request_id_filter=request_id,
    )
    if result.get("ok"):
        logger.info(
            "search_history",
            project_id=project_id,
            match_count=len(result.get("matches") or []),
            has_query=bool(query and query.strip()),
        )
    else:
        logger.warning(
            "search_history denied",
            project_id=project_id,
            error=result.get("error"),
        )
    return result
