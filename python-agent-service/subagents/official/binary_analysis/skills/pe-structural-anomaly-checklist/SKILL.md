---
name: pe-structural-anomaly-checklist
description: |
  FR-04 PE (PE32/PE32+) structural anomaly checklist: entry-point placement,
  section permissions / overlap / size ratios, TLS callback enumeration,
  overlay (post-image) detection, Rich Header toolchain fingerprint, and
  Load Config Directory mitigations (SafeSEH, CFG, ASLR/DEP flags). Maps checks
  to `headers` / `sections` facts (AC-3, AC-8, AC-9, AC-12, AC-13). Activates
  on Windows PE static analysis or any prompt centering on TLS callbacks,
  overlay blobs, or rich header signals; read together with
  `performing-static-malware-analysis-with-pe-studio` for imports, strings, and
  resources. 适用于 PE 结构疑点、入口点 / TLS 回调 / Overlay / Rich Header /
  Load Config 特征审查；与上游 PEStudio 方法论互补而非重复 imports/strings 深度。
license: Apache-2.0
compatibility: binary_analysis FR-04 · schema_version 1.0.0
allowed-tools: sandbox_session python_exec bash evidence_chain
metadata:
  id: Gap-02
  batch: C9
  adr: ADR-05, ADR-13
  fr: FR-04
  stability: stable
---

# PE Structural Anomaly Checklist (Gap-02)

> The upstream PEStudio-style skill
> (`performing-static-malware-analysis-with-pe-studio`) documents *what*
> pefile reveals. This checklist documents *which* anomalies matter for
> FR-04's acceptance criteria and maps each one directly to an evidence
> chain indicator. Read both: the PEStudio skill for extraction
> methodology, this one for the verdict-driving signals.

## When to Use

- `file_meta` bucket contains `indicator_type: file_meta` with
  `data.format = "PE"` (written by `file_identify` at FR-01) and you
  are at FR-04 structural parsing.
- You need a deterministic, repeatable list of structural red flags
  without drifting into imports / strings analysis (those stay in FR-06
  / the upstream PEStudio skill).
- You are preparing the `fact` indicators FR-07's priority queue needs
  (entry point function, TLS Callbacks — IR-05 / ADR-06).

**Do not use** for import-table / strings / resources anomaly analysis
— those belong in the upstream PEStudio skill and the FR-06 IOC
extraction workflow. Do not use for ELF / Mach-O — they have their own
specialist skills (`analyzing-linux-elf-malware`,
`analyzing-macho-structure`).

## Routing (orchestrator alignment)

- **Triggered by**: `binary-analysis-e2e-orchestrator` — Stage FR-02 (PE
  triage heuristics: timestamps, section names/counts) and Stage FR-04
  (full structural checklist alongside
  `performing-static-malware-analysis-with-pe-studio`).
- **Returns to**: the same orchestrator after appending FR-04 facts; do
  not claim FR-05 packing verdicts or FR-06 IOC ownership here.
- **Downgrade**: If `pefile` raises on a malformed image, retry with
  `lief` inside the sandbox. If both parsers fail, emit a
  `malformed_structure` (or stage-appropriate) fact per orchestrator
  Stage FR-04 guidance and continue; optionally add an
  `analysis_coverage` marker in the most relevant structural bucket when
  a checklist slice is skipped.

## Prerequisites

- `pefile` and `lief` available inside the sandbox; `pefile` is the
  primary tool because it exposes Rich Header and Load Config with
  stable attribute names, `lief` is a fallback for malformed files.
- Sample already uploaded to `/workspace/<analysis_id>/` (C6). Before
  `python_exec` or `bash`, follow the orchestrator: ensure a sandbox
  session exists (`sandbox_session`); run all parsing through
  `python_exec` in that workspace — **never read raw sample bytes on the
  host** (ADR-05 / NFR-04).
- Read `binary-analysis-evidence-chain-protocol` (Proto-02) before
  appending any indicator — bucket is chosen as the first argument to
  `evidence_chain.append_indicator` / `EvidenceChainStore.append`, not
  as a field on the Indicator model; `kind: fact` and `source_fr:
  "FR-04"` apply to every item below.

## The Checklist

Each row is (a) the FR-04 AC being satisfied, (b) the pefile attribute
path to probe, (c) the `indicator_type` to emit, (d) the default
`severity`. All indicators are `kind: fact` with
`data.producer = "pefile"` unless stated otherwise.

### 1 — Entry point placement (FR-04 AC-3)

The entry point VA maps back to one of the image's sections via
`pefile.get_section_by_rva(ep_rva)`. A healthy PE points `AddressOfEntryPoint`
inside `.text` (or an equivalent code section marked `IMAGE_SCN_CNT_CODE`).

