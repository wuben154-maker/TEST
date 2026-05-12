"""Error classification for the binary analysis system.

All public error classes correspond 1-to-1 to the error codes defined in §5.1
of the architecture design document.  Every error carries an ``error_code``
field that can be used for structured logging and programmatic handling.

The hierarchy is intentionally flat: every concrete error inherits directly
from :class:`BinaryAnalysisError` so callers can catch the base class when
they want to handle all domain errors uniformly.
"""

from __future__ import annotations

from typing import Any, Literal


class BinaryAnalysisError(Exception):
    """Base class for all binary-analysis domain errors.

    Args:
        message: Human-readable description of what went wrong.
        details: Optional mapping of additional structured context.
    """

    error_code: str = "BINARY_ANALYSIS_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error to a JSON-compatible mapping.

        Returns:
            A mapping containing ``error_code``, ``message``, and
            ``details`` keys.
        """
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Entry / file-format errors
# ---------------------------------------------------------------------------


class EntryFormatUnsupported(BinaryAnalysisError):
    """Raised when the submitted file cannot be identified as a supported format.

    Corresponds to the ``ENTRY_FORMAT_UNSUPPORTED`` error code (§5.1).
    Triggers E2E-01 exceptional path E1: analysis terminates immediately.
    """

    error_code = "ENTRY_FORMAT_UNSUPPORTED"


# ---------------------------------------------------------------------------
# Tool errors
# ---------------------------------------------------------------------------


class ToolUnavailable(BinaryAnalysisError):
    """Raised when a required tool binary is absent or fails to start.

    Corresponds to ``TOOL_UNAVAILABLE`` (§5.1).  The analysis continues with
    a coverage gap recorded in the evidence chain.
    """

    error_code = "TOOL_UNAVAILABLE"


class ToolTimeout(BinaryAnalysisError):
    """Raised when a tool call exceeds its configured timeout.

    Corresponds to ``TOOL_TIMEOUT`` (§5.1).  The subprocess is killed; no
    retry is attempted (§5.2).
    """

    error_code = "TOOL_TIMEOUT"


class ToolCrash(BinaryAnalysisError):
    """Raised when a tool subprocess exits with a non-zero status.

    Corresponds to ``TOOL_CRASH`` (§5.1).  ``stderr`` content should be
    captured in ``details["stderr"]``.
    """

    error_code = "TOOL_CRASH"


class ToolSchemaInvalid(BinaryAnalysisError):
    """Raised when a tool's output does not match its expected schema.

    Corresponds to ``TOOL_SCHEMA_INVALID`` (§5.1).  Funnels into the
    ``TOOL_UNAVAILABLE`` handling branch.
    """

    error_code = "TOOL_SCHEMA_INVALID"


# ---------------------------------------------------------------------------
# Sandbox errors  (v0.4, ADR-05/16)
# ---------------------------------------------------------------------------


class SandboxUnavailable(BinaryAnalysisError):
    """Raised when the E2B sandbox cannot be provisioned.

    Corresponds to ``SANDBOX_UNAVAILABLE`` (§5.1).  Causes include a missing
    ``E2B_API_KEY``, exhausted quota, or a non-existent template.  The
    ``BINARY_ANALYSIS_USE_E2B`` feature flag determines whether a local
    subprocess fallback is attempted.
    """

    error_code = "SANDBOX_UNAVAILABLE"


class SandboxCreateTimeout(BinaryAnalysisError):
    """Raised when ``AsyncSandbox.create`` exceeds the cold-start budget.

    Corresponds to ``SANDBOX_CREATE_TIMEOUT`` (§5.1).  One exponential-backoff
    retry is attempted before escalating to ``SandboxUnavailable``.
    """

    error_code = "SANDBOX_CREATE_TIMEOUT"


class SandboxNetworkError(BinaryAnalysisError):
    """Raised when the host-to-E2B control-plane TLS connection fails.

    Corresponds to ``SANDBOX_NETWORK_ERROR`` (§5.1).  Up to two retries with
    exponential backoff (1 s / 3 s) before escalating to ``SandboxUnavailable``.
    """

    error_code = "SANDBOX_NETWORK_ERROR"


class SandboxExecFailed(BinaryAnalysisError):
    """Raised when ``sandbox.commands.run`` returns non-zero and stderr indicates a crash.

    Corresponds to ``SANDBOX_EXEC_FAILED`` (§5.1).  Maps to the
    ``TOOL_CRASH`` handling path.
    """

    error_code = "SANDBOX_EXEC_FAILED"


class SandboxUnrecoverable(BinaryAnalysisError):
    """Raised when the sandbox is unavailable and the fallback is disabled.

    Corresponds to ``SANDBOX_UNRECOVERABLE`` (§5.1).  Terminates the analysis
    via E2E-01 exceptional path E4.
    """

    error_code = "SANDBOX_UNRECOVERABLE"


# ---------------------------------------------------------------------------
# LLM errors
# ---------------------------------------------------------------------------


class LlmNetworkError(BinaryAnalysisError):
    """Raised when the LLM provider is unreachable due to a network failure.

    Corresponds to ``LLM_NETWORK_ERROR`` (§5.1).  Retried with exponential
    backoff (1 s / 2 s / 4 s / 8 s, up to 4 attempts).
    """

    error_code = "LLM_NETWORK_ERROR"


class LlmRateLimit(BinaryAnalysisError):
    """Raised when the LLM provider responds with a rate-limit error.

    Corresponds to ``LLM_RATE_LIMIT`` (§5.1).  Retried according to the
    ``Retry-After`` header or a fixed interval (up to 3 attempts).
    """

    error_code = "LLM_RATE_LIMIT"


class LlmSchemaError(BinaryAnalysisError):
    """Raised when the LLM returns a malformed tool-calling payload.

    Corresponds to ``LLM_SCHEMA_ERROR`` (§5.1).  Retried once per round with
    an additional schema hint in the prompt.
    """

    error_code = "LLM_SCHEMA_ERROR"


class LlmUnrecoverable(BinaryAnalysisError):
    """Raised when all LLM retry attempts have been exhausted.

    Corresponds to ``LLM_UNRECOVERABLE`` (§5.1).  The analysis produces a
    tool-facts-only simplified report with ``Verdict = UNKNOWN``.
    """

    error_code = "LLM_UNRECOVERABLE"


# ---------------------------------------------------------------------------
# Budget / state errors
# ---------------------------------------------------------------------------


class BudgetExceeded(BinaryAnalysisError):
    """Raised when the token or round-count budget is exhausted.

    Corresponds to ``BUDGET_EXCEEDED`` (§5.1).  Forces the LLM into a
    convergence phase to produce the best available output.

    Args:
        message: Human-readable description of the budget breach.
        details: Optional mapping of structured context (consumed/budget/rounds).
        reason: Machine-readable budget type that was exceeded.  One of:
            ``"token"`` (token ceiling), ``"round"`` (LLM round ceiling), or
            ``"recursion_budget"`` (recursive child-sample budget exhausted).
    """

    error_code = "BUDGET_EXCEEDED"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        reason: Literal["round", "token", "recursion_budget"] = "token",
    ) -> None:
        super().__init__(message, details=details)
        self.reason = reason


class StateCorruption(BinaryAnalysisError):
    """Raised when the evidence chain's internal state is detected to be inconsistent.

    Corresponds to ``STATE_CORRUPTION`` (§5.1).  The full evidence-chain
    snapshot is written to the audit log before analysis terminates.  This
    always indicates an implementation bug, not a normal operating condition.
    """

    error_code = "STATE_CORRUPTION"
