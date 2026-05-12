"""Unit tests for :mod:`tools.file_identify` (C3/C6, FR-01 AC-1~9)."""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from errors import EntryFormatUnsupported, SandboxUnavailable
from evidence_chain.store import EvidenceChainStore
from registry import _LazyBinarySandboxClient
from sandbox.client import SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from schema.document_enums import DocumentFormat, DocumentTier
from schema.evidence_chain import Bucket
from tests.fixtures.binaries import (
    COUNTEREXAMPLE_EMPTY,
    COUNTEREXAMPLE_TEXT,
    COUNTEREXAMPLE_ZIP_AS_EXE,
    MINIMAL_PE32_X86,
    write_sample,
)
from tools.file_identify import FileIdentifyTool, identify_file

# ---------------------------------------------------------------------------
# Document format fixture bytes  (C3 / FR-01 AC-1~8)
#
# Each fixture provides the minimum bytes needed to trigger its magic-number
# or structure check in _detect_document_format without importing real
# Office files into the repository.
# ---------------------------------------------------------------------------

_OLE2_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 500

DOC_BYTES_PDF = b"%PDF-1.4 minimal\n" + b"\x00" * 64
DOC_BYTES_RTF = b"{\\rtf1\\ansi\\deff0{}}" + b"\x00" * 64
DOC_BYTES_OLE2_DOC = _OLE2_HEADER + "WordDocument".encode("utf-16-le") + b"\x00" * 64
DOC_BYTES_OLE2_XLS = _OLE2_HEADER + "Workbook".encode("utf-16-le") + b"\x00" * 64
DOC_BYTES_OLE2_PPT = (
    _OLE2_HEADER + "PowerPoint Document".encode("utf-16-le") + b"\x00" * 64
)
DOC_BYTES_ENCRYPTED_OFFICE = (
    _OLE2_HEADER + "EncryptionInfo".encode("utf-16-le") + b"\x00" * 64
)
DOC_BYTES_OLE2_DOC_WITH_ENCRYPTION_MARKER = (
    _OLE2_HEADER
    + "EncryptionInfo".encode("utf-16-le")
    + b"\x00" * 32
    + "WordDocument".encode("utf-16-le")
    + b"\x00" * 64
)
_OOXML_PREFIX = b"PK\x03\x04" + b"\x00" * 26
DOC_BYTES_OOXML_DOCX = _OOXML_PREFIX + b"wordprocessingml" + b"\x00" * 64
DOC_BYTES_OOXML_XLSX = _OOXML_PREFIX + b"spreadsheetml" + b"\x00" * 64
DOC_BYTES_OOXML_PPTX = _OOXML_PREFIX + b"presentationml" + b"\x00" * 64
DOC_BYTES_ONENOTE = (
    b"\xe4\x52\x5c\x7b\x8c\xd8\xa7\x4d\xae\xb1\x53\x78\xd0\x29\x96\xd3" + b"\x00" * 64
)
DOC_BYTES_HTA = (
    b'<HTA:APPLICATION ID="test"/>\r\n'
    b'<script language="VBScript">\r\n</script>' + b"\x00" * 64
)


