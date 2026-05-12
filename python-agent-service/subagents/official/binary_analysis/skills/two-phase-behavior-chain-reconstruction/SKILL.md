---
name: two-phase-behavior-chain-reconstruction
description: |
  Delivers the FR-17 two-phase (module-first, function-second) behavior chain
  methodology (ADR-07, FR-17 AC-7): cluster FR-07 callgraph facts into
  module-level behavior nodes, then drill into high-risk modules for
  function-level chains, loading specialist skills only when a gate condition
  fires, and appending inferences to `behavior_chain` with `evidence_refs` to
  FR-04 / FR-06 / FR-07 facts. The runtime activates this guide when a
  two-phase or behavior chain request applies to a large or multi-module
  sample, FR-17 behavior chain reconstruction is in scope, token-budget
  pressure suggests ADR-07’s split, or the analyst must explain how the sample
  reaches its end state. Triggers: two-phase, behavior chain, FR-17. 同场景中文优先词：两阶段、行为链、大样本/模块行为链、端到态归因。
license: Apache-2.0
compatibility: binary_analysis FR-17 · schema_version 1.0.0
allowed-tools: file_read python_exec evidence_chain
metadata:
  id: Gap-04
  batch: C9
  adr: ADR-04, ADR-07
  fr: FR-17
  ir: IR-04, IR-05
  stability: stable
---

# Two-Phase Behavior Chain Reconstruction (Gap-04)

> ADR-07 commits the project to a **module-first, function-second**
> behavior chain strategy to stay inside the NFR-05 token budget on
> large PE samples (FR-17 AC-7, risk table "大型 PE token 预算超限").
> This skill is the methodology wrapper: it tells the Agent how to
> drive the phases, when to delegate to upstream technique specialists,
> and how to encode the resulting graph as `inference` indicators per
> Proto-02.

## Upstream, downstream, and orchestrator

- **Triggered by** `binary-analysis-e2e-orchestrator` at **Stage FR-17** (see
  `### Stage FR-17`); `ghidra-priority-queue-workflow` may reference Gap-04
  when it hands off a complete FR-07 `disassembly` interface (IR-04 / IR-05)
  and callgraph inputs exist.
- **This skill does not** replace FR-07 or FR-04; it consumes their facts and
  may load specialist workflow skills (process injection, persistence, C2, …)
  **on demand** via `file_read` on `examples/binary_analysis/skills/<name>/SKILL.md`.
- **Hand back to the orchestrator** after `behavior_chain` inferences and any
  coverage records are written: follow **FR-09 → FR-08 → FR-13 → FR-14 → FR-15**
  as in the E2E-01 stage map (orchestrator: structured evidence is assembled
  in FR-09, then FR-08 consumes the behavior-chain and other buckets in the
  multi-round analysis round; FR-13 scores after that stage).
- **Degrade and exit** per E2E-01 when decompilation is skipped, `callgraph_edge`
  is missing, or coverage marks `decompilation` / `callgraph_unavailable`. Do
  not invent function callers/callees. If static facts in `imports`,
  `strings_iocs`, `packer`, or `embedded_payloads` support coarse capabilities,
  hand control back to the orchestrator's FR-17 static fallback so it can append
  `static_behavior_node` entries; otherwise append `analysis_coverage` and
  record the FR-17 gap.

## When to Use

- FR-07 has produced the required interface facts in `disassembly`:
  `decompiled_function`, `function_tag`, and `callgraph_edge`.
  `callgraph_edge` is the only source of call relationships for this
  skill. If those edges are missing, do not infer callers / callees
  from pseudo-C text, symbol names, import thunks, or function order.
  Either let the orchestrator write a coarse `static_behavior_node`
  fallback from already-sanitized static facts, or record
  `behavior_chain_unavailable` via an `analysis_coverage` fact and skip
  formal FR-17 (E2E-01 exception path E2).
- You are about to reconstruct the behavior chain for a sample whose
  function count exceeds the per-IMPL-GUIDE threshold (trigger for
  ADR-07's two-phase split).
- You need to attribute a sample's end-state (persistence + C2 + file
  exfil) back to the specific call chains that realise it.

