"""CompositeBackend - vendored from langchain-ai/deepagents. Plus our factory functions."""

from datetime import datetime, timezone
from pathlib import Path

from app._vendor.deepagents.backends.composite import CompositeBackend
from app._vendor.deepagents.backends.protocol import BackendFactory, BackendProtocol
from app._vendor.deepagents.backends.state import StateBackend
from app.datetime_support import format_api_datetime


def _fmt_ts(ts: float) -> str:
    """Inject into FilesystemBackend so file mtimes are formatted in the request's effective timezone."""
    return format_api_datetime(datetime.fromtimestamp(ts, tz=timezone.utc))

# Re-export
__all__ = [
    "CompositeBackend",
    "BackendFactory",
    "BackendProtocol",
    "StateBackend",
    "create_layered_backend",
    "create_middleware_backend",
]

# ============================================
# Factory: create_layered_backend, create_middleware_backend
# ============================================


def _attach_skill_virtual_routes(
    routes: dict[str, BackendProtocol],
    *,
    bundle_skill_routes: dict[str, str] | None = None,
    skills_subset_routes: dict[str, frozenset[str]] | None = None,
    main_skills_filtered_dirs: frozenset[str] | None = None,
) -> None:
    """Register ``/skills/``, optional ``/skills-main/``, bundle and subset skill roots."""
    from app._vendor.deepagents.backends.filesystem import FilesystemBackend
    from app.backends.filtered_skills_root import FilteredChildDirsFilesystemBackend
    from app.prompts.skills.discovery import SKILLS_DIR

    bundle_skill_routes = bundle_skill_routes or {}
    skills_subset_routes = skills_subset_routes or {}

    shared_fs: FilesystemBackend | None = None
    if SKILLS_DIR.exists():
        shared_fs = FilesystemBackend(root_dir=str(SKILLS_DIR), virtual_mode=True, fmt_timestamp=_fmt_ts)
        routes["/skills/"] = shared_fs
        if main_skills_filtered_dirs:
            routes["/skills-main/"] = FilteredChildDirsFilesystemBackend(
                shared_fs, main_skills_filtered_dirs
            )

    for prefix, root in bundle_skill_routes.items():
        p = Path(root)
        if p.is_dir():
            routes[prefix] = FilesystemBackend(root_dir=str(p.resolve()), virtual_mode=True, fmt_timestamp=_fmt_ts)

    base_for_subset = shared_fs
    if base_for_subset is None and SKILLS_DIR.exists():
        base_for_subset = FilesystemBackend(root_dir=str(SKILLS_DIR), virtual_mode=True, fmt_timestamp=_fmt_ts)
    for prefix, allowed in skills_subset_routes.items():
        if not allowed or base_for_subset is None:
            continue
        routes[prefix] = FilteredChildDirsFilesystemBackend(base_for_subset, allowed)


def create_layered_backend(
    store_backend: BackendProtocol | None = None,
    filesystem_backend: BackendProtocol | None = None,
    bundle_skill_routes: dict[str, str] | None = None,
    skills_subset_routes: dict[str, frozenset[str]] | None = None,
    main_skills_filtered_dirs: frozenset[str] | None = None,
) -> BackendFactory:
    """Create a BackendFactory for use with create_deep_agent.

    Returns a callable that takes ToolRuntime and returns CompositeBackend with:
    - default: StateBackend(rt) for ephemeral /temp/ and unmatched paths
    - /uploads/  → FilesystemBackend (upload_dir): on-demand disk reads, no memory load
    - /memories/, /parameters/ → InMemoryStore (official-style, no agent_store)
    - /skills/   → FilesystemBackend (skills dir)

    Uploaded files are referenced by virtual path (/uploads/session/file).
    The CompositeBackend strips the /uploads/ prefix and routes to FilesystemBackend
    which reads from disk on demand — large files never enter agent state.
    """
    from app.config import get_settings

    settings = get_settings()

    def _build_routes() -> dict[str, BackendProtocol]:
        routes: dict[str, BackendProtocol] = {}

        if store_backend is None:
            # Owner-scoped so cross-user/project isolation holds at the backend
            # namespace level. Shared InMemoryStore keeps behaviour identical
            # to the previous single-namespace setup for the same owner.
            from app.backends.owner_scoped_store import OwnerScopedStoreBackend

            routes["/memories/"] = OwnerScopedStoreBackend(base_namespace="memories")
            routes["/parameters/"] = OwnerScopedStoreBackend(base_namespace="parameters")
        else:
            routes["/memories/"] = store_backend
            routes["/parameters/"] = store_backend

        if filesystem_backend is not None:
            routes["/reports/"] = filesystem_backend

        # /workspace/ → WorkspaceFacade(Scoped(FilesystemBackend))
        # The facade hides the owner segment (u_<uid>/p_<pid> or s_<sid>) from
        # the LLM; the scoped backend enforces strict owner-root containment
        # on disk. /uploads/ stays as a legacy alias so in-flight attachment
        # flows keep working; new agent code should route via /workspace/.
        try:
            from app._vendor.deepagents.backends.filesystem import FilesystemBackend
            from app.backends.upload_scope import ScopedUploadFilesystemBackend
            from app.backends.workspace_facade import WorkspaceFacadeBackend

            upload_dir = Path(settings.upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            disk_fs = FilesystemBackend(
                root_dir=str(upload_dir), virtual_mode=True, fmt_timestamp=_fmt_ts
            )
            scoped = ScopedUploadFilesystemBackend(disk_fs)
            routes["/workspace/"] = WorkspaceFacadeBackend(scoped)
            routes["/uploads/"] = scoped
        except Exception:
            pass

        try:
            _attach_skill_virtual_routes(
                routes,
                bundle_skill_routes=bundle_skill_routes,
                skills_subset_routes=skills_subset_routes,
                main_skills_filtered_dirs=main_skills_filtered_dirs,
            )
        except Exception:
            pass

        return routes

    _routes = _build_routes()

    def factory(rt):
        from app.backends.path_aliases import PathAliasBackend

        return PathAliasBackend(
            CompositeBackend(
                default=StateBackend(rt),
                routes=_routes,
            )
        )

    return factory


def create_middleware_backend(
    bundle_skill_routes: dict[str, str] | None = None,
    skills_subset_routes: dict[str, frozenset[str]] | None = None,
    main_skills_filtered_dirs: frozenset[str] | None = None,
) -> BackendProtocol:
    """Create a CompositeBackend for middleware (FilesystemMiddleware, SummarizationMiddleware).

    Uses StandaloneStateBackend as default since ToolRuntime is not available at init.
    Same routes as create_layered_backend. Use for offloading and file tools before
    the agent has a runtime.
    """
    from app.backends.owner_scoped_store import OwnerScopedStoreBackend
    from app.backends.standalone_state import StandaloneStateBackend

    routes: dict[str, BackendProtocol] = {}
    routes["/memories/"] = OwnerScopedStoreBackend(base_namespace="memories")
    routes["/parameters/"] = OwnerScopedStoreBackend(base_namespace="parameters")

    try:
        _attach_skill_virtual_routes(
            routes,
            bundle_skill_routes=bundle_skill_routes,
            skills_subset_routes=skills_subset_routes,
            main_skills_filtered_dirs=main_skills_filtered_dirs,
        )
    except Exception:
        pass

    from app.backends.path_aliases import PathAliasBackend

    return PathAliasBackend(
        CompositeBackend(default=StandaloneStateBackend(), routes=routes)
    )
