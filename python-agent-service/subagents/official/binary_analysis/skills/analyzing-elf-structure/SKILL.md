---
name: analyzing-elf-structure
description: |
  Parses ELF (Executable and Linkable Format) structure for FR-04 / IR-09
  parity with the PE checklist (Gap-02) and the Mach-O parser (Gap-01).
  Walks the ELF header, program headers (PT_LOAD, PT_DYNAMIC, PT_INTERP,
  PT_GNU_STACK, PT_GNU_RELRO, PT_GNU_EH_FRAME), section headers
  (.text, .data, .bss, .dynamic, .got, .plt, .init_array, .fini_array,
  .symtab / .dynsym), the dynamic section (DT_NEEDED, DT_RPATH / DT_RUNPATH,
  DT_BIND_NOW), entry-point placement, GNU security mitigations, and
  .init_array / .fini_array pre-main initialiser pointers. Runs only inside
  the analysis sandbox via `python_exec` (e.g. lief) and `bash` (e.g. readelf);
  never on the host. Emits `kind: fact` indicators into the `headers`,
  `imports`, and `sections` buckets through `evidence_chain`. Activates on ELF
  samples (x86_64, ARM, AArch64, MIPS, RISC-V), shared objects (.so), kernel
  modules (.ko), or any Linux / Android / embedded malware FR-04 structural
  parsing request.
license: Apache-2.0
compatibility: binary_analysis FR-04 · IR-09 · schema_version 1.0.0
allowed-tools: sandbox_session bash python_exec evidence_chain
metadata:
  id: Gap-05
  batch: C10
  adr: ADR-05, ADR-13
  fr: FR-04
  ir: IR-09
  stability: stable
---

# Analyzing ELF Structure (Gap-05)

> `skills/` already contains a broad ELF specialist
> (`analyzing-linux-elf-malware`, originally brought in from upstream)
> that covers dynamic tracing (strace / ltrace), GDB, Ghidra
> decompilation, UPX unpacking, and string-based IOC extraction —
> surfaces that belong to FR-05, FR-06, and FR-07, not FR-04.
> This skill fills the structural-parsing gap so FR-04's acceptance criterion
> "对 ELF 文件，系统提供对等的结构解析能力" (AC-16) and IR-09 "对 ELF /
> Mach-O 的结构解析深度必须与 PE 对等" are met with a scope-limited,
> evidence-chain-aware workflow that is strictly analogous to Gap-01
> (`analyzing-macho-structure`) and Gap-02 (`pe-structural-anomaly-checklist`).

## Routing

- **Who loads this skill:** `binary-analysis-e2e-orchestrator` (Proto-01) at Stage FR-02 (ELF triage heuristics only) and Stage FR-04 (full structural pass). Assumes FR-01 already wrote `file_meta`; do not call `file_identify` again.
- **What it feeds:** Append-only writes via `evidence_chain` into `headers`, `sections`, and `imports` for downstream FR-05 through FR-08. FR-07 consumes `suspicious_import`, `elf_entry_point_*`, and `elf_init_array_entry`; code reverse engineering routes to `analyzing-linux-elf-malware` (FR-07), not this skill.
- **Degradation:** If parsing cannot complete, emit `malformed_structure` and an `analysis_coverage` indicator. If `readelf` / `objdump` are missing, continue with the Python parser and record the tool gap; never block the E2E pipeline.
- **Document path:** If `file_meta` indicates a document tier (`P0` / `P1` / `P2`), follow `document-analysis-e2e-orchestrator` instead; this skill is binary-only.

## When to Use

- The sample's `file_meta` bucket carries `indicator_type: file_meta`
  with `data.format = "ELF"` (written by `file_identify` at FR-01).
- You need to extract the ELF header, program headers, section headers,
  dynamic imports, and GNU mitigation flags before FR-05 (entropy), FR-06
  (strings), or FR-07 (decompilation) runs.
- Investigating a shared object (`.so`), kernel module (`.ko`), or a
  multi-arch ELF (e.g. a fat Android `.so` with both ARM and x86 slices
  embedded via the ABI split mechanism).
