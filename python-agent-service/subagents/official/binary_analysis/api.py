"""Public Python API for the BinaryAnalyst agent (L1 entry layer).

This module implements the DESIGN.md §4.1 L1 entry point that CLI (`cli.py`)
and third-party callers share.  The entry layer is intentionally thin per
ADR-01 + A-01:

- Validate and normalize the caller-supplied path (IR-08: Unicode / space /
  symlink handling via ``Path.expanduser().resolve(strict=True)``).
- Guard the entry-layer invariants from DESIGN.md §3.3 (path exists, is a
  regular file, readable, within ``max_file_size_mb``).  Failures raise
  :class:`~errors.EntryFormatUnsupported` before any Agent /
  Tool machinery is touched (E2E-01 E1 short-circuit).
- Delegate the heavy lifting to an :class:`AgentRunner` — either
  :func:`_default_runner` (F-manual production wiring) or a
  caller-injected stub (unit tests).

The default runner is gated on the presence of a usable LLM provider
credential (``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` / an explicit
``BINARY_ANALYSIS_MODEL`` override).  Without any of those, the runner
raises :class:`NotImplementedError` with ``match="F-manual"`` so the
unit-test contract established in C15 stays intact.

The module does **not** import ``analyst_graph`` / ``embedded_recursion`` at load time so
that callers who only need path validation do not pay the deepagents /
LangChain import cost (AGENTS.md CLI start-up performance guidance).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from audit import analysis_context
from config import settings as _settings_factory
from errors import EntryFormatUnsupported

if TYPE_CHECKING:  # pragma: no cover
    from schema.report import ReportV1

AnalysisMode = Literal["standard", "deep"]

# LangGraph safety cap when ``BINARY_ANALYSIS_RECURSION_LIMIT`` is unset or invalid.
_DEFAULT_LANGGRAPH_RECURSION_LIMIT = 500
_DEEP_MODE_TOKEN_BUDGET = 120_000
_DEEP_MODE_MAX_ROUNDS = 30


class AgentRunner(Protocol):
    """Callable signature for the full BinaryAnalyst execution runner.

    Implementations wire the model / sandbox client / evidence-chain store,
    build the Agent graph via
    :func:`analyst_graph.build_binary_analyst_agent`, invoke it,
    and materialise the final :class:`~schema.report.ReportV1`.

    The signature is declared here so :func:`analyze_binary` stays
    framework-agnostic and unit tests can inject hermetic stubs.

    The ``max_recursion_depth``, ``token_budget``, ``max_rounds``, and
    ``document_tier_override`` parameters carry the resolved configurability
    values from the CLI / env layer (C13 · FR-08 AC-2/3 · FR-30 AC-4).
    Runners that do not yet consume these values may accept ``**kwargs``.
    """

    def __call__(
        self,
        *,
        sample_path: Path,
        output_dir: Path,
        use_e2b: bool,
        analysis_id: str,
        max_recursion_depth: int,
        token_budget: int,
        max_rounds: int,
        document_tier_override: str | None,
        analysis_mode: AnalysisMode,
    ) -> ReportV1: ...


def _normalize_entry_path(path: str | Path) -> Path:
    """Resolve and validate a caller-provided sample path (§3.3 L1 layer).

    Enforces the DESIGN.md §3.3 "CLI / Python API 入口" row:
    - IR-08: Unicode / whitespace normalization via
      ``Path.expanduser().resolve(strict=True)``.
    - Path exists and is a regular file (not a directory, socket, device).
    - ``os.R_OK`` — caller's effective identity can read the file.
    - FR-01 AC-9: size ≤ ``BINARY_ANALYSIS_MAX_FILE_SIZE_MB``.

    Args:
        path: Caller-provided file path (absolute or relative; may contain
            Unicode / whitespace characters).

    Returns:
        The fully resolved :class:`pathlib.Path`.

    Raises:
        EntryFormatUnsupported: Any entry-layer invariant is violated; the
            error's ``details["reason"]`` discriminates the failure mode
            (``path_not_found`` / ``path_unresolvable`` /
            ``not_a_regular_file`` / ``not_readable`` / ``size_exceeded``).
    """
    raw = os.fspath(path)
    try:
        resolved = Path(raw).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        msg = f"sample path does not exist: {raw!r}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "path_not_found", "path": raw},
        ) from exc
    except OSError as exc:
        msg = f"sample path cannot be resolved: {raw!r}"
        raise EntryFormatUnsupported(
            msg,
            details={
                "reason": "path_unresolvable",
                "path": raw,
                "os_error": str(exc),
            },
        ) from exc

    if not resolved.is_file():
        msg = f"sample path is not a regular file: {resolved}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "not_a_regular_file", "path": str(resolved)},
        )

    if not os.access(resolved, os.R_OK):
        msg = f"sample path is not readable: {resolved}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "not_readable", "path": str(resolved)},
        )

    size_bytes = resolved.stat().st_size
    limit_bytes = _settings_factory().max_file_size_mb * 1024 * 1024
    if size_bytes > limit_bytes:
        msg = (
            f"sample exceeds configured size limit: {size_bytes} > {limit_bytes} bytes"
        )
        raise EntryFormatUnsupported(
            msg,
            details={
                "reason": "size_exceeded",
                "path": str(resolved),
                "size_bytes": size_bytes,
                "limit_bytes": limit_bytes,
            },
        )

    return resolved


def _new_analysis_id() -> str:
    """Generate a fresh ULID for the analysis session (NFR-06)."""
    from ulid import ULID  # noqa: PLC0415  (keeps ulid off the --help path)

    return str(ULID())


def _resolve_model_id() -> str | None:
    """Pick the LangChain chat-model identifier for the default runner.

    Precedence (first non-empty wins):

    1. ``BINARY_ANALYSIS_MODEL`` — explicit override, e.g.
       ``"google_genai:gemini-2.5-flash"`` /
       ``"openai:gpt-4o-mini"`` / ``"anthropic:claude-sonnet-4-5"``.
    2. ``GOOGLE_API_KEY`` → ``"google_genai:gemini-2.5-flash"``
       (override via ``BINARY_ANALYSIS_GOOGLE_MODEL``).
    3. ``OPENAI_API_KEY`` → ``"openai:gpt-4o-mini"``.
    4. ``ANTHROPIC_API_KEY`` → ``"anthropic:claude-sonnet-4-5-20250929"``.

    Returns ``None`` when no provider credential is discoverable so the
    caller can fall back to the F-manual ``NotImplementedError`` contract
    documented on :func:`_default_runner`.
    """
    explicit = os.environ.get("BINARY_ANALYSIS_MODEL", "").strip()
    if explicit:
        return explicit
    if os.environ.get("GOOGLE_API_KEY"):
        google_model = (
            os.environ.get("BINARY_ANALYSIS_GOOGLE_MODEL", "").strip()
            or "gemini-2.5-flash"
        )
        return f"google_genai:{google_model}"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai:gpt-4o-mini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-sonnet-4-5-20250929"
    return None


def init_binary_analysis_chat_model(model_id: str) -> Any:
    """Construct the default chat model with a sufficient HTTP request timeout.

    Long agent runs can keep one LLM streaming call open for many minutes. Many
    providers' httpx defaults use a ~300s read timeout; exceeding that raises
    :class:`httpx.RemoteProtocolError` ("Server disconnected without sending a
    response") even when the service is fine.

    The timeout comes from :attr:`Settings.llm_request_timeout` (env
    ``BINARY_ANALYSIS_LLM_REQUEST_TIMEOUT``) and is passed to
    :func:`langchain.chat_models.init_chat_model` as ``timeout=...`` (supported
    across major integrations).
    """
    from langchain.chat_models import init_chat_model  # noqa: PLC0415

    cfg = _settings_factory()
    return init_chat_model(model_id, timeout=float(cfg.llm_request_timeout))


def _locate_skills_root() -> Path:
    """Return the absolute path to the ``skills/`` directory shipped in-repo.

    The layout is ``examples/binary_analysis/api.py`` → the skills root sits
    at ``examples/binary_analysis/skills/`` (sibling to this file).  The path
    is **resolved**, not asserted to exist, so the runner surfaces a
    descriptive error when the package has been installed without the sibling
    ``skills/`` tree.
    """
    return (Path(__file__).resolve().parent / "skills").resolve()


def _build_initial_prompt(
    *,
    sample_path: Path,
    output_dir: Path,
    analysis_id: str,
    analysis_mode: AnalysisMode,
) -> str:
    """Compose the bootstrapping human message handed to the agent.

    The prompt tells the Agent:

    - Where the host-side sample is (so it can hand the path to
      ``file_identify`` which performs the sandbox upload).
    - The target ``output_dir`` for the final JSON / Markdown report so
      ``report_gen`` writes to the caller-supplied location.
    - The ``analysis_id`` so every tool call binds to the same audit
      context.

    The phrasing intentionally instructs the Agent to follow the
    ``binary-analysis-e2e-orchestrator`` skill rather than re-stating the
    entire protocol here; the skill already carries the canonical flow.
    """
    return (
        "You are invoked as the BinaryAnalyst static-analysis agent.\n\n"
        f"- host sample path: `{sample_path}`\n"
        f"- analysis_id: `{analysis_id}`\n"
        f"- report output_dir: `{output_dir}`\n\n"
        f"- analysis_mode: `{analysis_mode}`\n\n"
        "Start by loading the `binary-analysis-e2e-orchestrator` skill "
        "and follow its three-phase protocol. Hand the host sample path "
        "to the `file_identify` tool first so the sample is uploaded to "
        "the sandbox workspace; never read raw sample bytes into your "
        "reasoning context. When finished, call the `report_gen` tool "
        "with the analysis_id and output_dir above so the final "
        "`<sha256>.report.{json,md}` pair is written."
    )


def _default_runner(
    *,
    sample_path: Path,
    output_dir: Path,
    use_e2b: bool,
    analysis_id: str,
    max_recursion_depth: int,  # noqa: ARG001 — passed through; consumed by agent internals (C7/C8)
    token_budget: int,  # noqa: ARG001 — passed through; consumed by agent internals (C7)
    max_rounds: int,  # noqa: ARG001 — passed through; consumed by agent internals (C7)
    document_tier_override: str | None,  # noqa: ARG001 — passed through; consumed by identify_file (C4)
    analysis_mode: AnalysisMode,
) -> ReportV1:
    """Production runner for the BinaryAnalyst agent (F-manual wiring).

    Assembles the real dependency graph and drives
    :func:`analyst_graph.build_binary_analyst_agent`:

    1. Pick the LLM identifier via :func:`_resolve_model_id`.  Absent a
       provider credential the runner re-raises the historic
       :class:`NotImplementedError` so C15's
       ``test_default_runner_raises_not_implemented`` stays green.
    2. Spin up the selected :class:`SandboxClient` backend
       (subprocess fallback or E2B) and a fresh
       :class:`EvidenceChainStore`.
    3. Build the DeepAgent graph rooted at
       ``examples/binary_analysis/skills/``.
    4. Invoke the graph with a bootstrapping human message and
       degrade to :func:`~facts_report.build_facts_only_report`
       on :class:`LlmUnrecoverable` / :class:`BudgetExceeded` / any
       unexpected exception (E2E-01 E4 degradation path).
    5. Load and return the authoritative :class:`ReportV1` from disk.

    Raises:
        NotImplementedError: No LLM provider credential is configured
            (preserves the C15 unit-test contract).
        BinaryAnalysisError: Propagated from the Agent / Tool layers
            (wrapped by :mod:`cli`).
    """
    model_id = _resolve_model_id()
    if model_id is None:
        msg = (
            "The default BinaryAnalyst runner requires a configured LLM "
            "provider. Set BINARY_ANALYSIS_MODEL (provider:model slug) or "
            "one of OPENAI_API_KEY / ANTHROPIC_API_KEY in the environment. "
            "Unit tests should inject a custom runner via "
            "analyze_binary(..., runner=...) — this placeholder is "
            "retained for the C15 F-manual contract."
        )
        raise NotImplementedError(msg)

    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    from analyst_graph import build_binary_analyst_agent  # noqa: PLC0415
    from budget_guards import (  # noqa: PLC0415
        BudgetCoordinator,
        RecursionDepthGuard,
        RoundBudgetGuard,
        TokenBudgetGuard,
    )
    from embedded_recursion import recurse_child_sample  # noqa: PLC0415
    from errors import (  # noqa: PLC0415
        BinaryAnalysisError,
        BudgetExceeded,
        EntryFormatUnsupported,
        LlmUnrecoverable,
        StateCorruption,
    )
    from evidence_chain.store import (  # noqa: PLC0415
        EvidenceChainStore,
    )
    from facts_report import build_facts_only_report  # noqa: PLC0415
    from schema.evidence_chain import Bucket  # noqa: PLC0415
    from schema.indicator import Indicator, Severity  # noqa: PLC0415
    from schema.report import ReportV1  # noqa: PLC0415
    from tools.file_identify import identify_file  # noqa: PLC0415
    from tools.report_gen import (  # noqa: PLC0415
        ReportGenResult,
        build_report_v1,
        render_json,
        render_markdown,
    )

    cfg = _settings_factory()
    preflight = identify_file(sample_path, max_size_mb=cfg.max_file_size_mb)

    from sandbox.factory import build_binary_sandbox_client  # noqa: PLC0415

    sandbox_client = build_binary_sandbox_client(use_e2b=use_e2b)
    store = EvidenceChainStore(analysis_id=analysis_id)
    model = init_binary_analysis_chat_model(model_id)
    skills_root = _locate_skills_root()
    if not skills_root.is_dir():
        msg = (
            f"Skills root is missing: {skills_root}. The BinaryAnalyst agent "
            "requires the sibling `skills/` tree shipped alongside the "
            "package."
        )
        raise NotImplementedError(msg)
    budget_coordinator = BudgetCoordinator(
        token_guard=TokenBudgetGuard(budget=token_budget),
        round_guard=RoundBudgetGuard(max_rounds=max_rounds),
        depth_guard=RecursionDepthGuard(max_depth=max_recursion_depth),
    )
    child_report_registry: dict[str, ReportGenResult] = {}

    async def _handle_embedded_payloads(
        parent_analysis_id: str,
        payloads: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        handled: list[dict[str, Any]] = []
        for payload in payloads:
            enriched = dict(payload)
            if not payload.get("recursive_ready"):
                handled.append(enriched)
                continue
            child_sample_id = str(
                payload.get("child_sample_id") or payload.get("child_analysis_id") or ""
            )
            child_path = str(payload.get("extracted_to") or "")
            if not child_sample_id or not child_path:
                enriched["child_recursion_status"] = "skipped_missing_child_path"
                handled.append(enriched)
                continue
            result = await recurse_child_sample(
                store,
                child_sample_id,
                child_path,
                budget_coordinator,
                budget_coordinator.depth_guard,
                model=model,
                sandbox_client=sandbox_client,
                skills_root=skills_root,
                parent_analysis_id=parent_analysis_id,
                child_sha256=str(payload.get("sha256") or ""),
                child_suggested_format=str(payload.get("suggested_format") or ""),
                output_dir=output_dir,
            )
            enriched["child_recursion_status"] = result.get("status", "unknown")
            enriched["child_verdict"] = result.get("child_verdict", "unknown")
            child_report = result.get("child_report")
            if isinstance(child_report, dict):
                child_report_registry[child_sample_id] = ReportGenResult.model_validate(
                    child_report
                )
            handled.append(enriched)
        return handled

    graph = build_binary_analyst_agent(
        model=model,
        store=store,
        sandbox_client=sandbox_client,
        skills_root=skills_root,
        embedded_payload_handler=_handle_embedded_payloads,
    )

    initial_message = _build_initial_prompt(
        sample_path=sample_path,
        output_dir=output_dir,
        analysis_id=analysis_id,
        analysis_mode=analysis_mode,
    )

    degraded_reason: str | None = None
    # The agent's Sandbox tools (SandboxSessionTool / BashTool /
    # PythonExecTool / FileIdentifyTool) are async-only and raise
    # NotImplementedError when reached via a synchronous `graph.invoke`.
    # We therefore drive the graph through `asyncio.run(graph.ainvoke(...))`
    # so the tool async paths execute properly. This is a pure wiring
    # concern: `analyze_binary` remains sync at the public boundary.
    import asyncio  # noqa: PLC0415

    async def _drive_graph() -> None:
        import os as _os  # noqa: PLC0415

        limit_raw = _os.environ.get("BINARY_ANALYSIS_RECURSION_LIMIT", "").strip()
        try:
            recursion_limit = (
                int(limit_raw) if limit_raw else _DEFAULT_LANGGRAPH_RECURSION_LIMIT
            )
        except ValueError:
            recursion_limit = _DEFAULT_LANGGRAPH_RECURSION_LIMIT
        await graph.ainvoke(
            {"messages": [HumanMessage(content=initial_message)]},
            config={"recursion_limit": recursion_limit},
        )

    try:
        asyncio.run(_drive_graph())
    except LlmUnrecoverable as exc:
        degraded_reason = f"LlmUnrecoverable: {exc.message}"
    except BudgetExceeded as exc:
        degraded_reason = f"BudgetExceeded: {exc.message}"
    except (EntryFormatUnsupported, StateCorruption):
        # Entry-layer and state-integrity failures are non-recoverable:
        # propagate so the CLI surfaces them with the correct exit code
        # (2 / 3) instead of masking them behind a facts-only report.
        raise
    except BinaryAnalysisError as exc:
        # All other domain errors (Tool* / Sandbox* / LLM* except the
        # explicitly handled `LlmUnrecoverable` / `BudgetExceeded`) are
        # treated as degradation triggers — the agent may have raised
        # them mid-flight (e.g. LLM tried a non-whitelisted `bash`
        # command, remote sandbox timed out). Keep the analysis alive
        # and hand the incident to `build_facts_only_report`.
        degraded_reason = f"{exc.error_code}: {exc.message}"
    except Exception as exc:  # noqa: BLE001
        degraded_reason = f"{type(exc).__name__}: {exc}"

    def _ensure_preflight_file_meta() -> None:
        """Seed a pre-flight ``file_meta`` Indicator when the store is empty.

        Runs only in the degraded path (E4) where the LLM failed before
        ``FileIdentifyTool`` could populate the store. The Indicator is a
        ``fact`` derived from :func:`identify_file` — no sandbox upload is
        implied; the sandbox path is the canonical placeholder.
        """
        if store.snapshot().file_meta:
            return
        store.append(
            Bucket.file_meta,
            Indicator(
                source_fr="FR-01",
                indicator_type="file_meta",
                severity=Severity.INFO,
                kind="fact",
                data={
                    "absolute_path": str(sample_path),
                    "size_bytes": preflight.size_bytes,
                    "format": preflight.format,
                    "arch": preflight.arch,
                    "routing": preflight.routing,
                    "fingerprints": preflight.fingerprints,
                    "sandbox_path": f"/workspace/{analysis_id}/sample.bin",
                    "coverage_notes": preflight.coverage_notes,
                },
            ),
        )

    if degraded_reason is not None:
        _ensure_preflight_file_meta()
        result = build_facts_only_report(
            store=store,
            analysis_id=analysis_id,
            output_dir=output_dir,
            reason=degraded_reason,
            model_label=model_id,
        )
        return ReportV1.model_validate_json(
            Path(result.json_path).read_text(encoding="utf-8")
        )

    # Happy path: the agent is expected to have invoked `report_gen` and
    # written `<sha256>.report.{json,md}` under `output_dir`. Synthesize
    # from the store as a defensive safety net — if the agent forgot to
    # call the tool (or the store is empty), fall back to facts-only so
    # the caller always receives a ReportV1 instance.
    snapshot = store.snapshot()
    try:
        report = build_report_v1(
            snapshot,
            analysis_id=analysis_id,
            child_reports=child_report_registry,
        )
    except ValueError as exc:
        _ensure_preflight_file_meta()
        result = build_facts_only_report(
            store=store,
            analysis_id=analysis_id,
            output_dir=output_dir,
            reason=f"store lacks file_meta: {exc}",
            model_label=model_id,
        )
        return ReportV1.model_validate_json(
            Path(result.json_path).read_text(encoding="utf-8")
        )

    sha256 = report.fingerprints.sha256
    json_path = output_dir / f"{sha256}.report.json"
    md_path = output_dir / f"{sha256}.report.md"
    if child_report_registry or not json_path.exists():
        json_path.write_text(render_json(report), encoding="utf-8")
    if child_report_registry or not md_path.exists():
        md_path.write_text(render_markdown(report), encoding="utf-8")
    return ReportV1.model_validate_json(json_path.read_text(encoding="utf-8"))


def analyze_binary(
    path: str | Path,
    *,
    output_dir: str | Path | None = None,
    use_e2b: bool | None = None,
    runner: AgentRunner | None = None,
    max_recursion_depth: int | None = None,
    token_budget: int | None = None,
    max_rounds: int | None = None,
    document_tier_override: str | None = None,
    analysis_mode: AnalysisMode = "standard",
) -> ReportV1:
    """Run the BinaryAnalyst agent on a sample and return the typed report.

    Thin L1 wrapper: performs the §3.3 entry-layer validation (IR-08 +
    FR-01 AC-9), binds an ``analysis_id`` to the audit context (NFR-06),
    and delegates to the resolved :class:`AgentRunner`.

    Args:
        path: Filesystem path to the sample.  Accepts absolute and relative
            paths and Unicode / whitespace characters; symlinks are
            resolved via ``Path.resolve(strict=True)`` (IR-08).
        output_dir: Destination directory for ``<sha256>.report.{json,md}``.
            Defaults to the caller's current working directory.  Created
            on demand if missing.
        use_e2b: Override for the ``BINARY_ANALYSIS_USE_E2B`` feature flag
            for this one invocation.  ``None`` inherits ``Settings.use_e2b``.
        runner: Optional injected :class:`AgentRunner`.  Defaults to
            :func:`_default_runner` (production wiring, F-manual).
        max_recursion_depth: Override the maximum sub-agent recursion depth
            (FR-30 AC-4).  ``None`` reads ``DEEPAGENT_MAX_RECURSION_DEPTH``
            then falls back to :data:`~config.DEFAULT_MAX_RECURSION_DEPTH`.
        token_budget: Override the agent token budget (NFR-05).  Values
            above :data:`~config.TOKEN_BUDGET_HARD_CAP`
            (120 000) are silently capped.  ``None`` reads
            ``DEEPAGENT_TOKEN_BUDGET`` then falls back to
            :data:`~config.DEFAULT_TOKEN_BUDGET`.
        max_rounds: Override the maximum agent reasoning rounds (NFR-07).
            ``None`` reads ``DEEPAGENT_MAX_ROUNDS`` then falls back to
            :data:`~config.DEFAULT_MAX_ROUNDS`.
        document_tier_override: Debug knob — force a specific document-
            analysis tier (``"P0"`` / ``"P1"`` / ``"P2"``) instead of
            relying on the automatic ``identify_file`` detection.
        analysis_mode: ``"standard"`` keeps the resolved defaults; ``"deep"``
            raises token and round defaults for nested payload analysis unless
            caller/env overrides already supplied explicit values.

    Returns:
        The finalised :class:`~schema.report.ReportV1`
        instance emitted by the runner.

    Raises:
        EntryFormatUnsupported: The entry-layer validation fails (path
            missing / unresolvable / not a regular file / unreadable /
            exceeds configured size limit).
        NotImplementedError: No ``runner`` was provided and the default
            runner has not been wired (unit-test environment).
        BinaryAnalysisError: Propagated from the runner for downstream
            Agent / Tool failures (logged by CLI).
    """
    import warnings  # noqa: PLC0415

    from config import (  # noqa: PLC0415
        TOKEN_BUDGET_HARD_CAP,
        document_settings,
    )

    sample_path = _normalize_entry_path(path)

    output_path = Path(output_dir) if output_dir is not None else Path.cwd()
    output_path = output_path.expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)

    cfg = _settings_factory()
    effective_use_e2b = cfg.use_e2b if use_e2b is None else bool(use_e2b)
    if analysis_mode not in ("standard", "deep"):
        msg = f"unsupported analysis_mode: {analysis_mode!r}"
        raise ValueError(msg)

    # Resolve configurability params: caller arg > env > built-in default.
    doc_cfg = document_settings()
    eff_max_recursion_depth = (
        max_recursion_depth
        if max_recursion_depth is not None
        else doc_cfg.max_recursion_depth
    )
    eff_token_budget = (
        token_budget if token_budget is not None else doc_cfg.token_budget
    )
    if (
        analysis_mode == "deep"
        and token_budget is None
        and "DEEPAGENT_TOKEN_BUDGET" not in os.environ
    ):
        eff_token_budget = _DEEP_MODE_TOKEN_BUDGET
    if eff_token_budget > TOKEN_BUDGET_HARD_CAP:
        warnings.warn(
            f"token_budget {eff_token_budget} exceeds the hard cap "
            f"{TOKEN_BUDGET_HARD_CAP}; capped to {TOKEN_BUDGET_HARD_CAP}.",
            stacklevel=2,
        )
        eff_token_budget = TOKEN_BUDGET_HARD_CAP
    eff_max_rounds = max_rounds if max_rounds is not None else doc_cfg.max_rounds
    if (
        analysis_mode == "deep"
        and max_rounds is None
        and "DEEPAGENT_MAX_ROUNDS" not in os.environ
    ):
        eff_max_rounds = _DEEP_MODE_MAX_ROUNDS

    analysis_id = _new_analysis_id()

    selected_runner = runner if runner is not None else _default_runner
    with analysis_context(analysis_id):
        return selected_runner(
            sample_path=sample_path,
            output_dir=output_path,
            use_e2b=effective_use_e2b,
            analysis_id=analysis_id,
            max_recursion_depth=eff_max_recursion_depth,
            token_budget=eff_token_budget,
            max_rounds=eff_max_rounds,
            document_tier_override=document_tier_override,
            analysis_mode=analysis_mode,
        )


__all__ = [
    "AgentRunner",
    "analyze_binary",
    "AnalysisMode",
    "_DEFAULT_LANGGRAPH_RECURSION_LIMIT",
]
