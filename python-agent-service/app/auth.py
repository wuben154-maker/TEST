"""Local authentication module using JWT tokens."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import jwt
import structlog

from app.config import get_settings
from app.datetime_support import format_api_datetime

logger = structlog.get_logger()

# JWT settings
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7 days


def get_jwt_secret() -> str:
    """Get JWT secret key from settings or generate one."""
    settings = get_settings()
    # Use a combination of available keys or generate one
    secret = settings.openai_api_key or settings.google_api_key or "secmanus-local-dev-secret"
    return hashlib.sha256(secret.encode()).hexdigest()


def hash_password(password: str) -> str:
    """Hash password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{pwd_hash}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        salt, pwd_hash = hashed.split(":")
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == pwd_hash
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", error=str(e))
        return None


class LocalAuthManager:
    """Manages local user authentication."""

    def __init__(self, db_manager):
        self.db = db_manager

    async def register(self, email: str, password: str, username: Optional[str] = None) -> dict:
        """Register a new user."""
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            # Check if email exists
            existing = await conn.fetchrow(
                "SELECT id FROM profiles WHERE email = $1", email
            )
            if existing:
                raise ValueError("Email already registered")

            # Create user
            user_id = str(uuid4())
            pwd_hash = hash_password(password)

            await conn.execute(
                """
                INSERT INTO profiles (id, user_id, email, password_hash, username)
                VALUES ($1, $1, $2, $3, $4)
                """,
                user_id, email, pwd_hash, username or email.split("@")[0]
            )

            # Create default project for user
            project_id = str(uuid4())
            await conn.execute(
                """
                INSERT INTO projects (id, user_id, title)
                VALUES ($1, $2, $3)
                """,
                project_id, user_id, "新对话"
            )

        # Billing bootstrap uses its own pool.acquire(); run it after releasing the
        # registration connection so we never hold two pool connections at once
        # (avoids starvation under concurrent /analyze DB traffic).
        from app.billing.bootstrap import ensure_default_billing_for_user

        await ensure_default_billing_for_user(user_id)

        token = create_access_token(user_id, email)
        return {
            "user": {
                "id": user_id,
                "email": email,
                "username": username or email.split("@")[0],
            },
            "access_token": token,
            "token_type": "bearer",
        }

    async def login(self, email: str, password: str) -> dict:
        """Authenticate user and return token."""
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                """
                SELECT id, user_id, email, password_hash, username, avatar_url
                FROM profiles WHERE email = $1
                """,
                email
            )

            if not user:
                raise ValueError("Invalid email or password")

            if not verify_password(password, user["password_hash"]):
                raise ValueError("Invalid email or password")

            token = create_access_token(str(user["user_id"]), email)
            return {
                "user": {
                    "id": str(user["user_id"]),
                    "email": user["email"],
                    "username": user["username"],
                    "avatar_url": user["avatar_url"],
                },
                "access_token": token,
                "token_type": "bearer",
            }

    async def get_user(self, user_id: str) -> Optional[dict]:
        """Get user by ID."""
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                """
                SELECT user_id, email, username, avatar_url, created_at
                FROM profiles WHERE user_id = $1
                """,
                user_id
            )

            if not user:
                return None

            return {
                "id": str(user["user_id"]),
                "email": user["email"],
                "username": user["username"],
                "avatar_url": user["avatar_url"],
                "created_at": format_api_datetime(user["created_at"])
                if user["created_at"]
                else None,
            }

    async def update_profile(self, user_id: str, username: Optional[str] = None, 
                            avatar_url: Optional[str] = None) -> dict:
        """Update user profile."""
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            updates = []
            values = []
            idx = 1

            if username:
                updates.append(f"username = ${idx}")
                values.append(username)
                idx += 1

            if avatar_url:
                updates.append(f"avatar_url = ${idx}")
                values.append(avatar_url)
                idx += 1

            if not updates:
                return await self.get_user(user_id)

            values.append(user_id)
            query = f"""
                UPDATE profiles SET {', '.join(updates)}, updated_at = now()
                WHERE user_id = ${idx}
                RETURNING user_id, email, username, avatar_url
            """

            result = await conn.fetchrow(query, *values)
            return {
                "id": str(result["user_id"]),
                "email": result["email"],
                "username": result["username"],
                "avatar_url": result["avatar_url"],
            }
