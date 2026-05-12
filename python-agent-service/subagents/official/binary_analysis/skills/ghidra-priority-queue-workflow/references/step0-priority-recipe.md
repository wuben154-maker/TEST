# Step 0 — Priority list and `decompile_priority` (reference)

Long-form recipe for `ghidra-priority-queue-workflow` Step 0. The parent `SKILL.md` keeps invariants; this file holds the `HIGH_RISK_APIS` tables and a host-aligned Python sketch.

**Execution note.** Prefer appending Indicators with the `evidence_chain` tool in the agent loop. A `python_exec` block may import `binary_analysis` only when the analyst process mounts the same in-memory `EvidenceChainStore` as the tools (or when your runner injects a chain snapshot). **Sandbox-only** `python3 -c` runs often lack the full package graph; in that case emit a small JSON summary to a workspace file and let the next turn call `evidence_chain` to append the fact and write the priority list.

## High-risk API shortlists (non-exhaustive)

Keep aligned with FR-04 producer skills' per-format `suspicious_import` shortlists.

```python
HIGH_RISK_APIS_WIN32 = {
    # process injection
    "CreateRemoteThread", "VirtualAllocEx", "WriteProcessMemory",
    "NtMapViewOfSection", "QueueUserAPC",
    # persistence
    "RegSetValueEx", "RegSetValueExA", "RegSetValueExW",
    "CreateServiceA", "StartServiceCtrlDispatcher",
    # network / C2
    "InternetOpenA", "WinHttpOpen", "HttpSendRequestA",
    "WSAStartup", "connect",
    # cryptography
    "CryptAcquireContextA", "BCryptEncrypt", "CryptImportKey",
    # anti-debug / evasion
    "IsDebuggerPresent", "CheckRemoteDebuggerPresent",
    "NtQueryInformationProcess", "ZwSetInformationThread",
}

HIGH_RISK_APIS_POSIX = {
    # process manipulation
    "ptrace", "fork", "vfork", "execve", "execl", "execlp",
    "clone", "prctl", "kill", "setuid", "setgid",
    # dynamic loading
    "dlopen", "dlsym", "dlmopen", "dlclose",
    # network
    "socket", "connect", "bind", "listen", "accept",
    "sendto", "recvfrom", "getaddrinfo",
    # crypto
    "EVP_EncryptInit_ex", "EVP_DecryptInit_ex",
    "AES_set_encrypt_key", "RSA_public_encrypt", "SHA256_Init",
}

HIGH_RISK_APIS_MACH = {
    # process injection (note `_` prefix per Mach-O symbol convention)
    "_task_for_pid", "_mach_vm_allocate", "_mach_vm_write",
    "_mach_vm_protect", "_thread_create_running",
    "_ptrace", "_posix_spawn",
    # dynamic loading
    "_dlopen", "_dlsym", "_dlclose",
    "_NSCreateObjectFileImageFromMemory", "_NSLinkModule",
    # network
    "_socket", "_connect", "_CFNetworkCopySystemProxySettings",
    "_NSURLSessionDataTask", "_curl_easy_perform",
    # crypto
    "_CCCryptorCreate", "_CCCryptorUpdate",
    "_SecKeyCreateWithData", "_EVP_EncryptInit_ex",
    # persistence
    "_SMLoginItemSetEnabled", "_SMJobBless", "_LSRegisterURL",
}

HIGH_RISK_APIS_BY_FORMAT = {
    "PE":     HIGH_RISK_APIS_WIN32,
    "ELF":    HIGH_RISK_APIS_POSIX,
    "Mach-O": HIGH_RISK_APIS_MACH,
}
```

## Host-aligned Step 0 sketch (EvidenceChainStore)

Uses `EvidenceChainSnapshot` field names (`snap.imports`, not `snap.buckets["imports"]`). Every `Indicator` must include `source_fr` (Proto-02; typically `FR-07` for this workflow).

