---
name: analyzing-macho-structure
description: |
  Parses Mach-O (macOS / iOS) binary structure to depth comparable with PE and
  ELF coverage under FR-04 / IR-09. Walks the Mach header, load commands,
  LC_SEGMENT / LC_SECTION tables, LC_LOAD_DYLIB imports, LC_CODE_SIGNATURE,
  and __mod_init_func initialiser pointers. Runs only inside the analysis
  sandbox via python_exec (lief) and optional bash (otool / nm cross-checks),
  never on the host. Emits kind:fact indicators into headers, imports, and
  sections through evidence_chain.append_indicator. Triggers on Mach-O samples,
  thin or universal (fat) binaries, .dylib / .bundle / .kext inspection,
  macOS or iOS malware triage, or prompts that mention mach-o or mach header
  structural parsing before FR-05 through FR-07. 适用于 macOS·iOS Mach-O、
  mach header、通用二进制、dylib 与插件的 FR-04 结构解析及 IR-09 对等覆盖。
license: Apache-2.0
compatibility: binary_analysis FR-04 · IR-09 · schema_version 1.0.0
allowed-tools: sandbox_session bash python_exec evidence_chain
metadata:
  id: Gap-01
  batch: C9
  adr: ADR-05, ADR-13
  fr: FR-04
  ir: IR-09
  stability: stable
---

# analyzing-macho-structure

> `skills/` already carries a dedicated ELF specialist
> (`analyzing-linux-elf-malware`) and a PE checklist
> (`performing-static-malware-analysis-with-pe-studio`, both originally
> brought in from upstream) but no Mach-O equivalent. This skill fills
> that gap so FR-04's acceptance criterion
> "对 Mach-O 文件，系统提供对等的结构解析能力" (AC-16) and IR-09
> "对 ELF / Mach-O 的结构解析深度必须与 PE 对等" are met.

## When to Use

- The sample's `file_meta` bucket carries `indicator_type: file_meta`
  with `data.format = "Mach-O"` (written by `file_identify` at FR-01).
- Mach-O structure (header / load commands / imports / sections) is needed
  before FR-05 (entropy), FR-06 (strings), or FR-07 (decompilation).
- Investigating a `.dylib`, `.bundle`, `.kext`, or Mach-O universal (fat)
  binary that fans out to multiple architectures (x86_64 / arm64 / arm64e).
- macOS incident response needs a structural fingerprint (LC_UUID,
  LC_BUILD_VERSION, LC_CODE_SIGNATURE status) for attribution.

**Do not use** for Mach-O *code* reverse engineering (that is FR-07 via
Ghidra — see `reverse-engineering-malware-with-ghidra`) or for runtime
behaviour (`Objective-C` method swizzling, `DYLD_INSERT_LIBRARIES`
hooking) — the behaviour layer is FR-17 / Gap-04.

## Upstream / Downstream

| Direction | Owner | Notes |
|-----------|--------|------|
| **Triggered by** | `binary-analysis-e2e-orchestrator` | After FR-01 / FR-02 when the artifact is Mach-O (FR-04). |
| **Invokes** | `binary-analysis-evidence-chain-protocol` (Proto-02) | Before every `evidence_chain.append_indicator`; `binary-analysis-sanitize-untrusted-strings` (Proto-03) for any sample-derived strings in `data`. |
| **Hands off to** | FR-05 / FR-06 / FR-07 | Structure facts feed entropy, strings, and decompilation; FR-07 also consumes `reverse-engineering-malware-with-ghidra` + `ghidra-priority-queue-workflow` per orchestrator. |
| **Return to orchestrator** | When Mach-O slices are fully catalogued or a downgrade marker is written | Do not loop this skill for FR-08+; follow the E2E-01 stage order in `binary-analysis-e2e-orchestrator`. |

Document path (`document-analysis-e2e-orchestrator`) never reaches this skill.
If `doc_analysis_partial` applies, it is on the document side only — out of scope here.

## Prerequisites

