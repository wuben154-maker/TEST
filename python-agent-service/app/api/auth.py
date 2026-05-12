"""Authentication API routes."""

import asyncio
from typing import Any, Optional

import structlog
from app.auth import LocalAuthManager, create_access_token, decode_token
from app.config import get_settings
from app.db import get_db_manager, get_supabase_auth_client, get_supabase_client
from app.services.user_login_events import list_recent_logins_async, record_login_event_async
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user: dict
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[str] = None


class ProfilePatchBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)


class LoginHistoryItem(BaseModel):
    id: str
    logged_in_at: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    ip_country: Optional[str] = None


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Dependency to get current authenticated user.

    For both local and Supabase modes, we validate our own JWT token.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid auth scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"id": payload["sub"], "email": payload["email"]}


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Dependency to optionally get current user (no error if not authenticated)."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user.

    - local mode: use LocalAuthManager with local PostgreSQL
    - supabase mode: create user via Supabase Auth, then issue our own JWT
    """
    settings = get_settings()

    # Local database-backed auth
    if settings.database_mode == "local":
        try:
            db = get_db_manager()
            auth = LocalAuthManager(db)
            result = await auth.register(request.email, request.password, request.username)
            return result
        except ValueError as e:
            # Keep message for frontend mapping
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Registration failed", error=str(e), exc_info=True)
            # Return actionable message for common failures
            err_msg = str(e).lower()
            if "connection" in err_msg or "connect" in err_msg or "refused" in err_msg:
                raise HTTPException(status_code=503, detail="Database unavailable. Check PostgreSQL is running.")
            if "does not exist" in err_msg or "relation" in err_msg:
                raise HTTPException(
                    status_code=503,
                    detail="Database not initialized. Run scripts/db/init_local_db.sql.",
                )
            raise HTTPException(status_code=500, detail="Registration failed")

    # Supabase-backed auth (use auth client with anon key - avoids project mismatch)
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_auth_client()
            resp = client.auth.sign_up(
                {
                    "email": request.email,
                    "password": request.password,
                    "options": {
                        "email_redirect_to": settings.supabase_url or "",
                        "data": {"username": request.username}
                        if request.username
                        else {},
                    },
                }
            )

            # supabase-py may expose user directly or under .data
            user = getattr(resp, "user", None) or getattr(getattr(resp, "data", None), "user", None)

            if not user:
                # Try to extract error message from response if available
                msg = "Supabase registration failed"
                raise HTTPException(status_code=400, detail=msg)

            user_id = getattr(user, "id", None) or user.get("id")
            email = getattr(user, "email", None) or user.get("email")
            if not user_id or not email:
                raise HTTPException(status_code=400, detail="Supabase registration returned invalid user")

            access_token = create_access_token(str(user_id), email)

            from app.billing.bootstrap import ensure_default_billing_for_user

            try:
                await ensure_default_billing_for_user(str(user_id))
            except Exception as boot_e:
                logger.warning(
                    "billing_bootstrap_after_supabase_signup_failed",
                    user_id=str(user_id),
                    error=str(boot_e),
                )

            return {
                "user": {
                    "id": str(user_id),
                    "email": email,
                    "username": request.username or email.split("@")[0],
                    "avatar_url": None,
                },
                "access_token": access_token,
                "token_type": "bearer",
            }
        except HTTPException:
            raise
        except Exception as e:
            # Map common Supabase error messages to frontend-friendly ones
            msg = str(e)
            logger.error("Supabase registration failed", error=msg)

            # Heuristic mapping based on Supabase error text
            if "User already registered" in msg or "already registered" in msg:
                raise HTTPException(status_code=400, detail="Email already registered")
            if "Invalid login credentials" in msg or "Password should be at least 6 characters" in msg:
                raise HTTPException(status_code=400, detail="Invalid email or password format")
            # SSL/connection errors - often network, firewall, or Supabase project paused
            if "SSL" in msg or "UNEXPECTED_EOF" in msg or "EOF" in msg or "connection" in msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="无法连接 Supabase。请检查：1) Supabase 项目是否已暂停（Dashboard 恢复）2) 网络/代理设置 3) 防火墙是否拦截",
                )

            raise HTTPException(status_code=500, detail=f"Registration failed: {msg}")

    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for registration")


def _client_ip(http_request: Request) -> Optional[str]:
    settings = get_settings()
    if settings.trust_x_forwarded_for:
        xff = http_request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
    if http_request.client is None:
        return None
    host = http_request.client.host
    return str(host) if host else None


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
):
    """Authenticate user and return token.

    - local mode: use LocalAuthManager with local PostgreSQL
    - supabase mode: authenticate via Supabase Auth, then issue our own JWT
    """
    settings = get_settings()
    ua = http_request.headers.get("user-agent")
    ip = _client_ip(http_request)

    # Local database-backed auth
    if settings.database_mode == "local":
        try:
            db = get_db_manager()
            auth = LocalAuthManager(db)
            result = await auth.login(request.email, request.password)
            # Defer audit insert until after response — frees pool sooner under /analyze load.
            background_tasks.add_task(
                record_login_event_async, result["user"]["id"], ip, ua
            )
            return result
        except ValueError as e:
            # Preserve message for frontend mapping
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            logger.error("Login failed", error=str(e))
            raise HTTPException(status_code=500, detail="Authentication failed")

    # Supabase-backed auth (use auth client with anon key - avoids project mismatch)
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_auth_client()
            resp = client.auth.sign_in_with_password(
                {
                    "email": request.email,
                    "password": request.password,
                }
            )

            user = getattr(resp, "user", None) or getattr(getattr(resp, "data", None), "user", None)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid email or password")

            user_id = getattr(user, "id", None) or user.get("id")
            email = getattr(user, "email", None) or user.get("email")
            if not user_id or not email:
                raise HTTPException(status_code=401, detail="Invalid email or password")

            access_token = create_access_token(str(user_id), email)

            # Try to extract username from user_metadata if present
            username = None
            meta = getattr(user, "user_metadata", None) or user.get("user_metadata") if isinstance(user, dict) else None
            if isinstance(meta, dict):
                username = meta.get("username")

            payload = {
                "user": {
                    "id": str(user_id),
                    "email": email,
                    "username": username,
                    "avatar_url": None,
                },
                "access_token": access_token,
                "token_type": "bearer",
            }
            background_tasks.add_task(
                record_login_event_async, str(user_id), ip, ua
            )
            return payload
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e)
            logger.error("Supabase login failed", error=msg)

            if "Invalid login credentials" in msg or "Invalid email or password" in msg:
                raise HTTPException(status_code=401, detail="Invalid email or password")
            if "SSL" in msg or "UNEXPECTED_EOF" in msg or "EOF" in msg or "connection" in msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="无法连接 Supabase。请检查：1) Supabase 项目是否已暂停 2) 网络/代理 3) 防火墙",
                )

            raise HTTPException(status_code=500, detail="Authentication failed")

    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for login")


def _supabase_profile_from_admin(user_id: str, fallback_email: str) -> dict[str, Any]:
    """Load display name from Auth user_metadata (service_role client)."""
    try:
        client = get_supabase_client()
        u = client.auth.admin.get_user_by_id(user_id)
        mu = getattr(u, "user", None)
        meta: dict[str, Any] = {}
        if mu is not None:
            raw = getattr(mu, "user_metadata", None)
            if isinstance(raw, dict):
                meta = raw
        email = getattr(mu, "email", None) or fallback_email
        return {
            "id": user_id,
            "email": email,
            "username": meta.get("username"),
            "avatar_url": meta.get("avatar_url"),
        }
    except Exception as e:
        logger.warning("supabase_admin_get_user_failed", user_id=user_id, error=str(e))
        return {
            "id": user_id,
            "email": fallback_email,
            "username": None,
            "avatar_url": None,
        }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile.

    - local mode: load from local profiles table
    - supabase mode: load user_metadata via admin API when service_role is configured
    """
    settings = get_settings()

    if settings.database_mode == "local":
        db = get_db_manager()
        auth = LocalAuthManager(db)
        user = await auth.get_user(current_user["id"])

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    prof = await asyncio.to_thread(
        _supabase_profile_from_admin,
        current_user["id"],
        current_user["email"],
    )
    return prof


