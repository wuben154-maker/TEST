"""Database connection module supporting both local PostgreSQL and Supabase."""

from typing import Optional

import structlog
from app.config import get_settings

logger = structlog.get_logger()

# Optional imports - only needed when using database features
_supabase_client = None
_supabase_auth_client = None
_pg_pool = None


def _service_role_matches_project() -> bool:
    """Check if service_role key belongs to the same project as SUPABASE_URL."""
    settings = get_settings()
    if not settings.supabase_service_role_key or not settings.supabase_url:
        return False
    try:
        import jwt
        payload = jwt.decode(
            settings.supabase_service_role_key,
            options={"verify_signature": False},
        )
        key_ref = payload.get("ref", "")
        url_ref = settings.supabase_url.replace("https://", "").split(".supabase.co")[0]
        return key_ref == url_ref
    except Exception:
        return False


def get_supabase_auth_client():
    """Supabase client for Auth (sign_in, sign_up). Always uses anon key.

    Auth API requires key from same project as URL. Use anon key to avoid
    service_role key project mismatch (e.g. key from project B, URL from project A).
    """
    global _supabase_auth_client
    settings = get_settings()
    if settings.database_mode != "supabase":
        raise ValueError("Supabase client requested but database_mode is not 'supabase'")
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ValueError("Supabase URL and anon key required for auth")
    if _supabase_auth_client is None:
        from supabase import create_client
        _supabase_auth_client = create_client(
            settings.supabase_url, settings.supabase_anon_key
        )
        logger.info("Supabase auth client initialized (anon key)")
    return _supabase_auth_client


def get_supabase_client():
    """Get Supabase client for cloud database mode.

    Prefers service_role_key when available - it bypasses RLS, required for
    backend ops (projects, messages) since we use our own JWT auth rather than
    Supabase session. Without service_role, anon key requests fail RLS.
    """
    global _supabase_client

    settings = get_settings()

    if settings.database_mode != "supabase":
        raise ValueError("Supabase client requested but database_mode is not 'supabase'")

    if not settings.supabase_url:
        raise ValueError("Supabase URL is required for supabase mode")

    # Use service_role only if it matches this project; else anon (RLS will block)
    if _service_role_matches_project() and settings.supabase_service_role_key:
        key = settings.supabase_service_role_key
    else:
        key = settings.supabase_anon_key
    if not key:
        raise ValueError("Supabase anon key or service_role key is required")

    if _supabase_client is None:
        try:
            from supabase import create_client
            _supabase_client = create_client(settings.supabase_url, key)
            using_sr = _service_role_matches_project() and bool(settings.supabase_service_role_key)
            logger.info(
                "Supabase client initialized",
                url=settings.supabase_url,
                using_service_role=using_sr,
            )
            if not using_sr and settings.supabase_service_role_key:
                url_ref = settings.supabase_url.replace("https://", "").split(".supabase.co")[0]
                try:
                    import jwt
                    sr_ref = jwt.decode(
                        settings.supabase_service_role_key,
                        options={"verify_signature": False},
                    ).get("ref", "?")
                except Exception:
                    sr_ref = "?"
                logger.warning(
                    "SUPABASE_SERVICE_ROLE_KEY project mismatch! URL project=%s, service_role project=%s. "
                    "Get service_role from Supabase Dashboard for project %s (Settings > API).",
                    url_ref, sr_ref, url_ref,
                )
        except ImportError:
            raise ImportError("supabase package not installed. Run: pip install supabase")

    return _supabase_client


async def get_pg_pool():
    """Get PostgreSQL connection pool for local database mode."""
    global _pg_pool
    
    settings = get_settings()
    
    if settings.database_mode != "local":
        raise ValueError("PostgreSQL pool requested but database_mode is not 'local'")
    
    if _pg_pool is None:
        try:
            import asyncpg
            _pg_pool = await asyncpg.create_pool(
                host=settings.local_db_host,
                port=settings.local_db_port,
                database=settings.local_db_name,
                user=settings.local_db_user,
                password=settings.local_db_password,
                min_size=settings.local_db_pool_min_size,
                max_size=settings.local_db_pool_max_size,
            )
            logger.info(
                "PostgreSQL pool initialized",
                host=settings.local_db_host,
                database=settings.local_db_name,
            )
        except ImportError:
            raise ImportError("asyncpg package not installed. Run: pip install asyncpg")
    
    return _pg_pool


async def close_db_connections():
    """Close all database connections."""
    global _pg_pool, _supabase_client, _supabase_auth_client

    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("PostgreSQL pool closed")

    _supabase_client = None
    _supabase_auth_client = None


class DatabaseManager:
    """Unified database manager that works with both local and Supabase."""
    
    def __init__(self):
        self.settings = get_settings()
    
    @property
    def is_local(self) -> bool:
        return self.settings.database_mode == "local"
    
    @property
    def is_supabase(self) -> bool:
        return self.settings.database_mode == "supabase"
    
    async def execute_query(self, query: str, *args) -> list:
        """Execute a query and return results."""
        if self.is_local:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        else:
            client = get_supabase_client()
            # Supabase uses different query patterns
            # This is a simplified example - real implementation would differ
            raise NotImplementedError("Supabase raw query not implemented - use table methods")
    
    async def insert_message(self, project_id: str, user_id: str, content: str, 
                            msg_type: str, blocks: Optional[dict] = None) -> dict:
        """Insert a message into the messages table."""
        if self.is_local:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    INSERT INTO messages (project_id, user_id, content, type, blocks)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, created_at
                    """,
                    project_id, user_id, content, msg_type, blocks
                )
                return {"id": str(result["id"]), "created_at": result["created_at"]}
        else:
            client = get_supabase_client()
            result = client.table("messages").insert({
                "project_id": project_id,
                "user_id": user_id,
                "content": content,
                "type": msg_type,
                "blocks": blocks,
            }).execute()
            return result.data[0] if result.data else None
    
    async def get_messages(self, project_id: str, limit: int = 50) -> list:
        """Get messages for a project."""
        if self.is_local:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, content, type, blocks, created_at
                    FROM messages
                    WHERE project_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    project_id, limit
                )
                return [dict(row) for row in rows]
        else:
            client = get_supabase_client()
            result = client.table("messages").select("*").eq(
                "project_id", project_id
            ).order("created_at", desc=True).limit(limit).execute()
            return result.data
    
    async def health_check(self) -> dict:
        """Check database connectivity."""
        try:
            if self.is_local:
                pool = await get_pg_pool()
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                return {"status": "healthy", "mode": "local"}
            else:
                client = get_supabase_client()
                # Simple check - just verify client exists
                return {"status": "healthy", "mode": "supabase"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Singleton instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get the database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