- Open an active `sandbox_session` before `bash` or `python_exec`. All paths
  are under `/workspace/<analysis_id>/` after sandbox upload — **never read raw
  sample bytes on the host** (ADR-05 / NFR-04).
- `lief` (Mach-O parser) inside the sandbox image. Preferred over `macholib`
  for uniform load-command access and parity with PE parsing in FR-04.
- Optional: `otool` / `nm` inside the sandbox for cross-check via `bash`
  when available; Linux sandboxes may lack Apple cctools — treat as
  best-effort.
- Read Proto-02 before appending indicators; apply Proto-03 to sample-derived
  strings placed in `data` (paths, symbol names, team IDs, rpath strings).

## Workflow

### Step 1: Confirm Mach-O magic and detect fat binaries

Fat (universal) Mach-O binaries use `FAT_MAGIC` / `FAT_MAGIC_64` and wrap one
thin Mach-O per architecture. Every step below MUST iterate each slice
individually — treating a fat binary as a single Mach-O loses arch-specific
anomalies.

```python
# sandbox: python_exec
import lief

sample = "/workspace/{analysis_id}/sample.macho"
binaries = lief.MachO.parse(sample)  # FatBinary or single Binary

slices = list(binaries) if hasattr(binaries, "__iter__") else [binaries]
for idx, bin_ in enumerate(slices):
    hdr = bin_.header
    print(
        f"slice={idx} "
        f"cpu_type={hdr.cpu_type.name} "
        f"cpu_subtype={hdr.cpu_subtype} "
        f"file_type={hdr.file_type.name} "
        f"ncmds={hdr.nb_cmds} "
        f"flags={[f.name for f in hdr.flags_list]}"
    )
```

Each slice gets its own indicators with `data.slice_index = idx` so downstream
FR-08 can reason per architecture.

### Step 2: Enumerate load commands

Load commands are the backbone of a Mach-O — segments, dylibs, code signature,
and entry point are expressed as load commands. Signal value: unexpected
commands, missing expected commands, anomalous ordering.

```python
for cmd in bin_.commands:
    print(f"{cmd.command.name:<26} size={cmd.size}")
    # Examples: LC_SEGMENT_64, LC_DYLD_INFO_ONLY, LC_SYMTAB, LC_DYSYMTAB,
    # LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_RPATH, LC_UUID,
    # LC_MAIN, LC_CODE_SIGNATURE, LC_ENCRYPTION_INFO_64,
    # LC_BUILD_VERSION, LC_SOURCE_VERSION.
```

**Indicators to emit** (append to bucket `headers`, `kind: fact`,
`source_fr: "FR-04"`, `data.producer: "lief"`):

| `indicator_type` | When to emit | `severity` |
|------------------|--------------|------------|
| `macho_header` | always | `INFO` |
| `macho_load_cmd` | one per command, for the catalogue | `INFO` |
| `macho_encryption_info` | `LC_ENCRYPTION_INFO[_64]` present with `cryptid != 0` outside an iOS App Store binary context | `CRITICAL` |
| `macho_rpath_anomaly` | `LC_RPATH` contains `@loader_path/..` or absolute writable paths — DYLD hijack surface | `CRITICAL` |

### Step 3: LC_SEGMENT / sections to `sections` bucket

Every `LC_SEGMENT` / `LC_SEGMENT_64` owns zero or more sections (Mach-O analogue
of PE / ELF sections). Emit one `fact` per segment and per section.

```python
for seg in bin_.segments:
    print(
        f"segment={seg.name} "
        f"vaddr=0x{seg.virtual_address:x} "
        f"vsize=0x{seg.virtual_size:x} "
        f"fsize=0x{seg.file_size:x} "
        f"init_prot={seg.init_protection} "
        f"max_prot={seg.max_protection}"
    )
    for sec in seg.sections:
        print(
            f"  section={seg.name},{sec.name} "
            f"type={sec.type.name} "
            f"flags={[f.name for f in sec.flags_list]}"
        )
```

**Anomalies** (align with FR-04 PE checks; replicate for Mach-O):