@router.patch("/profile", response_model=UserResponse)
async def patch_profile(
    body: ProfilePatchBody,
    current_user: dict = Depends(get_current_user),
):
    """Update display name (stored as username / user_metadata.username)."""
    settings = get_settings()
    name = body.username.strip()
    if not name:
        raise HTTPException(status_code=400, detail="username must not be empty")

    if settings.database_mode == "local":
        db = get_db_manager()
        auth = LocalAuthManager(db)
        return await auth.update_profile(current_user["id"], username=name)

    def _patch_supabase() -> dict[str, Any]:
        client = get_supabase_client()
        uid = current_user["id"]
        existing = client.auth.admin.get_user_by_id(uid)
        mu = getattr(existing, "user", None)
        meta: dict[str, Any] = {}
        if mu is not None:
            raw = getattr(mu, "user_metadata", None)
            if isinstance(raw, dict):
                meta = dict(raw)
        meta["username"] = name
        client.auth.admin.update_user_by_id(uid, {"user_metadata": meta})
        return _supabase_profile_from_admin(uid, current_user["email"])

    return await asyncio.to_thread(_patch_supabase)


@router.get("/login-history", response_model=list[LoginHistoryItem])
async def login_history(
    current_user: dict = Depends(get_current_user),
    limit: int = 10,
):
    """Recent successful logins (newest first)."""
    cap = max(1, min(limit, 50))
    rows = await list_recent_logins_async(current_user["id"], cap)
    return rows


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout user (client should discard token)."""
    # JWT tokens are stateless, so logout is handled client-side
    return {"message": "Logged out successfully"}
