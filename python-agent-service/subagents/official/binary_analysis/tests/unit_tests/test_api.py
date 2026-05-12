"""Unit tests for ``binary_analysis.api.analyze_binary`` (C15, US-01 · C13 FR-08/FR-30).

Coverage:
- C15-AC2: thin wrapper returns a :class:`ReportV1` when delegated to a
  caller-injected runner (full production wiring lives behind F-manual).
- C15-AC3 API side: each entry-layer validation failure
  (non-existent / not-a-regular-file / unreadable / size-exceeded)
  raises :class:`EntryFormatUnsupported` per §3.3 + IR-08 + FR-01 AC-9.
- IR-08: Unicode / whitespace file names resolve via
  ``Path.expanduser().resolve(strict=True)``.
- C13-AC1: new configurability params forwarded to runner (FR-08 AC-2/3 · FR-30 AC-4).
- C13-AC2: token_budget above hard cap is capped + warns.
- C13-AC3: env ``DEEPAGENT_TOKEN_BUDGET`` honoured + overridable by caller arg.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from api import _DEFAULT_LANGGRAPH_RECURSION_LIMIT, analyze_binary
from config import (
    DEFAULT_MAX_RECURSION_DEPTH,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_TOKEN_BUDGET,
    TOKEN_BUDGET_HARD_CAP,
    document_settings,
)
from config import (
    settings as _settings_factory,
)
from errors import EntryFormatUnsupported
from evidence_chain.store import EvidenceChainStore
from schema.evidence_chain import Bucket
from schema.indicator import Indicator, Severity
from schema.report import ReportV1
from tools.report_gen import build_report_v1


@pytest.fixture(autouse=True)
def _reset_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each test sees a fresh ``Settings`` and ``DocumentSettings`` singleton.

    ``settings()`` is ``@lru_cache`` and its ``validate_e2b_credentials``
    raises when ``BINARY_ANALYSIS_USE_E2B`` (default true) is set without
    an API key, so we force the flag off in the unit-test environment.
    """
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    _settings_factory.cache_clear()
    document_settings.cache_clear()
    yield
    _settings_factory.cache_clear()
    document_settings.cache_clear()


