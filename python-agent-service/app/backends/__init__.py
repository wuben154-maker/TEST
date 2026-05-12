"""Backend implementations - Our extensions only.

Official backends (StateBackend, FilesystemBackend, CompositeBackend, StoreBackend,
LocalShellBackend, BaseSandbox, protocol types): import from app._vendor.deepagents.backends.

Our extensions:
- standalone_state: StandaloneStateBackend (no ToolRuntime)
- store: BaseStore, PostgresStore, InMemoryStore, StoreBackend, ContextStoreAdapter
- database_backend: DatabaseBackend (Supabase/Postgres)
- supabase_store: SupabaseStore
- composite: create_layered_backend, create_middleware_backend (+ CompositeBackend re-export)
"""

from app.backends.standalone_state import StandaloneStateBackend
from app.backends.store import (
    StoreBackend,
    InMemoryStore,
    PostgresStore,
    StoreConfig,
    ContextStoreAdapter,
)
from app.backends.database_backend import DatabaseBackend
from app.backends.supabase_store import SupabaseStore
from app.backends.composite import (
    CompositeBackend,
    create_layered_backend,
    create_middleware_backend,
)

__all__ = [
    # Our extensions
    "StandaloneStateBackend",
    "StoreBackend",
    "InMemoryStore",
    "PostgresStore",
    "SupabaseStore",
    "ContextStoreAdapter",
    "StoreConfig",
    "DatabaseBackend",
    "CompositeBackend",
    "create_layered_backend",
    "create_middleware_backend",
]
