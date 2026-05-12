---
name: ghidra-priority-queue-workflow
description: |
  It defines the only sanctioned FR-07 decompilation path: the agent
  must emit a decompile_priority fact and a machine-readable
  decompile_priority.txt list before it invokes analyzeheadless with
  DecompileByList.py, enforce a per-function timeout as the postScript
  third argument, and read results through paginated file_read of
  per-function .c files (IR-04, IR-05, FR-07 AC-4/5/7). It activates
  when the binary orchestrator is in Stage FR-07 且样本需要 Ghidra
  反编译调度、多函数 PE/ELF/Mach-O 在 token 预算下无法全量
  反编译、或必须写入 decompile_priority 并分页读取伪 C。 It consumes
  FR-01 file_meta, FR-04 imports/structural facts, FR-06 strings_iocs, and
  the orchestrator decompile_input fact; it feeds two-phase
  behavior-chain-reconstruction. Step 0 detail: references/step0-priority-recipe.md.
license: Apache-2.0
compatibility: binary_analysis FR-07 · schema_version 1.0.0
allowed-tools: python_exec bash file_read evidence_chain
metadata:
  id: Skill-FR07-PriorityQueue
  batch: S-02
  adr: ADR-06
  fr: FR-07
  ir: IR-04, IR-05
  ac: FR-07:AC-4, FR-07:AC-5, FR-07:AC-7
  stability: stable
---

# Ghidra Priority-Queue Workflow (FR-07 AC-4/5/7 · IR-04/05)

> **Why this skill exists.** FR-07 AC-5 (IR-05) forbids running a full
> Ghidra auto-analysis and then filtering functions after the fact —
> the budget is controlled by sorting **before** the decompiler runs.
> FR-07 AC-7 further requires a **per-function** timeout (not just a
> process-wide one), which only `DecompileByList.py` provides. IR-04
> layers on top: the decompile output MUST land as per-function files
> that the agent pages through with `file_read`, never as one mega
> `stdout` stream from `analyzeHeadless`.

## When to Use

- You are about to call `bash` with `analyzeHeadless` for FR-07. Always
  read this skill first; it is the **only** sanctioned invocation path.
- The sample has more functions than the round or token budget can
  support dumping in full, and the orchestrator has routed FR-07 and you
  have FR-04 `imports` + FR-06 `strings_iocs` (and related) signals.

**Do not use** when the sample is already severely packed
(`packing_severity_hint="SEVERE"`) unless the orchestrator has cancelled
that proactive skip with a non-packed FR-05 fact or
`unpack_result.status="success"` plus `data.unpacked_path`. Consult the
orchestrator's Stage FR-07 downgrade table before invoking Ghidra.

## Routing (upstream / downstream)

| Direction | Owner |
|----------|--------|
| **Invoked by** | `binary-analysis-e2e-orchestrator` Stage FR-07 (after `decompile_input` exists) and by skills that name this file as the pre-Ghidra gate (`reverse-engineering-malware-with-ghidra`, `analyzing-linux-elf-malware-with-ghidra`, etc.); `bash` tool text also points here for `analyzeHeadless`. |
| **Invokes / reads** | `binary-analysis-evidence-chain-protocol` (Proto-02) for `Indicator` fields and buckets; `reverse-engineering-malware-with-ghidra` for interpretation patterns only — not its raw CLI example. |
| **Hands off to** | `two-phase-behavior-chain-reconstruction` (FR-17) after `decompiled_function` + `function_tag` + `callgraph_edge` (or an explicit `analysis_coverage` gap). |
| **Return to orchestrator** | After Step 2 completion signals or a documented failure row in `Failure Modes`, yield control so FR-08 / scoring / reports see the new `disassembly` facts. |
| **Downgrade** | See `Failure Modes` and the orchestrator table (managed → FR-07b; all decompiles fail → `decompile_all_failed`; no call graph → `callgraph_unavailable`, etc.). |

## Invariants (hard constraints)