| `indicator_type` | Trigger | `severity` |
|------------------|---------|------------|
| `macho_writable_executable_segment` | `init_protection & VM_PROT_WRITE` **and** `init_protection & VM_PROT_EXECUTE` | `CRITICAL` |
| `macho_segment_size_mismatch` | `virtual_size > file_size * 4` — runtime-allocated dead drop | `WARNING` |
| `macho_nonstandard_segment` | segment name not in {`__PAGEZERO`, `__TEXT`, `__DATA`, `__DATA_CONST`, `__LINKEDIT`, `__OBJC`, `__LLVM`} | `INFO` |

### Step 4: LC_LOAD_DYLIB / LC_LOAD_WEAK_DYLIB to `imports` bucket

Every linked framework / dylib is a potential capability signal (FR-04 AC-6).
Group framework imports into the same capability semantics as PE analysis.

```python
for lib in bin_.libraries:
    print(f"{lib.name}  compat={lib.compatibility_version} current={lib.current_version}")
```

Capability grouping (emit one aggregated `fact` per capability with
`data.producer = "lief"` and `data.libraries = [...]`):

| Capability | Frameworks / dylibs (typical paths) |
|------------|-------------------------------------|
| `network` | `/usr/lib/libcurl.*`, `/System/Library/Frameworks/CFNetwork.framework/*`, `/System/Library/Frameworks/Network.framework/*` |
| `crypto` | `/usr/lib/libcrypto.*`, `/usr/lib/libssl.*`, `/System/Library/Frameworks/Security.framework/*`, `/System/Library/Frameworks/CommonCrypto.framework/*` |
| `persistence` | `/System/Library/Frameworks/ServiceManagement.framework/*`, `/System/Library/PrivateFrameworks/LoginItems.framework/*` |
| `process_manipulation` | `/usr/lib/system/libsystem_kernel.dylib` + symbol `task_for_pid`, `mach_vm_*`, `ptrace`, `_dyld_register_func_for_add_image` |
| `dynamic_loading` | `/usr/lib/system/libdyld.dylib` + `dlopen` / `dlsym` / `NSCreateObjectFileImageFromMemory` |

Also emit `indicator_type: macho_import_count` (`fact`, `INFO`) — very low
counts may indicate stripping / packing; cross-reference FR-05.

#### Per-symbol `suspicious_import` (FR-07 priority feed)

Emit one format-neutral `suspicious_import` `fact` per high-risk Mach-O dynamic
symbol in the bound / lazy import table (`bin_.imported_symbols` in `lief`).
Schema is owned by `binary-analysis-evidence-chain-protocol` (`data.module` /
`data.symbol` / `data.capability` / `data.thunk_addr` / `data.callers`).

| Capability | High-risk Mach-O symbols |
|------------|--------------------------|
| `process_manipulation` | `_task_for_pid`, `_mach_vm_allocate`, `_mach_vm_write`, `_mach_vm_protect`, `_thread_create_running`, `_ptrace`, `_posix_spawn` |
| `dynamic_loading` | `_dlopen`, `_dlsym`, `_dlclose`, `_NSCreateObjectFileImageFromMemory`, `_NSLinkModule` |
| `network` | `_socket`, `_connect`, `_CFNetworkCopySystemProxySettings`, `_NSURLSessionDataTask`, `_curl_easy_perform` |
| `crypto` | `_CCCryptorCreate`, `_CCCryptorUpdate`, `_SecKeyCreateWithData`, `_EVP_EncryptInit_ex` |
| `persistence` | `_SMLoginItemSetEnabled`, `_SMJobBless`, `_LSRegisterURL` |

**Resolving `thunk_addr` and `callers`** (best-effort):

- `thunk_addr`: walk `LC_DYLD_INFO_ONLY` bind info in `lief` to map symbol to
  `__la_symbol_ptr` / `__got`. Chained fixups (macOS 11.5+ / iOS 14+) may
  require a dedicated parser — omit when unknown.
- `callers`: scan executable segments with `capstone` (via `python_exec`,
  matching `hdr.cpu_type`) for branches to the stub / slot; use
  `LC_FUNCTION_STARTS` as function boundaries when present. Same contract as
  PE / ELF recipes in Proto-02.