```python
# python_exec in analyst process, or adjust for evidence_chain tool-only handoff
import pathlib

from binary_analysis.evidence_chain import EvidenceChainStore
from binary_analysis.schema.evidence_chain import Bucket
from binary_analysis.schema.indicator import Indicator, Severity

# Wall-time budget — see parent SKILL Invariant 4 + Step 1
BASH_TIMEOUT_S = 240
PER_FN_TIMEOUT_S = 30
HEADROOM = 0.8
TOP_N = max(8, int((BASH_TIMEOUT_S * HEADROOM) // PER_FN_TIMEOUT_S))

store = EvidenceChainStore(analysis_id=analysis_id)
snap = store.snapshot()
imports = [ind for ind in snap.imports if ind.kind == "fact"]
strings = [ind for ind in snap.strings_iocs if ind.kind == "fact"]
headers = [ind for ind in snap.headers if ind.kind == "fact"]
sections = [ind for ind in snap.sections if ind.kind == "fact"]
inputs = [
    ind for ind in snap.disassembly
    if ind.kind == "fact" and ind.indicator_type == "decompile_input"
]
file_meta = [
    ind for ind in snap.file_meta
    if ind.kind == "fact" and ind.indicator_type == "file_meta"
]
if not inputs:
    raise RuntimeError("FR-07 requires decompile_input before priority construction")
if not file_meta:
    raise RuntimeError("FR-07 requires FR-01 file_meta before priority construction")
decompile_input = inputs[-1].data
fmt = file_meta[-1].data.get("format")  # "PE" / "ELF" / "Mach-O" / ".NET" / ...

# Managed assemblies are FR-07b — refuse and emit DEGRADED
if fmt in {".NET", "CIL", "ManagedPE"}:
    store.append(
        Bucket.disassembly,
        Indicator(
            source_fr="FR-07",
            kind="fact",
            indicator_type="analysis_coverage",
            severity=Severity.WARNING,
            data={
                "dimension": "decompilation",
                "status": "DEGRADED",
                "reason": "managed_assembly_routed_to_fr07b",
                "format": fmt,
            },
        ),
    )
    raise SystemExit(0)

high_risk = HIGH_RISK_APIS_BY_FORMAT.get(fmt, set())
if not high_risk:
    store.append(
        Bucket.disassembly,
        Indicator(
            source_fr="FR-07",
            kind="fact",
            indicator_type="analysis_coverage",
            severity=Severity.INFO,
            data={
                "dimension": "decompilation",
                "status": "DEGRADED",
                "reason": "no_signal_provider_for_format",
                "format": fmt,
            },
        ),
    )

strategic_skip_refs = [
    ind.id for ind in snap.disassembly
    if ind.kind == "fact"
    and ind.indicator_type == "analysis_coverage"
    and ind.data.get("reason") == "fr02_ac8_strategic_skip"
]

scored: dict[str, dict] = {}

def boost(token: str, delta: int, reason: str) -> None:
    rec = scored.setdefault(token, {"score": 0, "reason": []})
    rec["score"] += delta
    rec["reason"].append(reason)

# --- Signal 1: high-risk imports (caller user functions) ---
for ind in imports:
    if ind.indicator_type != "suspicious_import":
        continue
    sym = ind.data.get("symbol")
    if sym not in high_risk:
        continue
    callers = ind.data.get("callers") or []
    if callers:
        for c in callers:
            addr = c.get("addr")
            if not addr:
                continue
            name = c.get("name") or f"FUN_{addr}"
            boost(f"{name}@{addr}", 10, f"api:{sym}")
    else:
        boost(sym, 10, f"api:{sym}:no_callers")

# --- Signal 2: pre-`main` initialisers ---
for ind in headers + sections:
    t = ind.indicator_type
    addr = ind.data.get("function_address") or ind.data.get("addr")
    if not addr:
        continue
    if t in {"tls_callback", "macho_mod_init_func", "elf_init_array_entry"}:
        boost(f"FUN_{addr}@{addr}", 15, f"init:{t}")
    elif t == "macho_writable_executable_segment" and ind.data.get("entry_function_address"):
        ea = ind.data["entry_function_address"]
        boost(f"FUN_{ea}@{ea}", 8, "rwx_segment_entry")

# --- Signal 3: deferred string xref (no-op until FR-06 provides xref) ---
for ind in strings:
    xref = ind.data.get("xref_function")
    if xref and xref in scored:
        boost(xref, 4, f"string:{ind.indicator_type}")

ranked = sorted(scored.items(), key=lambda kv: kv[1]["score"], reverse=True)[:TOP_N]

priority_path = pathlib.Path(f"/workspace/{analysis_id}/decompile_priority.txt")
priority_path.parent.mkdir(parents=True, exist_ok=True)
with priority_path.open("w") as fh:
    fh.write(f"# auto-generated by ghidra-priority-queue-workflow Step 0 (format={fmt})\n")
    for token, meta in ranked:
        fh.write(f"{token}  # score={meta['score']} reasons={','.join(meta['reason'])}\n")

store.append(
    Bucket.disassembly,
    Indicator(
        source_fr="FR-07",
        kind="fact",
        indicator_type="decompile_priority",
        severity=Severity.INFO,
        evidence_refs=strategic_skip_refs,
        data={
            "input_path": decompile_input["input_path"],
            "input_sha256": decompile_input.get("input_sha256"),
            "priority_list_path": str(priority_path),
            "total_candidates": len(ranked),
            "format": fmt,
            "signals": ["suspicious_import", "initialiser", "strings_iocs"],
            "top": [{"ref": tok, **meta} for tok, meta in ranked[:10]],
            "cancels_strategic_skip": bool(strategic_skip_refs),
            "budget": {
                "bash_timeout_s": BASH_TIMEOUT_S,
                "per_fn_timeout_s": PER_FN_TIMEOUT_S,
                "top_n": TOP_N,
            },
        },
    ),
)
```

## Deferred string-xref (P0-3)

FR-06 v1 may omit `data.xref_function` on `strings_iocs` facts; the loop above is a forward-compatible no-op until that field exists.

## Format-aware table (P0-5)

| Format | High-risk import set | Pre-`main` / structural extras | Status |
|--------|----------------------|-------------------------------|--------|
| PE | `HIGH_RISK_APIS_WIN32` | `tls_callback` (FR-04 headers) | active |
| ELF | `HIGH_RISK_APIS_POSIX` | `elf_init_array_entry` (FR-04 sections) | active |
| Mach-O | `HIGH_RISK_APIS_MACH` | `macho_mod_init_func` + `macho_writable_executable_segment` + `macho_rpath_anomaly` | active |
| Go (ELF / PE / Mach-O w/ pclntab) | host format | pclntab boost (deferred) | deferred |
| Rust (any) | host format | crate boost (deferred) | deferred |
| .NET / managed | n/a | n/a | reject — `analysis_coverage` with `data.reason="managed_assembly_routed_to_fr07b"`; FR-07b |