1. **Priority list MUST be written before `analyzeHeadless` runs.**
   Emit a `fact` indicator with `indicator_type="decompile_priority"`
   into the `disassembly` bucket naming every function reference the
   agent intends to decompile, in descending priority order. If the
   bucket has no `decompile_priority` fact when `analyzeHeadless`
   launches, the invocation is a protocol violation — abort and redo
   Step 0. Every such indicator must set `source_fr` to the owning
   functional requirement, typically `FR-07` (Proto-02).
   The machine-readable `decompile_priority.txt` file is also part of
   this gate: it MUST be created by `python_exec` using the canonical
   Step 0 recipe. Do not use `bash`, `printf`, `echo`, `tee`, or shell
   redirection (`>`, `>>`) to create or patch this file. `BashTool`
   rejects `analyzeHeadless ... DecompileByList.py` when the priority
   file is missing or empty.
2. **Input path MUST come from FR-07 `decompile_input`.**
   The orchestrator selects the original sample path or the FR-05
   `unpack_result.data.unpacked_path` and records that choice as a
   `decompile_input` fact in `disassembly`. Step 0 reads this fact and
   carries `data.input_path` / `data.input_sha256` into
   `decompile_priority`; Step 1 imports exactly that path. Do not fall
   back to `/workspace/<analysis_id>/sample.bin` after a successful
   unpack.
3. **`analyzeHeadless` MUST be invoked with
   `-postScript DecompileByList.py -scriptPath /opt/ghidra/scripts` and
   the script-args `<priority_list_path> <output_dir> [timeout_s]`.**
   Bare `analyzeHeadless ... -import sample.bin` (default whole-binary
   decompile) is banned by `config/bash_whitelist.yaml`'s comment and
   by `BashTool`'s tool-description guidance.
4. **Per-function timeout is the third script-arg.** Default `30`s;
   raise / lower via the `timeout_s` arg — never rely on Ghidra's
   process-wide timeout to bound individual functions (FR-07 AC-7).
5. **Results are read via `file_read`, not `stdout`.** `analyzeHeadless`
   writes per-function `.c` files plus `manifest.json` into
   `<output_dir>`; its stdout carries only a one-line summary. BashTool
   truncates stdout at 64 KiB, which cannot hold a real decompile
   corpus — the manifest + paginated file reads are the contract.
6. **FR-07 owns the FR-17 call surface.** Before handing off to
   `two-phase-behavior-chain-reconstruction`, write deterministic
   `decompiled_function`, `function_tag`, and `callgraph_edge` facts into
   `disassembly` (each with `source_fr` set consistently, typically
   `FR-07` for decompile path facts). FR-17 MUST NOT infer missing caller /
   callee relationships. If Ghidra or the postScript cannot export a
   call graph, append an `analysis_coverage` fact with
   `data.dimension="decompilation"`
   and `data.reason="callgraph_unavailable"`, then skip FR-17 or let it
   record `behavior_chain_unavailable`.

## Budget and LLM convergence (NFR-05)

Paging pseudo-C in Step 2 must stay within the session limits imposed by
`agent.md` (`max_rounds`, `token_budget`, `threshold_pct`). When
projected read volume would exceed the budget, shrink the paged
`file_read` windows first, then the number of functions, before asking
the LLM to narrate. This skill is not a report generator; the numeric
placeholders for the system prompt are defined only in `agent.md`.

## Workflow

### Step 0 · Build the priority queue (`python_exec`)

This step is a `python_exec` step, not a `bash` step. Generate
`/workspace/<aid>/decompile_priority.txt` from Python file I/O and append
the matching `decompile_priority` evidence-chain fact in the same step.
Shell redirection is unsupported by `bash` and is a contract violation
for this file.

Read `decompile_input`, `imports` (FR-04), `strings_iocs` (FR-06), plus
the format-specific entry-point / initialiser facts (TLS callbacks,
`__mod_init_func`, `.init_array`) and rank **caller user functions** —
not import symbol names — by a coarse capability score. The canonical
signal list and optional STRATEGIC_SKIP / managed handling live in
`references/step0-priority-recipe.md` together with a host-aligned
`EvidenceChainStore` sketch (use `snap.imports` / `snap.disassembly`, not
`snap.buckets[...]`).

**Caller-aware token format (P0-4).** The priority list emits **user
function references**, not import symbol names:

- `<caller_name>@<caller_addr>` — when the producer populated
  `data.callers[i].name` (e.g. `main@0x402100`).
- `FUN_<addr>@<caller_addr>` — when `data.callers[i].name` is null
  (e.g. `FUN_0x402550@0x402550`); the `FUN_` prefix matches the Ghidra
  default function-naming convention.
- `<symbol>` (bare) — legacy fallback when `data.callers` is missing
  or empty. Step 1 will most likely report `status="not_found"` for
  this token; see Failure Modes.

**Completion signal:** `disassembly` bucket contains a latest active
`decompile_priority` fact whose `data.priority_list_path` points to a
non-empty file, whose `data.input_path` matches the active
`decompile_input` fact, and whose `data.format` matches the FR-01
`file_meta.data.format`. For managed assemblies (`.NET` / `CIL` /
`ManagedPE`) Step 0 emits `analysis_coverage` instead and the
orchestrator routes to FR-07b; do not invoke Ghidra in that case.

### Step 1 · Invoke `analyzeHeadless` with the postScript (`bash`)

Exact command shape (shell tokens — no shell metachars):

```
analyzeHeadless /workspace/<aid>/ghidra-proj <aid> \
  -import <input_path-from-decompile_priority> \
  -scriptPath /opt/ghidra/scripts \
  -postScript DecompileByList.py \
    /workspace/<aid>/decompile_priority.txt \
    /workspace/<aid>/decompile/ \
    30 \
  -deleteProject \
  -readOnly
```

Notes:

- The `-import` path is the active `decompile_priority.data.input_path`;
  after successful FR-05 unpacking this is the unpacked artifact, not
  `/workspace/<aid>/sample.bin`.
- The three tokens after `DecompileByList.py` are forwarded by Ghidra
  as the script's `getScriptArgs()` — they are positional and MUST be
  in the order `priority_list_path`, `output_dir`, `per_fn_timeout_s`.
- `-outputFile` in the Ghidra CLI refers to a diagnostic log file, not
  the per-function decompile output. Per-function output is controlled
  by the postScript's `output_dir` argument; that directory is where
  `file_read` must target in Step 2.
- `-deleteProject` + `-readOnly` honour IR-03 (temp cleanup) without
  modifying the imported program.
- `BashTool.timeout_seconds` should be set explicitly (e.g. 240s) to
  bound the whole headless run; per-function timeout remains governed
  by the postScript's third script-arg (FR-07 AC-7 — two distinct
  timeouts, both required).

### Step 2 · Page the decompile output (`file_read`)

1. Read `manifest.json` first:

   ```
   file_read(path="/workspace/<aid>/decompile/manifest.json", offset=0, limit=200)
   ```

2. For each ranked `functions[i]` whose `status="ok"`, page the
   corresponding `.c` file. A 30-line window is usually enough for a
   single function; use offset/limit to scroll.

   ```
   file_read(
     path=functions[i].output_path,
     offset=0,
     limit=200,
   )
   ```

3. Record each usefully-analysed function as FR-07 interface facts in
   `disassembly` with `source_fr="FR-07"`:
   - `decompiled_function`: `data={address, name, lines_read,
     pseudo_c_sha256, truncated, output_path}` for the paged pseudo-C.
   - `function_tag`: `data={address, name, priority_rank,
     capability_tags, source="ghidra"}` so FR-17 has stable graph nodes
     even when a function body is truncated.
   Use `indicator_type="decompile_timeout"` / `"decompile_error"` for
   the timeout / not_found / error manifest entries so FR-15 can
   surface partial coverage.

4. Record call relationships as deterministic `callgraph_edge` facts in
   `disassembly`, one per caller -> callee edge exported by the
   postScript or by Ghidra's call graph API. Use
   `data={caller, callee, caller_name, callee_name, count, source="ghidra"}`
   where names and counts are optional. These facts are the only call
   graph that FR-17 may consume.

5. If no call graph is available, append an `analysis_coverage` fact into
   `disassembly` with `source_fr="FR-07"`, `data.dimension="decompilation"`,
   `data.status="DEGRADED"`, and `data.reason="callgraph_unavailable"`.
   Do not ask FR-17 to reconstruct call edges from pseudo-C text.