**Do not use** as a substitute for the specialist technique skills.
This skill points at them; it does not re-derive their detection
logic. Do not use when the decompiler has been skipped (packed /
timed-out / downgraded) — there is nothing to cluster in Phase 1.

## Prerequisites

- `binary-analysis-evidence-chain-protocol` (Proto-02) — every
  indicator written below is `kind: inference` with non-empty
  `evidence_refs` (and `source_fr: "FR-17"` for FR-17 outputs); break that rule and the audit gap test fires.
- `binary-analysis-sanitize-untrusted-strings` (Proto-03) — any
  sample-derived literal (function names, decompiled string literals,
  C2 URL snippets) that makes it into an inference's `data.rationale`
  MUST pass through `sanitize()` first.
- FR-04 structural facts in `imports` / `sections` (API capability
  grouping, TLS callbacks, module-boundary hints).
- FR-07 interface facts in `disassembly`:
  - `decompiled_function`: one fact per paged pseudo-C function that
    FR-17 may cite as source evidence.
  - `function_tag`: one fact per function node carrying address, name,
    and any deterministic capability / priority tags derived by FR-07.
  - `callgraph_edge`: deterministic caller -> callee facts exported by
    Ghidra or another FR-07 tool. FR-17 MUST NOT synthesize these edges.
  - `analysis_coverage` with `data.dimension="decompilation"` and a
    reason such as `callgraph_unavailable` means the FR-07 interface is
    incomplete; skip behavior-chain reconstruction instead of guessing.

## Phase 1 — Module-level behavior graph

### Step 1.1: Cluster the call graph into modules

"Module" here is a logical unit, not a PE module. Build an undirected
graph where nodes are FR-07 `function_tag` facts and edges are FR-07
`callgraph_edge` facts, then cluster. A simple community-detection pass
is enough for v1; weighted Louvain works well when edges carry call-count
weights. If the edge set is empty or absent, stop here. Do not rebuild a call
graph from decompiled text. Prefer the orchestrator-owned static fallback when
upstream facts can support coarse behavior nodes; otherwise append an
`analysis_coverage` fact to `behavior_chain` with
`data.reason="callgraph_unavailable"`.

```python
# Runs via the `python_exec` tool inside the sandbox.
# Prefer NetworkX for Louvain when available; fall back to a small-graph
# connected-components or connected-cliques heuristic if `import networkx` fails.
import networkx as nx
import networkx.algorithms.community as nxcomm

g = nx.Graph()
for func in facts_from_bucket("disassembly", indicator_type="function_tag"):
    g.add_node(func.data["address"], name=func.data.get("name"))

for edge in facts_from_bucket("disassembly", indicator_type="callgraph_edge"):
    g.add_edge(
        edge.data["caller"],
        edge.data["callee"],
        weight=edge.data.get("count", 1),
    )

partitions = list(nxcomm.greedy_modularity_communities(g, weight="weight"))
```

Each partition becomes a **module node** in the Phase-1 graph. Assign
a stable synthetic identifier like `mod_0001`, `mod_0002`, … — these
are addressable by Phase 2.

### Step 1.2: Label each module with capability categories

For each module (cluster), aggregate the API capability tags written
by FR-04 for the functions inside it. Use Proto-02's existing
capability taxonomy from the `imports` bucket:

| Capability | Typical Windows APIs (FR-04 `suspicious_import`) |
|------------|--------------------------------------------------|
| `process_manipulation` | `OpenProcess`, `VirtualAllocEx`, `WriteProcessMemory`, `CreateRemoteThread`, `NtQueueApcThread`, `NtMapViewOfSection`, `SetThreadContext` |
| `persistence` | `RegSetValueExW` on `Run` / `RunOnce` / service keys, `CreateServiceW`, `SchRpcRegisterTask`, `IShellLink::Save`, `CopyFileW` to a startup folder |
| `network_c2` | `InternetConnectW`, `HttpSendRequestW`, `WinHttpSendRequest`, `WSASocketW` + `connect`, `DnsQuery_A` with unusual record types |
| `file_io_exfil` | `CreateFileW` + `ReadFile` + `WriteFile` combinations on user-documents paths, `SHFileOperationW` |
| `crypto` | `BCryptGenRandom` + `BCryptEncrypt`, `CryptAcquireContextW` + `CryptEncrypt`, custom RC4 / ChaCha constants in `.data` |
| `anti_analysis` | `IsDebuggerPresent`, `CheckRemoteDebuggerPresent`, `NtQueryInformationProcess(ProcessDebugPort)`, `GetTickCount` + delay loops, `RDTSC` timing |
| `dynamic_loading` | `LoadLibraryW` + `GetProcAddress` lookups, `LdrGetProcedureAddress` |