- A Linux / Android incident response requires a structural fingerprint
  (entry-point placement, PT_GNU_STACK, DT_RPATH) for attribution.

**Do not use** for ELF dynamic tracing or code reverse engineering — that is
FR-07 via `analyzing-linux-elf-malware`. Do not use for strings / IOC extraction
(FR-06) or runtime behavior (FR-17).

## Prerequisites

- `lief` (ELF parser) available inside the analysis sandbox image. Preferred
  over `pyelftools` for FR-04 because `lief` exposes sections, segments, and
  the dynamic symbol table under a uniform interface shared with the PE and
  Mach-O parsers used in Gap-01 / Gap-02.
- `readelf` / `objdump` available via `bash` for best-effort cross-check;
  record missing binutils in `analysis_coverage` if no cross-check ran.
- The sample is already under `/workspace/<analysis_id>/` (sandbox session
  workspace). **Never read the raw bytes on the host** — ADR-05 / NFR-04
  mandates sandbox-only execution.
- Before any primitive call, if no session exists, create it with
  `sandbox_session(action="create")` (Proto-01 scheduling rule) before
  `python_exec` or `bash`.
- Before appending any indicator, read
  `binary-analysis-evidence-chain-protocol` (Proto-02) for the bucket
  routing + `kind: fact` contract. Indicators use `source_fr: "FR-04"` and
  append through `evidence_chain` (the schema has no `source_skill` field).

## Budget and LLM rounds (NFR-05)

Stay within the session limits in `agent.md` (`{max_rounds}`,
`{token_budget}`, `{threshold_pct}`). This workflow does not set those
values; the orchestrator and control surface do. Avoid unbounded
`readelf` / disassembly or byte scans — keep output bounded and
structured so FR-08 remains within the evidence-driven budget.

## Workflow

### Step 1: Confirm ELF magic & classify e_type / e_machine

Every ELF file opens with a 4-byte magic (`\x7fELF`). The ELF header then
declares the file's ABI class (32- vs 64-bit), endianness, OS/ABI, object
type (`ET_EXEC`, `ET_DYN`, `ET_REL`, `ET_CORE`), target machine
(`EM_X86_64`, `EM_ARM`, `EM_AARCH64`, `EM_MIPS`, `EM_RISCV`), and the
virtual entry-point address.

```python
# Via python_exec inside the sandbox.
import lief

sample = "/workspace/{analysis_id}/sample.elf"
elf = lief.ELF.parse(sample)
if elf is None:
    raise RuntimeError("lief: not a valid ELF file")

hdr = elf.header
print(
    f"e_type={hdr.file_type.name} "
    f"e_machine={hdr.machine_type.name} "
    f"e_class={'ELF64' if elf.type == lief.ELF.ELF_CLASS.CLASS64 else 'ELF32'} "
    f"e_entry=0x{hdr.entrypoint:x} "
    f"e_flags=0x{hdr.processor_flag:x} "
    f"stripped={elf.get_section('.symtab') is None}"
)
```

**Indicators to emit** (bucket: `headers`, `kind: fact`,
`data.producer: "lief"`):

| `indicator_type` | When to emit | `severity` |
|-----------------|--------------|-----------|
| `elf_header` | always | `INFO` |
| `elf_stripped` | `.symtab` absent | `INFO` |
| `elf_shared_object_pie` | `e_type = ET_DYN` on an executable (PIE) | `INFO` |
| `elf_et_rel_fragment` | `e_type = ET_REL` — relocatable, no segments | `WARNING` |

### Step 2: Program headers (segments) → `headers` bucket

Program headers describe *runtime* layout: which file ranges map to memory
(PT_LOAD), where `ld.so` is (PT_INTERP), where the dynamic linker data lives
(PT_DYNAMIC), and what GNU security policies are requested
(PT_GNU_STACK, PT_GNU_RELRO).

```python
for seg in elf.segments:
    print(
        f"type={seg.type.name} "
        f"vaddr=0x{seg.virtual_address:x} "
        f"vsize=0x{seg.virtual_size:x} "
        f"fsize=0x{seg.physical_size:x} "
        f"flags={seg.flags}"
    )
```

**Anomalies that aligned FR-04 AC-3 / AC-13 already flags for PE/Mach-O;
replicate for ELF**:

| `indicator_type` | Trigger | `severity` |
|-----------------|---------|-----------|
| `elf_wx_load_segment` | Any `PT_LOAD` with both `PF_W` and `PF_X` flags | `CRITICAL` |
| `elf_segment_size_mismatch` | `p_memsz > p_filesz * 4` — runtime zero-fill anomaly (packer unpack buffer) | `WARNING` |
| `elf_no_pt_gnu_stack` | `PT_GNU_STACK` segment absent (stack is implicitly executable) | `WARNING` |
| `elf_executable_stack` | `PT_GNU_STACK` present but `PF_X` is set | `CRITICAL` |
| `elf_no_pt_gnu_relro` | `PT_GNU_RELRO` absent (GOT/PLT not read-only after relocation) | `INFO` |
| `elf_missing_pt_interp` | `e_type = ET_EXEC` but `PT_INTERP` absent — statically linked | `INFO` |

> **Note on `elf_no_pt_gnu_stack`:** legitimate statically compiled binaries
> (Go, musl-libc) may legitimately omit this segment. Cross-reference with
> `elf_missing_pt_interp`; if both are present the binary is static and the
> absence is expected.

### Step 3: Section headers → `sections` bucket

Section headers describe the *link-time* view: named regions (.text, .data,
.rodata, .bss, .got, .plt, .dynamic, .init_array, .fini_array). Malware
commonly strips or renames sections — the absence of the section-header table
itself is a signal.

```python
if not elf.sections:
    # Section table stripped — valid ELF but reduces static analysis surface.
    print("WARN: no section headers (section table stripped)")
else:
    for sec in elf.sections:
        print(
            f"name={sec.name!r} "
            f"type={sec.type.name} "
            f"flags={sec.flags} "
            f"vaddr=0x{sec.virtual_address:x} "
            f"size={sec.size} "
            f"offset=0x{sec.offset:x}"
        )
```

**Anomalies to emit** (bucket: `sections`, `kind: fact`,
`data.producer: "lief"`):

| `indicator_type` | Trigger | `severity` |
|-----------------|---------|-----------|
| `elf_section_table_stripped` | `len(elf.sections) == 0` | `WARNING` |
| `elf_section` | one per section — the catalogue | `INFO` |
| `elf_wx_section` | section with both `SHF_WRITE` and `SHF_EXECINSTR` flags | `CRITICAL` |
| `elf_section_size_mismatch` | `sh_size` is zero but `SHF_ALLOC` is set (hollow section) | `WARNING` |
| `elf_nonstandard_section` | section name is not in the well-known set (`.text`, `.data`, `.bss`, `.rodata`, `.got`, `.got.plt`, `.plt`, `.plt.got`, `.plt.sec`, `.dynamic`, `.dynstr`, `.dynsym`, `.symtab`, `.strtab`, `.shstrtab`, `.init`, `.fini`, `.init_array`, `.fini_array`, `.rela.*`, `.rel.*`, `.note.*`, `.eh_frame`, `.eh_frame_hdr`, `.debug_*`, `.tdata`, `.tbss`, `.interp`) | `INFO` |
| `elf_section_high_entropy` | Section entropy ≥ 7.2 | `WARNING` *(seed for FR-05)* |

### Step 4: Dynamic section → `imports` bucket

The `.dynamic` section is the ELF analogue of the PE import directory and the
Mach-O LC_LOAD_DYLIB list. `DT_NEEDED` entries enumerate every shared library
the binary requests from the runtime linker. `DT_RPATH` / `DT_RUNPATH`
specify extra library search paths — an injection surface analogous to Mach-O
`LC_RPATH` anomalies.

```python
dyn = elf.get_section(".dynamic")
if dyn is not None:
    for entry in elf.dynamic_entries:
        print(f"dynamic_tag={entry.tag.name} raw_value={entry.value:#x}")
        if entry.tag in (lief.ELF.DYNAMIC_TAGS.NEEDED,
                         lief.ELF.DYNAMIC_TAGS.RPATH,
                         lief.ELF.DYNAMIC_TAGS.RUNPATH):
            print(f"  -> {entry.name!r}")
```