**Completion signal:** `disassembly` bucket contains at least one
`decompiled_function` fact, at least one `function_tag` fact, and either
one or more `callgraph_edge` facts or an explicit `analysis_coverage`
fact explaining why the call graph is unavailable. If every manifest
entry is `timeout` / `not_found`, append an `analysis_coverage` indicator
with `data.status="DEGRADED"` and `data.reason="decompile_all_failed"`
instead and skip FR-17.

## Failure Modes

| Symptom | Likely cause | Remedy |
|---|---|---|
| `analyzeHeadless` exits 0 but `manifest.json` missing | postScript not installed in `/opt/ghidra/scripts/` → E2B template out of date | Append `analysis_coverage` with `data.reason="manifest_missing"`; ensure `DecompileByList.py` in template; verify with `bash("ls /opt/ghidra/scripts/DecompileByList.py")` in sandbox. |
| Every entry `status="not_found"` | (a) FR-04 did not populate `data.callers` (bare sym tokens Thunk) or (b) no `suspicious_import` | Inspect `decompile_priority` signals and FR-04; re-run FR-04 with a producer that emits `data.callers` (see `binary-analysis-evidence-chain-protocol`). |
| Step 0 emits `analysis_coverage` w/ `reason="managed_assembly_routed_to_fr07b"` and exits 0 | `.NET` / `CIL` / `ManagedPE` | Expected — use FR-07b (`reverse-engineering-dotnet-malware-with-dnspy`). |
| `reason="no_signal_provider_for_format"` | Unknown or exotic `format` | Extend high-risk set or skip FR-07; rely on FR-06/FR-08. |
| `status="timeout"` on most entries | per-function budget too low | Re-run Step 1 with a higher third script-arg; do not raise `BashTool.timeout_seconds` without also raising per-function timeout coherently. |
| All manifest entries `timeout` / `not_found` / `error` | Selection could not decompile | Append `decompile_all_failed` and skip FR-17. |
| `BashTool` reports `stdout_truncated=True` | Wrong `analyzeHeadless` invocation (no postScript) | Re-read invariants: stdout must be a one-liner. |

## Interaction with Other Skills

- **`reverse-engineering-malware-with-ghidra`** — upstream methodology
  for pseudo-C interpretation. This project-level skill overrides that
  skill's raw `analyzeHeadless` example with the priority-queue
  invocation. Read it for C2 and structure interpretation, not the CLI
  from its Step 1.
- **`two-phase-behavior-chain-reconstruction`** (Gap-04) — consumes
  `decompiled_function` + `function_tag` + `callgraph_edge` from
  `disassembly`. If you record `callgraph_unavailable`, FR-17 must not
  guess.
- **`binary-analysis-evidence-chain-protocol`** (Proto-02) — governs
  `source_fr`, `kind`, and bucket placement before authoring
  `decompile_priority` / decompile facts.

## Output Format

This skill is a workflow wrapper, not a report generator. Success is
measured by the presence of:

1. A latest active `decompile_priority` fact in `disassembly` with
   `source_fr="FR-07"`.
2. `decompile_priority.data.input_path` matching the active
   `decompile_input` fact.
3. `decompile_priority.data.budget` recording the exact
   `bash_timeout_s` / `per_fn_timeout_s` / `top_n` used so the wall-time
   ceiling is auditable per analysis.
4. When a prior `analysis_coverage` fact carried
   `data.reason="fr02_ac8_strategic_skip"`, the new
   `decompile_priority` fact MUST set `data.cancels_strategic_skip=true`
   AND list that skip indicator's id under `evidence_refs`. Append-only
   evidence cannot retract the skip marker, so this cross-reference is
   how FR-13 / FR-15 see "skip cancelled".
5. A well-formed `/workspace/<aid>/decompile/manifest.json`.
6. One or more `decompiled_function` facts, each
   with `evidence_refs` to the `decompile_priority` fact and
   `source_fr="FR-07"`.
7. One or more `function_tag` facts.
8. One or more `callgraph_edge` facts, or an
   `analysis_coverage` fact with `data.reason="callgraph_unavailable"`.

**Related reference (progressive disclosure):** `references/step0-priority-recipe.md`
