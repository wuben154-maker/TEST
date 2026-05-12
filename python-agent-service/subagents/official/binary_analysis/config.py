"""Runtime configuration for the binary analysis system.

Environment variables are parsed once via :func:`settings`, which returns a
cached :class:`Settings` instance.  Every variable is documented in the §7
environment-variable table of the architecture design document.

Usage::

    from config import settings

    cfg = settings()
    if cfg.use_e2b:
        ...

The :func:`settings` function validates inter-variable constraints at startup:
if ``use_e2b`` is ``True`` but ``e2b_api_key`` is absent, a
:class:`~errors.SandboxUnavailable` error is raised
immediately — the caller should catch it and either enable the fallback or
abort.

Document-mode parameters live in a separate :class:`DocumentSettings` block
keyed by the ``DEEPAGENT_`` prefix (FR-08 AC-2/3 · FR-30 AC-4 · NFR-05/07).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from errors import SandboxUnavailable

# ---------------------------------------------------------------------------
# Document-mode / configurability constants (C7 forward-declaration stubs)
# ---------------------------------------------------------------------------

#: Hard cap for the agent token budget (FR-08 AC-2 / NFR-05).
TOKEN_BUDGET_HARD_CAP: int = 120_000

#: Default token budget when neither CLI nor env override is present.
DEFAULT_TOKEN_BUDGET: int = 80_000

#: Default maximum agent rounds (NFR-07).
DEFAULT_MAX_ROUNDS: int = 15

#: Default maximum recursion depth for document sub-agents (FR-30 AC-4).
DEFAULT_MAX_RECURSION_DEPTH: int = 2


class Settings(BaseSettings):
    """Parsed runtime configuration.

    All fields map 1-to-1 to the environment variables listed in §7.  Fields
    marked as ``None`` are optional; the :meth:`validate_e2b_credentials`
    validator enforces that ``e2b_api_key`` is present whenever ``use_e2b``
    is ``True``.

    Attributes:
        use_e2b: When ``True`` the sandbox client targets the remote E2B VM
            (ADR-05/16).  Set to ``False`` to fall back to the local
            subprocess mode (e.g. for offline / air-gapped / CI environments).
        e2b_api_key: E2B SaaS authentication key.  **Never** written to logs
            or the evidence chain (§6.2 + ADR-16).  Required when
            ``use_e2b=True``.
        e2b_template: E2B template identifier for the pre-built analysis
            environment (ADR-17).
        sandbox_timeout_seconds: Total lifetime of a sandbox session in
            seconds (NFR-02 + safety window).
        log_dir: Directory where per-analysis ``<analysis_id>.audit.jsonl``
            files are written (§6.2).
        max_file_size_mb: Maximum sample file size accepted at the entry point
            (FR-01 AC-9).
        llm_request_timeout: Per-request wall-clock timeout in seconds for the
            LLM HTTP client (including long streaming turns). Set above common
            ~300s provider defaults to avoid spurious disconnects on heavy runs.
    """

    model_config = SettingsConfigDict(
        env_prefix="BINARY_ANALYSIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    use_e2b: bool = True
    e2b_api_key: str | None = None
    e2b_template: str = "binary-analysis-ubuntu-2204"
    sandbox_timeout_seconds: int = 330
    log_dir: Path = Path("logs")
    max_file_size_mb: int = 100
    llm_request_timeout: float = 600.0

    model_config = SettingsConfigDict(
        env_prefix="BINARY_ANALYSIS_",
        # E2B_API_KEY lives outside the prefix (shared convention)
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _pull_e2b_api_key(cls, values: dict) -> dict:
        """Populate ``e2b_api_key`` from the ``E2B_API_KEY`` env var.

        pydantic-settings applies the ``BINARY_ANALYSIS_`` prefix to all
        fields, but ``E2B_API_KEY`` intentionally lives outside the prefix
        (it is a shared E2B convention).  This validator injects it before
        field parsing so the constraint check in
        :meth:`validate_e2b_credentials` can inspect it.
        """
        import os

        if "e2b_api_key" not in values or values.get("e2b_api_key") is None:
            values["e2b_api_key"] = os.environ.get("E2B_API_KEY")
        return values

    @model_validator(mode="after")
    def validate_e2b_credentials(self) -> Settings:
        """Raise :class:`~errors.SandboxUnavailable` when E2B is enabled but the API key is absent.

        Returns:
            The validated ``Settings`` instance (unchanged when the check
            passes).

        Raises:
            SandboxUnavailable: If ``use_e2b`` is ``True`` and
                ``e2b_api_key`` is ``None`` or empty.
        """
        if self.use_e2b and not self.e2b_api_key:
            msg = (
                "E2B_API_KEY is required when BINARY_ANALYSIS_USE_E2B=true. "
                "Set E2B_API_KEY or disable E2B with BINARY_ANALYSIS_USE_E2B=false."
            )
            raise SandboxUnavailable(msg)
        return self


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Return the cached, validated :class:`Settings` singleton.

    The instance is created once on first call and cached for the lifetime of
    the process.  Tests that need to vary env vars should clear the cache with
    ``settings.cache_clear()`` before each test.

    Returns:
        Parsed and validated :class:`Settings` instance.

    Raises:
        SandboxUnavailable: When ``BINARY_ANALYSIS_USE_E2B=true`` (the
            default) and ``E2B_API_KEY`` is absent.
        pydantic_settings.ValidationError: On any other configuration error.
    """
    return Settings()


# ---------------------------------------------------------------------------
# Document-mode settings (DEEPAGENT_* prefix — FR-08 AC-2/3 · FR-30 AC-4)
# ---------------------------------------------------------------------------


class DocumentSettings(BaseSettings):
    """Document-analysis runtime parameters read from ``DEEPAGENT_*`` env vars.

    All fields have safe defaults so the system runs without any
    ``DEEPAGENT_*`` variables set.  CLI arguments override these values at
    the :func:`~api.analyze_binary` boundary.

    Attributes:
        max_recursion_depth: Maximum sub-agent recursion depth for document
            analysis (FR-30 AC-4).  Corresponds to ``--max-recursion-depth``.
        token_budget: Soft token budget for the analysis session (NFR-05).
            Capped at :data:`TOKEN_BUDGET_HARD_CAP` (120 000).
        max_rounds: Maximum agent reasoning rounds (NFR-07).  Corresponds to
            ``--max-rounds``.
        vba_simulation_timeout_sec: Per-invocation timeout for the VBA
            simulation engine inside the sandbox.
        vba_max_instructions: Instruction cap for the VBA simulation engine.
        password_list_path: Path to the encrypted-document password dictionary
            mounted in the sandbox container.
    """

    model_config = SettingsConfigDict(
        env_prefix="DEEPAGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    max_recursion_depth: int = DEFAULT_MAX_RECURSION_DEPTH
    token_budget: int = DEFAULT_TOKEN_BUDGET
    max_rounds: int = DEFAULT_MAX_ROUNDS
    vba_simulation_timeout_sec: int = 60
    vba_max_instructions: int = 100_000
    password_list_path: Path = Path("/etc/deepagent/container_password_list.yaml")


@lru_cache(maxsize=1)
def document_settings() -> DocumentSettings:
    """Return the cached :class:`DocumentSettings` singleton.

    Tests that need to vary ``DEEPAGENT_*`` env vars should call
    ``document_settings.cache_clear()`` before and after each test.

    Returns:
        Parsed :class:`DocumentSettings` instance.
    """
    return DocumentSettings()