| Check | `indicator_type` | `severity` | Rationale |
|-------|-------|-----------|-----------|
| EP VA is 0 | `entry_point_zero` | `CRITICAL` | Stripped / weaponised stub |
| EP is not inside any section | `entry_point_oob` | `CRITICAL` | Manual header forging |
| EP's owning section lacks `IMAGE_SCN_MEM_EXECUTE` | `entry_point_non_exec_section` | `CRITICAL` | Classic packer tell |
| EP's owning section is writable (`IMAGE_SCN_MEM_WRITE`) | `entry_point_wx_section` | `CRITICAL` | Runtime-patched unpack stub |
| EP's owning section name not in `{.text, .code, CODE, .init}` | `entry_point_odd_section` | `WARNING` | Custom packer / loader |

Bucket: `headers`. Data payload: `{"producer": "pefile", "ep_rva":
0x..., "section": "<name>", "section_characteristics": 0x...}`.

### 2 — Section table sanity (FR-04 AC-3)

Iterate `pe.sections` once and emit one `pe_section` fact per section
(INFO) plus any of the anomalies below.

| Check | `indicator_type` | `severity` |
|-------|-------|-----------|
| Section is both writable AND executable | `section_writable_executable` | `CRITICAL` |
| Raw size = 0 but virtual size > 0 (lazy unpack) | `section_empty_raw` | `CRITICAL` |
| `virtual_size / max(raw_size, 1) > 10` | `section_virtual_oversized` | `WARNING` |
| `raw_size > virtual_size * 4` | `section_raw_oversized` | `INFO` |
| Two sections overlap on file or in VA space | `section_overlap` | `CRITICAL` |
| Section name non-printable / > 8 bytes stored as UTF-8 garbage | `section_name_nonprintable` | `WARNING` |
| Section entropy ≥ 7.2 | `section_high_entropy` | `WARNING` *(seed for FR-05)* |

Bucket: `sections`. Data payload includes `{producer, name, raw_size,
virtual_size, characteristics, entropy, file_offset, virtual_address}`.

### 3 — TLS Callback enumeration (FR-04 AC-8)

Code listed in `IMAGE_DIRECTORY_ENTRY_TLS.AddressOfCallBacks` runs
*before* `main`, making it a classic hiding spot for unpack stubs,
anti-debug pivots, and self-modifying stubs.

```python
if hasattr(pe, "DIRECTORY_ENTRY_TLS"):
    tls = pe.DIRECTORY_ENTRY_TLS.struct
    cb_rva = tls.AddressOfCallBacks - pe.OPTIONAL_HEADER.ImageBase
    # Walk the null-terminated array of callback addresses
    callbacks = []
    offset = pe.get_offset_from_rva(cb_rva)
    while True:
        ptr = pe.get_dword_at_rva(cb_rva) if pe.PE_TYPE == pefile.PE_TYPE.PE32 \
            else pe.get_qword_at_rva(cb_rva)
        if ptr == 0:
            break
        callbacks.append(ptr)
        cb_rva += 4 if pe.PE_TYPE == pefile.PE_TYPE.PE32 else 8
```

Emit:

| Situation | `indicator_type` | `severity` |
|-----------|-------|-----------|
| `DIRECTORY_ENTRY_TLS` present, zero callbacks | `tls_directory_empty` | `INFO` |
| 1..N callbacks found | `tls_callback` (one per) | `WARNING` |
| Callback VA outside of any section | `tls_callback_oob` | `CRITICAL` |
| Callback VA inside a writable section | `tls_callback_wx` | `CRITICAL` |

Bucket: `headers`. Data payload: `{"producer": "pefile",
"callback_va": 0x..., "section": "<name>"}`.
FR-07 MUST consume `tls_callback` facts when building the
decompilation priority queue (ADR-06).

### 4 — Overlay detection (FR-04 AC-9)

Overlay = bytes present in the file after the last section's
`PointerToRawData + SizeOfRawData`. Legitimate uses: certificate tables
(Authenticode), installer self-extractors. Malicious uses: stashed
config, second-stage payload, stolen-file steganography.

```python
last_section = max(pe.sections, key=lambda s: s.PointerToRawData + s.SizeOfRawData)
end_of_image = last_section.PointerToRawData + last_section.SizeOfRawData
file_size = pe.__data__.__len__()
overlay_size = file_size - end_of_image
```

