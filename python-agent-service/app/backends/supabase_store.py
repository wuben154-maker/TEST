"""Supabase Store - BaseStore implementation using Supabase client.

Used when DATABASE_MODE=supabase. Stores key-value data in agent_store table.
Requires agent_store table to exist (see supabase migrations).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.backends.store import BaseStore, StoreItem, StoreConfig
from app.datetime_support import format_api_datetime, now_app

logger = structlog.get_logger()


class SupabaseStore(BaseStore):
    """Supabase-backed persistent store using REST API."""

    TABLE_NAME = "agent_store"

    def __init__(self, config: StoreConfig | None = None):
        self.config = config or StoreConfig()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from app.db import get_supabase_client
            self._client = get_supabase_client()
        return self._client

    async def get(self, key: str, namespace: str = "default") -> StoreItem | None:
        client = self._get_client()
        result = (
            client.table(self.TABLE_NAME)
            .select("*")
            .eq("namespace", namespace)
            .eq("key", key)
            .execute()
        )
        if not result.data or len(result.data) == 0:
            return None
        row = result.data[0]
        expires_at = row.get("expires_at")
        if expires_at:
            from datetime import datetime
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                return None
        return StoreItem(
            key=row["key"],
            value=row["value"],
            namespace=row["namespace"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=expires_at,
            metadata=row.get("metadata") or {},
        )

    async def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl_hours: int | None = None,
        metadata: dict | None = None,
    ) -> StoreItem:
        client = self._get_client()
        now = format_api_datetime(now_app())
        expires_at = None
        if ttl_hours is not None:
            expires_at = format_api_datetime(now_app() + timedelta(hours=ttl_hours))

        payload = {
            "namespace": namespace,
            "key": key,
            "value": value,
            "metadata": metadata or {},
            "updated_at": now,
            "expires_at": expires_at,
        }

        result = (
            client.table(self.TABLE_NAME)
            .upsert(
                payload,
                on_conflict="namespace,key",
                ignore_duplicates=False,
            )
            .execute()
        )
        if result.data and len(result.data) > 0:
            row = result.data[0]
        else:
            row = {**payload, "created_at": now}
        return StoreItem(
            key=key,
            value=value,
            namespace=namespace,
            created_at=row.get("created_at", now),
            updated_at=now,
            expires_at=expires_at,
            metadata=metadata or {},
        )

    async def delete(self, key: str, namespace: str = "default") -> bool:
        client = self._get_client()
        result = (
            client.table(self.TABLE_NAME)
            .delete()
            .eq("namespace", namespace)
            .eq("key", key)
            .execute()
        )
        return True

    async def list_keys(self, namespace: str = "default", prefix: str = "") -> list[str]:
        client = self._get_client()
        result = (
            client.table(self.TABLE_NAME)
            .select("key")
            .eq("namespace", namespace)
            .execute()
        )
        keys = [
            row["key"]
            for row in (result.data or [])
            if not prefix or row["key"].startswith(prefix)
        ]
        return sorted(keys)

    async def search(self, pattern: str, namespace: str = "default") -> list[StoreItem]:
        import re
        client = self._get_client()
        result = (
            client.table(self.TABLE_NAME)
            .select("*")
            .eq("namespace", namespace)
            .execute()
        )
        try:
            regex = re.compile(pattern)
        except re.error:
            regex = re.compile(re.escape(pattern))
        items = []
        for row in result.data or []:
            if regex.search(row["key"]) or regex.search(str(row.get("value", ""))):
                items.append(
                    StoreItem(
                        key=row["key"],
                        value=row["value"],
                        namespace=row["namespace"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        expires_at=row.get("expires_at"),
                        metadata=row.get("metadata") or {},
                    )
                )
        return items

    async def cleanup_expired(self) -> int:
        client = self._get_client()
        now = datetime.now(timezone.utc).isoformat()
        result = (
            client.table(self.TABLE_NAME)
            .delete()
            .lt("expires_at", now)
            .not_.is_("expires_at", "null")
            .execute()
        )
        return len(result.data) if result.data else 0