A module may carry zero, one, or several labels. Store the labelled
module graph as an `inference` indicator in `behavior_chain`:

```json
{
  "bucket": "behavior_chain",
  "kind": "inference",
  "indicator_type": "module_behavior_node",
  "source_fr": "FR-17",
  "severity": "INFO",
  "confidence": "HIGH",
  "data": {
    "module_id": "mod_0001",
    "function_count": 42,
    "entry_functions": ["sub_401000", "sub_401200"],
    "capabilities": ["process_manipulation", "anti_analysis"]
  },
  "evidence_refs": ["<imports_suspicious_import_VirtualAllocEx>", "..."]
}
```

Edges between modules (derived from cross-cluster call edges) become
inferences with `indicator_type: "module_behavior_edge"` and
`data = {"src": "mod_0001", "dst": "mod_0004", "edge_count": 7}`.

### Step 1.3: Seed Phase 2 from the module graph

Select the modules worth detailed analysis:

- Module contains `process_manipulation` **or** `persistence` **or**
  `network_c2` → **always** zoom in.
- Module is an articulation point whose removal disconnects the graph
  (i.e. the only bridge from `entry point's module` to a sink module)
  → zoom in.
- Module carries `anti_analysis` alone → zoom in only if token budget
  allows (it is valuable context but not a verdict driver).
- Plain utility modules (`crypto` alone, `file_io_exfil` alone without
  a network edge) → defer, note them in `analysis_coverage`.

Record the selection decision as a single `inference` with
`indicator_type: "module_selection"` and `confidence: HIGH` so the
audit trail shows *why* Phase 2 chose certain modules.

## Phase 2 — Function-level behavior chain

For each selected module, dispatch to the upstream specialist skill
whose detection pattern matches the module's capability labels. Read
specialist content **on demand** with `file_read` — never all of them up-front —
this is where the token budget is spent.

### Specialist gate table

Read specialist `SKILL.md` bodies only when the gate below fires. The table is the
single dispatch surface for Phase 2; it is not a substitute for the
specialist's detection logic.