def _stub_report(analysis_id: str = "aid-stub") -> ReportV1:
    """Build a minimal ``ReportV1`` via the real report builder."""
    store = EvidenceChainStore(analysis_id=analysis_id)
    store.append(
        Bucket.file_meta,
        Indicator(
            source_fr="FR-01",
            indicator_type="file_meta",
            severity=Severity.INFO,
            kind="fact",
            data={
                "absolute_path": "/workspace/aid/sample.bin",
                "size_bytes": 64,
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
    return build_report_v1(store.snapshot(), analysis_id=analysis_id)


def test_default_langgraph_recursion_limit() -> None:
    """F-manual default runner uses this cap when env override is absent."""
    assert _DEFAULT_LANGGRAPH_RECURSION_LIMIT == 500


# ---------------------------------------------------------------------------
# C15-AC2 happy path — runner delegation
# ---------------------------------------------------------------------------


class TestRunnerDelegation:
    def test_returns_report_v1_via_injected_runner(self, tmp_path: Path) -> None:
        """C15-AC2: valid sample + stub runner → ``ReportV1`` instance."""
        sample = tmp_path / "sample.exe"
        sample.write_bytes(b"MZ" + b"\x00" * 128)

        captured: dict[str, object] = {}
        stub = _stub_report()

        def runner(
            *,
            sample_path: Path,
            output_dir: Path,
            use_e2b: bool,
            analysis_id: str,
            **kwargs: object,
        ) -> ReportV1:
            captured["sample_path"] = sample_path
            captured["output_dir"] = output_dir
            captured["use_e2b"] = use_e2b
            captured["analysis_id"] = analysis_id
            captured.update(kwargs)
            return stub

        out_dir = tmp_path / "out"
        result = analyze_binary(
            sample,
            output_dir=out_dir,
            use_e2b=False,
            runner=runner,
        )

        assert isinstance(result, ReportV1)
        assert result is stub
        assert captured["sample_path"] == sample.resolve(strict=True)
        assert captured["output_dir"] == out_dir.resolve()
        assert captured["use_e2b"] is False
        # ULID: 26-char Crockford base32.
        assert isinstance(captured["analysis_id"], str)
        assert len(captured["analysis_id"]) == 26

    def test_use_e2b_defaults_to_settings(self, tmp_path: Path) -> None:
        """When ``use_e2b=None`` the runner receives ``Settings.use_e2b``."""
        sample = tmp_path / "sample.bin"
        sample.write_bytes(b"MZ" + b"\x00" * 16)

        seen: dict[str, bool] = {}

        def runner(*, use_e2b: bool, **_: object) -> ReportV1:
            seen["use_e2b"] = use_e2b
            return _stub_report()

        analyze_binary(sample, runner=runner)

        # Fixture forces BINARY_ANALYSIS_USE_E2B=false.
        assert seen["use_e2b"] is False

    def test_output_dir_is_created(self, tmp_path: Path) -> None:
        """Entry layer creates a missing ``output_dir`` (thin-wrapper courtesy)."""
        sample = tmp_path / "s.bin"
        sample.write_bytes(b"MZ")
        out_dir = tmp_path / "nested" / "out"

        def runner(**_: object) -> ReportV1:
            return _stub_report()

        analyze_binary(sample, output_dir=out_dir, runner=runner)
        assert out_dir.is_dir()

    def test_default_runner_raises_not_implemented(self, tmp_path: Path) -> None:
        """Default runner pointer is unwired — production assembly is F-manual."""
        sample = tmp_path / "s.bin"
        sample.write_bytes(b"MZ")
        with pytest.raises(NotImplementedError, match="F-manual"):
            analyze_binary(sample)


# ---------------------------------------------------------------------------
# C15-AC3 API side — EntryFormatUnsupported on entry-layer failures
# ---------------------------------------------------------------------------


class TestEntryValidation:
    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does-not-exist.exe"
        with pytest.raises(EntryFormatUnsupported) as excinfo:
            analyze_binary(missing, runner=lambda **_: _stub_report())
        assert excinfo.value.error_code == "ENTRY_FORMAT_UNSUPPORTED"
        assert excinfo.value.details["reason"] == "path_not_found"

    def test_directory_raises(self, tmp_path: Path) -> None:
        with pytest.raises(EntryFormatUnsupported) as excinfo:
            analyze_binary(tmp_path, runner=lambda **_: _stub_report())
        assert excinfo.value.details["reason"] == "not_a_regular_file"

    @pytest.mark.skipif(
        sys.platform.startswith("win"),
        reason="POSIX chmod semantics; Windows ACLs differ.",
    )
    def test_unreadable_raises(self, tmp_path: Path) -> None:
        sample = tmp_path / "locked.bin"
        sample.write_bytes(b"MZ")
        try:
            sample.chmod(0o000)
            if os.access(sample, os.R_OK):
                pytest.skip("chmod(0o000) is ineffective (e.g. running as root).")
            with pytest.raises(EntryFormatUnsupported) as excinfo:
                analyze_binary(sample, runner=lambda **_: _stub_report())
            assert excinfo.value.details["reason"] == "not_readable"
        finally:
            sample.chmod(0o644)

    def test_oversized_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BINARY_ANALYSIS_MAX_FILE_SIZE_MB", "1")
        _settings_factory.cache_clear()

        sample = tmp_path / "big.bin"
        sample.write_bytes(b"\x00" * (2 * 1024 * 1024))

        with pytest.raises(EntryFormatUnsupported) as excinfo:
            analyze_binary(sample, runner=lambda **_: _stub_report())
        assert excinfo.value.details["reason"] == "size_exceeded"
        assert excinfo.value.details["limit_bytes"] == 1 * 1024 * 1024

    def test_unicode_path_is_resolved(self, tmp_path: Path) -> None:  # noqa: D102
        """IR-08: Unicode + whitespace filenames normalise cleanly."""
        sample = tmp_path / "测试 sample.exe"
        sample.write_bytes(b"MZ")

        captured: dict[str, Path] = {}

        def runner(*, sample_path: Path, **_: object) -> ReportV1:
            captured["p"] = sample_path
            return _stub_report()

        analyze_binary(sample, runner=runner)
        assert captured["p"] == sample.resolve(strict=True)
        assert captured["p"].name == "测试 sample.exe"


# ---------------------------------------------------------------------------
# C13 — configurability params forwarded through analyze_binary (FR-08/FR-30)
# ---------------------------------------------------------------------------


class TestC13ConfigurabilityParams:
    """Runner receives resolved param values; env and defaults respected."""

    def _make_sample(self, tmp_path: Path) -> Path:
        sample = tmp_path / "sample.exe"
        sample.write_bytes(b"MZ" + b"\x00" * 32)
        return sample

    def test_default_params_forwarded_to_runner(self, tmp_path: Path) -> None:
        """When no CLI/caller overrides, runner sees built-in defaults."""
        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(sample, runner=runner)
        assert captured["max_recursion_depth"] == DEFAULT_MAX_RECURSION_DEPTH
        assert captured["token_budget"] == DEFAULT_TOKEN_BUDGET
        assert captured["max_rounds"] == DEFAULT_MAX_ROUNDS
        assert captured["document_tier_override"] is None
        assert captured["analysis_mode"] == "standard"

    def test_caller_params_override_defaults(self, tmp_path: Path) -> None:
        """Caller-supplied params win over env / built-in defaults."""
        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(
            sample,
            runner=runner,
            max_recursion_depth=4,
            token_budget=50_000,
            max_rounds=8,
            document_tier_override="P1",
            analysis_mode="deep",
        )
        assert captured["max_recursion_depth"] == 4
        assert captured["token_budget"] == 50_000
        assert captured["max_rounds"] == 8
        assert captured["document_tier_override"] == "P1"
        assert captured["analysis_mode"] == "deep"

    def test_deep_mode_raises_default_budget_profile(self, tmp_path: Path) -> None:
        """analysis_mode=deep raises token and round defaults unless overridden."""
        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(sample, runner=runner, analysis_mode="deep")
        assert captured["token_budget"] == TOKEN_BUDGET_HARD_CAP
        assert captured["max_rounds"] == 30
        assert captured["max_recursion_depth"] == DEFAULT_MAX_RECURSION_DEPTH

    def test_invalid_analysis_mode_rejected(self, tmp_path: Path) -> None:
        sample = self._make_sample(tmp_path)
        with pytest.raises(ValueError, match="unsupported analysis_mode"):
            analyze_binary(
                sample, runner=lambda **_: _stub_report(), analysis_mode="max"
            )  # type: ignore[arg-type]

    def test_token_budget_above_hard_cap_capped_with_warning(
        self, tmp_path: Path
    ) -> None:
        """token_budget > TOKEN_BUDGET_HARD_CAP → capped + warning."""
        import warnings as _warnings

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        with _warnings.catch_warnings(record=True) as w:
            _warnings.simplefilter("always")
            analyze_binary(sample, runner=runner, token_budget=200_000)

        assert captured["token_budget"] == TOKEN_BUDGET_HARD_CAP
        assert any("120" in str(warning.message) for warning in w), (
            f"Expected hard-cap warning, got: {[str(x.message) for x in w]}"
        )

    def test_env_token_budget_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEEPAGENT_TOKEN_BUDGET env var is picked up when caller passes None."""
        monkeypatch.setenv("DEEPAGENT_TOKEN_BUDGET", "55000")
        document_settings.cache_clear()

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(sample, runner=runner)
        assert captured["token_budget"] == 55_000

    def test_caller_token_budget_overrides_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Caller arg takes priority over DEEPAGENT_TOKEN_BUDGET env var."""
        monkeypatch.setenv("DEEPAGENT_TOKEN_BUDGET", "55000")
        document_settings.cache_clear()

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(sample, runner=runner, token_budget=65_000)
        assert captured["token_budget"] == 65_000

    def test_env_max_recursion_depth_honoured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEEPAGENT_MAX_RECURSION_DEPTH env var is picked up when caller passes None."""
        monkeypatch.setenv("DEEPAGENT_MAX_RECURSION_DEPTH", "5")
        document_settings.cache_clear()

        sample = self._make_sample(tmp_path)
        captured: dict[str, object] = {}

        def runner(**kwargs: object) -> ReportV1:
            captured.update(kwargs)
            return _stub_report()

        analyze_binary(sample, runner=runner)
        assert captured["max_recursion_depth"] == 5
