"""SOC vendor authorization storage and HITL credential collection service."""

from __future__ import annotations

import asyncio
import json
import textwrap
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import structlog
from langgraph.types import interrupt

from app.backends.store import EncryptionManager
from app.config import get_settings
from app.db import get_pg_pool, get_supabase_client
from subagents.official.soc_alert.tools.soc_alert.api.provider_registry import (
    build_hitl_fields,
    get_provider,
)

logger = structlog.get_logger()

_SQL_PG_UPSERT_USER_VENDOR_CONNECTION = textwrap.dedent(
    """
    INSERT INTO user_vendor_connections
        (user_id, provider_code, display_name, auth_type, auth_status, metadata)
    VALUES ($1, $2, $3, $4, 'active', $5::jsonb)
    ON CONFLICT (user_id, provider_code, display_name)
    DO UPDATE SET
        auth_type = EXCLUDED.auth_type,
        auth_status = 'active',
        metadata = EXCLUDED.metadata,
        updated_at = now()
    RETURNING id
    """
).strip()

_SQL_PG_UPSERT_USER_VENDOR_SECRET = textwrap.dedent(
    """
    INSERT INTO user_vendor_connection_secrets
        (connection_id, secret_ciphertext, secret_version, encryption_meta)
    VALUES ($1, $2, 1, '{}'::jsonb)
    ON CONFLICT (connection_id)
    DO UPDATE SET
        secret_ciphertext = EXCLUDED.secret_ciphertext,
        rotated_at = now()
    """
).strip()


def _credentials_log_summary(creds: dict[str, Any]) -> dict[str, Any]:
    """Non-secret shape of credentials for logs (never log passwords or tokens)."""
    if not isinstance(creds, dict) or not creds:
        return {}
    keys = sorted(k for k in creds.keys() if k != "remember_auth")
    out: dict[str, Any] = {
        "field_keys": keys,
        "has_username": bool(str(creds.get("username") or "").strip()),
        "has_password": bool(str(creds.get("password") or "").strip()),
    }
    bu = str(creds.get("base_url") or "").strip()
    if bu:
        try:
            parsed = urlparse(bu if "://" in bu else f"https://{bu}")
            host = (parsed.netloc or "").strip()
            if not host and parsed.path:
                host = parsed.path.split("/")[0]
            if host:
                out["base_url_host"] = host
            else:
                out["base_url_present"] = True
        except Exception:
            out["base_url_present"] = True
    return out


@dataclass
class EphemeralAuthRecord:
    """In-memory auth cache record for one request/session/provider."""

    credentials: dict[str, Any]
    expires_at: float