| Gate | Input buckets | Required facts before `file_read` | Specialist skill(s) to load | Output indicator type | Do not read when |
|------|---------------|------------------------------|-----------------------------|-----------------------|------------------|
| `process_injection` | `imports`, `disassembly`, `strings_iocs`, `behavior_chain` | A selected module has `process_manipulation` plus at least two injection primitives (`VirtualAllocEx`, `WriteProcessMemory`, `CreateRemoteThread`, `NtMapViewOfSection`, `QueueUserAPC`, `SetThreadContext`) in the same reachable cluster, or a FR-07 `function_tag` already marks injection. | Primary: `detecting-process-injection-techniques`; secondary for hollowing-specific evidence: `detecting-process-hollowing-technique`. | `function_behavior_node`, `function_behavior_edge`, `module_chain_summary` with `data.capability="process_manipulation"`. | Only one API appears globally; APIs are imported but never reached from decompiled functions; FR-07 lacks `callgraph_edge`; evidence is a generic unpacking stub without target-process manipulation. |
| `dll_sideloading` | `imports`, `sections`, `strings_iocs`, `disassembly` | `dynamic_loading` or `process_manipulation` module plus suspicious DLL path / basename, side-by-side manifest, custom search path, writable directory load, or `LoadLibrary` / `LdrLoadDll` xref to a sample-derived DLL string. | `detecting-dll-sideloading-attacks`. | `function_behavior_node` and `module_chain_summary` with `data.capability="dynamic_loading"` or `"dll_sideloading"`. | DLL names are system libraries only; there is no path / basename evidence; loading occurs only through normal import table resolution; no selected module reaches the load call. |
| `fileless` | `strings_iocs`, `imports`, `disassembly`, `behavior_chain` | Command-line / script facts mention PowerShell, WMI, mshta, rundll32, regsvr32, wscript, cscript, encoded command, in-memory .NET reflection, or dropped `.ps1` / `.bat` stage, and the selected module links that string to execution or network behavior. | `detecting-fileless-malware-techniques`. | `function_behavior_node` / `module_chain_summary` with `data.capability="fileless_execution"`. | Script / LOLBin string is isolated and not referenced by decompiled code; the sample is a document parent rather than a binary child; IOC extraction was truncated before xrefs were available. |
| `persistence` | `imports`, `strings_iocs`, `disassembly`, `behavior_chain` | Selected module carries `persistence` capability: Run / RunOnce registry writes, service creation, scheduled task registration, startup-folder copy, launch agent / plist, systemd / crontab, or equivalent OS-specific autostart path. | `analyzing-malware-persistence-with-autoruns`. | `function_behavior_node` / `module_chain_summary` with `data.capability="persistence"`. | Only benign installer-like imports exist; path is a common system path with no write / activation call; no callgraph path connects persistence facts to the sample's execution flow. |
| `generic_c2_behavior` | `imports`, `strings_iocs`, `disassembly`, `behavior_chain` | `network_c2` module plus outbound API cluster and at least one denoised URL / domain / IP, beacon interval / jitter logic, custom protocol parser, DNS / ICMP / HTTP(S) channel, or behavior edge from persistence / unpacking into network code. | Primary: `analyzing-command-and-control-communication`; secondary for tunneling / covert channels: `analyzing-network-covert-channels-in-malware`. | `function_behavior_node`, `function_behavior_edge`, `module_chain_summary` with `data.capability="network_c2"`. | Network APIs are framework noise; all network IOCs were denoised as benign CDN / update infrastructure; a family workflow already produced HIGH-confidence Cobalt Strike / Agent Tesla config and no additional behavior detail is needed. |
| `ransomware_behavior` | `imports`, `strings_iocs`, `disassembly`, `behavior_chain` | `crypto` plus `file_io_exfil` / file traversal module, ransom-note string, extension rewrite, shadow-copy deletion, or behavior edge from key generation to victim-file writes. | Primary: `analyzing-ransomware-encryption-mechanisms`; secondary after function-level crypto evidence exists: `reverse-engineering-ransomware-encryption-routine`. | `function_behavior_node` / `module_chain_summary` with `data.capability="ransomware_encryption"`. | Crypto is only used by TLS / packer / config decoding; no file traversal or ransom-note evidence exists; decompilation coverage is too partial to tie crypto to victim files. |
| `sandbox_evasion` | `imports`, `strings_iocs`, `headers`, `disassembly`, `behavior_chain` | `anti_analysis` module dominates or gates a malicious path: debugger / VM checks, sleep / timing loops, CPUID / RDTSC, process / username / domain probes, window / mouse interaction checks, API unhooking, or packer / protector facts tied to anti-analysis branches. | `analyzing-malware-sandbox-evasion-techniques`. | `function_behavior_node` / `module_chain_summary` with `data.capability="anti_analysis"`; optionally `function_behavior_edge` showing the gated branch. | Only static packer identity exists with no code-level anti-analysis branch; one common API (`IsDebuggerPresent`) appears unused; behavior chain has no malicious path affected by the evasion check. |

The Agent MUST `file_read` the chosen specialist `SKILL.md` before
emitting the function-level inferences for that module. If no gate fires
for a selected module, emit a concise `module_chain_summary` from the
existing facts and record why no specialist was read under
`data.specialist_gate="none"`.

### Step 2.1: Within each module, order functions by reachability