Capability grouping — emit one aggregated `fact` per capability with
`data.libraries = [...]` (bucket: `imports`):

| Capability | Typical library / symbol patterns |
|------------|------------------------------------|
| `network` | `libcurl.so.*`, `libssl.so.*`, `socket`, `connect`, `sendto`, `recvfrom` |
| `crypto` | `libcrypto.so.*`, `libssl.so.*`, `EVP_*`, `AES_*`, `SHA256_*` |
| `process_manipulation` | `ptrace`, `fork`, `execve`, `clone`, `prctl`, `kill` |
| `dynamic_loading` | `libdl.so.*`, `dlopen`, `dlsym`, `dlmopen` |
| `persistence` | strings hinting `crontab`, `systemd`, `ld.so.preload`, `init.d` (deferred to FR-06; note the surface here only) |

Also emit `indicator_type: elf_import_count` (fact, INFO) — if `DT_NEEDED`
count is absurdly low (< 2 libraries) that is a signal of static linking /
stripping / packing and should be cross-referenced from FR-05.

**Anomalies** (bucket: `imports`):

| `indicator_type` | Trigger | `severity` |
|-----------------|---------|-----------|
| `elf_rpath_anomaly` | `DT_RPATH` or `DT_RUNPATH` contains a writable or relative path (`.`, `$ORIGIN/..`, `/tmp`, `/var/tmp`) — runtime library hijack surface | `CRITICAL` |
| `elf_missing_bind_now` | Neither `DT_BIND_NOW` nor `DF_BIND_NOW` set AND `PT_GNU_RELRO` absent — lazy binding + writable GOT | `WARNING` |
| `elf_no_dynamic_section` | Statically linked binary (no `.dynamic`); combined with `elf_missing_pt_interp` confirms static | `INFO` |

#### Per-symbol `suspicious_import` (FR-07 priority feed)

In addition to the capability aggregate above, emit one
**format-neutral** `suspicious_import` `fact` per high-risk POSIX symbol
present in the dynamic symbol table (`.dynsym`). FR-07's
priority-queue Step 0 consumes the same `indicator_type` across PE /
ELF / Mach-O — the schema (`data.module` / `data.symbol` /
`data.capability` / `data.thunk_addr` / `data.callers`) is owned by
`binary-analysis-evidence-chain-protocol`. The per-symbol fact is
mandatory; `data.thunk_addr` and `data.callers` are best-effort.

The high-risk POSIX shortlist below mirrors the capability grouping:

| Capability | High-risk POSIX symbols |
|------------|------------------------|
| `process_manipulation` | `ptrace`, `fork`, `vfork`, `execve`, `execl`, `execlp`, `clone`, `prctl`, `kill`, `setuid`, `setgid` |
| `dynamic_loading` | `dlopen`, `dlsym`, `dlmopen`, `dlclose` |
| `network` | `socket`, `connect`, `bind`, `listen`, `accept`, `sendto`, `recvfrom`, `getaddrinfo` |
| `crypto` | `EVP_EncryptInit_ex`, `EVP_DecryptInit_ex`, `AES_set_encrypt_key`, `RSA_public_encrypt`, `SHA256_Init` |
| `anti_debug` | `ptrace`, `personality`, `prctl` (when called with `PR_SET_DUMPABLE` — runtime check; static skill records the symbol only) |

**Resolving `thunk_addr` and `callers`** (best-effort; optional
`python_exec` with `capstone` for disassembly if installed in the sandbox
image — not a first-class project tool, only a library used under
`python_exec`):

- `thunk_addr`: walk `.rela.plt` / `.rel.plt` and find the `r_offset`
  whose target symbol matches `symbol`; that's the GOT entry — the
  PLT stub address is the per-arch fixed offset away (`r_offset - 6`
  on x86_64; tooling-dependent on ARM / MIPS). When the relocation
  table is stripped or the arch-specific stride is uncertain, omit
  `thunk_addr`.
- `callers`: scan executable `PT_LOAD` segment bytes once with
  `capstone` (multi-arch) for `call` / `bl` / `jal` instructions
  whose target is the PLT stub, and walk back to the containing
  function using `.symtab` boundaries (when present) or the entry
  point as a single-function fallback. Same best-effort contract as
  the PE recipe in `performing-static-malware-analysis-with-pe-studio`
  Step 4.

