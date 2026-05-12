"""Unit tests for ``binary_analysis.cli`` (C15, US-01 + A-01 · C13 FR-08/FR-30).

Coverage:
- C15-AC1: ``deepagent-analyze --help`` advertises ``path`` / ``--output-dir`` /
  ``--use-e2b`` / ``--no-use-e2b``; parser composes the mutually exclusive
  flag pair onto a single ``use_e2b`` destination.
- C15-AC1 / AC-3: invalid path → exit code ``2`` with a single-line JSON
  blob on stderr carrying ``error_code="ENTRY_FORMAT_UNSUPPORTED"``.
- Fast-startup invariant (AGENTS.md): the ``binary_analysis.cli`` module
  imports no heavy agent/LLM/LangGraph/deepagents packages at import time.
- C13-AC1: ``--token-budget`` / ``--max-rounds`` / ``--max-recursion-depth``
  / ``--document-tier-override`` are accepted and passed to ``analyze_binary``.
- C13-AC2: ``--token-budget > 120 000`` → capped to 120 000 + warning.
- C13-AC3: env ``DEEPAGENT_TOKEN_BUDGET`` is honoured when no CLI flag given.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import cli
from config import settings as _settings_factory
from schema.report import ReportV1


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    _settings_factory.cache_clear()
    yield
    _settings_factory.cache_clear()


# ---------------------------------------------------------------------------
# C15-AC1 — argparse surface
# ---------------------------------------------------------------------------


class TestArgumentParser:
    def test_help_advertises_all_flags(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Every public flag surfaces in ``--help`` output."""
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--help"])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "deepagent-analyze" in out
        assert "path" in out.lower()
        assert "--output-dir" in out
        assert "--use-e2b" in out
        assert "--no-use-e2b" in out
        # C13 new flags
        assert "--max-recursion-depth" in out
        assert "--token-budget" in out
        assert "--max-rounds" in out
        assert "--document-tier-override" in out

    def test_parser_defaults_use_e2b_to_none(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["sample.bin"])
        assert ns.path == "sample.bin"
        assert ns.use_e2b is None
        assert ns.output_dir is None
        # C13 defaults
        assert ns.max_recursion_depth is None
        assert ns.token_budget is None
        assert ns.max_rounds is None
        assert ns.document_tier_override is None

    def test_parser_parses_use_e2b_true(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["sample.bin", "--use-e2b"])
        assert ns.use_e2b is True

    def test_parser_parses_no_use_e2b(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["sample.bin", "--no-use-e2b"])
        assert ns.use_e2b is False

    def test_parser_rejects_mutually_exclusive_flags(self) -> None:
        parser = cli.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["s.bin", "--use-e2b", "--no-use-e2b"])

    def test_parser_accepts_output_dir(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["s.bin", "--output-dir", "./reports"])
        assert ns.output_dir == "./reports"


# ---------------------------------------------------------------------------
# C15-AC3 — error translation on stderr
# ---------------------------------------------------------------------------