| Check | `indicator_type` | `severity` |
|-------|-------|-----------|
| `overlay_size == 0` | `overlay_absent` | `INFO` |
| Overlay size > 0, Authenticode-shaped (starts with `0x30 0x82`) | `overlay_authenticode` | `INFO` |
| Overlay size > 0, entropy < 6.0 | `overlay_data` | `INFO` |
| Overlay size > 0, entropy ≥ 6.0 | `overlay_high_entropy` | `WARNING` |
| Overlay starts with `MZ` or `PE\0\0` | `overlay_embedded_pe` | `CRITICAL` |

Bucket: `sections`. Data payload: `{"producer": "pefile", "offset":
<file_offset>, "size": <bytes>, "entropy": <float>, "preview_sha256":
"<hash of first 4 KiB>"}`. **Never include raw overlay bytes** in LLM
context — that violates NFR-03.

### 5 — Rich Header fingerprinting (FR-04 AC-12)

The Rich Header is an undocumented Microsoft-linker artefact between
the DOS stub and the PE header. Each `comp.id` encodes a `(prodID,
build)` pair — the toolchain versions that contributed object files.
Two unrelated samples sharing a Rich Header fingerprint is strong
attribution signal.

```python
rh = pe.parse_rich_header()
if rh:
    checksum = rh["checksum"]
    entries = [
        {"comp_id": cid >> 16, "build": cid & 0xFFFF, "count": cnt}
        for cid, cnt in zip(rh["values"][::2], rh["values"][1::2])
    ]
```

| Situation | `indicator_type` | `severity` |
|-----------|-------|-----------|
| Rich Header parses with ≥ 1 entry | `rich_header_fingerprint` | `INFO` |
| Rich Header present but checksum mismatch (forged) | `rich_header_forged` | `CRITICAL` |
| Rich Header absent on an otherwise MSVC-shaped binary | `rich_header_stripped` | `INFO` |

Bucket: `headers`. Data payload: `{"producer": "pefile", "checksum":
0x..., "entries": [...]}`.
FR-13 uses this for family / campaign clustering, don't drop the raw
entries.

### 6 — Load Config security features (FR-04 AC-13)

The Load Config Directory advertises which mitigations the binary
*opts into*. Malware rarely opts into anything.

```python
lc = getattr(pe, "DIRECTORY_ENTRY_LOAD_CONFIG", None)
if lc:
    struct = lc.struct
    # Useful fields (PE32+):
    # - SEHandlerTable / SEHandlerCount   (SafeSEH exception table)
    # - GuardCFCheckFunctionPointer        (Control Flow Guard stub)
    # - GuardCFFunctionTable / GuardCFFunctionCount
    # - DllCharacteristics (also in optional header) for DYNAMIC_BASE
    #   (ASLR), NX_COMPAT (DEP), HIGH_ENTROPY_VA, FORCE_INTEGRITY.
```

Emit one `fact` in `headers` with
`indicator_type: load_config_features`, `severity: INFO`, and
`data.producer: "pefile"`.
Its structured `data` summarises each mitigation:

```json
{
  "source_fr": "FR-04",
  "indicator_type": "load_config_features",
  "severity": "INFO",
  "kind": "fact",
  "data": {
    "producer": "pefile",
    "safe_seh": true,
    "safe_seh_handler_count": 42,
    "control_flow_guard": false,
    "cfg_function_count": 0,
    "dynamic_base_aslr": true,
    "nx_compat_dep": true,
    "high_entropy_va": false,
    "force_integrity": false
  }
}
```

Then emit one *additional* indicator per missing mitigation that
FR-13's rules engine wants to score:

| Missing feature | `indicator_type` | `severity` |
|-----------------|-------------------|------------|
| `DllCharacteristics & IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE == 0` | `mitigation_aslr_missing` | `WARNING` |
| `DllCharacteristics & IMAGE_DLLCHARACTERISTICS_NX_COMPAT == 0` | `mitigation_dep_missing` | `WARNING` |
| CFG opt-in absent on a 64-bit sample compiled after MSVC 2015 | `mitigation_cfg_missing` | `INFO` |
| SafeSEH table absent on a 32-bit MSVC sample | `mitigation_safeseh_missing` | `INFO` |

Bucket for all of the above: `headers`.

## Cross-References to Other Skills

- FR-04 imports / capability grouping → upstream
  `performing-static-malware-analysis-with-pe-studio`.
- FR-05 entropy & packing decision → this skill seeds it via
  `section_high_entropy`; the decision itself runs in
  `analyzing-packed-malware-with-upx-unpacker` (UPX) or
  `detecting-commercial-packers-with-die` (Themida / VMProtect / Enigma).
  For DIE scans, use `bash` inside the sandbox per Stage FR-05; do not
  invent standalone agent tools.