When neither `capstone` nor the relocation tables are usable, omit
`thunk_addr` / `callers` and rely on the bare `symbol` token —
priority-queue Step 0 will fall back to name-only lookup with the
documented `not_found` failure mode.

Example (ELF, callers populated — fields match `Indicator`; bucket chosen at append time, not a JSON field on the record):

```json
{
  "source_fr": "FR-04",
  "indicator_type": "suspicious_import",
  "severity": "WARNING",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "producer": "lief",
    "module": "libc.so.6",
    "symbol": "ptrace",
    "capability": "process_manipulation",
    "thunk_addr": "0x40e500",
    "callers": [
      {"addr": "0x402100", "name": "main"},
      {"addr": "0x402550", "name": null}
    ]
  }
}
```

### Step 5: Entry-point placement (FR-04 AC-3)

The ELF entry point (`e_entry`) is a virtual address that maps into one of the
`PT_LOAD` segments. A healthy executable entry point lands inside a
non-writable, executable `PT_LOAD` that covers the `.text` section.

```python
ep = hdr.entrypoint
ep_segment = None
ep_section = None

for seg in elf.segments:
    if seg.type == lief.ELF.SEGMENT_TYPES.LOAD:
        seg_start = seg.virtual_address
        seg_end = seg_start + seg.virtual_size
        if seg_start <= ep < seg_end:
            ep_segment = seg
            break

if elf.sections and ep_segment is not None:
    for sec in elf.sections:
        sec_start = sec.virtual_address
        sec_end = sec_start + sec.size
        if sec.size > 0 and sec_start <= ep < sec_end:
            ep_section = sec
            break

print(f"ep=0x{ep:x} segment={ep_segment} section={ep_section and ep_section.name!r}")
```

| `indicator_type` | Trigger | `severity` |
|-----------------|---------|-----------|
| `elf_entry_point_zero` | `e_entry == 0` on `ET_EXEC` | `CRITICAL` |
| `elf_entry_point_oob` | `e_entry` does not fall inside any `PT_LOAD` | `CRITICAL` |
| `elf_entry_point_wx_segment` | Owning `PT_LOAD` has both `PF_W` and `PF_X` | `CRITICAL` |
| `elf_entry_point_odd_section` | Owning section is not `.text` / `.init` / `_start` | `WARNING` |

Bucket: `headers`. Data payload: `{"producer": "lief", "ep_va":
0x..., "segment_flags": "RX", "section": "<name or null>"}`.

FR-07 MUST consume `elf_entry_point_*` facts when building the decompilation
priority queue (ADR-06 / IR-05).

### Step 6: .init_array / .fini_array — pre-main initialisers

ELF's analogue of PE TLS Callbacks and Mach-O `__mod_init_func` is the
`.init_array` section: an array of function pointers that the dynamic linker
calls *before* `main`. Code here executes invisibly before the nominal entry
point and is a classic packer/dropper hiding spot (FR-04 AC-8).

```python
for sec_name in (".init_array", ".fini_array", ".init", ".fini"):
    sec = elf.get_section(sec_name)
    if sec is None:
        continue
    pointer_size = 8 if elf.type == lief.ELF.ELF_CLASS.CLASS64 else 4
    count = sec.size // pointer_size if pointer_size else 0
    print(f"{sec_name}: {count} pointer(s), size={sec.size}")
```

Emit one `fact, severity: WARNING, indicator_type:
elf_init_array_entry` per pointer-slot (not per byte), with
`data.producer = "lief"`, `data.section = ".init_array"`, and
`data.slot_index = N` into the `headers` bucket. FR-07 MUST consume these to seed decompilation
priority (IR-05 / ADR-06).

### Step 7: Cross-check with `readelf` (best-effort)

When GNU binutils are available in the sandbox, a `bash` cross-check
strengthens confidence in the `lief` parse. Mark results with
`evidence_refs` back to the `lief` output, set `data.producer =
"readelf"` or `"objdump"` as appropriate, and log an `analysis_coverage`
or packer-bucket `tool_missing`-style fact if `readelf` is absent (per Proto-02 cross-bucket conventions).