Walk the module's induced subgraph starting from its *entry
functions* — functions called from outside the module (inbound edges
whose source is not in the module). This gives a deterministic
traversal order, which is essential for NFR-09 (determinism on the
fact-facing side; inferences are allowed to vary but the traversal
order feeding them must not).

### Step 2.2: Emit behavior chain nodes per function

For each function that materially contributes to the module's
behavior (not every leaf — an `memcpy` wrapper is noise), emit an
`inference` indicator in `behavior_chain`:

```json
{
  "bucket": "behavior_chain",
  "kind": "inference",
  "indicator_type": "function_behavior_node",
  "source_fr": "FR-17",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "data": {
    "module_id": "mod_0004",
    "function_address": "0x00403120",
    "function_name": "sub_403120",
    "step_label": "Decrypt second-stage from .rsrc @ sub_403120",
    "capability": "crypto",
    "mitre_attack": ["T1027"]
  },
  "evidence_refs": [
    "<disassembly_function_fact_at_0x00403120>",
    "<strings_iocs_c2_url_fact>",
    "<imports_suspicious_import_CryptDecrypt>"
  ]
}
```

> `severity` is `INFO | WARNING | CRITICAL` only — use `WARNING` for a
> single suspicious step, escalate to `CRITICAL` when the step is the
> sample's primary malicious action (e.g. payload execute, key
> exfiltration). `HIGH | MEDIUM | LOW` belongs to `confidence`, never
> to `severity`.

Notes:

- `step_label` is analyst-readable prose describing *what the step
  achieves*, not just *what the API call is*. "Decrypt second-stage
  from .rsrc" beats "Call CryptDecrypt".
- `mitre_attack` is optional but highly encouraged; it must be the
  LLM's inference (no external ATT&CK library per SPEC scope).
- `confidence` follows Proto-02's calibration: HIGH when the
  specialist skill's signature (e.g. VirtualAllocEx + WriteProcessMemory
  + CreateRemoteThread in the same function) fires cleanly; MEDIUM
  when only two of three canonical ingredients are present; LOW when
  we are reasoning from a single weak indicator.

### Step 2.3: Emit edges to form the chain

Edges are ordered — the chain expresses "step A happens before step
B". Encode causal / control-flow order as directed edges:

```json
{
  "bucket": "behavior_chain",
  "kind": "inference",
  "indicator_type": "function_behavior_edge",
  "source_fr": "FR-17",
  "severity": "INFO",
  "confidence": "MEDIUM",
  "data": {
    "src": "<function_behavior_node id for sub_401000>",
    "dst": "<function_behavior_node id for sub_403120>",
    "edge_kind": "control_flow",
    "condition": "only on first run (registry sentinel)"
  },
  "evidence_refs": ["<function_behavior_node_ids>"]
}
```

`edge_kind` is one of `control_flow` (caller → callee),
`data_flow` (A writes a value B reads), or `temporal` (A happens at
install time, B happens at run time on later boots).

### Step 2.4: Emit the chain summary

One terminal inference captures the module's *end-state* in prose:

```json
{
  "bucket": "behavior_chain",
  "kind": "inference",
  "indicator_type": "module_chain_summary",
  "source_fr": "FR-17",
  "severity": "CRITICAL",
  "confidence": "MEDIUM",
  "data": {
    "module_id": "mod_0004",
    "end_state": "Persistent user-scope backdoor with HTTPS C2; deploys a scheduled task for boot persistence and decrypts its second stage from an embedded resource at first run.",
    "primary_technique": "persistence+c2",
    "mitre_attack": ["T1053.005", "T1071.001"]
  },
  "evidence_refs": ["<every function_behavior_node id in this module>"]
}
```

> Calibrate `severity` from the module's end-state: `CRITICAL` for a
> malicious end-state (persistence, C2, ransomware encryption, process
> injection), `WARNING` for suspicious-but-ambiguous modules (e.g.
> crypto-only without observed encryption target), `INFO` for benign
> utility summaries.

The narrative layer is what FR-08 (LLM multi-round analysis) consumes
via its behavior-chain integration round (FR-08 AC-7) and what FR-15
renders in the report's behavior chain section (FR-15 AC-7).

## Token-Budget Discipline (ADR-07, NFR-05)

