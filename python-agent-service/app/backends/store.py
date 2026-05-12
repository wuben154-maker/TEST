"""Store Backend - Persistent storage using LangGraph Store or database.

This implements the "Long-term Context (Hard Drive)" strategy from DeepAgents.
Supports Redis and PostgreSQL as persistent backends.

Key features:
- Cross-session persistence via LangGraph Store
- Namespace-based organization
- TTL support for automatic expiration
- Encrypted storage for sensitive data (parameters) using AES-256-GCM
"""

import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Generic, TypeVar
from uuid import uuid4

import structlog
from app.datetime_support import format_api_datetime, now_app
from app._vendor.deepagents.backends.protocol import (BackendProtocol,
                                                      EditResult,
                                                      FileDownloadResponse,
                                                      FileInfo,
                                                      FileUploadResponse,
                                                      GrepMatch, WriteResult)
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = structlog.get_logger()

T = TypeVar("T")


# ============================================
# Data Models
# ============================================

@dataclass
class StoreItem:
    """A single item in the store."""
    
    key: str
    value: Any
    namespace: str = "default"
    created_at: datetime = field(default_factory=now_app)
    updated_at: datetime = field(default_factory=now_app)
    expires_at: datetime | None = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if item has expired."""
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now > exp.astimezone(timezone.utc)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "value": self.value,
            "namespace": self.namespace,
            "created_at": format_api_datetime(self.created_at),
            "updated_at": format_api_datetime(self.updated_at),
            "expires_at": format_api_datetime(self.expires_at)
            if self.expires_at
            else None,
            "metadata": self.metadata,
        }


# ============================================
# Encryption Utilities
# ============================================

class EncryptionManager:
    """AES-256-GCM encryption manager for sensitive data."""
    
    def __init__(self, encryption_key: str | None = None):
        """Initialize encryption manager.
        
        Args:
            encryption_key: Base64-encoded 32-byte key, or None to derive from env var
        """
        if encryption_key:
            # Use provided key (base64 encoded)
            try:
                self._key = base64.b64decode(encryption_key)
            except Exception:
                raise ValueError("Invalid encryption key format (must be base64)")
        else:
            # Derive key from environment variable
            key_material = os.environ.get("STORE_ENCRYPTION_KEY", "")
            if not key_material:
                # Generate a default key for development (NOT for production!)
                logger.warning("No encryption key provided, using default (NOT SECURE for production)")
                key_material = "default-encryption-key-change-in-production"
            
            # Derive 32-byte key using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"store-encryption-salt-v1",  # In production, use random salt per key
                iterations=480000,
            )
            self._key = kdf.derive(key_material.encode())
        
        if len(self._key) != 32:
            raise ValueError("Encryption key must be 32 bytes")
        
        self._aesgcm = AESGCM(self._key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using AES-256-GCM.
        
        Returns base64-encoded ciphertext with nonce prepended.
        Format: base64(nonce + ciphertext + tag)
        """
        import secrets

        # Generate 12-byte nonce (recommended for GCM)
        nonce = secrets.token_bytes(12)
        
        # Encrypt
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = self._aesgcm.encrypt(nonce, plaintext_bytes, None)
        
        # Combine nonce + ciphertext and encode
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('utf-8')
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext using AES-256-GCM.
        
        Args:
            ciphertext: Base64-encoded string containing nonce + ciphertext + tag
        
        Returns:
            Decrypted plaintext string
        """
        try:
            encrypted_data = base64.b64decode(ciphertext.encode('utf-8'))
            
            # Extract nonce (first 12 bytes) and ciphertext
            nonce = encrypted_data[:12]
            ciphertext_bytes = encrypted_data[12:]
            
            # Decrypt
            plaintext_bytes = self._aesgcm.decrypt(nonce, ciphertext_bytes, None)
            return plaintext_bytes.decode('utf-8')
        except Exception as e:
            logger.error("Decryption failed", error=str(e))
            raise ValueError(f"Failed to decrypt: {str(e)}")


@dataclass
class StoreConfig:
    """Configuration for store backend."""
    
    # Connection settings
    connection_url: str | None = None
    
    # TTL defaults
    default_ttl_hours: int | None = None  # None = no expiration
    memory_ttl_hours: int = 24  # Short-term memory TTL
    
    # Encryption for sensitive data
    encryption_key: str | None = None
    encrypt_namespaces: list[str] = field(default_factory=lambda: ["parameters", "secrets"])
    
    # Cleanup settings
    cleanup_interval_minutes: int = 60
    max_items_per_namespace: int = 10000
    
    def _should_encrypt(self, namespace: str) -> bool:
        """Check if namespace should be encrypted."""
        # Check if namespace starts with any encrypt_namespaces prefix
        for encrypt_ns in self.encrypt_namespaces:
            if namespace.startswith(encrypt_ns) or namespace.startswith(f"{encrypt_ns}/"):
                return True
        return False


# ============================================
# Abstract Store Interface
# ============================================

class BaseStore(ABC):
    """Abstract base class for persistent stores."""
    
    @abstractmethod
    async def get(self, key: str, namespace: str = "default") -> StoreItem | None:
        """Get an item by key."""
        ...
    
    @abstractmethod
    async def set(
        self, 
        key: str, 
        value: Any, 
        namespace: str = "default",
        ttl_hours: int | None = None,
        metadata: dict | None = None,
    ) -> StoreItem:
        """Set an item."""
        ...
    
    @abstractmethod
    async def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete an item."""
        ...
    
    @abstractmethod
    async def list_keys(self, namespace: str = "default", prefix: str = "") -> list[str]:
        """List keys in a namespace."""
        ...
    
    @abstractmethod
    async def search(self, pattern: str, namespace: str = "default") -> list[StoreItem]:
        """Search items by pattern."""
        ...
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired items, return count removed."""
        ...


# ============================================
# Context Store Adapter
# ============================================

class ContextStoreAdapter(BaseStore):
    """Adapter that maps ContextRetriever namespace format to path-based store.

    ContextRetriever uses namespace like "memories/session_id" and key "param1".
    DatabaseBackend's store uses namespace "memories" and key "/session_id/param1".
    This adapter translates between the two formats.
    Supports both memories and parameters base namespaces.
    """

    def __init__(self, store: BaseStore, base_namespaces: list[str] | None = None):
        self._store = store
        self._base_namespaces = base_namespaces or ["memories", "parameters"]

    def _parse_namespace(self, namespace: str) -> tuple[str, str] | None:
        """Parse namespace to (base_namespace, suffix). Returns None if not in our format."""
        for base in self._base_namespaces:
            if namespace.startswith(f"{base}/"):
                suffix = namespace[len(base) + 1:]
                return base, suffix
        return None

    def _map_namespace_key(self, namespace: str, key: str) -> tuple[str, str]:
        """Map ContextRetriever (namespace, key) to store (namespace, key)."""
        parsed = self._parse_namespace(namespace)
        if not parsed:
            return namespace, key
        base, suffix = parsed
        store_key = f"/{suffix}/{key}" if key else f"/{suffix}/"
        return base, store_key

    def _map_namespace_prefix(self, namespace: str) -> tuple[str, str]:
        """Map namespace to (store_namespace, key_prefix)."""
        parsed = self._parse_namespace(namespace)
        if not parsed:
            return namespace, ""
        base, suffix = parsed
        return base, f"/{suffix}/"

    def _strip_prefix(self, key: str, prefix: str) -> str:
        if key.startswith(prefix):
            return key[len(prefix):]
        return key

    async def get(self, key: str, namespace: str = "default") -> StoreItem | None:
        store_ns, store_key = self._map_namespace_key(namespace, key)
        item = await self._store.get(store_key, store_ns)
        if item:
            item = StoreItem(key=key, value=item.value, namespace=namespace,
                            created_at=item.created_at, updated_at=item.updated_at,
                            expires_at=item.expires_at, metadata=item.metadata)
        return item

    async def set(
        self,
        key: str,
        value: Any,
        namespace: str = "default",
        ttl_hours: int | None = None,
        metadata: dict | None = None,
    ) -> StoreItem:
        store_ns, store_key = self._map_namespace_key(namespace, key)
        item = await self._store.set(store_key, value, store_ns, ttl_hours, metadata)
        return StoreItem(key=key, value=item.value, namespace=namespace,
                        created_at=item.created_at, updated_at=item.updated_at,
                        expires_at=item.expires_at, metadata=item.metadata)

    async def delete(self, key: str, namespace: str = "default") -> bool:
        store_ns, store_key = self._map_namespace_key(namespace, key)
        return await self._store.delete(store_key, store_ns)

    async def list_keys(self, namespace: str = "default", prefix: str = "") -> list[str]:
        store_ns, key_prefix = self._map_namespace_prefix(namespace)
        keys = await self._store.list_keys(store_ns, key_prefix)
        stripped = [self._strip_prefix(k, key_prefix) for k in keys]
        return [k for k in stripped if k.startswith(prefix)]

    async def search(self, pattern: str, namespace: str = "default") -> list[StoreItem]:
        store_ns, key_prefix = self._map_namespace_prefix(namespace)
        items = await self._store.search(pattern, store_ns)
        results = []
        for item in items:
            if item.key.startswith(key_prefix):
                rel_key = self._strip_prefix(item.key, key_prefix)
                results.append(StoreItem(key=rel_key, value=item.value, namespace=namespace,
                                        created_at=item.created_at, updated_at=item.updated_at,
                                        expires_at=item.expires_at, metadata=item.metadata))
        return results

    async def cleanup_expired(self) -> int:
        return await self._store.cleanup_expired()


# ============================================
# In-Memory Store (for testing/development)
# ============================================

class InMemoryStore(BaseStore):
    """In-memory store implementation (non-persistent)."""
    
    def __init__(self, config: StoreConfig | None = None):
        self.config = config or StoreConfig()
        self._data: dict[str, dict[str, StoreItem]] = {}
        self._encryption_manager: EncryptionManager | None = None
        
        # Initialize encryption manager if encryption is configured
        if self.config.encryption_key or os.environ.get("STORE_ENCRYPTION_KEY"):
            try:
                self._encryption_manager = EncryptionManager(self.config.encryption_key)
            except Exception as e:
                logger.warning("Failed to initialize encryption manager", error=str(e))
                self._encryption_manager = None
    
    def _get_namespace(self, namespace: str) -> dict[str, StoreItem]:
        """Get or create namespace."""
        if namespace not in self._data:
            self._data[namespace] = {}
        return self._data[namespace]
    
    async def get(self, key: str, namespace: str = "default") -> StoreItem | None:
        ns = self._get_namespace(namespace)
        item = ns.get(key)
        
        if item and item.is_expired:
            del ns[key]
            return None
        
        if item and self._encryption_manager and self.config._should_encrypt(namespace):
            # Decrypt value if namespace requires encryption
            try:
                import json
                if isinstance(item.value, str):
                    decrypted_value = self._encryption_manager.decrypt(item.value)
                    # Try to parse as JSON if it was originally a non-string value
                    try:
                        decrypted_value = json.loads(decrypted_value)
                    except json.JSONDecodeError:
                        pass  # Keep as string
                    # Return item with decrypted value
                    return StoreItem(
                        key=item.key,
                        value=decrypted_value,
                        namespace=item.namespace,
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                        expires_at=item.expires_at,
                        metadata=item.metadata,
                    )
            except Exception as e:
                logger.error("Failed to decrypt value", key=key, namespace=namespace, error=str(e))
                return None
        
        return item
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        namespace: str = "default",
        ttl_hours: int | None = None,
        metadata: dict | None = None,
    ) -> StoreItem:
        ns = self._get_namespace(namespace)
        
        expires_at = None
        if ttl_hours is not None:
            expires_at = now_app() + timedelta(hours=ttl_hours)
        elif self.config.default_ttl_hours:
            expires_at = now_app() + timedelta(hours=self.config.default_ttl_hours)
        
        # Encrypt value if namespace requires encryption
        stored_value = value
        if self._encryption_manager and self.config._should_encrypt(namespace):
            if isinstance(value, str):
                try:
                    stored_value = self._encryption_manager.encrypt(value)
                except Exception as e:
                    logger.error("Failed to encrypt value", key=key, namespace=namespace, error=str(e))
                    raise ValueError(f"Encryption failed: {str(e)}")
            else:
                # For non-string values, convert to JSON string first
                import json
                json_str = json.dumps(value, ensure_ascii=False)
                stored_value = self._encryption_manager.encrypt(json_str)
        
        item = StoreItem(
            key=key,
            value=stored_value,
            namespace=namespace,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        
        ns[key] = item
        return item
    
    async def delete(self, key: str, namespace: str = "default") -> bool:
        ns = self._get_namespace(namespace)
        if key in ns:
            del ns[key]
            return True
        return False
    
    async def list_keys(self, namespace: str = "default", prefix: str = "") -> list[str]:
        ns = self._get_namespace(namespace)
        keys = [k for k in ns.keys() if k.startswith(prefix)]
        return sorted(keys)
    
    async def search(self, pattern: str, namespace: str = "default") -> list[StoreItem]:
        import re
        ns = self._get_namespace(namespace)
        try:
            regex = re.compile(pattern)
        except re.error:
            # Fallback to literal search when pattern has invalid regex (e.g. from user input)
            regex = re.compile(re.escape(pattern))
        
        results = []
        for key, item in ns.items():
            if item.is_expired:
                continue
            # Search in key and string values
            if regex.search(key):
                results.append(item)
            elif isinstance(item.value, str) and regex.search(item.value):
                results.append(item)
        
        return results
    
    async def cleanup_expired(self) -> int:
        count = 0
        for namespace in list(self._data.keys()):
            ns = self._data[namespace]
            expired_keys = [k for k, v in ns.items() if v.is_expired]
            for key in expired_keys:
                del ns[key]
                count += 1
        return count


# ============================================
# PostgreSQL Store
# ============================================

class PostgresStore(BaseStore):
    """PostgreSQL-backed persistent store."""
    
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS agent_store (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        namespace VARCHAR(255) NOT NULL,
        key VARCHAR(255) NOT NULL,
        value JSONB NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        expires_at TIMESTAMP WITH TIME ZONE,
        UNIQUE(namespace, key)
    );
    
    CREATE INDEX IF NOT EXISTS idx_store_namespace ON agent_store(namespace);
    CREATE INDEX IF NOT EXISTS idx_store_expires ON agent_store(expires_at) WHERE expires_at IS NOT NULL;
    """
    
    def __init__(self, config: StoreConfig | None = None, pool: Any = None):
        self.config = config or StoreConfig()
        self._pool = pool
        self._encryption_manager: EncryptionManager | None = None
        
        # Initialize encryption manager if encryption is configured
        if self.config.encryption_key or os.environ.get("STORE_ENCRYPTION_KEY"):
            try:
                self._encryption_manager = EncryptionManager(self.config.encryption_key)
            except Exception as e:
                logger.warning("Failed to initialize encryption manager", error=str(e))
                self._encryption_manager = None
    
    async def _get_pool(self):
        """Get database connection pool."""
        if self._pool is None:
            from app.db import get_pg_pool
            self._pool = await get_pg_pool()
        return self._pool
    
    async def ensure_table(self):
        """Ensure the store table exists."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_SQL)
    
    async def get(self, key: str, namespace: str = "default") -> StoreItem | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT key, value, namespace, created_at, updated_at, expires_at, metadata
                FROM agent_store
                WHERE namespace = $1 AND key = $2
                AND (expires_at IS NULL OR expires_at > NOW())
                """,
                namespace, key
            )
            
            if not row:
                return None
            
            value = row["value"]
            
            # Decrypt value if namespace requires encryption
            if self._encryption_manager and self.config._should_encrypt(namespace):
                try:
                    import json

                    # PostgreSQL JSONB returns as dict/str, encrypted value is stored as string
                    if isinstance(value, str):
                        # Try to decrypt (might be encrypted string or plain JSON string)
                        try:
                            decrypted_value = self._encryption_manager.decrypt(value)
                            # Try to parse as JSON
                            try:
                                value = json.loads(decrypted_value)
                            except json.JSONDecodeError:
                                value = decrypted_value
                        except (ValueError, Exception):
                            # If decryption fails, assume it's plain JSON string
                            try:
                                value = json.loads(value)
                            except json.JSONDecodeError:
                                pass  # Keep as string
                    elif isinstance(value, (dict, list)):
                        # Already parsed JSON, check if it contains encrypted marker
                        if isinstance(value, dict) and value.get("_encrypted"):
                            decrypted_value = self._encryption_manager.decrypt(value["_encrypted"])
                            try:
                                value = json.loads(decrypted_value)
                            except json.JSONDecodeError:
                                value = decrypted_value
                        # Otherwise, value is already decrypted JSON
                except Exception as e:
                    logger.error("Failed to decrypt value", key=key, namespace=namespace, error=str(e))
                    return None
            
            return StoreItem(
                key=row["key"],
                value=value,
                namespace=row["namespace"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                expires_at=row["expires_at"],
                metadata=row["metadata"] or {},
            )
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        namespace: str = "default",
        ttl_hours: int | None = None,
        metadata: dict | None = None,
    ) -> StoreItem:
        import json
        
        expires_at = None
        if ttl_hours is not None:
            expires_at = now_app() + timedelta(hours=ttl_hours)
        elif self.config.default_ttl_hours:
            expires_at = now_app() + timedelta(hours=self.config.default_ttl_hours)
        
        # Encrypt value if namespace requires encryption
        stored_value = value
        if self._encryption_manager and self.config._should_encrypt(namespace):
            # Convert to JSON string first, then encrypt
            json_str = json.dumps(value, ensure_ascii=False)
            try:
                encrypted_str = self._encryption_manager.encrypt(json_str)
                # Store encrypted string as JSONB (PostgreSQL will handle it)
                stored_value = encrypted_str
            except Exception as e:
                logger.error("Failed to encrypt value", key=key, namespace=namespace, error=str(e))
                raise ValueError(f"Encryption failed: {str(e)}")
        else:
            # Store as JSON
            stored_value = value
        
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # If encrypted, store as string in JSONB; otherwise store as JSON
            if isinstance(stored_value, str) and self._encryption_manager and self.config._should_encrypt(namespace):
                # Store encrypted string directly in JSONB
                value_jsonb = stored_value
            else:
                value_jsonb = json.dumps(stored_value, ensure_ascii=False)
            
            row = await conn.fetchrow(
                """
                INSERT INTO agent_store (namespace, key, value, metadata, expires_at)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5)
                ON CONFLICT (namespace, key) DO UPDATE SET
                    value = EXCLUDED.value,
                    metadata = EXCLUDED.metadata,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                RETURNING created_at, updated_at
                """,
                namespace, key, value_jsonb, json.dumps(metadata or {}), expires_at
            )
            
            return StoreItem(
                key=key,
                value=value,  # Return original unencrypted value
                namespace=namespace,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                expires_at=expires_at,
                metadata=metadata or {},
            )
    
    async def delete(self, key: str, namespace: str = "default") -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM agent_store WHERE namespace = $1 AND key = $2",
                namespace, key
            )
            return "DELETE 1" in result
    
    async def list_keys(self, namespace: str = "default", prefix: str = "") -> list[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key FROM agent_store
                WHERE namespace = $1 AND key LIKE $2
                AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY key
                """,
                namespace, f"{prefix}%"
            )
            return [row["key"] for row in rows]
    
    async def search(self, pattern: str, namespace: str = "default") -> list[StoreItem]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key, value, namespace, created_at, updated_at, expires_at, metadata
                FROM agent_store
                WHERE namespace = $1 
                AND (key ~ $2 OR value::text ~ $2)
                AND (expires_at IS NULL OR expires_at > NOW())
                """,
                namespace, pattern
            )
            
            return [
                StoreItem(
                    key=row["key"],
                    value=row["value"],
                    namespace=row["namespace"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                    metadata=row["metadata"] or {},
                )
                for row in rows
            ]
    
    async def cleanup_expired(self) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM agent_store WHERE expires_at IS NOT NULL AND expires_at < NOW()"
            )
            # Extract count from "DELETE X"
            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0


