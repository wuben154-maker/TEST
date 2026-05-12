"""Minimal PE / ELF / Mach-O sample bytes for FileIdentifyTool tests (C6).

This module provides byte-level fixtures for the C6 batch.  We deliberately
construct the samples programmatically (rather than committing pre-built
binaries) so the repository stays free of opaque binary blobs that an
automated malware scanner might flag.

Each fixture satisfies the *minimum* structural requirements needed by
:func:`binary_analysis.tools.file_identify.identify_file`:

- PE32 / PE32+: DOS stub with valid ``e_lfanew`` → ``PE\\x00\\x00`` signature →
  minimal ``IMAGE_FILE_HEADER`` with a real ``Machine`` value →
  ``IMAGE_OPTIONAL_HEADER`` whose ``Magic`` distinguishes 32 vs 32+.
- ELF64: canonical ``\\x7fELF`` ident + a 64-byte header with a real
  ``e_machine`` value.
- Mach-O 64: ``0xFEEDFACF`` magic + ``cputype`` / ``cpusubtype`` /
  ``filetype``.

Counter-examples intentionally do NOT satisfy any of the magic-number
checks, so :func:`identify_file` raises :class:`EntryFormatUnsupported`.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# PE  (Windows)
# ---------------------------------------------------------------------------

_PE_MACHINE_X86 = 0x014C
_PE_MACHINE_X64 = 0x8664
_PE_MACHINE_ARM = 0x01C0
_PE_MACHINE_ARM64 = 0xAA64

_PE_OPT_MAGIC_32 = 0x010B
_PE_OPT_MAGIC_32_PLUS = 0x020B


def _make_pe(*, machine: int, pe_plus: bool) -> bytes:
    """Build a minimum-viable PE image for structural recognition.

    The resulting bytes are NOT a loadable executable; they only expose the
    fields that static identification relies on:

    - DOS magic ``MZ`` at offset 0.
    - ``e_lfanew`` at offset ``0x3C`` pointing at the NT header.
    - PE signature ``PE\\x00\\x00`` + ``IMAGE_FILE_HEADER`` (20 bytes) at
      that offset.
    - ``IMAGE_OPTIONAL_HEADER`` whose first two bytes encode PE32 vs PE32+.
    """
    e_lfanew = 0x40
    dos_header = b"MZ" + b"\x00" * (e_lfanew - 6) + struct.pack("<I", e_lfanew)
    opt_magic = _PE_OPT_MAGIC_32_PLUS if pe_plus else _PE_OPT_MAGIC_32
    size_opt_header = 240 if pe_plus else 224
    file_header = struct.pack(
        "<HHIIIHH",
        machine,
        0,
        0,
        0,
        0,
        size_opt_header,
        0x0002,
    )
    optional_header = struct.pack("<H", opt_magic) + b"\x00" * (size_opt_header - 2)
    return dos_header + b"PE\x00\x00" + file_header + optional_header


MINIMAL_PE32_X86: bytes = _make_pe(machine=_PE_MACHINE_X86, pe_plus=False)
MINIMAL_PE32_PLUS_X64: bytes = _make_pe(machine=_PE_MACHINE_X64, pe_plus=True)
MINIMAL_PE_ARM64: bytes = _make_pe(machine=_PE_MACHINE_ARM64, pe_plus=True)

# ---------------------------------------------------------------------------
# ELF  (Linux)
# ---------------------------------------------------------------------------

_ELF_EM_386 = 3
_ELF_EM_X86_64 = 62
_ELF_EM_ARM = 40
_ELF_EM_AARCH64 = 183


def _make_elf64(e_machine: int) -> bytes:
    """Build a minimum-viable 64-bit ELF header (little-endian)."""
    e_ident = (
        b"\x7fELF"
        + bytes([2, 1, 1, 0])  # class=ELF64, data=LE, version=1, osabi=SYSV
        + b"\x00" * 8
    )
    rest = struct.pack(
        "<HHIQQQIHHHHHH",
        2,  # e_type = ET_EXEC
        e_machine,
        1,  # e_version
        0,  # e_entry
        0,  # e_phoff
        0,  # e_shoff
        0,  # e_flags
        64,  # e_ehsize
        0,
        0,
        0,
        0,
        0,
    )
    return e_ident + rest


MINIMAL_ELF64_X64: bytes = _make_elf64(_ELF_EM_X86_64)
MINIMAL_ELF64_ARM64: bytes = _make_elf64(_ELF_EM_AARCH64)

# ---------------------------------------------------------------------------
# Mach-O  (macOS / iOS)
# ---------------------------------------------------------------------------

_MACHO_MAGIC_64_LE = 0xFEEDFACF

_MACHO_CPU_X86_64 = 0x01000007
_MACHO_CPU_ARM64 = 0x0100000C


def _make_macho64(cputype: int) -> bytes:
    """Build a minimum-viable 64-bit Mach-O header (little-endian)."""
    return struct.pack(
        "<IIIIIIII",
        _MACHO_MAGIC_64_LE,
        cputype,
        0,  # cpusubtype
        2,  # filetype = MH_EXECUTE
        0,  # ncmds
        0,  # sizeofcmds
        0,  # flags
        0,  # reserved
    )


MINIMAL_MACHO64_X64: bytes = _make_macho64(_MACHO_CPU_X86_64)
MINIMAL_MACHO64_ARM64: bytes = _make_macho64(_MACHO_CPU_ARM64)

# ---------------------------------------------------------------------------
# Counter-examples  (FR-01 AC-6 / E2E-01 exception E1)
# ---------------------------------------------------------------------------

COUNTEREXAMPLE_TEXT: bytes = b"This is plain UTF-8 text and not an executable.\n"
COUNTEREXAMPLE_ZIP_AS_EXE: bytes = b"PK\x03\x04" + b"\x00" * 256
COUNTEREXAMPLE_EMPTY: bytes = b""

# ---------------------------------------------------------------------------
# Fixture materialisation helpers
# ---------------------------------------------------------------------------

SampleKind = Literal[
    "pe32_x86",
    "pe32plus_x64",
    "pe_arm64",
    "elf64_x64",
    "elf64_arm64",
    "macho64_x64",
    "macho64_arm64",
    "text",
    "zip_as_exe",
    "empty",
]

_KIND_TO_BYTES: dict[str, bytes] = {
    "pe32_x86": MINIMAL_PE32_X86,
    "pe32plus_x64": MINIMAL_PE32_PLUS_X64,
    "pe_arm64": MINIMAL_PE_ARM64,
    "elf64_x64": MINIMAL_ELF64_X64,
    "elf64_arm64": MINIMAL_ELF64_ARM64,
    "macho64_x64": MINIMAL_MACHO64_X64,
    "macho64_arm64": MINIMAL_MACHO64_ARM64,
    "text": COUNTEREXAMPLE_TEXT,
    "zip_as_exe": COUNTEREXAMPLE_ZIP_AS_EXE,
    "empty": COUNTEREXAMPLE_EMPTY,
}


def write_sample(target: Path, kind: SampleKind) -> Path:
    """Write the named fixture bytes to ``target`` and return the path.

    Args:
        target: Destination file path.  Parent directories are created on
            demand.
        kind: One of the :data:`SampleKind` literals.

    Returns:
        The absolute ``Path`` of the materialised fixture.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_KIND_TO_BYTES[kind])
    return target.resolve()


__all__ = [
    "COUNTEREXAMPLE_EMPTY",
    "COUNTEREXAMPLE_TEXT",
    "COUNTEREXAMPLE_ZIP_AS_EXE",
    "MINIMAL_ELF64_ARM64",
    "MINIMAL_ELF64_X64",
    "MINIMAL_MACHO64_ARM64",
    "MINIMAL_MACHO64_X64",
    "MINIMAL_PE32_PLUS_X64",
    "MINIMAL_PE32_X86",
    "MINIMAL_PE_ARM64",
    "SampleKind",
    "write_sample",
]
