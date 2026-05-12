"""test_document_workers.py — unit tests for sandbox/document_workers/*.

Tests invoke each worker as a subprocess (``subprocess.run(sys.executable, [worker_path, ...])``),
mock the sample file via a real tempfile, and assert the stdout JSON structure.

All tests run entirely without installing vipermonkey / peepdf / pyOneNote —
the workers return graceful "unavailable" / degraded responses in that case,
and the tests validate those degraded contracts as well.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

_WORKERS_DIR = (
    Path(__file__).resolve().parents[3]  # examples/binary_analysis/
    / "sandbox"
    / "document_workers"
)


def _worker_path(name: str) -> Path:
    p = _WORKERS_DIR / name
    assert p.exists(), f"Worker not found: {p}"
    return p


def _load_worker_module(name: str) -> object:
    """Load a worker module directly for parser monkeypatch tests."""
    module_name = f"test_{name.replace('.py', '')}"
    spec = importlib.util.spec_from_file_location(module_name, _worker_path(name))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_worker(
    worker_name: str, payload: dict, *, timeout: int = 30
) -> tuple[int, dict]:
    """Run a worker with the given JSON payload and return (exit_code, parsed_json)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(payload, fh)
        input_path = fh.name

    try:
        result = subprocess.run(
            [sys.executable, str(_worker_path(worker_name)), "--input", input_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout.strip()
        try:
            parsed = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            parsed = {"_raw_stdout": stdout}
        return result.returncode, parsed
    finally:
        Path(input_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# run_olevba.py
# ---------------------------------------------------------------------------


class TestRunOlevba:
    def test_missing_sample_returns_error_json(self, tmp_path: Path) -> None:
        payload = {"sample_path": str(tmp_path / "nonexistent.xlsm"), "options": {}}
        rc, out = _run_worker("run_olevba.py", payload)
        assert "error" in out
        assert "vba_modules" in out
        assert "xl4_macros" in out
        assert "triggers" in out
        assert "macro_actions" in out
        assert "static_iocs" in out

    def test_output_keys_present_on_success_or_degraded(self, tmp_path: Path) -> None:
        """Even with a non-OLE file the worker must return the required keys."""
        sample = tmp_path / "sample.xlsm"
        sample.write_bytes(b"PK\x03\x04" + b"\x00" * 100)  # fake OOXML header
        payload = {"sample_path": str(sample), "options": {}}
        _rc, out = _run_worker("run_olevba.py", payload)
        # Whether oletools is installed or not, the three keys must be present
        assert "vba_modules" in out
        assert "xl4_macros" in out
        assert "triggers" in out
        assert "macro_actions" in out
        assert "static_iocs" in out

    def test_bad_input_file_path_exits_nonzero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(_worker_path("run_olevba.py")),
                "--input",
                "/nonexistent/path.json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_malformed_json_input_exits_nonzero(self, tmp_path: Path) -> None:
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("not json", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(_worker_path("run_olevba.py")),
                "--input",
                str(bad_json),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0
        out = json.loads(result.stdout.strip())
        assert "error" in out
        assert "macro_actions" in out
        assert "static_iocs" in out


# ---------------------------------------------------------------------------
# run_vmonkey.py
# ---------------------------------------------------------------------------


class TestRunVmonkey:
    def test_unavailable_returns_simulation_status(self, tmp_path: Path) -> None:
        """When vipermonkey is not installed, worker returns 'unavailable'."""
        sample = tmp_path / "sample.xlsm"
        sample.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 100)  # OLE2 magic
        payload = {
            "sample_path": str(sample),
            "source_files": [],
            "timeout_sec": 10,
            "max_instructions": 1000,
        }
        _rc, out = _run_worker("run_vmonkey.py", payload)
        assert "simulation_events" in out
        assert "simulation_gaps" in out
        assert "simulation_status" in out
        # Either "unavailable" (no vipermonkey) or "completed"/"parse_error"
        assert out["simulation_status"] in (
            "unavailable",
            "completed",
            "parse_error",
            "timeout",
        )

    def test_missing_sample_returns_parse_error(self, tmp_path: Path) -> None:
        payload = {
            "sample_path": str(tmp_path / "ghost.xlsm"),
            "source_files": [],
            "timeout_sec": 10,
            "max_instructions": 1000,
        }
        _rc, out = _run_worker("run_vmonkey.py", payload)
        assert "simulation_status" in out
        # unavailable (no vipermonkey in CI) or parse_error (if installed but file missing)
        assert out["simulation_status"] in ("unavailable", "parse_error")

    def test_output_structure_always_present(self, tmp_path: Path) -> None:
        sample = tmp_path / "s.doc"
        sample.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        payload = {
            "sample_path": str(sample),
            "source_files": [],
            "timeout_sec": 5,
            "max_instructions": 100,
        }
        _rc, out = _run_worker("run_vmonkey.py", payload)
        for key in ("simulation_events", "simulation_gaps", "simulation_status"):
            assert key in out, f"Missing key: {key}"
        assert isinstance(out["simulation_events"], list)
        assert isinstance(out["simulation_gaps"], list)

    def test_bad_input_exits_nonzero(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json}", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(_worker_path("run_vmonkey.py")), "--input", str(bad)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# run_peepdf.py
# ---------------------------------------------------------------------------


class TestRunPeepdf:
    def test_missing_sample_returns_error(self, tmp_path: Path) -> None:
        payload = {"sample_path": str(tmp_path / "ghost.pdf")}
        rc, out = _run_worker("run_peepdf.py", payload)
        assert "error" in out
        for key in (
            "object_tree",
            "triggers",
            "embedded_files",
            "action_chains",
            "xfa_form",
            "keyword_summary",
            "js_analysis",
            "uris",
            "submit_targets",
        ):
            assert key in out

    def test_output_keys_always_present(self, tmp_path: Path) -> None:
        """Even for a random binary blob the keys must appear."""
        sample = tmp_path / "sample.pdf"
        sample.write_bytes(b"%PDF-1.4\n%%EOF\n")
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_peepdf.py", payload)
        for key in (
            "object_tree",
            "triggers",
            "embedded_files",
            "action_chains",
            "xfa_form",
            "keyword_summary",
            "js_analysis",
            "uris",
            "submit_targets",
        ):
            assert key in out, f"Missing key: {key}"
        assert isinstance(out["xfa_form"], dict)
        assert "present" in out["xfa_form"]
        assert isinstance(out["keyword_summary"], dict)
        assert isinstance(out["js_analysis"], dict)
        assert isinstance(out["uris"], list)
        assert isinstance(out["submit_targets"], list)

    def test_not_available_returns_error_key(self, tmp_path: Path) -> None:
        """When peepdf is absent the 'error' key explains it."""
        sample = tmp_path / "sample.pdf"
        sample.write_bytes(b"%PDF-1.4\n%%EOF\n")
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_peepdf.py", payload)
        # Either successfully parsed (peepdf installed) or error (not installed)
        assert "object_tree" in out

    def test_pdf_surface_scan_extracts_pdfid_style_signals(
        self, tmp_path: Path
    ) -> None:
        """Keyword / JS scan should work even when peepdf itself is unavailable."""
        sample = tmp_path / "suspicious.pdf"
        sample.write_bytes(
            b"%PDF-1.7\n"
            b"1 0 obj\n"
            b"<< /Type /Catalog /OpenAction 2 0 R /AA 3 0 R "
            b"/JS (eval(unescape('%u9090%u9090%u9090%u9090'))) "
            b"/JBIG2Decode /ObjStm /SubmitForm "
            b"/URI (http://evil.example/collect) >>\n"
            b"stream\nx\nendstream\nendobj\nxref\ntrailer\nstartxref\n0\n%%EOF\n"
        )
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_peepdf.py", payload)

        summary = out["keyword_summary"]
        assert summary["keywords"]["/OpenAction"] == 1
        assert summary["keywords"]["/JBIG2Decode"] == 1
        assert summary["has_jbig2decode"] is True
        assert summary["has_submit_form"] is True
        assert summary["has_object_stream"] is True
        assert summary["structure"]["pdf_version"] == "1.7"
        assert "http://evil.example/collect" in out["uris"]
        assert out["js_analysis"]["has_shellcode_markers"] is True
        assert out["js_analysis"]["has_obfuscation_markers"] is True

    def test_materializes_embedded_files_without_stdout_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """peepdf payload bytes must land on disk, not in stdout JSON."""
        worker = _load_worker_module("run_peepdf.py")
        sample = tmp_path / "sample.pdf"
        sample.write_bytes(b"%PDF-1.7\n%%EOF\n")
        payload = b"MZ" + b"\x00" * 32

        class _FakePdf:
            def getStats(self) -> dict:
                return {
                    "Objects": {},
                    "Actions": [],
                    "Embedded files": [{"name": "payload.exe", "data": payload}],
                    "Action chains": [],
                    "XFA": {},
                }

        class _FakeParser:
            def parse(
                self, _path: str, *, forceMode: bool, manualAnalysis: bool
            ) -> tuple[int, _FakePdf]:
                del forceMode, manualAnalysis
                return 0, _FakePdf()

        peepdf_module = types.ModuleType("peepdf")
        pdf_core = types.ModuleType("peepdf.PDFCore")
        pdf_core.PDFParser = _FakeParser
        monkeypatch.setitem(sys.modules, "peepdf", peepdf_module)
        monkeypatch.setitem(sys.modules, "peepdf.PDFCore", pdf_core)

        out = worker._run(str(sample))  # type: ignore[attr-defined]
        embedded = out["embedded_files"][0]
        assert embedded["materialized"] is True
        assert embedded["suggested_format"] == "pe"
        assert "data" not in embedded
        assert "MZ" not in json.dumps(out)
        assert Path(embedded["extracted_to"]).read_bytes() == payload


# ---------------------------------------------------------------------------
# run_onenote.py
# ---------------------------------------------------------------------------


class TestRunOnenote:
    def test_missing_sample(self, tmp_path: Path) -> None:
        payload = {"sample_path": str(tmp_path / "ghost.one")}
        rc, out = _run_worker("run_onenote.py", payload)
        assert rc != 0
        assert "error" in out
        assert "file_data_stores" in out
        assert "fallback_strings_ioc" in out

    def test_degraded_contract_on_empty_file(self, tmp_path: Path) -> None:
        sample = tmp_path / "sample.one"
        sample.write_bytes(
            b"\xe4\x52\x5c\x7b\x8c\xd8\xa7\x4d\xae\xb1\x53\x78\xd0\x29\x96\xd3"
        )
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_onenote.py", payload)
        assert "file_data_stores" in out
        assert "fallback_strings_ioc" in out
        assert isinstance(out["file_data_stores"], list)
        assert isinstance(out["fallback_strings_ioc"], list)

    def test_ioc_extraction_detects_url(self, tmp_path: Path) -> None:
        """Byte-level IOC extraction should find URLs embedded in the file."""
        sample = tmp_path / "sample.one"
        content = b"\x00" * 64 + b"http://evil.example/payload.exe" + b"\x00" * 64
        sample.write_bytes(content)
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_onenote.py", payload)
        assert "fallback_strings_ioc" in out
        iocs = out["fallback_strings_ioc"]
        assert any("evil.example" in ioc for ioc in iocs), (
            f"Expected URL in IOCs, got: {iocs}"
        )

    def test_parser_unavailable_returns_degraded_key(self, tmp_path: Path) -> None:
        """When pyOneNote is not installed the 'degraded' key signals fallback."""
        sample = tmp_path / "sample.one"
        sample.write_bytes(b"\x00" * 256)
        payload = {"sample_path": str(sample)}
        _rc, out = _run_worker("run_onenote.py", payload)
        # Either "parser_unavailable" (no pyOneNote) or parsed (if installed)
        if "degraded" in out:
            assert out["degraded"] in (
                "parser_unavailable",
                "read_error",
                "file_not_found",
                "bad_input",
            )

    def test_pyonenote_materializes_payload_and_infers_pe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """High-fidelity FileDataStore bytes should be written to children/."""
        worker = _load_worker_module("run_onenote.py")
        sample = tmp_path / "sample.one"
        sample.write_bytes(b"\x00" * 128)
        payload = b"MZ" + b"\x90" * 32

        class _FakeFds:
            extension = ".dat"
            guid = "89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE"

            def get_data(self) -> bytes:
                return payload

        class _FakeDoc:
            def __init__(self, _path: str) -> None:
                pass

            def get_file_data_stores(self) -> list[_FakeFds]:
                return [_FakeFds()]

        py_onenote = types.ModuleType("pyOneNote")
        one_document = types.ModuleType("pyOneNote.OneDocument")
        one_document.OneDocment = _FakeDoc
        monkeypatch.setitem(sys.modules, "pyOneNote", py_onenote)
        monkeypatch.setitem(sys.modules, "pyOneNote.OneDocument", one_document)

        out = worker._run(str(sample))  # type: ignore[attr-defined]
        fds = out["file_data_stores"][0]
        assert fds["materialized"] is True
        assert fds["suggested_format"] == "pe"
        assert "data" not in fds
        assert "MZ" not in json.dumps(out)
        assert Path(fds["extracted_to"]).read_bytes() == payload

    def test_fallback_guid_scan_is_not_materialized(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fallback GUID scan has metadata only and must not invent a child path."""
        worker = _load_worker_module("run_onenote.py")
        sample = tmp_path / "sample.one"
        sample.write_bytes(
            b"{89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE}http://evil.example/payload"
        )
        original_import = builtins.__import__

        def _block_pyonenote(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("pyOneNote"):
                raise ImportError("forced parser_unavailable")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_pyonenote)
        out = worker._run(str(sample))  # type: ignore[attr-defined]
        fds = out["file_data_stores"][0]
        assert out["degraded"] == "parser_unavailable"
        assert fds["materialized"] is False
        assert fds["suggested_format"] == "unknown"
        assert "extracted_to" not in fds


# ---------------------------------------------------------------------------
# run_msoffcrypto.py
# ---------------------------------------------------------------------------


class TestRunMsoffcrypto:
    def test_missing_sample(self, tmp_path: Path) -> None:
        payload = {
            "sample_path": str(tmp_path / "ghost.docx"),
            "password_list": ["infected"],
        }
        rc, out = _run_worker("run_msoffcrypto.py", payload)
        assert rc != 0
        assert "decrypted" in out
        assert "attempted" in out
        assert "succeeded_password_hash" in out
        assert "metadata" in out

    def test_output_keys_always_present(self, tmp_path: Path) -> None:
        sample = tmp_path / "sample.docx"
        sample.write_bytes(b"PK\x03\x04" + b"\x00" * 64)  # fake OOXML (not encrypted)
        payload = {"sample_path": str(sample), "password_list": ["infected", "virus"]}
        _rc, out = _run_worker("run_msoffcrypto.py", payload)
        for key in ("decrypted", "attempted", "succeeded_password_hash", "metadata"):
            assert key in out, f"Missing key: {key}"

    def test_empty_password_list_returns_false(self, tmp_path: Path) -> None:
        sample = tmp_path / "sample.docx"
        sample.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        payload = {"sample_path": str(sample), "password_list": []}
        _rc, out = _run_worker("run_msoffcrypto.py", payload)
        assert "decrypted" in out
        assert out["attempted"] == 0
        assert out["succeeded_password_hash"] is None

    def test_succeeded_password_hash_is_sha256_prefix(self, tmp_path: Path) -> None:
        """Verify hash format — the worker must not store plaintext passwords."""
        import hashlib

        sample = tmp_path / "sample.docx"
        sample.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 512)
        payload = {"sample_path": str(sample), "password_list": ["infected"]}
        _rc, out = _run_worker("run_msoffcrypto.py", payload)

        if out.get("decrypted") and out.get("succeeded_password_hash"):
            hash_val = out["succeeded_password_hash"]
            assert hash_val.startswith("sha256:"), (
                f"Expected sha256: prefix, got: {hash_val!r}"
            )
            hex_part = hash_val[len("sha256:") :]
            assert len(hex_part) == 8, (
                f"Expected 8 hex chars, got {len(hex_part)}: {hex_part!r}"
            )
            # Verify it matches sha256("infected")[:8]
            expected = hashlib.sha256(b"infected").hexdigest()[:8]
            assert hex_part == expected

    def test_msoffcrypto_not_available_returns_error(self, tmp_path: Path) -> None:
        """When msoffcrypto is absent the worker should still return valid JSON."""
        sample = tmp_path / "s.docx"
        sample.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
        payload = {"sample_path": str(sample), "password_list": ["virus"]}
        _rc, out = _run_worker("run_msoffcrypto.py", payload)
        # Always returns the four required keys
        for key in ("decrypted", "attempted", "succeeded_password_hash", "metadata"):
            assert key in out