# ============================================
# Store Backend (implements BackendProtocol)
# ============================================

class StoreBackend(BackendProtocol):
    """Backend that uses a store for persistence.
    
    This adapts the Store interface to the BackendProtocol,
    allowing it to be used in the composite backend routing.
    
    Files are stored as:
    - path -> key
    - content -> value
    - directory -> namespace prefix
    """
    
    def __init__(self, store: BaseStore | None = None, namespace: str = "files"):
        self.store = store or InMemoryStore()
        self.namespace = namespace
    
    def _path_to_key(self, path: str) -> str:
        """Convert file path to store key."""
        # Normalize path
        if not path.startswith("/"):
            path = "/" + path
        return path

    def _get_sync_loop(self, op: str):
        """Get or create event loop for sync wrappers used in worker threads."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            return loop
        except RuntimeError:
            pass
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("loop closed")
            return loop
        except (RuntimeError, Exception):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    
    def ls_info(self, path: str) -> list[FileInfo]:
        """List files in a directory."""
        key_prefix = self._path_to_key(path)
        if not key_prefix.endswith("/"):
            key_prefix += "/"
        
        # Run async in sync context
        loop = self._get_sync_loop("ls_info")
        keys = loop.run_until_complete(
            self.store.list_keys(self.namespace, key_prefix)
        )
        
        # Extract immediate children
        seen_dirs = set()
        files = []
        
        for key in keys:
            relative = key[len(key_prefix):]
            if "/" in relative:
                # It's a subdirectory
                dir_name = relative.split("/")[0]
                subdir_path = key_prefix + dir_name + "/"
                if subdir_path not in seen_dirs:
                    seen_dirs.add(subdir_path)
                    files.append(FileInfo(
                        path=subdir_path,
                        is_dir=True,
                        size=0,
                        modified_at="",
                    ))
            else:
                # It's a file
                files.append(FileInfo(
                    path=key,
                    is_dir=False,
                    size=0,
                    modified_at="",
                ))
        
        return files
    
    def read(self, file_path: str, offset: int = 0, limit: int = 500) -> str:
        """Read file content."""
        key = self._path_to_key(file_path)
        
        loop = self._get_sync_loop("read")
        item = loop.run_until_complete(self.store.get(key, self.namespace))
        
        if not item:
            return f"Error: File not found: {file_path}"
        
        content = item.value if isinstance(item.value, str) else str(item.value)
        lines = content.split("\n")
        
        # Apply pagination
        selected = lines[offset:offset + limit]
        
        # Format with line numbers
        result = []
        for i, line in enumerate(selected, start=offset + 1):
            result.append(f"{i:4}: {line}")
        
        return "\n".join(result)
    
    def write(self, file_path: str, content: str) -> WriteResult:
        """Write file content."""
        key = self._path_to_key(file_path)
        
        loop = self._get_sync_loop("write")
        loop.run_until_complete(
            self.store.set(key, content, self.namespace)
        )
        
        return WriteResult(error=None, path=file_path, files_update=None)
    
    def edit(
        self, 
        file_path: str, 
        old_string: str, 
        new_string: str, 
        replace_all: bool = False
    ) -> EditResult:
        """Edit file by replacing content."""
        key = self._path_to_key(file_path)
        
        loop = self._get_sync_loop("edit")
        item = loop.run_until_complete(self.store.get(key, self.namespace))
        
        if not item:
            return EditResult(error=f"File not found: {file_path}")
        
        content = item.value if isinstance(item.value, str) else str(item.value)
        
        if old_string not in content:
            return EditResult(error="Pattern not found in file")
        
        if replace_all:
            new_content = content.replace(old_string, new_string)
            count = content.count(old_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
            count = 1
        
        loop.run_until_complete(
            self.store.set(key, new_content, self.namespace)
        )
        
        return EditResult(
            error=None,
            path=file_path,
            files_update=None,
            occurrences=count,
        )
    
    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Find files matching pattern."""
        import fnmatch
        
        key_prefix = self._path_to_key(path)
        
        loop = self._get_sync_loop("glob_info")
        keys = loop.run_until_complete(
            self.store.list_keys(self.namespace, key_prefix)
        )
        
        matches = []
        for key in keys:
            if fnmatch.fnmatch(key, pattern) or fnmatch.fnmatch(key.split("/")[-1], pattern):
                matches.append(FileInfo(
                    path=key,
                    is_dir=False,
                    size=0,
                    modified_at="",
                ))
        
        return matches
    
    def grep_raw(
        self, 
        pattern: str, 
        path: str | None = None, 
        glob: str | None = None
    ) -> list[GrepMatch]:
        """Search for pattern in files. Uses literal matching (not regex) per tool spec."""
        import re
        
        # Escape pattern for literal search - agent may pass special chars (e.g. "eval(")
        # that would cause "missing ), unterminated subpattern" in re.compile
        escaped = re.escape(pattern)
        
        loop = self._get_sync_loop("grep_raw")
        items = loop.run_until_complete(
            self.store.search(escaped, self.namespace)
        )
        
        regex = re.compile(escaped)
        matches = []
        
        for item in items:
            content = item.value if isinstance(item.value, str) else str(item.value)
            lines = content.split("\n")
            
            for i, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(GrepMatch(
                        path=item.key,
                        line=i,
                        text=line,
                    ))
        
        return matches

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to store."""
        results: list[FileUploadResponse] = []
        loop = self._get_sync_loop("upload_files")
        for path, content in files:
            key = self._path_to_key(path)
            try:
                content_str = content.decode("utf-8", errors="replace")
                loop.run_until_complete(self.store.set(key, content_str, self.namespace))
                results.append(FileUploadResponse(path=path, error=None))
            except Exception:
                results.append(FileUploadResponse(path=path, error="permission_denied"))
        return results

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from store."""
        results: list[FileDownloadResponse] = []
        loop = self._get_sync_loop("download_files")
        for path in paths:
            key = self._path_to_key(path)
            item = loop.run_until_complete(self.store.get(key, self.namespace))
            if not item:
                results.append(FileDownloadResponse(path=path, content=None, error="file_not_found"))
                continue
            content = item.value if isinstance(item.value, str) else str(item.value)
            results.append(FileDownloadResponse(path=path, content=content.encode("utf-8"), error=None))
        return results