class TestErrorTranslation:
    def test_nonexistent_path_returns_exit_2_with_structured_stderr(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        missing = tmp_path / "does-not-exist.exe"
        code = cli.main([str(missing)])
        assert code == cli.EXIT_ENTRY_FORMAT_UNSUPPORTED == 2

        err = capsys.readouterr().err.strip()
        lines = [ln for ln in err.splitlines() if ln.strip()]
        assert lines, f"expected structured JSON on stderr, got: {err!r}"
        payload = json.loads(lines[-1])
        assert payload["error_code"] == "ENTRY_FORMAT_UNSUPPORTED"
        assert "details" in payload
        assert payload["details"]["reason"] == "path_not_found"
        assert "message" in payload

    def test_domain_error_returns_nonzero(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-entry domain errors exit with a distinct non-zero code."""
        import api as api_mod
        from errors import SandboxUnavailable

        sample = tmp_path / "s.bin"
        sample.write_bytes(b"MZ")

        def boom(**_: object) -> ReportV1:
            raise SandboxUnavailable("E2B offline")

        monkeypatch.setattr(api_mod, "_default_runner", boom)

        code = cli.main([str(sample)])
        assert code == cli.EXIT_DOMAIN_ERROR
        assert code != 0
        assert code != cli.EXIT_ENTRY_FORMAT_UNSUPPORTED

        err = capsys.readouterr().err.strip().splitlines()[-1]
        payload = json.loads(err)
        assert payload["error_code"] == "SANDBOX_UNAVAILABLE"


# ---------------------------------------------------------------------------
# C15-AC1 / AC-2 — happy path (runner injected through ``api._default_runner``)
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_prints_report_summary(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import api as api_mod
        from evidence_chain.store import EvidenceChainStore
        from schema.evidence_chain import Bucket
        from schema.indicator import Indicator, Severity
        from tools.report_gen import build_report_v1

        sample = tmp_path / "sample.exe"
        sample.write_bytes(b"MZ" + b"\x00" * 32)

        def runner(**_: object) -> ReportV1:
            store = EvidenceChainStore(analysis_id="aid-cli")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "mime_type": "application/x-dosexec",
                        "platform": "Windows",
                        "fingerprints": {
                            "sha256": "d" * 64,
                            "md5": "e" * 32,
                            "sha1": "f" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-cli")

        monkeypatch.setattr(api_mod, "_default_runner", runner)

        code = cli.main([str(sample), "--output-dir", str(tmp_path / "out")])
        assert code == 0

        out = capsys.readouterr().out.strip()
        # Single JSON line summary on stdout.
        payload = json.loads(out.splitlines()[-1])
        assert payload["sha256"] == "d" * 64
        assert payload["verdict"] in {
            "MALICIOUS",
            "SUSPICIOUS",
            "BENIGN",
            "UNKNOWN",
        }


# ---------------------------------------------------------------------------
# AGENTS.md fast-startup invariant — no heavy imports from ``cli``
# ---------------------------------------------------------------------------


class TestFastStartup:
    _FORBIDDEN_PREFIXES: tuple[str, ...] = (
        "deepagents",
        "langchain",
        "langgraph",
        # Graph / tool assembly drags in deepagents.
        "analyst_graph",
        "tool_builder",
        "embedded_recursion",
        "tools",
        "sandbox",
    )

    def test_cli_module_imports_no_heavy_deps(self) -> None:
        """Re-importing ``cli`` must not pull any heavy package into sys.modules."""
        # Wipe the heavy entries so we test the module's top-level surface.
        to_purge = [
            name
            for name in list(sys.modules)
            if any(name.startswith(p) for p in self._FORBIDDEN_PREFIXES)
        ]
        for name in to_purge:
            sys.modules.pop(name, None)

        sys.modules.pop("cli", None)
        importlib.import_module("cli")

        leaked: list[str] = [
            name
            for name in sys.modules
            if any(name.startswith(p) for p in self._FORBIDDEN_PREFIXES)
        ]
        assert not leaked, f"cli import leaked heavy modules: {leaked}"

    def test_help_does_not_import_analyst_graph(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--help`` path must not drag in ``analyst_graph``."""
        sys.modules.pop("analyst_graph", None)
        with pytest.raises(SystemExit):
            cli.main(["--help"])
        capsys.readouterr()
        assert "analyst_graph" not in sys.modules


# ---------------------------------------------------------------------------
# C13 — new configurability parameters (FR-08 AC-2/3 · FR-30 AC-4)
# ---------------------------------------------------------------------------


class TestC13ConfigurabilityParameters:
    """Verify that C13 CLI params are parsed and forwarded correctly."""

    def _make_sample(self, tmp_path: Path) -> Path:
        sample = tmp_path / "sample.exe"
        sample.write_bytes(b"MZ" + b"\x00" * 32)
        return sample

    def test_parser_accepts_max_recursion_depth(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["s.bin", "--max-recursion-depth", "3"])
        assert ns.max_recursion_depth == 3

    def test_parser_accepts_token_budget(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["s.bin", "--token-budget", "50000"])
        assert ns.token_budget == 50_000

    def test_parser_accepts_max_rounds(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["s.bin", "--max-rounds", "10"])
        assert ns.max_rounds == 10

    def test_parser_accepts_document_tier_override(self) -> None:
        parser = cli.build_parser()
        for tier in ("P0", "P1", "P2"):
            ns = parser.parse_args(["s.bin", "--document-tier-override", tier])
            assert ns.document_tier_override == tier

    def test_parser_accepts_analysis_mode(self) -> None:
        parser = cli.build_parser()
        ns = parser.parse_args(["s.bin", "--analysis-mode", "deep"])
        assert ns.analysis_mode == "deep"

    def test_parser_rejects_invalid_document_tier(self) -> None:
        parser = cli.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["s.bin", "--document-tier-override", "P3"])

    def test_token_budget_above_hard_cap_is_capped_with_warning(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--token-budget 150000 → effective value 120000 + warning on stderr."""
        import api as api_mod

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            from evidence_chain.store import EvidenceChainStore
            from schema.evidence_chain import Bucket
            from schema.indicator import Indicator, Severity
            from tools.report_gen import build_report_v1

            store = EvidenceChainStore(analysis_id="aid-cap")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "mime_type": "application/x-dosexec",
                        "platform": "Windows",
                        "fingerprints": {
                            "sha256": "a" * 64,
                            "md5": "b" * 32,
                            "sha1": "c" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-cap")

        monkeypatch.setattr(api_mod, "_default_runner", runner)
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            code = cli.main(
                [str(sample), "--token-budget", "150000", "--output-dir", str(tmp_path)]
            )

        assert code == 0
        assert captured.get("token_budget") == 120_000
        assert any("120" in str(warning.message) for warning in w), (
            f"Expected warning about hard cap, got: {[str(x.message) for x in w]}"
        )

    def test_max_recursion_depth_forwarded_to_runner(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--max-recursion-depth 3 → runner receives max_recursion_depth=3."""
        import api as api_mod

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            from evidence_chain.store import EvidenceChainStore
            from schema.evidence_chain import Bucket
            from schema.indicator import Indicator, Severity
            from tools.report_gen import build_report_v1

            store = EvidenceChainStore(analysis_id="aid-rd")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "mime_type": "application/x-dosexec",
                        "platform": "Windows",
                        "fingerprints": {
                            "sha256": "b" * 64,
                            "md5": "c" * 32,
                            "sha1": "d" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-rd")

        monkeypatch.setattr(api_mod, "_default_runner", runner)
        code = cli.main(
            [
                str(sample),
                "--max-recursion-depth",
                "3",
                "--output-dir",
                str(tmp_path),
            ]
        )
        assert code == 0
        assert captured.get("max_recursion_depth") == 3
        assert captured.get("analysis_mode") == "standard"

    def test_analysis_mode_forwarded_to_runner(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--analysis-mode deep → runner receives analysis_mode=deep."""
        import api as api_mod

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            from evidence_chain.store import EvidenceChainStore
            from schema.evidence_chain import Bucket
            from schema.indicator import Indicator, Severity
            from tools.report_gen import build_report_v1

            store = EvidenceChainStore(analysis_id="aid-mode")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "fingerprints": {
                            "sha256": "4" * 64,
                            "md5": "5" * 32,
                            "sha1": "6" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-mode")

        monkeypatch.setattr(api_mod, "_default_runner", runner)
        code = cli.main(
            [str(sample), "--analysis-mode", "deep", "--output-dir", str(tmp_path)]
        )
        assert code == 0
        assert captured.get("analysis_mode") == "deep"

    def test_env_token_budget_honoured_when_no_cli_flag(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """DEEPAGENT_TOKEN_BUDGET=60000 is used when --token-budget is absent."""
        import api as api_mod
        from config import document_settings

        monkeypatch.setenv("DEEPAGENT_TOKEN_BUDGET", "60000")
        document_settings.cache_clear()

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            from evidence_chain.store import EvidenceChainStore
            from schema.evidence_chain import Bucket
            from schema.indicator import Indicator, Severity
            from tools.report_gen import build_report_v1

            store = EvidenceChainStore(analysis_id="aid-env")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "mime_type": "application/x-dosexec",
                        "platform": "Windows",
                        "fingerprints": {
                            "sha256": "e" * 64,
                            "md5": "f" * 32,
                            "sha1": "0" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-env")

        monkeypatch.setattr(api_mod, "_default_runner", runner)
        code = cli.main([str(sample), "--output-dir", str(tmp_path)])
        assert code == 0
        assert captured.get("token_budget") == 60_000
        document_settings.cache_clear()

    def test_cli_token_budget_overrides_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI --token-budget takes precedence over DEEPAGENT_TOKEN_BUDGET."""
        import api as api_mod
        from config import document_settings

        monkeypatch.setenv("DEEPAGENT_TOKEN_BUDGET", "60000")
        document_settings.cache_clear()

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            from evidence_chain.store import EvidenceChainStore
            from schema.evidence_chain import Bucket
            from schema.indicator import Indicator, Severity
            from tools.report_gen import build_report_v1

            store = EvidenceChainStore(analysis_id="aid-pri")
            store.append(
                Bucket.file_meta,
                Indicator(
                    source_fr="FR-01",
                    indicator_type="file_meta",
                    severity=Severity.INFO,
                    kind="fact",
                    data={
                        "absolute_path": "/workspace/aid/sample.bin",
                        "size_bytes": 33,
                        "format": "PE32",
                        "arch": "x86_64",
                        "mime_type": "application/x-dosexec",
                        "platform": "Windows",
                        "fingerprints": {
                            "sha256": "1" * 64,
                            "md5": "2" * 32,
                            "sha1": "3" * 40,
                        },
                    },
                ),
            )
            return build_report_v1(store.snapshot(), analysis_id="aid-pri")

        monkeypatch.setattr(api_mod, "_default_runner", runner)
        code = cli.main(
            [str(sample), "--token-budget", "70000", "--output-dir", str(tmp_path)]
        )
        assert code == 0
        assert captured.get("token_budget") == 70_000
        document_settings.cache_clear()


def test_console_script_registered() -> None:
    """pyproject.toml exposes the ``deepagent-analyze`` console script."""
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        pytest.skip("importlib.metadata.entry_points unavailable")

    eps: Any = entry_points()
    group = (
        eps.select(group="console_scripts")
        if hasattr(eps, "select")
        else eps.get("console_scripts", [])
    )
    names = {ep.name: ep.value for ep in group}
    assert "deepagent-analyze" in names
    assert names["deepagent-analyze"] == "cli:main"