When neither `capstone` nor the dyld bind table is usable, omit `thunk_addr` /
`callers`; FR-07 Step 0 falls back to symbol tokens.

Example (`imports` bucket):

```json
{
  "source_fr": "FR-04",
  "indicator_type": "suspicious_import",
  "severity": "WARNING",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "producer": "lief",
    "module": "/usr/lib/system/libsystem_kernel.dylib",
    "symbol": "_task_for_pid",
    "capability": "process_manipulation",
    "thunk_addr": "0x100008010",
    "callers": [
      {"addr": "0x100004080", "name": "_main"},
      {"addr": "0x1000051a0", "name": null}
    ],
    "slice_index": 0
  }
}
```

### Step 5: Initialisers — `__mod_init_func` / `__mod_term_func`

Mach-O's analogue of PE TLS callbacks: pointers in `__DATA,__mod_init_func`
and `__DATA,__mod_term_func`. FR-04 AC-8 mandates this surface.

```python
for seg in bin_.segments:
    for sec in seg.sections:
        if sec.name in ("__mod_init_func", "__mod_term_func"):
            size = len(sec.content)
            pointer_size = 8 if hdr.cpu_type.name.endswith("64") else 4
            count = size // pointer_size
            print(f"{seg.name},{sec.name}: {count} initialiser(s)")
```

Emit one `fact`, `severity: WARNING`, `indicator_type: macho_mod_init_func` per
initialiser into bucket **`headers`**, with `data.producer = "lief"`,
`data.function_address = 0x...`, and `data.slice_index`. FR-07 uses these for
priority seeding (IR-05 / ADR-06).

### Step 6: LC_CODE_SIGNATURE presence and code-signing policy

| Situation | `indicator_type` | `severity` |
|-----------|------------------|------------|
| `LC_CODE_SIGNATURE` absent | `macho_unsigned` | `WARNING` |
| `LC_CODE_SIGNATURE` present, team ID empty / `TeamIdentifier` = `-` | `macho_adhoc_signed` | `INFO` |
| `LC_CODE_SIGNATURE` present and parses | `macho_signed` | `INFO` |

v1 does **not** verify certificate chains (FR-04 AC-4).

### Step 7: Cross-check with `otool` / `nm` (best-effort)

When the sandbox has `otool` / `nm`, optional `bash` cross-check strengthens
confidence. Mark `data.producer` as `"otool"` / `"nm"`; use `evidence_refs` to
link back to matching `lief` facts when both exist. If binaries are absent,
record downgrade via `analysis_coverage` (cross-bucket convention, see
Proto-02) rather than inventing facts.

```bash
otool -h /workspace/{analysis_id}/sample.macho
otool -l /workspace/{analysis_id}/sample.macho
otool -L /workspace/{analysis_id}/sample.macho
nm -gU /workspace/{analysis_id}/sample.macho
```

## Degrade / tool-missing paths

| Condition | Action |
|-----------|--------|
| `lief` import or parse fails | Append `indicator_type: malformed_structure` (`fact`, `CRITICAL`, `headers`, `data.producer: "lief"`) and an `analysis_coverage` marker with `data.dimension: "structure"`, `data.status: "DEGRADED"` per Proto-02. |
| `otool` / `nm` missing | Skip cross-check; optional `analysis_coverage` note — do not fail the stage. |
| `capstone` unavailable | Omit `callers` / partial `thunk_addr`; FR-07 uses symbol fallback. |
| Universal binary | Never collapse slices — emit per `slice_index`. |

Token budget, round limits, and `{threshold_pct}` convergence are enforced by
`agent.md` and the orchestrator (`{token_budget}`, `{max_rounds}`,
`{threshold_pct}` placeholders); this workflow does not override them.

## Key Concepts