- FR-07 decompilation priority queue → consumes `tls_callback` and
  `entry_point_*` facts from this skill (IR-05 / ADR-06).
- FR-17 behavior chain → `two-phase-behavior-chain-reconstruction`
  reads these facts when sketching the module-level graph.

## Key Concepts

| Term | Definition |
|------|------------|
| **Entry Point (EP)** | RVA in `OPTIONAL_HEADER.AddressOfEntryPoint`; first code executed when the loader transfers control. |
| **Section Characteristics** | Bit flags on each section header (readable / writable / executable / contains-code / contains-initialized-data / discardable). |
| **TLS Callback** | Pointer registered in the TLS directory; invoked by the loader *before* the EP fires, per thread. |
| **Overlay** | File bytes past the last section's raw extent — not memory-mapped by the loader. |
| **Rich Header** | Undocumented signature block between the DOS stub and PE header storing Microsoft toolchain version counters; acts as a compiler fingerprint. |
| **Load Config Directory** | Optional PE data directory declaring security features (SafeSEH, CFG, ASLR opt-in flags). |
| **DllCharacteristics** | Bitfield in the optional header declaring the loader-visible mitigation opt-ins (`DYNAMIC_BASE`, `NX_COMPAT`, `HIGH_ENTROPY_VA`, `FORCE_INTEGRITY`, `CONTROL_FLOW_GUARD`, ...). |

## Tools & Systems

- **pefile** — Python PE parser; the primary tool here. `parse_rich_header`,
  `DIRECTORY_ENTRY_TLS`, `DIRECTORY_ENTRY_LOAD_CONFIG`, and
  `get_section_by_rva` are the only APIs you strictly need.
- **lief** — Fallback when `pefile` raises on malformed PEs; also the
  parser used for Mach-O (Gap-01) and ELF.
- **bash** — Optional cross-check (e.g. DIE) when entropy anomalies fire;
  delegate packer signature work to `detecting-commercial-packers-with-die`
  rather than duplicating FR-05 methodology here.

## Common Scenarios

### Scenario: Tight checklist run on an MSVC-compiled dropper

**Context**: A 32-bit PE arrives from a phishing campaign. FR-01 says
PE32, FR-02 heuristic triage records `packing_severity_hint=LIGHT`. The analyst needs
the structural anomaly summary before budgeting Ghidra time.

**Approach**:
1. EP (section 1) — points at `.rsrc` (`entry_point_non_exec_section`, CRITICAL);
   an unmistakable packer signature.
2. Section table — `.text` has raw size 0 but virtual size 0x8000
   (`section_empty_raw`, CRITICAL); `.rsrc` entropy 7.6
   (`section_high_entropy`, WARNING).
3. TLS — no TLS directory.
4. Overlay — 24 KiB trailing blob, entropy 7.8
   (`overlay_high_entropy`, WARNING); preview hash captured.
5. Rich Header — parses with 4 entries (MSVC 2017 linker + cvtres
   + link.exe) → `rich_header_fingerprint`; useful for campaign
   clustering later.
6. Load Config — ASLR on, DEP on, SafeSEH **missing** on a 32-bit
   MSVC binary → `mitigation_safeseh_missing` (INFO).

FR-05 immediately flags `packed_pe` because `.text` is hollow and
`.rsrc` is a code-shaped high-entropy blob; FR-07 schedules the
overlay for secondary unpack after EP-triggered runtime unpacking.

**Pitfalls**:
- Assuming a missing Rich Header means non-MSVC — MinGW, Rust and
  packer-stripped samples all legitimately miss it.
- Treating every high-entropy section as "packed" — high-entropy
  resources are common (PNG assets, JPEG icons, compressed game
  data). The seed is a hint, FR-05 makes the call.
- Counting overlay as a section — it is not mapped and does not belong
  in the section table; use a dedicated `overlay_*` `indicator_type`.

## Output Format

This skill does not emit its own report. Successful application is
visible as a stable set of indicators in the evidence chain:

- At least one of `entry_point_*` in `headers`.
- N `pe_section` facts in `sections`, plus any triggered anomaly
  `indicator_type` values
  from section 2.
- Zero-or-more `tls_callback[_oob|_wx]` in `headers`.
- One of `overlay_*` in `sections`.
- `rich_header_fingerprint` (or `rich_header_forged` /
  `rich_header_stripped`) in `headers`.
- `load_config_features` plus any triggered `mitigation_*_missing` in
  `headers`.

Every indicator is `kind: fact`, `source_fr: "FR-04"`, with
`confidence` omitted per Proto-02. Put the parser provenance in
`data.producer` (`"pefile"` by default, `"lief"` on fallback), never in a
top-level `tool` field.