```bash
readelf -h /workspace/{analysis_id}/sample.elf      # ELF header
readelf -l /workspace/{analysis_id}/sample.elf      # program headers
readelf -S /workspace/{analysis_id}/sample.elf      # section headers
readelf -d /workspace/{analysis_id}/sample.elf      # dynamic section
readelf -s /workspace/{analysis_id}/sample.elf      # symbol tables
```

## Key Concepts

| Term | Definition |
|------|------------|
| **ELF Header** | First 64 bytes (ELF64) of the file; declares magic, class (32/64-bit), endianness, OS/ABI, object type (`ET_EXEC` / `ET_DYN` / `ET_REL` / `ET_CORE`), machine type, entry-point VA, and offsets to the segment and section tables. |
| **Program Header (segment)** | Runtime descriptor telling `ld.so` how to map the file into memory — `PT_LOAD` (mappable), `PT_DYNAMIC` (dynamic linker data), `PT_INTERP` (interpreter path), `PT_GNU_STACK` (stack executable bit), `PT_GNU_RELRO` (GOT/PLT hardening). |
| **Section Header** | Link-time descriptor naming regions of the file (`.text`, `.data`, `.bss`, `.got`, `.plt`, …). May be stripped post-link to reduce size or hinder analysis. |
| **Dynamic Section (`.dynamic`)** | Array of dynamic-linker entries directing the runtime linker: `DT_NEEDED` (library names), `DT_RPATH` / `DT_RUNPATH` (library search paths), `DT_BIND_NOW` / `DF_BIND_NOW` (eager symbol resolution), `DT_DEBUG`. |
| **GOT / PLT** | Global Offset Table and Procedure Linkage Table; ELF lazy-binding structures. Without `RELRO` + `BIND_NOW`, the GOT is writable at runtime — a classic hijack target for `ret2plt` / `GOT overwrite` attacks. |
| **PT_GNU_STACK** | Optional program header that sets the executable permission of the process stack. Absence implies the stack is executable (historical default) — a signal of old toolchain or deliberate removal. |
| **PT_GNU_RELRO** | Marks a memory range to be made read-only after relocation; protects the GOT and other sensitive tables. Combined with `BIND_NOW` this constitutes "Full RELRO". |
| **`.init_array` / `.fini_array`** | Sections holding arrays of function pointers called by `ld.so` before/after `main`; ELF analogue of PE TLS Callbacks and Mach-O `__mod_init_func`. |
| **Stripped** | ELF binary with the `.symtab` section removed. `.dynsym` (exported/imported dynamic symbols) may still be present; `.symtab` (all local symbols + debug names) is optional and commonly stripped in production. |

## Tools & Systems

- **lief** — Cross-platform binary parser (Python API) that exposes ELF, PE,
  and Mach-O under a uniform interface; the preferred tool inside the
  analysis sandbox (invoked under `python_exec`).
- **readelf** — GNU binutils ELF inspector (`-h`, `-l`, `-S`, `-d`, `-s`,
  `-r`); best-effort cross-check when available.
- **objdump** — GNU disassembler / metadata dumper; useful for `.plt` /
  `.got` inspection when `readelf` output is insufficient.
- **pyelftools** — Pure-Python ELF parser; fallback when `lief` raises on
  malformed files. Exposes `ELFFile`, `iter_segments()`, `iter_sections()`,
  and `get_section_by_name()`.

## Common Scenarios

### Scenario: Triaging an ARM64 ELF dropped into `/usr/local/bin/` on a cloud VM

**Context**: An EDR alert fires on a new binary in `/usr/local/bin/sshd_cfg`
on a production ARM64 Ubuntu 22.04 cloud instance. The analyst submits the
binary path to the binary_analysis backend for structural triage before
spinning up an isolated execution environment.

**Approach**:
1. FR-01 `file_identify` writes `indicator_type: file_meta` with
   `data.format = "ELF"` and `data.arch = "AARCH64"` into `file_meta`;
   FR-02 heuristic triage records no strong family or packer route.