Global LLM control uses the formatted system prompt limits: when the
agent is in the analysis rounds, treat `{max_rounds}`, `{token_budget}`,
and `{threshold_pct}` in `agent.md` as the **hard** convergence and
over-cap signals (NFR-05 / FR-08). This skill’s Phase-1/Phase-2
percentages are **advisory** detail-layer budgets; they do not override
the global prompt envelope.

Phase 1 should consume **≤ 15% of the skill detail budget**. If Phase
1 alone blows past that threshold, the sample is large enough that
you should (a) cap the module count via a minimum-function-count
filter (drop clusters with ≤ 3 functions into an "other" bucket), and
(b) suppress delegation to secondary specialists unless the primary
specialist fails to yield a HIGH-confidence result.

Phase 2 is allowed **≤ 60% of the skill detail budget** in aggregate
across all selected modules. Specialist `SKILL.md` bodies loaded via
`file_read` are charged against the progressive-disclosure / detail
layer automatically; avoid loading a specialist until its gate is true.

When truncation is forced, emit one `analysis_coverage` fact into the
`behavior_chain` bucket (`indicator_type: "analysis_coverage"`,
`kind: "fact"`, `data: {"dimension": "behavior_chain", "status":
"DEGRADED", "reason": "phase2_truncated", "deferred_modules":
["mod_0005", ...]}`) so FR-15 reports "N modules analysed, M deferred".

## Anti-Patterns

- Inventing call relationships inside FR-17. The call graph is an
  FR-07 fact surface (`callgraph_edge`). FR-17 may cluster, select, and
  summarize, but it must not recover missing caller / callee edges from
  pseudo-C text or narrative reasoning.
- Skipping Phase 1 and going straight to function-level chains.
  On samples with > 500 functions you will either run out of context
  or produce a chain so noisy it is unreadable.
- Writing `kind: fact` in `behavior_chain` for LLM-produced nodes.
  The two-phase reconstruction itself is LLM-driven, so every
  `module_behavior_node` / `function_behavior_node` / `*_edge` /
  `module_chain_summary` this skill emits MUST be `kind: "inference"`
  with a non-empty `evidence_refs` list (Proto-02). Proto-02 does
  allow `kind: "fact"` in the `behavior_chain` bucket, but ONLY for
  mechanically-derived artefacts produced outside this skill — e.g.
  an FR-07 call-graph segment exported directly from Ghidra with
  `data.producer="ghidra"`. If you find yourself about to mark an
  LLM-synthesised behavior step as `fact`, you are off-script.
- Emitting a `function_behavior_node` with empty `evidence_refs`.
  The LLM must cite the underlying FR-04 / FR-06 / FR-07 facts; the
  `schema.indicator._enforce_inference_rules` validator will reject
  the append outright and `audit_gaps` will flag it.
- Using `tag` / `value` / `tool` as top-level Indicator fields.
  They do not exist on the pydantic model (see Proto-02 Anti-Patterns);
  use `indicator_type` / `data` / (record the producer under
  `data.producer` when useful).
- Using `severity: "HIGH"` / `"MEDIUM"` / `"LOW"`. Those values
  belong to `confidence`. `severity` is strictly `INFO | WARNING |
  CRITICAL` (see `schema.indicator.Severity`).
- Duplicating the specialist skill's detection rules inside a
  function_behavior_node's `data.rationale`. Reference the
  specialist by name in the prose, keep the indicator lean.
- Generating an `end_state` summary that is not grounded in the
  per-function nodes. The self-consistency verification round in
  FR-08 (AC-6) will flag the contradiction and force downgrade.

## Key Concepts

| Term | Definition |
|------|------------|
| **Module (Phase 1 node)** | Call-graph cluster produced by community detection over FR-07's function nodes; logical unit, not a PE / dylib module. |
| **Capability label** | Coarse category (`process_manipulation`, `persistence`, `network_c2`, …) derived from the API imports in the module's functions. |
| **Behavior chain node** | A single step in the narrative — e.g. "Decrypt the second stage from .rsrc at sub_403120"; one `function_behavior_node` inference. |
| **Articulation point** | Graph-theoretic notion: a node whose removal disconnects the graph. Articulation-point modules are mandatory-zoom-in targets in Phase 2. |
| **End-state** | Analyst-readable prose describing the module's final observable effect ("persistent user-scope backdoor with HTTPS C2"). |

