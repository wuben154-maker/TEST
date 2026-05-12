"""Console entry point for the BinaryAnalyst agent.

Registered as the ``deepagent-analyze`` console script in
``pyproject.toml``.  The module layout is deliberately narrow to satisfy
the AGENTS.md CLI start-up guidance: nothing from
``analyst_graph`` / ``binary_analysis.api`` / deepagents /
LangChain is imported at module load time.  Heavy imports happen inside
:func:`main` after ``argparse`` has accepted the arguments so that
``deepagent-analyze --help`` and ``--version`` remain instantaneous.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections.abc import Sequence

#: Hard cap for ``--token-budget``; mirrors :data:`~config.TOKEN_BUDGET_HARD_CAP`.
_TOKEN_BUDGET_HARD_CAP: int = 120_000

EXIT_OK: int = 0
EXIT_ENTRY_FORMAT_UNSUPPORTED: int = 2
EXIT_DOMAIN_ERROR: int = 3
EXIT_UNEXPECTED_ERROR: int = 4


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser.

    Kept as a module-level helper so unit tests can assert the flag
    surface without driving :func:`main` end-to-end.

    Returns:
        Configured :class:`argparse.ArgumentParser` for
        ``deepagent-analyze``.
    """
    parser = argparse.ArgumentParser(
        prog="deepagent-analyze",
        description=(
            "Run the BinaryAnalyst static analysis agent on a suspicious "
            "PE / ELF / Mach-O sample and emit a JSON + Markdown report."
        ),
    )
    parser.add_argument(
        "path",
        metavar="PATH",
        help=(
            "filesystem path to the sample (absolute or relative; Unicode "
            "and whitespace characters are supported)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        metavar="PATH",
        default=None,
        help=(
            "directory to write <sha256>.report.{json,md} into; defaults "
            "to the current working directory."
        ),
    )
    sandbox_group = parser.add_mutually_exclusive_group()
    sandbox_group.add_argument(
        "--use-e2b",
        dest="use_e2b",
        action="store_true",
        default=None,
        help=(
            "force the remote E2B sandbox backend for this run "
            "(overrides BINARY_ANALYSIS_USE_E2B)."
        ),
    )
    sandbox_group.add_argument(
        "--no-use-e2b",
        dest="use_e2b",
        action="store_false",
        default=None,
        help="force the local subprocess sandbox fallback for this run.",
    )

    # ------------------------------------------------------------------
    # C13: configurability parameters (FR-08 AC-2/3 · FR-30 AC-4)
    # ------------------------------------------------------------------
    parser.add_argument(
        "--max-recursion-depth",
        dest="max_recursion_depth",
        type=int,
        default=None,
        metavar="INT",
        help=(
            "override the maximum sub-agent recursion depth for document "
            "analysis (FR-30 AC-4).  Falls back to DEEPAGENT_MAX_RECURSION_DEPTH "
            "or the built-in default of 2."
        ),
    )
    parser.add_argument(
        "--token-budget",
        dest="token_budget",
        type=int,
        default=None,
        metavar="INT",
        help=(
            "override the agent token budget for this run (NFR-05).  "
            "Values above 120 000 are capped to 120 000 and a warning is "
            "emitted.  Falls back to DEEPAGENT_TOKEN_BUDGET or 80 000."
        ),
    )
    parser.add_argument(
        "--max-rounds",
        dest="max_rounds",
        type=int,
        default=None,
        metavar="INT",
        help=(
            "override the maximum agent reasoning rounds (NFR-07).  "
            "Falls back to DEEPAGENT_MAX_ROUNDS or 15."
        ),
    )
    parser.add_argument(
        "--document-tier-override",
        dest="document_tier_override",
        choices=["P0", "P1", "P2"],
        default=None,
        metavar="P0|P1|P2",
        help=(
            "debug: force a specific document-analysis tier, bypassing the "
            "automatic tier detection in identify_file."
        ),
    )
    parser.add_argument(
        "--analysis-mode",
        dest="analysis_mode",
        choices=["standard", "deep"],
        default="standard",
        metavar="standard|deep",
        help=(
            "analysis profile. standard keeps default budgets; deep raises "
            "token/round defaults for nested payload analysis unless explicit "
            "budget flags or DEEPAGENT_* env vars are supplied."
        ),
    )
    return parser


def _load_cli_dotenv() -> None:
    """Populate process env from a sibling ``.env`` file (F-manual wiring).

    The loader is invoked from :func:`main` (never at module import) so
    ``test_api.py`` — which bypasses the CLI and expects the unit-test
    env to stay clean — keeps seeing an empty provider-key surface.

    Loading is best-effort: when ``python-dotenv`` or the ``.env`` file
    is missing the CLI carries on with whatever the process environment
    already contains.  ``override=False`` is intentional: monkeypatched /
    explicitly exported variables always win over ``.env`` values.
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return

    import pathlib  # noqa: PLC0415

    candidates = [
        pathlib.Path.cwd() / ".env",
        pathlib.Path(__file__).resolve().parent / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def _emit_structured_error(
    *,
    error_code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> None:
    """Write a single-line JSON error blob to stderr."""
    payload: dict[str, object] = {
        "error_code": error_code,
        "message": message,
        "details": details or {},
    }
    sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def _emit_report_summary(report: object) -> None:
    """Write a single-line JSON summary of the report to stdout."""
    fingerprints = getattr(report, "fingerprints", None)
    verdict = getattr(report, "verdict", None)
    escalation = getattr(report, "escalation_recommendation", None)
    summary: dict[str, object] = {
        "sha256": getattr(fingerprints, "sha256", None),
        "verdict": getattr(getattr(verdict, "label", None), "value", None),
        "risk_score": getattr(getattr(report, "risk_score", None), "value", None),
        "escalation": getattr(getattr(escalation, "level", None), "value", None),
        "schema_version": getattr(report, "schema_version", None),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``deepagent-analyze`` with ``argv`` (defaults to :data:`sys.argv`).

    The function is exposed as the ``deepagent-analyze`` console script
    and is the main integration point exercised by
    ``tests/unit_tests/test_cli.py``.

    Args:
        argv: Argument vector excluding the program name.  ``None`` falls
            back to ``sys.argv[1:]`` (argparse default).

    Returns:
        Process exit code:

        - ``0`` — analysis succeeded.
        - ``2`` — entry-layer validation failed
          (``ENTRY_FORMAT_UNSUPPORTED``; E2E-01 E1).
        - ``3`` — other :class:`BinaryAnalysisError` propagated from the
          Agent / Tool layers.
        - ``4`` — unexpected non-domain exception.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Heavy imports are deferred so --help / argparse validation stay fast.
    _load_cli_dotenv()
    from api import analyze_binary  # noqa: PLC0415
    from errors import (  # noqa: PLC0415
        BinaryAnalysisError,
        EntryFormatUnsupported,
    )

    # Enforce the hard cap on --token-budget before delegating (FR-08 AC-2).
    token_budget = args.token_budget
    if token_budget is not None and token_budget > _TOKEN_BUDGET_HARD_CAP:
        warnings.warn(
            f"--token-budget {token_budget} exceeds the hard cap "
            f"{_TOKEN_BUDGET_HARD_CAP}; capped to {_TOKEN_BUDGET_HARD_CAP}.",
            stacklevel=1,
        )
        token_budget = _TOKEN_BUDGET_HARD_CAP

    try:
        report = analyze_binary(
            args.path,
            output_dir=args.output_dir,
            use_e2b=args.use_e2b,
            max_recursion_depth=args.max_recursion_depth,
            token_budget=token_budget,
            max_rounds=args.max_rounds,
            document_tier_override=args.document_tier_override,
            analysis_mode=args.analysis_mode,
        )
    except EntryFormatUnsupported as exc:
        _emit_structured_error(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )
        return EXIT_ENTRY_FORMAT_UNSUPPORTED
    except BinaryAnalysisError as exc:
        _emit_structured_error(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )
        return EXIT_DOMAIN_ERROR
    except Exception as exc:  # noqa: BLE001
        _emit_structured_error(
            error_code="UNEXPECTED_ERROR",
            message=str(exc) or exc.__class__.__name__,
            details={"exception_type": exc.__class__.__name__},
        )
        return EXIT_UNEXPECTED_ERROR

    _emit_report_summary(report)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