2. FR-04 activates this skill. We parse the ELF header: `ET_DYN`, `EM_AARCH64`,
   stripped (`.symtab` absent). Emit `elf_header` (INFO) + `elf_stripped` (INFO).
3. Program headers: `PT_GNU_STACK` absent → `elf_no_pt_gnu_stack` (WARNING);
   `PT_GNU_RELRO` absent → `elf_no_pt_gnu_relro` (INFO). One `PT_LOAD`
   carries `PF_W | PF_X` → `elf_wx_load_segment` (CRITICAL).
4. Section headers: only 3 sections present (section table not fully stripped,
   but suspiciously sparse). No `.init_array`. One section named `.obb` —
   emit `elf_nonstandard_section` (INFO).
5. Dynamic section: `DT_NEEDED: libpthread.so.0`, `libdl.so.2` — emit
   `capability: dynamic_loading`; import count = 2 → `elf_import_count` (INFO,
   low-import anomaly hint). `DT_RPATH` = `/tmp/.libcache` →
   `elf_rpath_anomaly` (CRITICAL).
6. Entry-point: `e_entry` falls inside the `PF_W | PF_X` segment →
   `elf_entry_point_wx_segment` (CRITICAL). FR-07 later schedules this address
   first in the decompilation priority queue.
7. FR-05 confirms global entropy 7.4 — packed or encrypted payload likely.
   FR-08 infers `cryptominer or backdoor` with MEDIUM confidence from the
   `dynamic_loading` capability + `elf_rpath_anomaly` + high entropy.

**Pitfalls**:
- Mistaking a PIE executable (`ET_DYN`) for a shared library — check whether
  `e_entry` is non-zero; a shared library typically has `e_entry = 0`.
- Running `readelf` or `ldd` on the malware outside the sandbox; `ldd`
  internally exec's the binary, which can trigger payload execution
  (also documented in `analyzing-linux-elf-malware`).
- Trusting the absence of `.symtab` as proof of intentional hardening — most
  release binaries strip it; only the combination with other signals
  (`elf_wx_load_segment`, low import count, high entropy) elevates severity.

## Output Format

This skill does not emit its own report; every finding flows into the
shared evidence chain per Proto-02. A successful run is visible as:

- One `elf_header` fact in `headers`, per sample.
- N `elf_segment` facts in `headers`, plus any triggered anomaly
  `indicator_type` values
  (`elf_wx_load_segment` / `elf_segment_size_mismatch` / `elf_no_pt_gnu_stack`
  / `elf_executable_stack` / `elf_no_pt_gnu_relro`).
- One of `elf_entry_point_*` facts in `headers`.
- M `elf_section` facts in `sections`, plus triggered `elf_wx_section` /
  `elf_section_size_mismatch` / `elf_nonstandard_section` /
  `elf_section_high_entropy` anomalies where applicable.
- K `elf_capability` aggregated facts in `imports`, plus `elf_import_count`
  and raw `elf_needed_library` facts.
- One `suspicious_import` (`indicator_type: suspicious_import`) fact per
  high-risk POSIX symbol present in the dynamic symbol table, in
  `imports`, with `data.module` / `data.symbol` / `data.capability`
  populated and `data.thunk_addr` / `data.callers` populated whenever
  the relocation table + `capstone` xref scan succeeds. This is the
  format-neutral feed FR-07 priority-queue Step 0 consumes alongside
  PE / Mach-O.
- Zero or more `elf_init_array_entry` facts in `headers` so FR-07 can pick
  them up during priority ranking.
- One `elf_rpath_anomaly` and/or `elf_missing_bind_now` fact in `imports` where warranted.

All indicators are `kind: fact`, `source_fr: "FR-04"`, and omit
`confidence`; put provenance under `data.producer`. Facts use `evidence_refs: []`
unless cross-referencing other indicators (then list their ids).

If `lief.ELF.parse` fails mid-stream (malformed section table, truncated
file), emit one `fact` in `headers` with `severity: CRITICAL`,
`indicator_type: malformed_structure`, and `data.producer = "lief"`;
record the downgrade in `analysis_coverage` per Proto-01 downgrade
discipline — never raise into the Agent loop.