def _make_ooxml_zip(entries: dict[str, bytes]) -> bytes:
    """Build a minimal compressed OOXML-like ZIP fixture."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


DOC_BYTES_DOCM_COMPRESSED = _make_ooxml_zip(
    {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Override PartName="/word/document.xml" '
            b'ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/>'
            b'<Override PartName="/word/vbaProject.bin" '
            b'ContentType="application/vnd.ms-office.vbaProject"/>'
            b"</Types>"
        ),
        "word/document.xml": b"<w:document/>",
        "word/vbaProject.bin": b"fake-vba-project",
    }
)
# PDF+PE polyglot: valid PE at offset 0 + PDF magic embedded in the body
DOC_BYTES_POLYGLOT_PDF_PE = MINIMAL_PE32_X86 + b"\x00" * 32 + b"%PDF-1.4 embedded\n"

# ---------------------------------------------------------------------------
# Shared fixtures / fakes
# ---------------------------------------------------------------------------


class _FakeSandboxClient:
    """Minimal in-memory :class:`SandboxClient` for Tool integration tests.

    Captures every ``upload`` call so tests can assert the exact bytes
    delivered to the sandbox.  ``create`` / ``kill`` maintain a simple
    session model matching the real :class:`SandboxSession` contract.
    """

    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes]] = []
        self.created: list[str] = []
        self.downloads: dict[str, bytes] = {}

    async def create(self, analysis_id: str) -> SandboxSession:
        self.created.append(analysis_id)
        session = SandboxSession(
            analysis_id=analysis_id,
            sandbox_id=f"fake-{analysis_id}",
            backend="subprocess",
            workdir=sandbox_workspace(analysis_id),
            created_at=0.0,
        )
        _SESSION_REGISTRY[analysis_id] = session
        return session

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        self.uploads.append((path, data))

    async def exec(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def download(self, session: SandboxSession, path: str) -> bytes:
        del session
        return self.downloads[path]

    async def kill(self, session: SandboxSession) -> None:
        _SESSION_REGISTRY.pop(session.analysis_id, None)


class _CreateFailingSandboxClient(_FakeSandboxClient):
    async def create(self, analysis_id: str) -> SandboxSession:
        raise SandboxUnavailable(
            "sandbox quota exhausted",
            details={"reason": "quota_exhausted", "analysis_id": analysis_id},
        )


class _UploadFailingSandboxClient(_FakeSandboxClient):
    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        raise OSError("network write failed")


class _StaticSamplePathResolver:
    def __init__(self, host_path: Path, display_path: str = "/workspace/sample.exe"):
        self.host_path = host_path
        self.display_path = display_path
        self.calls: list[str] = []

    def resolve(self, path: str) -> SimpleNamespace:
        self.calls.append(path)
        return SimpleNamespace(
            kind="host_upload",
            host_path=self.host_path,
            display_path=self.display_path,
        )


@pytest.fixture(autouse=True)
def _clean_registry():
    _SESSION_REGISTRY.clear()
    yield
    _SESSION_REGISTRY.clear()


@pytest.fixture()
def fake_client() -> _FakeSandboxClient:
    return _FakeSandboxClient()


@pytest.fixture()
def store() -> EvidenceChainStore:
    return EvidenceChainStore(analysis_id="aid-test")


@pytest.fixture()
def tool(
    fake_client: _FakeSandboxClient, store: EvidenceChainStore
) -> FileIdentifyTool:
    return FileIdentifyTool(
        sandbox_client=fake_client,
        store=store,
        max_file_size_mb=1,
    )


# ---------------------------------------------------------------------------
# FR-01 AC-1: path handling  (absolute / relative / Unicode / spaces)
# ---------------------------------------------------------------------------


class TestAC1PathHandling:
    def test_absolute_path_accepted(self, tmp_path: Path):
        sample = write_sample(tmp_path / "sample.exe", "pe32_x86")
        result = identify_file(sample, max_size_mb=1)
        assert result.absolute_path == str(sample)

    def test_relative_path_accepted(self, tmp_path: Path, monkeypatch):
        write_sample(tmp_path / "rel-sample.exe", "pe32_x86")
        monkeypatch.chdir(tmp_path)
        result = identify_file("./rel-sample.exe", max_size_mb=1)
        assert Path(result.absolute_path) == (tmp_path / "rel-sample.exe").resolve()

    def test_unicode_and_space_in_path(self, tmp_path: Path):
        sample = write_sample(tmp_path / "测试 sample.exe", "pe32_x86")
        result = identify_file(sample, max_size_mb=1)
        assert result.absolute_path == str(sample)

    def test_missing_path_raises_entry_format_unsupported(self, tmp_path: Path):
        missing = tmp_path / "does-not-exist.bin"
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(missing, max_size_mb=1)
        assert ei.value.details["reason"] == "path_not_found"

    def test_directory_path_rejected(self, tmp_path: Path):
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(tmp_path, max_size_mb=1)
        assert ei.value.details["reason"] == "not_a_file"


# ---------------------------------------------------------------------------
# FR-01 AC-2: format + architecture identification
# ---------------------------------------------------------------------------


class TestAC2FormatAndArchitecture:
    def test_pe32_x86(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("PE32", "x86")

    def test_pe32plus_x64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32plus_x64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("PE32+", "x64")

    def test_pe_arm64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe_arm64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("PE32+", "ARM64")

    def test_elf64_x64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.out", "elf64_x64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("ELF", "x64")

    def test_elf64_arm64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.out", "elf64_arm64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("ELF", "ARM64")

    def test_macho64_x64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.macho", "macho64_x64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("Mach-O", "x64")

    def test_macho64_arm64(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.macho", "macho64_arm64")
        result = identify_file(sample, max_size_mb=1)
        assert (result.format, result.arch) == ("Mach-O", "ARM64")


# ---------------------------------------------------------------------------
# FR-01 AC-3: routing (PE → full; ELF / Mach-O → structural_only)
# ---------------------------------------------------------------------------


class TestAC3Routing:
    def test_pe_routes_to_full(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        assert identify_file(sample, max_size_mb=1).routing == "full"

    def test_elf_routes_to_structural_only(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.out", "elf64_x64")
        assert identify_file(sample, max_size_mb=1).routing == "structural_only"

    def test_macho_routes_to_structural_only(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.macho", "macho64_x64")
        assert identify_file(sample, max_size_mb=1).routing == "structural_only"


# ---------------------------------------------------------------------------
# FR-01 AC-4: fingerprint set (6 keys for PE, 5 keys otherwise)
# ---------------------------------------------------------------------------


class TestAC4Fingerprints:
    def test_pe_has_six_fingerprint_slots(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        fp = identify_file(sample, max_size_mb=1).fingerprints
        assert set(fp.keys()) == {"md5", "sha1", "sha256", "ssdeep", "tlsh", "imphash"}

    def test_elf_has_five_fingerprint_slots(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.out", "elf64_x64")
        fp = identify_file(sample, max_size_mb=1).fingerprints
        assert set(fp.keys()) == {"md5", "sha1", "sha256", "ssdeep", "tlsh"}

    def test_macho_has_five_fingerprint_slots(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.macho", "macho64_x64")
        fp = identify_file(sample, max_size_mb=1).fingerprints
        assert set(fp.keys()) == {"md5", "sha1", "sha256", "ssdeep", "tlsh"}

    def test_cryptographic_hashes_are_hex_digests(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        fp = identify_file(sample, max_size_mb=1).fingerprints
        assert fp["md5"] is not None and len(fp["md5"]) == 32  # noqa: PLR2004
        assert fp["sha1"] is not None and len(fp["sha1"]) == 40  # noqa: PLR2004
        assert fp["sha256"] is not None and len(fp["sha256"]) == 64  # noqa: PLR2004
        int(fp["md5"], 16)
        int(fp["sha1"], 16)
        int(fp["sha256"], 16)

    def test_cryptographic_hashes_match_known_values(self, tmp_path: Path):
        """Regression guard: computed digests must match hashlib on the same bytes."""
        import hashlib

        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        fp = identify_file(sample, max_size_mb=1).fingerprints
        expected_sha256 = hashlib.sha256(MINIMAL_PE32_X86).hexdigest()
        assert fp["sha256"] == expected_sha256


# ---------------------------------------------------------------------------
# FR-01 AC-5 + AC-7: evidence chain write + sandbox upload + zero-byte leakage
# ---------------------------------------------------------------------------


class TestAC5AndAC7EvidenceAndZeroLeakage:
    async def test_tool_appends_file_meta_indicator(
        self, tmp_path: Path, tool: FileIdentifyTool, store: EvidenceChainStore
    ):
        sample = write_sample(tmp_path / "a.exe", "pe32plus_x64")
        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-ev"})

        file_meta_indicators = store.query(bucket=Bucket.file_meta)
        assert len(file_meta_indicators) == 1
        ind = file_meta_indicators[0]
        assert ind.kind == "fact"
        assert ind.source_fr == "FR-01"
        assert ind.data["format"] == "PE32+"
        assert ind.data["arch"] == "x64"
        assert ind.data["sandbox_path"] == "/workspace/aid-ev/sample.bin"
        assert result["indicator_id"] == ind.id

    async def test_sample_bytes_uploaded_to_sandbox(
        self, tmp_path: Path, tool: FileIdentifyTool, fake_client: _FakeSandboxClient
    ):
        write_sample(tmp_path / "a.exe", "pe32_x86")
        await tool.ainvoke(
            {
                "path": str(tmp_path / "a.exe"),
                "analysis_id": "aid-up",
            }
        )
        assert len(fake_client.uploads) == 1
        dest, uploaded_bytes = fake_client.uploads[0]
        assert dest == "/workspace/aid-up/sample.bin"
        assert uploaded_bytes == MINIMAL_PE32_X86

    async def test_workspace_path_resolved_before_sandbox_upload(
        self,
        tmp_path: Path,
        fake_client: _FakeSandboxClient,
        store: EvidenceChainStore,
    ):
        sample = write_sample(tmp_path / "stored_sample.exe", "pe32_x86")
        resolver = _StaticSamplePathResolver(sample)
        tool = FileIdentifyTool(
            sandbox_client=fake_client,
            store=store,
            max_file_size_mb=1,
            sample_path_resolver=resolver,
        )

        result = await tool.ainvoke(
            {"path": "/workspace/sample.exe", "analysis_id": "aid-resolve"}
        )

        assert result["ok"] is True
        assert resolver.calls == ["/workspace/sample.exe"]
        assert fake_client.uploads == [
            ("/workspace/aid-resolve/sample.bin", MINIMAL_PE32_X86)
        ]
        indicator = store.query(bucket=Bucket.file_meta)[0]
        assert indicator.data["absolute_path"] == "/workspace/sample.exe"

    async def test_tool_return_value_contains_no_raw_bytes(
        self, tmp_path: Path, tool: FileIdentifyTool
    ):
        """FR-01 AC-7 / NFR-03 — serialised return value must not leak sample bytes."""
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-leak"})
        serialised = json.dumps(result, ensure_ascii=False, default=str)

        # Sample bytes in their raw form must NEVER appear in the JSON payload.
        # We probe with a non-printable byte signature that is unlikely to
        # coincide with any metadata field.
        unique_signature = MINIMAL_PE32_X86[64:96]  # straddles PE header region
        assert unique_signature.decode("latin-1") not in serialised

        # Return structure must be a predictable, bounded metadata payload.
        allowed_keys = {
            "ok",
            "indicator_id",
            "format",
            "arch",
            "routing",
            "fingerprints",
            "size_bytes",
            "sandbox_path",
            "coverage_notes",
            # C3 document fields (FR-01 AC-8)
            "document_format",
            "document_tier",
            "is_document",
            "polyglot_document_priority",
        }
        assert set(result.keys()) == allowed_keys

    async def test_tool_reuses_existing_session_when_present(
        self, tmp_path: Path, tool: FileIdentifyTool, fake_client: _FakeSandboxClient
    ):
        write_sample(tmp_path / "a.exe", "pe32_x86")
        pre_existing = await fake_client.create("aid-reuse")
        await tool.ainvoke(
            {
                "path": str(tmp_path / "a.exe"),
                "analysis_id": "aid-reuse",
            }
        )
        assert fake_client.created == ["aid-reuse"]  # exactly one create
        assert fake_client.uploads[0][0] == "/workspace/aid-reuse/sample.bin"
        assert _SESSION_REGISTRY["aid-reuse"] is pre_existing

    async def test_tool_identifies_sandbox_resident_child_sample(
        self,
        tool: FileIdentifyTool,
        fake_client: _FakeSandboxClient,
        store: EvidenceChainStore,
    ):
        """FR-30 child payloads already in a parent sandbox can seed child analysis."""
        parent = await fake_client.create("parent-doc")
        child_path = "/workspace/parent-doc/children/payload.bin"
        fake_client.downloads[child_path] = MINIMAL_PE32_X86

        result = await tool.ainvoke(
            {
                "path": child_path,
                "analysis_id": "child-pe",
            }
        )

        assert result["ok"] is True
        assert result["format"] == "PE32"
        assert result["sandbox_path"] == "/workspace/child-pe/sample.bin"
        assert fake_client.uploads[-1] == (
            "/workspace/child-pe/sample.bin",
            MINIMAL_PE32_X86,
        )
        assert _SESSION_REGISTRY["parent-doc"] is parent
        assert _SESSION_REGISTRY["child-pe"].analysis_id == "child-pe"
        ind = store.query(bucket=Bucket.file_meta)[0]
        assert ind.data["absolute_path"] == child_path

    async def test_virtual_workspace_path_without_active_session_not_sandbox_unavailable(
        self,
        tmp_path: Path,
        tool: FileIdentifyTool,
        fake_client: _FakeSandboxClient,
        store: EvidenceChainStore,
    ):
        """UI-style /workspace/<id>/file must not hit sandbox-resident branch without a session."""
        ui_style = "/workspace/01arbitraryidnotreal/malware.exe"
        result = await tool.ainvoke(
            {"path": ui_style, "analysis_id": "child-pe"},
        )

        assert result["ok"] is False
        assert result["error_code"] == "ENTRY_FORMAT_UNSUPPORTED"
        assert result["details"]["reason"] == "path_not_found"
        facts = store.query(bucket=Bucket.file_meta)
        assert len(facts) == 1
        assert facts[0].indicator_type == "format_unsupported"

    async def test_tool_carves_embedded_pe_child_sample(
        self, tmp_path: Path, fake_client: _FakeSandboxClient, store: EvidenceChainStore
    ):
        """PE32 parents with nested MZ/PE images get child_sample_ref facts."""
        sample = tmp_path / "parent-with-child.exe"
        padding = b"PADDING" * 8
        child_offset = len(MINIMAL_PE32_X86) + len(padding)
        sample.write_bytes(MINIMAL_PE32_X86 + padding + MINIMAL_PE32_X86)
        calls: list[tuple[str, list[dict[str, Any]]]] = []

        async def _handler(
            analysis_id: str, payloads: list[dict[str, Any]]
        ) -> list[dict[str, Any]]:
            calls.append((analysis_id, payloads))
            return [
                {**payload, "child_recursion_status": "completed"}
                for payload in payloads
            ]

        tool = FileIdentifyTool(
            sandbox_client=fake_client,
            store=store,
            max_file_size_mb=1,
            embedded_payload_handler=_handler,
        )

        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-carve"})

        assert len(calls) == 1
        assert calls[0][0] == "aid-carve"
        assert result["embedded_payloads"][0]["child_recursion_status"] == "completed"
        payload = store.query(bucket=Bucket.embedded_payloads)[0]
        assert payload.indicator_type == "child_sample_ref"
        assert payload.kind == "fact"
        assert payload.data["source"] == "pe_carving"
        assert payload.data["source_region"] == "overlay"
        assert payload.data["decoder"] == "none"
        assert payload.data["offset"] == child_offset
        assert payload.data["suggested_format"] == "pe"
        assert payload.data["recursive_ready"] is True
        child_upload = fake_client.uploads[-1]
        assert child_upload[0] == payload.data["extracted_to"]
        assert child_upload[1] == MINIMAL_PE32_X86

    async def test_tool_carves_xor_encoded_embedded_pe_child_sample(
        self, tmp_path: Path, fake_client: _FakeSandboxClient, store: EvidenceChainStore
    ):
        """Single-byte XOR encoded child PE buffers are decoded before upload."""
        sample = tmp_path / "parent-with-xor-child.exe"
        key = 0x23
        encoded_child = bytes(byte ^ key for byte in MINIMAL_PE32_X86)
        padding = b"PAD" * 16
        child_offset = len(MINIMAL_PE32_X86) + len(padding)
        sample.write_bytes(MINIMAL_PE32_X86 + padding + encoded_child)

        tool = FileIdentifyTool(
            sandbox_client=fake_client,
            store=store,
            max_file_size_mb=1,
        )

        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-xor"})

        payload = store.query(bucket=Bucket.embedded_payloads)[0]
        assert result["embedded_payloads"][0]["decoder"] == "xor_single_byte"
        assert payload.data["offset"] == child_offset
        assert payload.data["decoder_metadata"] == {"xor_key": key}
        assert payload.data["source_region"] == "decoded_buffer"
        assert fake_client.uploads[-1][1] == MINIMAL_PE32_X86

    async def test_tool_returns_structured_sandbox_create_failure(
        self, tmp_path: Path, store: EvidenceChainStore
    ):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        tool = FileIdentifyTool(
            sandbox_client=_CreateFailingSandboxClient(),
            store=store,
            max_file_size_mb=1,
        )

        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-create"})

        assert result["ok"] is False
        assert result["error_code"] == "SANDBOX_UNAVAILABLE"
        assert result["reason"] == "quota_exhausted"
        assert store.query(bucket=Bucket.file_meta) == []

    async def test_lazy_sandbox_client_defers_missing_e2b_key_until_tool_use(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        from config import settings as binary_settings

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
        monkeypatch.setenv("E2B_API_KEY", "")
        binary_settings.cache_clear()
        client = _LazyBinarySandboxClient()
        try:
            with pytest.raises(SandboxUnavailable):
                await client.create("aid-no-key")
        finally:
            binary_settings.cache_clear()

    async def test_tool_returns_structured_upload_failure(
        self, tmp_path: Path, store: EvidenceChainStore
    ):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        tool = FileIdentifyTool(
            sandbox_client=_UploadFailingSandboxClient(),
            store=store,
            max_file_size_mb=1,
        )

        result = await tool.ainvoke({"path": str(sample), "analysis_id": "aid-upload"})

        assert result["ok"] is False
        assert result["error_code"] == "SANDBOX_UNAVAILABLE"
        assert result["reason"] == "sample_upload_failed"
        assert result["details"]["error_type"] == "OSError"
        assert store.query(bucket=Bucket.file_meta) == []


# ---------------------------------------------------------------------------
# FR-01 AC-6: unsupported format → EntryFormatUnsupported
# ---------------------------------------------------------------------------


class TestAC6UnsupportedFormat:
    def test_plain_text_rejected(self, tmp_path: Path):
        path = tmp_path / "note.txt"
        path.write_bytes(COUNTEREXAMPLE_TEXT)
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(path, max_size_mb=1)
        assert ei.value.details["reason"] == "unknown_format"

    def test_zip_disguised_as_exe_rejected(self, tmp_path: Path):
        path = tmp_path / "fake.exe"
        path.write_bytes(COUNTEREXAMPLE_ZIP_AS_EXE)
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(path, max_size_mb=1)
        assert ei.value.details["reason"] == "unknown_format"

    def test_empty_file_rejected(self, tmp_path: Path):
        path = tmp_path / "empty.bin"
        path.write_bytes(COUNTEREXAMPLE_EMPTY)
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(path, max_size_mb=1)
        assert ei.value.details["reason"] == "empty_file"

    async def test_tool_returns_structured_format_unsupported(
        self,
        tmp_path: Path,
        tool: FileIdentifyTool,
        store: EvidenceChainStore,
        fake_client: _FakeSandboxClient,
    ):
        path = tmp_path / "note.txt"
        path.write_bytes(COUNTEREXAMPLE_TEXT)
        result = await tool.ainvoke({"path": str(path), "analysis_id": "aid-fail"})
        assert result["ok"] is False
        assert result["error_code"] == "ENTRY_FORMAT_UNSUPPORTED"
        assert result["details"]["reason"] == "unknown_format"
        assert result["format_unsupported"] is True
        # The Agent-facing tool path records the E1 fact but does not upload
        # unsupported bytes into the sandbox.
        facts = store.query(bucket=Bucket.file_meta)
        assert len(facts) == 1
        assert facts[0].indicator_type == "format_unsupported"
        assert facts[0].data["fingerprints"]["sha256"]
        assert fake_client.created == []
        assert fake_client.uploads == []


# ---------------------------------------------------------------------------
# FR-01 AC-8: read-only open, mtime preserved
# ---------------------------------------------------------------------------


class TestAC8ReadOnly:
    def test_identify_does_not_change_mtime(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        original_mtime = os.stat(sample).st_mtime
        identify_file(sample, max_size_mb=1)
        assert os.stat(sample).st_mtime == original_mtime

    def test_identify_does_not_change_bytes(self, tmp_path: Path):
        sample = write_sample(tmp_path / "a.exe", "pe32_x86")
        original_bytes = sample.read_bytes()
        identify_file(sample, max_size_mb=1)
        assert sample.read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# FR-01 AC-9: file size cap (BINARY_ANALYSIS_MAX_FILE_SIZE_MB, default 100 MB)
# ---------------------------------------------------------------------------


class TestAC9SizeCap:
    def test_oversize_file_raises_entry_format_unsupported(self, tmp_path: Path):
        path = tmp_path / "big.bin"
        path.write_bytes(b"\x00" * (2 * 1024 * 1024))  # 2 MiB
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(path, max_size_mb=1)
        assert ei.value.details["reason"] == "size_exceeded"
        assert ei.value.details["max_bytes"] == 1 * 1024 * 1024

    def test_size_cap_uses_settings_default_when_unset(self, monkeypatch):
        """AC-9 default: ``Settings.max_file_size_mb`` defaults to 100 MiB (see C1).

        🟡 The explicit default is not pinned in SPEC / DESIGN — recorded in
        IMPL-PROGRESS.md Phase-S feedback.  This test serves as the
        canonical reference while the spec catches up.
        """
        from config import Settings

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
        monkeypatch.delenv("BINARY_ANALYSIS_MAX_FILE_SIZE_MB", raising=False)
        assert Settings().max_file_size_mb == 100  # noqa: PLR2004


# ---------------------------------------------------------------------------
# C3 / FR-01 AC-1~8: Document format identification
# ---------------------------------------------------------------------------


class TestDocumentFormatIdentification:
    """FR-01 AC-1: Each of the 11 document formats is detected and labelled."""

    def _write(self, path: Path, data: bytes) -> Path:
        path.write_bytes(data)
        return path

    def test_pdf_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.pdf", DOC_BYTES_PDF)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.PDF
        assert result.is_document is True

    def test_rtf_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.rtf", DOC_BYTES_RTF)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.RTF
        assert result.is_document is True

    def test_ole2_doc_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.doc", DOC_BYTES_OLE2_DOC)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OLE2_DOC
        assert result.is_document is True

    def test_ole2_doc_wins_over_encryption_marker(self, tmp_path: Path):
        p = self._write(
            tmp_path / "protected.doc", DOC_BYTES_OLE2_DOC_WITH_ENCRYPTION_MARKER
        )
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OLE2_DOC
        assert result.document_tier == DocumentTier.P0
        assert result.is_document is True

    def test_ole2_xls_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.xls", DOC_BYTES_OLE2_XLS)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OLE2_XLS
        assert result.is_document is True

    def test_ole2_ppt_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.ppt", DOC_BYTES_OLE2_PPT)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OLE2_PPT
        assert result.is_document is True

    def test_encrypted_office_detected(self, tmp_path: Path):
        """FR-01 AC-4: encrypted Office identified from magic + stream name only."""
        p = self._write(tmp_path / "encrypted.docx", DOC_BYTES_ENCRYPTED_OFFICE)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.ENCRYPTED_OFFICE
        assert result.is_document is True

    def test_ooxml_docx_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.docx", DOC_BYTES_OOXML_DOCX)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OOXML_DOCX_MACRO
        assert result.is_document is True

    def test_compressed_docm_detected_without_raw_content_type_marker(
        self, tmp_path: Path
    ):
        """Real OOXML macro documents should not depend on raw prefix scans."""
        assert b"wordprocessingml" not in DOC_BYTES_DOCM_COMPRESSED[:4096]
        p = self._write(tmp_path / "sample.docm", DOC_BYTES_DOCM_COMPRESSED)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OOXML_DOCX_MACRO
        assert result.document_tier == DocumentTier.P0
        assert result.is_document is True

    def test_ooxml_xlsx_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.xlsx", DOC_BYTES_OOXML_XLSX)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OOXML_XLSX_MACRO
        assert result.is_document is True

    def test_ooxml_pptx_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.pptx", DOC_BYTES_OOXML_PPTX)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.OOXML_PPTX_MACRO
        assert result.is_document is True

    def test_onenote_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.one", DOC_BYTES_ONENOTE)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.ONENOTE
        assert result.is_document is True

    def test_hta_detected(self, tmp_path: Path):
        p = self._write(tmp_path / "sample.hta", DOC_BYTES_HTA)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.HTA
        assert result.is_document is True

    def test_document_format_field_is_none_for_pe(self, tmp_path: Path):
        """Non-document binaries keep document_format=None / is_document=False."""
        p = write_sample(tmp_path / "a.exe", "pe32_x86")
        result = identify_file(p, max_size_mb=1)
        assert result.document_format is None
        assert result.is_document is False
        assert result.polyglot_document_priority is False

    def test_document_format_is_none_for_generic_zip(self, tmp_path: Path):
        """A ZIP without OOXML content-type markers is still rejected."""
        p = tmp_path / "fake.exe"
        p.write_bytes(COUNTEREXAMPLE_ZIP_AS_EXE)
        with pytest.raises(EntryFormatUnsupported) as ei:
            identify_file(p, max_size_mb=1)
        assert ei.value.details["reason"] == "unknown_format"


# ---------------------------------------------------------------------------
# C3 / FR-01 AC-2 + AC-5: document_tier labelling (P0 / P1 / P2)
# ---------------------------------------------------------------------------


class TestDocumentTierLabelling:
    """FR-01 AC-2: correct tier annotated; FR-01 AC-5: P2 annotated in FR-01."""

    def _write(self, path: Path, data: bytes) -> Path:
        path.write_bytes(data)
        return path

    def test_pdf_is_p0(self, tmp_path: Path):
        p = self._write(tmp_path / "s.pdf", DOC_BYTES_PDF)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P0

    def test_ole2_doc_is_p0(self, tmp_path: Path):
        p = self._write(tmp_path / "s.doc", DOC_BYTES_OLE2_DOC)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P0

    def test_ole2_xls_is_p0(self, tmp_path: Path):
        p = self._write(tmp_path / "s.xls", DOC_BYTES_OLE2_XLS)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P0

    def test_ooxml_docx_is_p0(self, tmp_path: Path):
        p = self._write(tmp_path / "s.docx", DOC_BYTES_OOXML_DOCX)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P0

    def test_ooxml_xlsx_is_p0(self, tmp_path: Path):
        p = self._write(tmp_path / "s.xlsx", DOC_BYTES_OOXML_XLSX)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P0

    def test_ole2_ppt_is_p1(self, tmp_path: Path):
        p = self._write(tmp_path / "s.ppt", DOC_BYTES_OLE2_PPT)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P1

    def test_ooxml_pptx_is_p1(self, tmp_path: Path):
        p = self._write(tmp_path / "s.pptx", DOC_BYTES_OOXML_PPTX)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P1

    def test_rtf_is_p1(self, tmp_path: Path):
        p = self._write(tmp_path / "s.rtf", DOC_BYTES_RTF)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P1

    def test_hta_is_p1(self, tmp_path: Path):
        p = self._write(tmp_path / "s.hta", DOC_BYTES_HTA)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P1

    def test_onenote_is_p2(self, tmp_path: Path):
        """FR-01 AC-5: P2 tier annotated in FR-01 stage (not deferred)."""
        p = self._write(tmp_path / "s.one", DOC_BYTES_ONENOTE)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P2

    def test_encrypted_office_is_p2(self, tmp_path: Path):
        """FR-01 AC-5: encrypted_office → P2 annotated in FR-01 stage."""
        p = self._write(tmp_path / "s.docx", DOC_BYTES_ENCRYPTED_OFFICE)
        assert identify_file(p, max_size_mb=1).document_tier == DocumentTier.P2


# ---------------------------------------------------------------------------
# C3 / FR-01 AC-7: Polyglot document priority
# ---------------------------------------------------------------------------


class TestPolyglotDocumentPriority:
    """FR-01 AC-7: PDF+PE polyglot → document wins; polyglot_document_priority=True."""

    def test_pdf_pe_polyglot_document_format_is_pdf(self, tmp_path: Path):
        p = tmp_path / "polyglot.bin"
        p.write_bytes(DOC_BYTES_POLYGLOT_PDF_PE)
        result = identify_file(p, max_size_mb=1)
        assert result.document_format == DocumentFormat.PDF

    def test_pdf_pe_polyglot_priority_flag_set(self, tmp_path: Path):
        p = tmp_path / "polyglot.bin"
        p.write_bytes(DOC_BYTES_POLYGLOT_PDF_PE)
        result = identify_file(p, max_size_mb=1)
        assert result.polyglot_document_priority is True

    def test_pdf_pe_polyglot_is_document_true(self, tmp_path: Path):
        p = tmp_path / "polyglot.bin"
        p.write_bytes(DOC_BYTES_POLYGLOT_PDF_PE)
        result = identify_file(p, max_size_mb=1)
        assert result.is_document is True

    def test_pdf_pe_polyglot_tier_is_p0(self, tmp_path: Path):
        p = tmp_path / "polyglot.bin"
        p.write_bytes(DOC_BYTES_POLYGLOT_PDF_PE)
        result = identify_file(p, max_size_mb=1)
        assert result.document_tier == DocumentTier.P0

    def test_pure_pe_without_pdf_magic_not_polyglot(self, tmp_path: Path):
        p = write_sample(tmp_path / "a.exe", "pe32_x86")
        result = identify_file(p, max_size_mb=1)
        assert result.polyglot_document_priority is False
        assert result.document_format is None


# ---------------------------------------------------------------------------
# C3 / FR-01 AC-8: document fields written to file_meta evidence-chain bucket
# ---------------------------------------------------------------------------


class TestDocumentFieldsInEvidenceChain:
    """FR-01 AC-8: document_format / document_tier written to file_meta fact Indicator."""

    async def test_document_format_in_file_meta_indicator(
        self,
        tmp_path: Path,
        tool: FileIdentifyTool,
        store: EvidenceChainStore,
    ):
        p = tmp_path / "sample.pdf"
        p.write_bytes(DOC_BYTES_PDF)
        await tool.ainvoke({"path": str(p), "analysis_id": "aid-doc-pdf"})

        indicators = store.query(bucket=Bucket.file_meta)
        assert len(indicators) == 1
        ind = indicators[0]
        assert ind.data["document_format"] == DocumentFormat.PDF
        assert ind.data["document_tier"] == DocumentTier.P0
        assert ind.data["is_document"] is True

    async def test_encrypted_office_p2_in_file_meta_indicator(
        self,
        tmp_path: Path,
        tool: FileIdentifyTool,
        store: EvidenceChainStore,
    ):
        p = tmp_path / "encrypted.docx"
        p.write_bytes(DOC_BYTES_ENCRYPTED_OFFICE)
        await tool.ainvoke({"path": str(p), "analysis_id": "aid-doc-enc"})

        indicators = store.query(bucket=Bucket.file_meta)
        assert indicators[0].data["document_format"] == DocumentFormat.ENCRYPTED_OFFICE
        assert indicators[0].data["document_tier"] == DocumentTier.P2

    async def test_non_document_has_null_document_fields_in_indicator(
        self,
        tmp_path: Path,
        tool: FileIdentifyTool,
        store: EvidenceChainStore,
    ):
        p = write_sample(tmp_path / "a.exe", "pe32_x86")
        await tool.ainvoke({"path": str(p), "analysis_id": "aid-exe"})

        ind = store.query(bucket=Bucket.file_meta)[0]
        assert ind.data["document_format"] is None
        assert ind.data["document_tier"] is None
        assert ind.data["is_document"] is False
