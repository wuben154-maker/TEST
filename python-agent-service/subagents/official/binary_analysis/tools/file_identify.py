"""FileIdentifyTool — entry-point sample identification (FR-01 / ADR-13).

This module is the single Tool responsible for admitting a sample into the
analysis pipeline.  It enforces three structural guarantees:

1. **Trust boundary (NFR-03)** — sample bytes only leave the host via
   :func:`~sandbox.client.upload_sample_to_sandbox`; the
   Tool's return value contains structured metadata (path, format, arch,
   fingerprints) but **never** the raw bytes.
2. **Evidence chain (FR-01 AC-5)** — one ``fact``-kind Indicator is
   appended to the ``file_meta`` bucket capturing size / path / format /
   fingerprints so downstream FRs have an audit-trail anchor.
3. **Structured error routing (FR-01 AC-6)** — unsupported inputs
   (unknown format, counter-example files, empty files, missing paths,
   oversized files) raise :class:`~errors.EntryFormatUnsupported`
   so the orchestration layer can short-circuit into E2E-01 exception E1.

Design note
-----------

The public :func:`identify_file` helper is *pure*: it performs no sandbox
or evidence-chain side effects.  This split keeps the identification logic
unit-testable without async machinery and lets tests assert the "zero
bytes in return value" contract independently of the Tool wrapper.

Optional libraries (``lief``, ``pefile``, ``ssdeep``, ``tlsh``) are imported
lazily.  When unavailable the corresponding fingerprint slot is set to
``None`` and a coverage note is attached to the Indicator; the core
identification still succeeds from magic-number parsing alone.

C3 extension (FR-01 document branch)
--------------------------------------

:func:`_detect_document_format` appends document-format awareness via
lightweight magic-byte / structure probes.  Four new Optional fields are
added to :class:`FileIdentifyResult`:

- ``document_format`` — one of :class:`~schema.document_enums.DocumentFormat`
- ``document_tier`` — ``P0`` / ``P1`` / ``P2`` per complexity table
- ``is_document`` — ``True`` when a document format is confirmed
- ``polyglot_document_priority`` — ``True`` for PDF+PE polyglots (doc wins)

All four fields default to ``None`` / ``False`` so e2e01 callers that do
not yet consume them remain fully backward-compatible (FR-01 AC-6).
"""

from __future__ import annotations

import hashlib
import inspect
import io
import re
import struct
import tempfile
import zipfile
import zlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict
from ulid import ULID

from audit import log_indicator_write
from config import settings
from errors import BinaryAnalysisError, EntryFormatUnsupported
from evidence_chain.store import EvidenceChainStore
from sandbox.client import (
    SandboxClient,
    SandboxSession,
    upload_sample_to_sandbox,
)
from sandbox.registry import get_or_create_session, get_session
from schema.document_enums import DocumentFormat, DocumentTier
from schema.evidence_chain import Bucket
from schema.indicator import Confidence, Indicator, Severity

FormatName = Literal["PE32", "PE32+", "ELF", "Mach-O", "document"]
Arch = Literal["x86", "x64", "ARM", "ARM64", "unknown"]
Routing = Literal["full", "structural_only"]

# ---------------------------------------------------------------------------
# PE / ELF / Mach-O magic-number tables
# ---------------------------------------------------------------------------

_PE_MACHINE_MAP: dict[int, Arch] = {
    0x014C: "x86",
    0x8664: "x64",
    0x01C0: "ARM",
    0x01C4: "ARM",
    0xAA64: "ARM64",
}
_PE_OPT_MAGIC_32 = 0x010B
_PE_OPT_MAGIC_32_PLUS = 0x020B

_ELF_EMACHINE_MAP: dict[int, Arch] = {
    3: "x86",
    62: "x64",
    40: "ARM",
    183: "ARM64",
}

_MACHO_CPUTYPE_MAP: dict[int, Arch] = {
    0x00000007: "x86",
    0x01000007: "x64",
    0x0000000C: "ARM",
    0x0100000C: "ARM64",
}

_MACHO_MAGICS_LE = {0xFEEDFACE, 0xFEEDFACF}
_MACHO_MAGICS_BE = {0xCEFAEDFE, 0xCFFAEDFE}

_MAX_CARVED_PE_CHILDREN = 4
_MAX_DECODED_BUFFER_CANDIDATES = 8
_MAX_DECODED_BUFFER_SIZE = 8 * 1024 * 1024
_PE_DOS_LFANEW_OFFSET = 0x3C
_PE_NT_SIGNATURE = b"PE\x00\x00"
_IMAGE_FILE_HEADER_SIZE = 20
_IMAGE_SECTION_HEADER_SIZE = 40
_MIN_EMBEDDED_PE_OFFSET = 0x40

# ---------------------------------------------------------------------------
# Document format magic / structure constants (C3 / FR-01 AC-1~8)
# ---------------------------------------------------------------------------

# PDF: first 5 bytes
_PDF_MAGIC = b"%PDF-"

# RTF: first 5 bytes
_RTF_MAGIC = b"{\\rtf"

# OLE2 Compound Document File: 8-byte signature (legacy Office + encrypted Office)
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# OneNote section file: 16-byte magic
_ONENOTE_MAGIC = b"\xe4\x52\x5c\x7b\x8c\xd8\xa7\x4d\xae\xb1\x53\x78\xd0\x29\x96\xd3"

# OOXML: ZIP local-file-header signature (Office Open XML = ZIP + content types)
_OOXML_ZIP_MAGIC = b"PK\x03\x04"

# OLE2 directory stream names stored as UTF-16 LE within the compound document.
# Scanning the first 8 KB is sufficient for typical files whose directory
# sector resides early in the file.
_OLE2_STREAM_ENCRYPTION_INFO = "EncryptionInfo".encode("utf-16-le")
_OLE2_STREAM_WORD_DOCUMENT = "WordDocument".encode("utf-16-le")
_OLE2_STREAM_WORKBOOK = "Workbook".encode("utf-16-le")
_OLE2_STREAM_BOOK = "Book".encode("utf-16-le")
_OLE2_STREAM_PPT = "PowerPoint Document".encode("utf-16-le")

# OOXML content-type namespace fragments found in [Content_Types].xml.
# The file is usually the first ZIP entry and often stored without compression,
# so scanning the raw bytes within the first 4 KB is a reliable heuristic.
_OOXML_WORD_CT = b"wordprocessingml"
_OOXML_EXCEL_CT = b"spreadsheetml"
_OOXML_PPT_CT = b"presentationml"

# HTA has no fixed magic; look for the <HTA: tag within the first 512 bytes.
_HTA_TAG_UPPER = b"<HTA:"