class VendorAuthService:
    """Resolve provider credentials from DB or temporary memory."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._encryptor = EncryptionManager()
        self._ephemeral: dict[tuple[str, str, str], EphemeralAuthRecord] = {}
        self._lock = asyncio.Lock()
        self._inflight_resolves: dict[tuple[str, str, str, str], asyncio.Future[dict[str, Any]]] = {}
        self._inflight_lock = asyncio.Lock()

    @staticmethod
    def _norm(value: str | None) -> str:
        return (value or "").strip()

    def _ephemeral_key(
        self,
        *,
        session_id: str | None,
        request_id: str | None,
        provider_code: str,
    ) -> tuple[str, str, str]:
        return (
            self._norm(session_id) or "default",
            self._norm(request_id) or "default",
            self._norm(provider_code),
        )

    def _singleflight_key(
        self,
        *,
        provider_code: str,
        session_id: str | None,
        request_id: str | None,
        user_id: str | None,
    ) -> tuple[str, str, str, str]:
        return (
            self._norm(provider_code),
            self._norm(session_id) or "default",
            self._norm(request_id) or "default",
            self._norm(user_id) or "default",
        )

    async def clear_request_ephemeral(self, request_id: str) -> None:
        """Clear all in-memory credentials for one request."""
        rid = self._norm(request_id)
        if not rid:
            logger.info("soc_auth_ephemeral_clear_skipped", reason="empty_request_id")
            return
        async with self._lock:
            keys = [k for k in self._ephemeral.keys() if k[1] == rid]
            for key in keys:
                self._ephemeral.pop(key, None)
        logger.info(
            "soc_auth_ephemeral_cleared",
            request_id=rid,
            cleared_count=len(keys),
        )

    async def set_ephemeral(
        self,
        *,
        session_id: str | None,
        request_id: str | None,
        provider_code: str,
        credentials: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """Save temporary credentials for one request/session/provider."""
        key = self._ephemeral_key(
            session_id=session_id,
            request_id=request_id,
            provider_code=provider_code,
        )
        rec = EphemeralAuthRecord(
            credentials=dict(credentials or {}),
            expires_at=time.time() + max(1, ttl_seconds),
        )
        async with self._lock:
            self._ephemeral[key] = rec
        logger.info(
            "soc_auth_ephemeral_set",
            provider_code=provider_code,
            session_id=key[0],
            request_id=key[1],
            ttl_seconds=ttl_seconds,
            credential_fields=sorted(rec.credentials.keys()),
        )

    async def get_ephemeral(
        self,
        *,
        session_id: str | None,
        request_id: str | None,
        provider_code: str,
    ) -> dict[str, Any] | None:
        """Get temporary credentials if still valid."""
        key = self._ephemeral_key(
            session_id=session_id,
            request_id=request_id,
            provider_code=provider_code,
        )
        async with self._lock:
            rec = self._ephemeral.get(key)
            if not rec:
                logger.info(
                    "soc_auth_ephemeral_miss",
                    provider_code=provider_code,
                    session_id=key[0],
                    request_id=key[1],
                )
                return None
            if rec.expires_at <= time.time():
                self._ephemeral.pop(key, None)
                logger.info(
                    "soc_auth_ephemeral_expired",
                    provider_code=provider_code,
                    session_id=key[0],
                    request_id=key[1],
                )
                return None
            logger.info(
                "soc_auth_ephemeral_hit",
                provider_code=provider_code,
                session_id=key[0],
                request_id=key[1],
                credential_fields=sorted(rec.credentials.keys()),
            )
            return dict(rec.credentials)

    async def _get_connection_local(
        self,
        *,
        user_id: str,
        provider_code: str,
    ) -> dict[str, Any] | None:
        logger.info(
            "soc_auth_db_lookup_local_query",
            provider_code=provider_code,
            has_user_id=bool(self._norm(user_id)),
        )
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.id, c.provider_code, c.auth_type, c.auth_status,
                       c.metadata, c.display_name, s.secret_ciphertext
                FROM user_vendor_connections c
                LEFT JOIN user_vendor_connection_secrets s
                  ON s.connection_id = c.id
                WHERE c.user_id = $1
                  AND c.provider_code = $2
                  AND c.auth_status IN ('active', 'pending')
                ORDER BY c.updated_at DESC
                LIMIT 1
                """,
                user_id,
                provider_code,
            )
            if not row:
                logger.info("soc_auth_db_lookup_local_miss", provider_code=provider_code)
                return None
            encrypted = row.get("secret_ciphertext")
            secret_data: dict[str, Any] = {}
            if isinstance(encrypted, str) and encrypted.strip():
                try:
                    plain = self._encryptor.decrypt(encrypted)
                    loaded = json.loads(plain)
                    if isinstance(loaded, dict):
                        secret_data = loaded
                except Exception as exc:
                    logger.warning("failed_to_decrypt_vendor_secret", error=str(exc))
            logger.info(
                "soc_auth_db_lookup_local_hit",
                provider_code=provider_code,
                has_credentials=bool(secret_data),
                credential_fields=sorted(secret_data.keys()),
                auth_status=row["auth_status"],
            )
            return {
                "connection_id": str(row["id"]),
                "provider_code": row["provider_code"],
                "auth_type": row["auth_type"],
                "auth_status": row["auth_status"],
                "metadata": row["metadata"] or {},
                "display_name": row["display_name"],
                "credentials": secret_data,
            }

    async def _get_connection_supabase(
        self,
        *,
        user_id: str,
        provider_code: str,
    ) -> dict[str, Any] | None:
        logger.info(
            "soc_auth_db_lookup_supabase_query",
            provider_code=provider_code,
            has_user_id=bool(self._norm(user_id)),
        )
        client = get_supabase_client()
        res = (
            client.table("user_vendor_connections")
            .select("id,provider_code,auth_type,auth_status,metadata,display_name")
            .eq("user_id", user_id)
            .eq("provider_code", provider_code)
            .in_("auth_status", ["active", "pending"])
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        row = res.data[0] if res.data else None
        if not row:
            logger.info("soc_auth_db_lookup_supabase_miss", provider_code=provider_code)
            return None
        sres = (
            client.table("user_vendor_connection_secrets")
            .select("secret_ciphertext")
            .eq("connection_id", row["id"])
            .limit(1)
            .execute()
        )
        encrypted = sres.data[0]["secret_ciphertext"] if sres.data else ""
        secret_data: dict[str, Any] = {}
        if encrypted:
            try:
                plain = self._encryptor.decrypt(encrypted)
                loaded = json.loads(plain)
                if isinstance(loaded, dict):
                    secret_data = loaded
            except Exception as exc:
                logger.warning("failed_to_decrypt_vendor_secret", error=str(exc))
        logger.info(
            "soc_auth_db_lookup_supabase_hit",
            provider_code=provider_code,
            has_credentials=bool(secret_data),
            credential_fields=sorted(secret_data.keys()),
            auth_status=row["auth_status"],
        )
        return {
            "connection_id": row["id"],
            "provider_code": row["provider_code"],
            "auth_type": row["auth_type"],
            "auth_status": row["auth_status"],
            "metadata": row.get("metadata") or {},
            "display_name": row.get("display_name", provider_code),
            "credentials": secret_data,
        }

    async def get_active_connection(
        self,
        *,
        user_id: str | None,
        provider_code: str,
    ) -> dict[str, Any] | None:
        """Read one active user-provider connection from DB."""
        uid = self._norm(user_id)
        if not uid:
            logger.info(
                "soc_auth_db_lookup_skipped",
                provider_code=provider_code,
                reason="empty_user_id",
            )
            return None
        if self._settings.database_mode == "local":
            logger.info("soc_auth_db_lookup_start", provider_code=provider_code, database_mode="local")
            out = await self._get_connection_local(user_id=uid, provider_code=provider_code)
            logger.info(
                "soc_auth_db_lookup_done",
                provider_code=provider_code,
                database_mode="local",
                found=bool(out),
            )
            return out
        if self._settings.database_mode == "supabase":
            logger.info("soc_auth_db_lookup_start", provider_code=provider_code, database_mode="supabase")
            out = await self._get_connection_supabase(user_id=uid, provider_code=provider_code)
            logger.info(
                "soc_auth_db_lookup_done",
                provider_code=provider_code,
                database_mode="supabase",
                found=bool(out),
            )
            return out
        logger.info(
            "soc_auth_db_lookup_skipped",
            provider_code=provider_code,
            reason="unsupported_database_mode",
            database_mode=self._settings.database_mode,
        )
        return None

    async def _save_local(
        self,
        *,
        user_id: str,
        provider_code: str,
        auth_type: str,
        display_name: str,
        metadata: dict[str, Any],
        plaintext_dict: dict[str, Any],
    ) -> None:
        ciphertext = self._encryptor.encrypt(json.dumps(plaintext_dict, ensure_ascii=False))
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    _SQL_PG_UPSERT_USER_VENDOR_CONNECTION,
                    user_id,
                    provider_code,
                    display_name,
                    auth_type,
                    json.dumps(metadata or {}),
                )
                cid = str(row["id"])
                await conn.execute(
                    _SQL_PG_UPSERT_USER_VENDOR_SECRET,
                    cid,
                    ciphertext,
                )
                logger.info(
                    "soc_auth_db_save_sql",
                    dialect="postgresql",
                    provider_code=provider_code,
                    user_id=user_id,
                    connection_id=cid,
                    statements=[
                        {
                            "name": "upsert_user_vendor_connections",
                            "sql": _SQL_PG_UPSERT_USER_VENDOR_CONNECTION,
                            "param_count": 5,
                        },
                        {
                            "name": "upsert_user_vendor_connection_secrets",
                            "sql": _SQL_PG_UPSERT_USER_VENDOR_SECRET,
                            "param_count": 2,
                        },
                    ],
                )

    async def _save_supabase(
        self,
        *,
        user_id: str,
        provider_code: str,
        auth_type: str,
        display_name: str,
        metadata: dict[str, Any],
        plaintext_dict: dict[str, Any],
    ) -> None:
        ciphertext = self._encryptor.encrypt(json.dumps(plaintext_dict, ensure_ascii=False))
        client = get_supabase_client()
        conn = (
            client.table("user_vendor_connections")
            .upsert(
                {
                    "user_id": user_id,
                    "provider_code": provider_code,
                    "display_name": display_name,
                    "auth_type": auth_type,
                    "auth_status": "active",
                    "metadata": metadata or {},
                },
                on_conflict="user_id,provider_code,display_name",
            )
            .execute()
        )
        row = conn.data[0] if conn.data else None
        if not row:
            return
        client.table("user_vendor_connection_secrets").upsert(
            {
                "connection_id": row["id"],
                "secret_ciphertext": ciphertext,
                "secret_version": 1,
                "encryption_meta": {},
            },
            on_conflict="connection_id",
        ).execute()
        logger.info(
            "soc_auth_db_save_sql",
            dialect="supabase_postgrest",
            provider_code=provider_code,
            user_id=user_id,
            connection_id=row["id"],
            operations=[
                {
                    "table": "user_vendor_connections",
                    "verb": "upsert",
                    "on_conflict": "user_id,provider_code,display_name",
                },
                {
                    "table": "user_vendor_connection_secrets",
                    "verb": "upsert",
                    "on_conflict": "connection_id",
                },
            ],
        )

    async def save_connection_secret(
        self,
        *,
        user_id: str | None,
        provider_code: str,
        auth_type: str,
        display_name: str,
        metadata: dict[str, Any] | None,
        plaintext_dict: dict[str, Any],
    ) -> None:
        """Persist user credentials in DB."""
        uid = self._norm(user_id)
        if not uid:
            logger.info(
                "soc_auth_db_save_skipped",
                provider_code=provider_code,
                reason="empty_user_id",
            )
            return
        logger.info(
            "soc_auth_db_save_start",
            provider_code=provider_code,
            database_mode=self._settings.database_mode,
            display_name=display_name,
            credential_fields=sorted((plaintext_dict or {}).keys()),
        )
        if self._settings.database_mode == "local":
            await self._save_local(
                user_id=uid,
                provider_code=provider_code,
                auth_type=auth_type,
                display_name=display_name,
                metadata=metadata or {},
                plaintext_dict=plaintext_dict,
            )
            logger.info(
                "soc_auth_db_saved",
                provider_code=provider_code,
                database_mode="local",
                display_name=display_name,
                credential_fields=sorted((plaintext_dict or {}).keys()),
            )
            return
        if self._settings.database_mode == "supabase":
            await self._save_supabase(
                user_id=uid,
                provider_code=provider_code,
                auth_type=auth_type,
                display_name=display_name,
                metadata=metadata or {},
                plaintext_dict=plaintext_dict,
            )
            logger.info(
                "soc_auth_db_saved",
                provider_code=provider_code,
                database_mode="supabase",
                display_name=display_name,
                credential_fields=sorted((plaintext_dict or {}).keys()),
            )
            return
        logger.warning(
            "soc_auth_db_save_skipped",
            provider_code=provider_code,
            reason="unsupported_database_mode",
            database_mode=self._settings.database_mode,
        )

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on"}

    async def resolve_or_request_credentials(
        self,
        *,
        provider_code: str,
        session_id: str | None,
        request_id: str | None,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Resolve credentials with singleflight guard per provider/scope."""
        key = self._singleflight_key(
            provider_code=provider_code,
            session_id=session_id,
            request_id=request_id,
            user_id=user_id,
        )
        owner = False
        async with self._inflight_lock:
            fut = self._inflight_resolves.get(key)
            if fut is None:
                fut = asyncio.get_running_loop().create_future()
                self._inflight_resolves[key] = fut
                owner = True
                logger.info(
                    "soc_auth_singleflight_owner",
                    provider_code=key[0],
                    session_id=key[1],
                    request_id=key[2],
                    user_id=key[3],
                )
            else:
                logger.info(
                    "soc_auth_singleflight_wait",
                    provider_code=key[0],
                    session_id=key[1],
                    request_id=key[2],
                    user_id=key[3],
                )

        if owner:
            try:
                creds = await self._resolve_or_request_credentials_inner(
                    provider_code=provider_code,
                    session_id=session_id,
                    request_id=request_id,
                    user_id=user_id,
                )
                if not fut.done():
                    fut.set_result(creds)
                return creds
            except Exception as exc:
                if not fut.done():
                    fut.set_exception(exc)
                raise
            finally:
                async with self._inflight_lock:
                    self._inflight_resolves.pop(key, None)
        return await asyncio.shield(fut)

    async def _resolve_or_request_credentials_inner(
        self,
        *,
        provider_code: str,
        session_id: str | None,
        request_id: str | None,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Resolve credentials; interrupt user for missing auth when needed."""
        logger.info(
            "soc_auth_resolve_start",
            provider_code=provider_code,
            has_user_id=bool(self._norm(user_id)),
            has_session_id=bool(self._norm(session_id)),
            has_request_id=bool(self._norm(request_id)),
        )
        _ = get_provider(provider_code)  # validates provider existence
        logger.info("soc_auth_resolve_provider_validated", provider_code=provider_code)
        cached = await self.get_ephemeral(
            session_id=session_id,
            request_id=request_id,
            provider_code=provider_code,
        )
        if cached:
            logger.info("soc_auth_resolve_source", provider_code=provider_code, source="ephemeral_cache")
            logger.info(
                "soc_auth_resolve_credentials_summary",
                provider_code=provider_code,
                source="ephemeral_cache",
                credentials_summary=_credentials_log_summary(cached),
            )
            logger.info(
                "soc_auth_resolve_done",
                provider_code=provider_code,
                source="ephemeral_cache",
                credential_fields=sorted(cached.keys()),
            )
            return cached

        db_conn = await self.get_active_connection(
            user_id=user_id,
            provider_code=provider_code,
        )
        if db_conn and isinstance(db_conn.get("credentials"), dict) and db_conn["credentials"]:
            logger.info(
                "soc_auth_resolve_source",
                provider_code=provider_code,
                source="persistent_store",
                credential_fields=sorted(db_conn["credentials"].keys()),
            )
            creds = dict(db_conn["credentials"])
            logger.info(
                "soc_auth_resolve_credentials_summary",
                provider_code=provider_code,
                source="persistent_store",
                credentials_summary=_credentials_log_summary(creds),
            )
            logger.info(
                "soc_auth_resolve_done",
                provider_code=provider_code,
                source="persistent_store",
                credential_fields=sorted(creds.keys()),
            )
            return creds

        rid = self._norm(request_id) or str(uuid.uuid4())
        if not self._norm(request_id):
            logger.info(
                "soc_auth_request_id_fallback",
                provider_code=provider_code,
                generated_request_id=rid,
            )
        payload = {
            "interruptKind": "user_input_v1",
            "requestId": rid,
            "kind": "form",
            "prompt": f"Please provide {provider_code} authorization details",
            "fields": build_hitl_fields(provider_code),
        }
        logger.info("soc_auth_hitl_interrupt_emit", provider_code=provider_code, request_id=rid)
        response = interrupt(payload)
        answer = response if isinstance(response, dict) else {}
        logger.info(
            "soc_auth_hitl_interrupt_received",
            provider_code=provider_code,
            request_id=rid,
            response_type=type(response).__name__,
            has_answer_dict=isinstance(response, dict),
        )
        credentials = answer.get("credentials", answer)
        if not isinstance(credentials, dict):
            credentials = {}
        # Resume payloads may place remember_auth at top-level or inside credentials (UI form).
        remember_raw = answer.get("remember_auth")
        if remember_raw is None or remember_raw == "":
            remember_raw = credentials.get("remember_auth")
        remember_auth = self._to_bool(remember_raw)
        credentials.pop("remember_auth", None)
        logger.info(
            "soc_auth_hitl_interrupt_resume",
            provider_code=provider_code,
            request_id=rid,
            remember_auth=remember_auth,
            credential_fields=sorted(credentials.keys()),
        )
        logger.info(
            "soc_auth_hitl_credentials_summary",
            provider_code=provider_code,
            request_id=rid,
            remember_auth=remember_auth,
            credentials_summary=_credentials_log_summary(credentials),
        )
        if remember_auth and self._norm(user_id):
            await self.save_connection_secret(
                user_id=user_id,
                provider_code=provider_code,
                auth_type="basic",
                display_name=provider_code,
                metadata={"source": "hitl_form"},
                plaintext_dict=credentials,
            )
            logger.info(
                "soc_auth_resolve_done",
                provider_code=provider_code,
                source="hitl_persistent_store",
                credential_fields=sorted(credentials.keys()),
            )
        else:
            if remember_auth and not self._norm(user_id):
                logger.info(
                    "soc_auth_remember_skipped_no_user_id",
                    provider_code=provider_code,
                    request_id=rid,
                )
            await self.set_ephemeral(
                session_id=session_id,
                request_id=request_id,
                provider_code=provider_code,
                credentials=credentials,
            )
            logger.info("soc_auth_resolve_source", provider_code=provider_code, source="hitl_ephemeral")
            logger.info(
                "soc_auth_resolve_done",
                provider_code=provider_code,
                source="hitl_ephemeral",
                credential_fields=sorted(credentials.keys()),
            )
        return credentials


_vendor_auth_service: VendorAuthService | None = None


def get_vendor_auth_service() -> VendorAuthService:
    """Singleton accessor."""
    global _vendor_auth_service
    if _vendor_auth_service is None:
        _vendor_auth_service = VendorAuthService()
    return _vendor_auth_service