## Tools & Systems

- **networkx** — Community detection + articulation points + traversal
  order. Runs under the `python_exec` tool inside the sandbox. If
  `networkx` is not importable, use a **stdlib-only** partition / traversal
  fallback; do not assume extra packages on the host.
- **`file_read`** — Read specialist `SKILL.md` files (progressive
  disclosure path); pass paths under `examples/binary_analysis/skills/`.
- **`evidence_chain` tool, `action="append"`** — The sole writer into
  `behavior_chain`; never hand-craft JSON on disk (ADR-02 / Proto-02).

## Common Scenarios

### Scenario: Mid-sized backdoor dropper (~250 functions)

**Context**: A 250-function PE32 backdoor with persistence,
encrypted C2, and a scheduled-task installer. FR-07 decompiled
every function; the call graph has 1,100 edges.

**Approach**:
1. Phase 1 runs Louvain and lands on 6 communities. Two contain
   `persistence` capability signals, one contains `network_c2`, one
   contains `crypto` + `anti_analysis`, the remaining two are utility.
2. Phase 2 selection: three modules (persistence × 2, network_c2 × 1).
   The crypto module is an articulation point on the path from entry
   to network_c2 — it also gets selected. Utility modules deferred.
3. For the persistence modules, `file_read` of
   `analyzing-malware-persistence-with-autoruns` → emit
   `function_behavior_node` per install / activation function →
   emit `module_chain_summary` with MITRE T1053.005 + T1547.001.
4. For the network_c2 module, `file_read` of
   `analyzing-command-and-control-communication` → emit chain nodes
   for TLS pinning, beacon format, and jitter computation.
5. For the crypto articulation-point module, no dedicated specialist
   in scope — emit inference nodes citing the FR-04 import facts
   (`BCryptEncrypt`) directly with `confidence: MEDIUM`.
6. Finally emit one module-edge chain: `persistence_1 → crypto →
   network_c2`, wiring the end-state narrative together.

FR-08's behavior-chain integration round consumes `module_chain_summary`
nodes first, then drills down into individual `function_behavior_node`
items as it needs rationale. FR-13 weighs the combined set.

**Pitfalls**:
- Over-zooming: reading every specialist skill for every module
  bankrupts the token budget before FR-13 even starts.
- Losing the edges between modules: without `module_behavior_edge`
  and `function_behavior_edge` inferences, the "chain" is really
  just a list — FR-15's Mermaid renderer becomes an unordered dump.
- Stuffing the sample's raw strings into `data.end_state` without
  Proto-03 sanitisation; the narrative is LLM-facing and MUST be
  wrapped if it carries sample-derived content.

## Output Format

Successful application is visible as a stable shape in the
`behavior_chain` bucket:

- N `module_behavior_node` inferences (one per Phase 1 cluster).
- M `module_behavior_edge` inferences connecting the module graph.
- Exactly one `module_selection` inference recording why Phase 2
  picked which modules.
- K `function_behavior_node` + L `function_behavior_edge` inferences
  per selected Phase-2 module.
- One `module_chain_summary` inference per selected module.
- Optional `analysis_coverage` fact (`kind: "fact"`,
  `indicator_type: "analysis_coverage"`, `data.status: "DEGRADED"`,
  `data.reason: "phase2_truncated"`) appended into the `behavior_chain`
  bucket if deferrals happened.

All **FR-17 methodology** indicators (`module_behavior_*`,
`function_behavior_*`, `module_chain_summary`, `module_selection`) are
`kind: inference` with `source_fr: "FR-17"`, a non-empty `evidence_refs`
list, and a `confidence` from Proto-02's HIGH / MEDIUM / LOW calibration.
`analysis_coverage` / truncation rows may be `kind: fact` when they
encode mechanical status only (per Proto-02 and the E2E-01 gap path).