# Analysis-complexity tier table (FR-01 AC-2 / SPEC §FR-01 AC-2)
#   P0 — fully supported  (docx / xlsx / doc / xls / pdf)
#   P1 — best-effort      (pptx / ppt / rtf / hta)
#   P2 — degraded-path    (onenote / encrypted_office)
_DOC_TIER_MAP: dict[DocumentFormat, DocumentTier] = {
    DocumentFormat.OOXML_DOCX_MACRO: DocumentTier.P0,
    DocumentFormat.OOXML_XLSX_MACRO: DocumentTier.P0,
    DocumentFormat.OOXML_PPTX_MACRO: DocumentTier.P1,
    DocumentFormat.OLE2_DOC: DocumentTier.P0,
    DocumentFormat.OLE2_XLS: DocumentTier.P0,
    DocumentFormat.OLE2_PPT: DocumentTier.P1,
    DocumentFormat.PDF: DocumentTier.P0,
    DocumentFormat.RTF: DocumentTier.P1,
    DocumentFormat.HTA: DocumentTier.P1,
    DocumentFormat.ONENOTE: DocumentTier.P2,
    DocumentFormat.ENCRYPTED_OFFICE: DocumentTier.P2,
}


def _ooxml_format_from_zip(data: bytes) -> DocumentFormat | None:
    """Identify OOXML family from ZIP entries and content types."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = {name.lstrip("/").lower() for name in zf.namelist()}
            content_types = b""
            try:
                content_types = zf.read("[Content_Types].xml").lower()
            except KeyError:
                pass
    except zipfile.BadZipFile:
        return None

    if any(name.startswith("word/") for name in names) or (
        _OOXML_WORD_CT in content_types
        or b"ms-word.document.macroenabled" in content_types
    ):
        return DocumentFormat.OOXML_DOCX_MACRO
    if any(name.startswith("xl/") for name in names) or (
        _OOXML_EXCEL_CT in content_types
        or b"ms-excel.sheet.macroenabled" in content_types
    ):
        return DocumentFormat.OOXML_XLSX_MACRO
    if any(name.startswith("ppt/") for name in names) or (
        _OOXML_PPT_CT in content_types
        or b"ms-powerpoint.presentation.macroenabled" in content_types
    ):
        return DocumentFormat.OOXML_PPTX_MACRO
    return None


EmbeddedPayloadHandler = Callable[
    [str, list[dict[str, Any]]],
    Awaitable[list[dict[str, Any]]] | list[dict[str, Any]],
]
"""Optional callback for recursively analyzing carved child payloads."""


@dataclass(frozen=True)
class FileIdentifyResult:
    """Pure identification result (no sandbox / evidence-chain side effects).

    Attributes:
        format: Detected executable format, or ``"document"`` for files that
            are recognised as a document type but not as PE / ELF / Mach-O.
        arch: Detected target architecture; ``"unknown"`` for pure documents.
        routing: ``"full"`` for PE, ``"structural_only"`` for ELF / Mach-O /
            document per FR-01 AC-3.
        fingerprints: Mapping of fingerprint algorithm → hex digest.  Always
            contains ``md5`` / ``sha1`` / ``sha256``; ``ssdeep`` / ``tlsh``
            / ``imphash`` are present only when the corresponding optional
            library is installed (value may be ``None`` on best-effort
            failure).
        size_bytes: Sample size on disk in bytes.
        absolute_path: Canonical absolute host path after ``resolve()``.
        mtime: Sample ``st_mtime`` at identification time; captured so
            tests can assert FR-01 AC-8 (read-only open).
        coverage_notes: Non-empty list names the optional fingerprints that
            could not be computed (e.g. ``["ssdeep", "tlsh"]``).
        document_format: Detected document format enum value, or ``None`` for
            non-document files (C3 / FR-01 AC-1).
        document_tier: Analysis-complexity tier ``P0`` / ``P1`` / ``P2``, or
            ``None`` for non-document files (C3 / FR-01 AC-2).
        is_document: ``True`` when a document format is confirmed; ``False``
            for pure PE / ELF / Mach-O binaries (C3 / FR-01 AC-3).
        polyglot_document_priority: ``True`` when the file simultaneously
            satisfies a document magic check and a PE magic check — document
            routing wins (C3 / FR-01 AC-7).
    """

    format: FormatName
    arch: Arch
    routing: Routing
    fingerprints: dict[str, str | None]
    size_bytes: int
    absolute_path: str
    mtime: float
    coverage_notes: list[str] = field(default_factory=list)
    # C3 additions — all Optional to preserve e2e01 backward-compatibility
    document_format: DocumentFormat | None = None
    document_tier: DocumentTier | None = None
    is_document: bool = False
    polyglot_document_priority: bool = False


# ---------------------------------------------------------------------------
# Path resolution (FR-01 AC-1 / IR-08)
# ---------------------------------------------------------------------------


def _resolve_host_path(raw_path: str | Path) -> Path:
    """Normalise ``raw_path`` to a readable absolute :class:`Path`.

    Handles the FR-01 AC-1 requirements: absolute or relative inputs,
    Unicode characters, embedded spaces, ``~`` expansion.  Converts all
    path-level errors into :class:`EntryFormatUnsupported` so the caller
    only has to handle one exception type (IR-08).

    Args:
        raw_path: User-supplied path, absolute or relative.

    Returns:
        The resolved absolute path.

    Raises:
        EntryFormatUnsupported: If the path is missing, not a regular file,
            or cannot be read.
    """
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        msg = f"sample path does not exist: {raw_path!r}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "path_not_found", "path": str(raw_path)},
        ) from exc
    except OSError as exc:
        msg = f"sample path cannot be opened: {raw_path!r}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "path_not_readable", "path": str(raw_path)},
        ) from exc
    if not resolved.is_file():
        msg = f"sample path is not a regular file: {resolved!s}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "not_a_file", "path": str(resolved)},
        )
    return resolved


# ---------------------------------------------------------------------------
# Format detection  (FR-01 AC-2 / AC-3)
# ---------------------------------------------------------------------------


def _detect_pe(data: bytes) -> tuple[FormatName, Arch] | None:
    """Return ``(format, arch)`` for a PE image or ``None`` on structural failure."""
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    try:
        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    except struct.error:
        return None
    if e_lfanew + 24 > len(data):
        return None
    if data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        return None
    machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
    arch: Arch = _PE_MACHINE_MAP.get(machine, "unknown")
    opt_magic_offset = e_lfanew + 24
    if opt_magic_offset + 2 > len(data):
        return None
    opt_magic = struct.unpack_from("<H", data, opt_magic_offset)[0]
    if opt_magic == 0x020B:
        return "PE32+", arch
    if opt_magic == 0x010B:
        return "PE32", arch
    return None


def _detect_elf(data: bytes) -> tuple[FormatName, Arch] | None:
    """Return ``("ELF", arch)`` for an ELF image or ``None`` on structural failure."""
    if len(data) < 20 or data[:4] != b"\x7fELF":
        return None
    is_le = data[5] == 1
    endian = "<" if is_le else ">"
    try:
        e_machine = struct.unpack_from(f"{endian}H", data, 0x12)[0]
    except struct.error:
        return None
    arch: Arch = _ELF_EMACHINE_MAP.get(e_machine, "unknown")
    return "ELF", arch


def _detect_macho(data: bytes) -> tuple[FormatName, Arch] | None:
    """Return ``("Mach-O", arch)`` for a Mach-O image or ``None`` on structural failure."""
    if len(data) < 8:
        return None
    magic_le = struct.unpack_from("<I", data, 0)[0]
    magic_be = struct.unpack_from(">I", data, 0)[0]
    if magic_le in _MACHO_MAGICS_LE:
        endian = "<"
    elif magic_be in _MACHO_MAGICS_BE:
        endian = ">"
    else:
        return None
    cputype = struct.unpack_from(f"{endian}I", data, 4)[0]
    arch: Arch = _MACHO_CPUTYPE_MAP.get(cputype, "unknown")
    return "Mach-O", arch


def _detect_format(data: bytes) -> tuple[FormatName, Arch]:
    """Dispatch to the per-format detectors in declaration order.

    Raises:
        EntryFormatUnsupported: If none of the detectors recognise ``data``.
    """
    for detector in (_detect_pe, _detect_elf, _detect_macho):
        found = detector(data)
        if found is not None:
            return found
    msg = "sample bytes do not match any supported format (PE / ELF / Mach-O)"
    raise EntryFormatUnsupported(msg, details={"reason": "unknown_format"})


# ---------------------------------------------------------------------------
# Document format detection  (C3 / FR-01 AC-1~8)
# ---------------------------------------------------------------------------


def _detect_document_format(
    data: bytes,
) -> tuple[DocumentFormat | None, DocumentTier | None]:
    """Detect document format via magic bytes and lightweight structure probes.

    Detection order (highest-confidence first):

    1. OneNote: fixed 16-byte section-file magic.
    2. PDF: ``%PDF-`` at offset 0.
    3. RTF: ``{\\rtf`` at offset 0.
    4. OLE2: 8-byte signature; subtype resolved by scanning the first 8 KB for
       UTF-16-LE stream names (``WordDocument`` / ``Workbook`` / ``Book`` /
       ``PowerPoint Document`` win over a generic ``EncryptionInfo`` marker).
    5. OOXML: ``PK\\x03\\x04`` at offset 0; subtype resolved by scanning the
       first 4 KB for content-type namespace fragments from
       ``[Content_Types].xml``.
    6. HTA: case-insensitive ``<HTA:`` tag within the first 512 bytes.

    Args:
        data: Raw file bytes (may be a large buffer; only a prefix is scanned).

    Returns:
        A ``(DocumentFormat, DocumentTier)`` pair when recognised, or
        ``(None, None)`` for non-document data.

    Notes:
        - A generic ZIP without OOXML content-type markers returns
          ``(None, None)``; the caller's counter-example check remains intact.
        - An unrecognised OLE2 file (no known stream name found) is classified
          conservatively as ``ENCRYPTED_OFFICE`` (P2) since the real subtype
          cannot be inferred from magic alone.
    """
    if not data:
        return None, None

    # OneNote section file: 16-byte magic
    if len(data) >= 16 and data[:16] == _ONENOTE_MAGIC:
        fmt = DocumentFormat.ONENOTE
        return fmt, _DOC_TIER_MAP[fmt]

    # PDF
    if data[:5] == _PDF_MAGIC:
        fmt = DocumentFormat.PDF
        return fmt, _DOC_TIER_MAP[fmt]

    # RTF
    if data[:5] == _RTF_MAGIC:
        fmt = DocumentFormat.RTF
        return fmt, _DOC_TIER_MAP[fmt]

    # OLE2: legacy Office and encrypted Office
    if data[:8] == _OLE2_MAGIC:
        scan = data[: min(len(data), 8192)]
        if _OLE2_STREAM_WORD_DOCUMENT in scan:
            fmt = DocumentFormat.OLE2_DOC
            return fmt, _DOC_TIER_MAP[fmt]
        if _OLE2_STREAM_WORKBOOK in scan or _OLE2_STREAM_BOOK in scan:
            fmt = DocumentFormat.OLE2_XLS
            return fmt, _DOC_TIER_MAP[fmt]
        if _OLE2_STREAM_PPT in scan:
            fmt = DocumentFormat.OLE2_PPT
            return fmt, _DOC_TIER_MAP[fmt]
        if _OLE2_STREAM_ENCRYPTION_INFO in scan:
            fmt = DocumentFormat.ENCRYPTED_OFFICE
            return fmt, _DOC_TIER_MAP[fmt]
        # Unrecognised OLE2: conservatively classify as encrypted_office (P2)
        fmt = DocumentFormat.ENCRYPTED_OFFICE
        return fmt, _DOC_TIER_MAP[fmt]

    # OOXML (ZIP-based Office formats)
    if data[:4] == _OOXML_ZIP_MAGIC:
        zip_fmt = _ooxml_format_from_zip(data)
        if zip_fmt is not None:
            return zip_fmt, _DOC_TIER_MAP[zip_fmt]

        scan = data[: min(len(data), 4096)]
        if _OOXML_WORD_CT in scan:
            fmt = DocumentFormat.OOXML_DOCX_MACRO
            return fmt, _DOC_TIER_MAP[fmt]
        if _OOXML_EXCEL_CT in scan:
            fmt = DocumentFormat.OOXML_XLSX_MACRO
            return fmt, _DOC_TIER_MAP[fmt]
        if _OOXML_PPT_CT in scan:
            fmt = DocumentFormat.OOXML_PPTX_MACRO
            return fmt, _DOC_TIER_MAP[fmt]
        # ZIP without recognised OOXML content type → not a document
        return None, None

    # HTA: HTML Application — no fixed magic; scan for <HTA: tag
    preview_upper = data[: min(len(data), 512)].upper()
    if _HTA_TAG_UPPER in preview_upper:
        fmt = DocumentFormat.HTA
        return fmt, _DOC_TIER_MAP[fmt]

    return None, None


# ---------------------------------------------------------------------------
# Fingerprints  (FR-01 AC-4)
# ---------------------------------------------------------------------------


def _cryptographic_hashes(data: bytes) -> dict[str, str]:
    """Compute the mandatory MD5 / SHA-1 / SHA-256 digests (hex)."""
    return {
        "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
        "sha1": hashlib.sha1(data, usedforsecurity=False).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _optional_ssdeep(data: bytes) -> str | None:
    """Return the ssdeep digest when the library is installed, else ``None``."""
    try:
        import ssdeep  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return ssdeep.hash(data)
    except Exception:  # noqa: BLE001 — optional dependency, degrade gracefully
        return None


def _optional_tlsh(data: bytes) -> str | None:
    """Return the TLSH digest when the library is installed, else ``None``."""
    try:
        import tlsh  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        digest = tlsh.hash(data)
    except Exception:  # noqa: BLE001
        return None
    # TLSH returns "TNULL" for inputs below ~50 bytes; surface that as None.
    if not digest or digest == "TNULL":
        return None
    return digest


def _optional_imphash(data: bytes, *, fmt: FormatName) -> str | None:
    """Return the PE imphash when ``pefile`` is installed, else ``None``.

    imphash is defined only for PE images; other formats always yield ``None``.
    """
    if fmt not in ("PE32", "PE32+"):
        return None
    try:
        import pefile  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        pe = pefile.PE(data=data, fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        return pe.get_imphash() or None
    except Exception:  # noqa: BLE001
        return None


def _compute_fingerprints(
    data: bytes, *, fmt: FormatName
) -> tuple[dict[str, str | None], list[str]]:
    """Compute the full fingerprint set + the list of unavailable optional slots.

    The returned mapping always contains 5 keys for non-PE formats
    (``md5`` / ``sha1`` / ``sha256`` / ``ssdeep`` / ``tlsh``) and 6 keys
    for PE formats (adds ``imphash``) so callers can rely on key presence
    for structural assertions.  A missing optional library shows up as a
    ``None`` value and is listed in the returned coverage notes.
    """
    fp: dict[str, str | None] = dict(_cryptographic_hashes(data))
    fp["ssdeep"] = _optional_ssdeep(data)
    fp["tlsh"] = _optional_tlsh(data)
    if fmt in ("PE32", "PE32+"):
        fp["imphash"] = _optional_imphash(data, fmt=fmt)
    notes = [key for key, value in fp.items() if value is None]
    return fp, notes


# ---------------------------------------------------------------------------
# Routing  (FR-01 AC-3)
# ---------------------------------------------------------------------------


def _routing_for(fmt: FormatName) -> Routing:
    """PE → full pipeline; ELF / Mach-O → structural-only subset."""
    return "full" if fmt in ("PE32", "PE32+") else "structural_only"


# ---------------------------------------------------------------------------
# Pure identification entry point
# ---------------------------------------------------------------------------


def identify_file(
    path: str | Path,
    *,
    max_size_mb: int,
) -> FileIdentifyResult:
    """Identify a sample's format / arch / fingerprints without side effects.

    Implements FR-01 AC-1~8 (C3 extension adds document branch).
    Side-effectful AC-5 (evidence-chain append) and AC-7 (sandbox upload /
    zero-byte return) are handled by :class:`FileIdentifyTool`.

    Args:
        path: Absolute or relative host path to the sample.
        max_size_mb: Hard upper bound on sample size in mebibytes.
            Exceeding this bound raises :class:`EntryFormatUnsupported`
            with ``reason='size_exceeded'``.

    Returns:
        A :class:`FileIdentifyResult` describing the sample.  Document files
        that are not also a PE / ELF / Mach-O binary have ``format='document'``
        and ``arch='unknown'``.

    Raises:
        EntryFormatUnsupported: On path errors, empty files, size overrun,
            or files that are neither a recognised executable nor a document.
    """
    host_path = _resolve_host_path(path)
    stat = host_path.stat()
    size_bytes = stat.st_size
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes == 0:
        msg = f"sample file is empty: {host_path!s}"
        raise EntryFormatUnsupported(
            msg,
            details={"reason": "empty_file", "path": str(host_path)},
        )
    if size_bytes > max_bytes:
        msg = (
            f"sample size {size_bytes} bytes exceeds max_file_size_mb={max_size_mb} "
            f"({max_bytes} bytes)"
        )
        raise EntryFormatUnsupported(
            msg,
            details={
                "reason": "size_exceeded",
                "size_bytes": size_bytes,
                "max_bytes": max_bytes,
            },
        )
    with host_path.open("rb") as fh:
        data = fh.read()

    # --- Document format detection (C3 / FR-01 AC-1~8) ---
    doc_fmt, doc_tier = _detect_document_format(data)

    # Polyglot: PE magic at offset 0 + PDF magic anywhere in the body.
    # In this case the document format wins the routing decision (FR-01 AC-7).
    is_polyglot = False
    if doc_fmt is None and _detect_pe(data) is not None and _PDF_MAGIC in data:
        doc_fmt = DocumentFormat.PDF
        doc_tier = _DOC_TIER_MAP[DocumentFormat.PDF]
        is_polyglot = True

    # --- Executable format detection ---
    fmt: FormatName
    arch: Arch
    try:
        fmt, arch = _detect_format(data)
        # Edge case: document magic at offset 0 AND executable magic also
        # detected (e.g. PDF-first polyglot with embedded PE structures).
        if doc_fmt is not None and not is_polyglot:
            is_polyglot = True
    except EntryFormatUnsupported:
        if doc_fmt is not None:
            # Pure document: no recognised executable format.
            fmt = "document"
            arch = "unknown"
        else:
            raise

    fingerprints, coverage_notes = _compute_fingerprints(data, fmt=fmt)
    return FileIdentifyResult(
        format=fmt,
        arch=arch,
        routing=_routing_for(fmt),
        fingerprints=fingerprints,
        size_bytes=size_bytes,
        absolute_path=str(host_path),
        mtime=stat.st_mtime,
        coverage_notes=coverage_notes,
        document_format=doc_fmt,
        document_tier=doc_tier,
        is_document=doc_fmt is not None,
        polyglot_document_priority=is_polyglot,
    )


# ---------------------------------------------------------------------------
# LangChain tool wrapper  (FR-01 AC-5 / AC-7)
# ---------------------------------------------------------------------------


class FileIdentifyInput(BaseModel):
    """Input schema for :class:`FileIdentifyTool`."""

    path: str
    analysis_id: str

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class EmbeddedPeCandidate:
    """Validated embedded PE image candidate found inside another PE."""

    offset: int
    size_bytes: int
    format: str
    sha256: str
    data: bytes
    source_region: str
    decoder: str = "none"
    decoded_offset: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def _pe_image_span(data: bytes, offset: int) -> tuple[int, str] | None:
    """Return `(size, format)` for a valid PE image starting at `offset`."""
    if offset < 0 or offset + _PE_DOS_LFANEW_OFFSET + 4 > len(data):
        return None
    if data[offset : offset + 2] != b"MZ":
        return None
    e_lfanew = struct.unpack_from("<I", data, offset + _PE_DOS_LFANEW_OFFSET)[0]
    nt_offset = offset + e_lfanew
    file_header_offset = nt_offset + len(_PE_NT_SIGNATURE)
    if (
        e_lfanew < _PE_DOS_LFANEW_OFFSET
        or file_header_offset + _IMAGE_FILE_HEADER_SIZE > len(data)
        or data[nt_offset:file_header_offset] != _PE_NT_SIGNATURE
    ):
        return None

    machine, number_of_sections, _, _, _, size_opt_header, _ = struct.unpack_from(
        "<HHIIIHH", data, file_header_offset
    )
    if machine not in _PE_MACHINE_MAP:
        return None
    optional_offset = file_header_offset + _IMAGE_FILE_HEADER_SIZE
    section_table = optional_offset + size_opt_header
    if optional_offset + 2 > len(data) or section_table > len(data):
        return None
    optional_magic = struct.unpack_from("<H", data, optional_offset)[0]
    if optional_magic == _PE_OPT_MAGIC_32:
        fmt = "pe"
    elif optional_magic == _PE_OPT_MAGIC_32_PLUS:
        fmt = "pe"
    else:
        return None

    end = section_table
    if number_of_sections:
        section_table_end = section_table + (
            number_of_sections * _IMAGE_SECTION_HEADER_SIZE
        )
        if section_table_end > len(data):
            return None
        end = section_table_end
        for idx in range(number_of_sections):
            section_offset = section_table + idx * _IMAGE_SECTION_HEADER_SIZE
            size_raw = struct.unpack_from("<I", data, section_offset + 16)[0]
            ptr_raw = struct.unpack_from("<I", data, section_offset + 20)[0]
            if ptr_raw and size_raw:
                end = max(end, offset + ptr_raw + size_raw)
    if end <= offset or end > len(data):
        return None
    return end - offset, fmt


@dataclass(frozen=True)
class DecodedBufferCandidate:
    """Static decoded buffer that may contain a PE image."""

    offset: int
    data: bytes
    decoder: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _parent_pe_image_size(data: bytes) -> int | None:
    """Return the parent PE span when the file starts with a valid PE."""
    span = _pe_image_span(data, 0)
    return span[0] if span is not None else None


def _source_region_for_offset(data: bytes, offset: int) -> str:
    """Best-effort provenance for a carved payload offset."""
    parent_size = _parent_pe_image_size(data)
    if parent_size is not None and offset >= parent_size:
        return "overlay"
    return "raw_scan"


def _append_pe_candidates_from_buffer(
    candidates: list[EmbeddedPeCandidate],
    *,
    source: bytes,
    decoded: bytes,
    source_offset: int,
    source_region: str,
    decoder: str,
    metadata: dict[str, Any] | None = None,
    seen_sha256: set[str],
) -> None:
    """Append structurally valid PE children from a decoded/raw buffer."""
    search_from = 0 if decoder != "none" else _MIN_EMBEDDED_PE_OFFSET
    while len(candidates) < _MAX_CARVED_PE_CHILDREN:
        decoded_offset = decoded.find(b"MZ", search_from)
        if decoded_offset < 0:
            break
        span = _pe_image_span(decoded, decoded_offset)
        if span is None:
            search_from = decoded_offset + 2
            continue
        size_bytes, fmt = span
        child = decoded[decoded_offset : decoded_offset + size_bytes]
        sha256 = hashlib.sha256(child).hexdigest()
        if sha256 in seen_sha256:
            search_from = decoded_offset + size_bytes
            continue
        seen_sha256.add(sha256)
        absolute_offset = (
            source_offset + decoded_offset if decoder == "none" else source_offset
        )
        region = source_region
        if decoder == "none":
            region = _source_region_for_offset(source, absolute_offset)
        candidates.append(
            EmbeddedPeCandidate(
                offset=absolute_offset,
                size_bytes=size_bytes,
                format=fmt,
                sha256=sha256,
                data=child,
                source_region=region,
                decoder=decoder,
                decoded_offset=decoded_offset,
                metadata=metadata or {},
            )
        )
        search_from = decoded_offset + size_bytes


def _iter_compressed_buffers(data: bytes) -> list[DecodedBufferCandidate]:
    """Return zlib/gzip decoded buffers from common embedded stream signatures."""
    candidates: list[DecodedBufferCandidate] = []
    signatures = (b"\x1f\x8b", b"\x78\x01", b"\x78\x9c", b"\x78\xda")
    for sig in signatures:
        search_from = 0
        while len(candidates) < _MAX_DECODED_BUFFER_CANDIDATES:
            offset = data.find(sig, search_from)
            if offset < 0:
                break
            try:
                decoded = zlib.decompress(
                    data[offset:],
                    31 if sig == b"\x1f\x8b" else 0,
                    bufsize=_MAX_DECODED_BUFFER_SIZE,
                )
            except zlib.error:
                search_from = offset + 1
                continue
            if 0 < len(decoded) <= _MAX_DECODED_BUFFER_SIZE:
                candidates.append(
                    DecodedBufferCandidate(
                        offset=offset,
                        data=decoded,
                        decoder="gzip" if sig == b"\x1f\x8b" else "zlib",
                    )
                )
            search_from = offset + 1
    return candidates


_BASE64_RE = re.compile(rb"(?:[A-Za-z0-9+/]{80,}={0,2})")


def _iter_base64_buffers(data: bytes) -> list[DecodedBufferCandidate]:
    """Return bounded base64-decoded buffers that may contain staged payloads."""
    import base64
    import binascii

    candidates: list[DecodedBufferCandidate] = []
    for match in _BASE64_RE.finditer(data):
        if len(candidates) >= _MAX_DECODED_BUFFER_CANDIDATES:
            break
        raw = match.group()
        try:
            decoded = base64.b64decode(raw, validate=True)
        except binascii.Error:
            continue
        if 0 < len(decoded) <= _MAX_DECODED_BUFFER_SIZE:
            candidates.append(
                DecodedBufferCandidate(
                    offset=match.start(),
                    data=decoded,
                    decoder="base64",
                )
            )
    return candidates


def _iter_xor_pe_buffers(data: bytes) -> list[DecodedBufferCandidate]:
    """Return single-byte XOR decoded buffers that validate as PE at the hit."""
    candidates: list[DecodedBufferCandidate] = []
    search_from = _MIN_EMBEDDED_PE_OFFSET
    while len(candidates) < _MAX_DECODED_BUFFER_CANDIDATES:
        if search_from + 2 > len(data):
            break
        hit: tuple[int, int] | None = None
        for offset in range(search_from, len(data) - 1):
            key = data[offset] ^ 0x4D
            if key == 0:
                continue
            if data[offset + 1] ^ key == 0x5A:
                hit = (offset, key)
                break
        if hit is None:
            break
        offset, key = hit
        decoded = bytes(byte ^ key for byte in data[offset:])
        if _pe_image_span(decoded, 0) is not None:
            candidates.append(
                DecodedBufferCandidate(
                    offset=offset,
                    data=decoded,
                    decoder="xor_single_byte",
                    metadata={"xor_key": key},
                )
            )
        search_from = offset + 2
    return candidates


def _iter_decoded_buffers(data: bytes) -> list[DecodedBufferCandidate]:
    """Return static decoded buffers without executing sample code."""
    buffers: list[DecodedBufferCandidate] = []
    for producer in (
        _iter_compressed_buffers,
        _iter_base64_buffers,
        _iter_xor_pe_buffers,
    ):
        for candidate in producer(data):
            buffers.append(candidate)
            if len(buffers) >= _MAX_DECODED_BUFFER_CANDIDATES:
                return buffers
    return buffers


def _find_embedded_pe_candidates(data: bytes) -> list[EmbeddedPeCandidate]:
    """Find valid nested PE images while ignoring the parent image at offset 0."""
    candidates: list[EmbeddedPeCandidate] = []
    seen_sha256: set[str] = set()
    _append_pe_candidates_from_buffer(
        candidates,
        source=data,
        decoded=data,
        source_offset=0,
        source_region="raw_scan",
        decoder="none",
        seen_sha256=seen_sha256,
    )
    for decoded in _iter_decoded_buffers(data):
        if len(candidates) >= _MAX_CARVED_PE_CHILDREN:
            break
        _append_pe_candidates_from_buffer(
            candidates,
            source=data,
            decoded=decoded.data,
            source_offset=decoded.offset,
            source_region="decoded_buffer",
            decoder=decoded.decoder,
            metadata=decoded.metadata,
            seen_sha256=seen_sha256,
        )
    return candidates


def _workspace_analysis_id(path: str) -> str | None:
    """Return candidate analysis id from a logical `/workspace/<aid>/...` path.

    UI virtual workspace paths reuse the same ``/workspace/`` prefix but are not
    binary-analysis sandbox sessions. Callers must only treat the path as
    sandbox-resident when :func:`~sandbox.registry.get_session` confirms an
    active session for this id (:meth:`FileIdentifyTool._arun`).
    """
    parts = path.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[1] == "workspace" and parts[2]:
        return parts[2]
    return None


def _build_file_meta_indicator(
    result: FileIdentifyResult, *, sandbox_path: str
) -> Indicator:
    """Build the ``file_meta``-bucket Indicator for FR-01 AC-5 / AC-8.

    The Indicator carries ``kind='fact'`` since all fields derive from
    deterministic tool observations (magic-number parsing + hashlib).
    Document-format fields (C3 / FR-01 AC-8) are always included so that
    downstream FRs can read ``document_format`` / ``document_tier`` from
    the evidence chain without re-invoking the tool.
    """
    return Indicator(
        source_fr="FR-01",
        indicator_type="file_meta",
        severity=Severity.INFO,
        confidence=Confidence.HIGH,
        kind="fact",
        data={
            "format": result.format,
            "arch": result.arch,
            "routing": result.routing,
            "fingerprints": result.fingerprints,
            "size_bytes": result.size_bytes,
            "absolute_path": result.absolute_path,
            "mtime": result.mtime,
            "sandbox_path": sandbox_path,
            "coverage_notes": result.coverage_notes,
            # C3 document fields (FR-01 AC-8) — None / False for non-documents
            "document_format": result.document_format,
            "document_tier": result.document_tier,
            "is_document": result.is_document,
            "polyglot_document_priority": result.polyglot_document_priority,
        },
    )


def _build_format_unsupported_indicator(
    raw_path: str | Path,
    exc: EntryFormatUnsupported,
    *,
    max_size_mb: int,
) -> Indicator:
    """Build a deterministic FR-01 fact for the E1 unsupported-format path.

    The pure `identify_file` helper still raises so API / CLI preflight can
    preserve their structured exception contract.  The LangGraph Tool path
    needs a non-throwing fact so `langgraph dev` sessions do not fail the run
    before the agent can short-circuit.
    """
    absolute_path = str(raw_path)
    size_bytes = 0
    fingerprints: dict[str, str | None] = {}
    coverage_notes: list[str] = ["format_unsupported"]

    try:
        host_path = _resolve_host_path(raw_path)
        absolute_path = str(host_path)
        size_bytes = host_path.stat().st_size
        max_bytes = max_size_mb * 1024 * 1024
        if size_bytes <= max_bytes:
            with host_path.open("rb") as fh:
                data = fh.read()
            fingerprints, optional_notes = _compute_fingerprints(data, fmt="document")
            coverage_notes.extend(optional_notes)
        else:
            coverage_notes.append("fingerprints_skipped_size_exceeded")
    except EntryFormatUnsupported:
        coverage_notes.append("fingerprints_unavailable")
    except OSError:
        coverage_notes.append("fingerprints_unavailable")

    return Indicator(
        source_fr="FR-01",
        indicator_type="format_unsupported",
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        kind="fact",
        data={
            "format": "unsupported",
            "arch": "unknown",
            "routing": "structural_only",
            "fingerprints": fingerprints,
            "size_bytes": size_bytes,
            "absolute_path": absolute_path,
            "sandbox_path": None,
            "coverage_notes": coverage_notes,
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "document_format": None,
            "document_tier": None,
            "is_document": False,
            "polyglot_document_priority": False,
        },
    )


class FileIdentifyTool(BaseTool):
    """Entry-point sample-identification tool (FR-01 / ADR-13).

    The tool is async-only because uploading the sample to the sandbox
    requires awaiting the :class:`SandboxClient` Protocol.  Invoke via
    :meth:`~langchain_core.tools.BaseTool.ainvoke` / :meth:`arun`.

    Args:
        sandbox_client: Concrete backend implementing :class:`SandboxClient`.
        store: The per-analysis :class:`EvidenceChainStore` used by
            downstream FRs.
        max_file_size_mb: Override for the size cap; defaults to
            :func:`binary_analysis.config.settings().max_file_size_mb` when
            ``None``.
    """

    name: str = "file_identify"
    description: str = (
        "Identify a binary sample at the given SecManus workspace path "
        "(`/workspace/<file>`), legacy upload path (`/uploads/...`), host "
        "filesystem path for standalone/dev runs, or a "
        "/workspace/<analysis_id>/... path when that analysis_id already has "
        "an active sandbox session. Validates format (PE32 / PE32+ / ELF / "
        "Mach-O), detects "
        "target architecture, computes cryptographic + fuzzy fingerprints, "
        "uploads the sample bytes to the sandbox workspace, and appends a "
        "'file_meta' fact Indicator to the evidence chain. "
        "Returns structured metadata only — never raw bytes."
    )
    args_schema: type[BaseModel] = FileIdentifyInput
    # ``SandboxClient`` is a structural Protocol; store it as ``Any`` so
    # Pydantic does not try to build a schema for it (same pattern as
    # ``SandboxSessionTool``).
    sandbox_client: Any
    store: EvidenceChainStore
    max_file_size_mb: int | None = None
    embedded_payload_handler: EmbeddedPayloadHandler | None = None
    sample_path_resolver: Any | None = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        """The Tool is async-only; use :meth:`ainvoke`."""
        msg = (
            "FileIdentifyTool is async-only (sandbox upload); invoke via "
            ".ainvoke(...) rather than .invoke(...)."
        )
        raise NotImplementedError(msg)

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        inp = FileIdentifyInput(**kwargs)
        max_mb = self.max_file_size_mb
        if max_mb is None:
            max_mb = settings().max_file_size_mb
        source_analysis_id = _workspace_analysis_id(inp.path)
        if source_analysis_id is not None:
            source_session = await get_session(source_analysis_id)
            if source_session is not None:
                return await self._identify_sandbox_resident_sample(
                    inp,
                    source_analysis_id=source_analysis_id,
                    max_size_mb=max_mb,
                )
        sample_host_path = Path(inp.path)
        sample_display_path = inp.path
        if self.sample_path_resolver is not None:
            try:
                resolved = self.sample_path_resolver.resolve(inp.path)
            except Exception as exc:
                return _exception_to_result(
                    exc,
                    analysis_id=inp.analysis_id,
                    reason="sample_path_resolve_failed",
                    default_error_code="TOOL_SCHEMA_INVALID",
                )
            if resolved is not None:
                sample_host_path = Path(getattr(resolved, "host_path", resolved))
                sample_display_path = str(
                    getattr(resolved, "display_path", inp.path)
                )
        try:
            result = identify_file(sample_host_path, max_size_mb=max_mb)
            if sample_display_path != str(sample_host_path):
                result = replace(result, absolute_path=sample_display_path)
        except EntryFormatUnsupported as exc:
            indicator = _build_format_unsupported_indicator(
                sample_host_path,
                exc,
                max_size_mb=max_mb,
            )
            if sample_display_path != str(sample_host_path):
                indicator.data["absolute_path"] = sample_display_path
            self.store.append(Bucket.file_meta, indicator)
            log_indicator_write(
                indicator_id=indicator.id,
                bucket=Bucket.file_meta.value,
                kind=indicator.kind,
                severity=indicator.severity.value,
                source_fr=indicator.source_fr,
            )
            return {
                "ok": False,
                "indicator_id": indicator.id,
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "format_unsupported": True,
            }
        try:
            session = await self._ensure_session(inp.analysis_id)
        except Exception as exc:
            return _exception_to_result(
                exc,
                analysis_id=inp.analysis_id,
                reason="sandbox_create_failed",
                default_error_code="SANDBOX_UNAVAILABLE",
            )
        try:
            sandbox_path = await upload_sample_to_sandbox(
                self.sandbox_client,
                session,
                sample_host_path,
                filename="sample.bin",
            )
        except Exception as exc:
            return _exception_to_result(
                exc,
                analysis_id=inp.analysis_id,
                reason="sample_upload_failed",
                default_error_code="SANDBOX_UNAVAILABLE",
            )
        indicator = _build_file_meta_indicator(result, sandbox_path=sandbox_path)
        self.store.append(Bucket.file_meta, indicator)
        log_indicator_write(
            indicator_id=indicator.id,
            bucket=Bucket.file_meta.value,
            kind=indicator.kind,
            severity=indicator.severity.value,
            source_fr=indicator.source_fr,
        )
        embedded_payloads = await self._materialize_embedded_pe_payloads(
            analysis_id=inp.analysis_id,
            data=sample_host_path.read_bytes()
            if result.format in {"PE32", "PE32+"}
            else b"",
            file_meta_indicator_id=indicator.id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "indicator_id": indicator.id,
            "format": result.format,
            "arch": result.arch,
            "routing": result.routing,
            "fingerprints": result.fingerprints,
            "size_bytes": result.size_bytes,
            "sandbox_path": sandbox_path,
            "coverage_notes": result.coverage_notes,
            # C3 document fields (FR-01 AC-8)
            "document_format": result.document_format,
            "document_tier": result.document_tier,
            "is_document": result.is_document,
            "polyglot_document_priority": result.polyglot_document_priority,
        }
        if embedded_payloads:
            response["embedded_payloads"] = embedded_payloads
        return response

    async def _identify_sandbox_resident_sample(
        self,
        inp: FileIdentifyInput,
        *,
        source_analysis_id: str,
        max_size_mb: int,
    ) -> dict[str, Any]:
        """Identify a child sample already materialized inside a sandbox.

        Document recursion produces child payloads under the parent document's
        workspace. This path keeps raw bytes inside the Tool boundary: bytes are
        downloaded from the source sandbox, identified via a private temp file,
        uploaded into the child analysis workspace as `sample.bin`, and only
        structured metadata is returned to the Agent.
        """
        source_session = await get_session(source_analysis_id)
        if source_session is None:
            return {
                "ok": False,
                "error_code": "SANDBOX_UNAVAILABLE",
                "message": (
                    "sandbox-resident sample has no active source session: "
                    f"{source_analysis_id}"
                ),
                "details": {
                    "reason": "source_sandbox_missing",
                    "source_analysis_id": source_analysis_id,
                    "path": inp.path,
                },
                "format_unsupported": True,
            }
        try:
            data = await self.sandbox_client.download(source_session, inp.path)
        except Exception as exc:
            return _exception_to_result(
                exc,
                analysis_id=inp.analysis_id,
                reason="sandbox_child_download_failed",
                default_error_code="SANDBOX_UNAVAILABLE",
            )

        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            result = identify_file(tmp_path, max_size_mb=max_size_mb)
            result = replace(result, absolute_path=inp.path)
        except EntryFormatUnsupported as exc:
            indicator = _build_format_unsupported_indicator(
                inp.path,
                exc,
                max_size_mb=max_size_mb,
            )
            self.store.append(Bucket.file_meta, indicator)
            log_indicator_write(
                indicator_id=indicator.id,
                bucket=Bucket.file_meta.value,
                kind=indicator.kind,
                severity=indicator.severity.value,
                source_fr=indicator.source_fr,
            )
            return {
                "ok": False,
                "indicator_id": indicator.id,
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "format_unsupported": True,
            }
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

        try:
            child_session = await self._ensure_session(inp.analysis_id)
            sandbox_path = f"{child_session.workdir.rstrip('/')}/sample.bin"
            await self.sandbox_client.upload(child_session, sandbox_path, data)
        except Exception as exc:
            return _exception_to_result(
                exc,
                analysis_id=inp.analysis_id,
                reason="sandbox_child_upload_failed",
                default_error_code="SANDBOX_UNAVAILABLE",
            )

        indicator = _build_file_meta_indicator(result, sandbox_path=sandbox_path)
        self.store.append(Bucket.file_meta, indicator)
        log_indicator_write(
            indicator_id=indicator.id,
            bucket=Bucket.file_meta.value,
            kind=indicator.kind,
            severity=indicator.severity.value,
            source_fr=indicator.source_fr,
        )
        embedded_payloads = await self._materialize_embedded_pe_payloads(
            analysis_id=inp.analysis_id,
            data=data if result.format in {"PE32", "PE32+"} else b"",
            file_meta_indicator_id=indicator.id,
        )
        response: dict[str, Any] = {
            "ok": True,
            "indicator_id": indicator.id,
            "format": result.format,
            "arch": result.arch,
            "routing": result.routing,
            "fingerprints": result.fingerprints,
            "size_bytes": result.size_bytes,
            "sandbox_path": sandbox_path,
            "coverage_notes": result.coverage_notes,
            "document_format": result.document_format,
            "document_tier": result.document_tier,
            "is_document": result.is_document,
            "polyglot_document_priority": result.polyglot_document_priority,
        }
        if embedded_payloads:
            response["embedded_payloads"] = embedded_payloads
        return response

    async def _materialize_embedded_pe_payloads(
        self,
        *,
        analysis_id: str,
        data: bytes,
        file_meta_indicator_id: str,
    ) -> list[dict[str, Any]]:
        """Carve nested PE images and upload them under the current workspace."""
        if not data:
            return []
        session = await self._ensure_session(analysis_id)
        payloads: list[dict[str, Any]] = []
        for idx, candidate in enumerate(_find_embedded_pe_candidates(data), start=1):
            child_sample_id = str(ULID())
            extracted_to = (
                f"{session.workdir.rstrip('/')}/children/"
                f"pe_carved_{idx:03d}_{candidate.sha256[:16]}.bin"
            )
            await self.sandbox_client.upload(session, extracted_to, candidate.data)
            indicator = Indicator(
                source_fr="FR-04",
                indicator_type="child_sample_ref",
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                kind="fact",
                evidence_refs=[file_meta_indicator_id],
                data={
                    "source": "pe_carving",
                    "source_region": candidate.source_region,
                    "offset": candidate.offset,
                    "decoded_offset": candidate.decoded_offset,
                    "decoder": candidate.decoder,
                    "decoder_metadata": candidate.metadata,
                    "sha256": candidate.sha256,
                    "size_bytes": candidate.size_bytes,
                    "suggested_format": candidate.format,
                    "child_sample_id": child_sample_id,
                    "child_analysis_id": child_sample_id,
                    "extracted_to": extracted_to,
                    "materialized": True,
                    "recursive_ready": True,
                    "materialization_status": "worker_materialized",
                },
            )
            self.store.append(Bucket.embedded_payloads, indicator)
            log_indicator_write(
                indicator_id=indicator.id,
                bucket=Bucket.embedded_payloads.value,
                kind=indicator.kind,
                severity=indicator.severity.value,
                source_fr=indicator.source_fr,
            )
            payloads.append(dict(indicator.data))
        if payloads and self.embedded_payload_handler is not None:
            handled = self.embedded_payload_handler(analysis_id, payloads)
            if inspect.isawaitable(handled):
                return await handled
            return handled
        return payloads

    async def _ensure_session(self, analysis_id: str) -> SandboxSession:
        """Return the session bound to ``analysis_id``, creating one if absent.

        Delegates to :func:`get_or_create_session` so the check-or-create
        window is serialised per ``analysis_id`` — guards against the
        FB-F-02 race where an LLM's parallel tool calls would each spin up
        a distinct remote sandbox.
        """
        client: SandboxClient = self.sandbox_client
        try:
            return await get_or_create_session(client, analysis_id)
        except Exception as exc:
            raise _SessionCreateFailed(exc, analysis_id=analysis_id) from exc


class _SessionCreateFailed(Exception):
    """Wrapper used to route session creation failures through tool output."""

    def __init__(self, cause: Exception, *, analysis_id: str) -> None:
        self.cause = cause
        self.analysis_id = analysis_id
        super().__init__(str(cause))


def _exception_to_result(
    exc: Exception,
    *,
    analysis_id: str,
    reason: str,
    default_error_code: str,
) -> dict[str, Any]:
    """Convert sandbox admission failures into recoverable ToolMessages."""
    if isinstance(exc, _SessionCreateFailed):
        exc = exc.cause
        reason = "sandbox_create_failed"
        default_error_code = "SANDBOX_UNAVAILABLE"

    if isinstance(exc, BinaryAnalysisError):
        details = dict(exc.details)
        message = exc.message
        error_code = exc.error_code
    else:
        details = {}
        message = f"{reason}: {type(exc).__name__}"
        error_code = default_error_code

    details.setdefault("reason", reason)
    details.setdefault("analysis_id", analysis_id)
    details.setdefault("error_type", type(exc).__name__)
    return {
        "ok": False,
        "error_code": error_code,
        "reason": details.get("reason"),
        "message": message,
        "details": details,
    }


__all__ = [
    "FileIdentifyInput",
    "FileIdentifyResult",
    "FileIdentifyTool",
    "identify_file",
]