| Term | Definition |
|------|------------|
| **Mach Header** | First 28 / 32 bytes declaring magic, CPU type / subtype, file type (`MH_EXECUTE`, `MH_DYLIB`, …), and load-command count. |
| **Load Command** | Variable-length directive for `dyld` — segments, libraries, signature, entry point, etc. |
| **Segment (`LC_SEGMENT`)** | File region mapped into virtual memory; contains sections. |
| **Section** | Named subdivision (`__TEXT,__text`, `__DATA,__mod_init_func`, …). |
| **Fat / Universal Binary** | Wrapper with multiple thin Mach-O slices behind `FAT_MAGIC`. |
| **LC_CODE_SIGNATURE** | Points at embedded signature blob; Gatekeeper relevance. |
| **`__mod_init_func`** | Pre-`main` initialiser pointers. |
| **DYLD_INSERT_LIBRARIES** | Runtime injection primitive; pairs with `LC_RPATH` risk analysis. |

## Parsers and commands (sandbox only)

- **lief** — Python API via `python_exec`; primary parser.
- **otool** / **nm** — optional `bash` helpers when installed in the image.
- **codesign** — not used in v1 (host-specific; out of scope for IR-10 parity).

## Common scenario: `.dylib` under `~/Library/LaunchAgents/`

1. FR-01 `file_identify` writes `file_meta` with `data.format = "Mach-O"`; FR-02
   records no strong packer route.
2. FR-04 runs this skill: walk `MH_DYLIB`, emit header + load-command catalogue;
   flag `macho_unsigned` (`WARNING`) and toxic `LC_RPATH` (`macho_rpath_anomaly`,
   `CRITICAL`) if present.
3. `LC_LOAD_DYLIB` + `suspicious_import` for `task_for_pid` etc.; emit capability
   aggregates into `imports`.
4. `__DATA,__mod_init_func` → `macho_mod_init_func` in `headers` for FR-07.
5. FR-05 entropy; FR-08 may infer persistence / injection as **`inference`**
   with non-empty `evidence_refs` to the facts above (never copy LLM text into
   fact buckets).

**Pitfalls**: launchd plists normally reference executables, not dylibs;
parsing fat binaries as one slice misses arm64-only payloads; `LC_CODE_SIGNATURE`
presence does not prove trusted signing in v1.

## Output checklist

This skill does not emit standalone reports. A successful run produces:

- `macho_header` + `macho_load_cmd` facts per slice in `headers`.
- Segment / section facts in `sections`, plus anomaly types when triggered.
- Capability aggregates and `macho_import_count` in `imports`; per-symbol
  `suspicious_import` facts for FR-07 Step 0.
- `macho_mod_init_func` facts in `headers`.
- One of `macho_unsigned` / `macho_adhoc_signed` / `macho_signed` in `headers`.

All structural findings are `kind: fact`, `source_fr: "FR-04"`, with optional
`confidence` omitted for deterministic facts. Use `data.producer` for
`lief` / `otool` / `nm`. Sample-derived strings in `data` follow Proto-03.

## Mach-O hand-off to FR-07

When the orchestrator routes Mach-O to FR-07, use `reverse-engineering-malware-with-ghidra`
plus `ghidra-priority-queue-workflow`, seeded from this skill's facts:

| Mach-O fact | FR-07 priority hint |
|-------------|----------------------|
| `macho_mod_init_func` | **Highest** — pre-`main` surface; one queue entry per `data.function_address`. |
| `suspicious_import` (`process_manipulation`) | **High** — emit per `data.callers[i]` when present; else symbol token. |
| `suspicious_import` (`dynamic_loading`) | **High** — hide-capability pattern. |
| `macho_writable_executable_segment` | **High** — RWX / self-decrypt landing zones. |
| `macho_rpath_anomaly` | **High** — DYLD hijack surface. |
| `suspicious_import` (`network` / `crypto`) | **Medium** |
| `macho_capability` aggregates | **Background** — summary only; `suspicious_import` is the Step 0 feed. |
| `macho_unsigned` / `macho_adhoc_signed` | **Background** — context only. |

Objective-C dispatch, Swift demangling, and dedicated Mach-O Ghidra deep-dives
remain tracked in the orchestrator (`binary-analysis-e2e-orchestrator` Mach-O /
FR-07 notes); this skill stops at FR-04 structure parsing.
