---
name: detecting-commercial-packers-with-die
description: |
  Identifies commercial packers and protectors (e.g. Themida, VMProtect, Enigma
  Protector, Obsidium, Armadillo, MPRESS) using the Detect It Easy (DIE) signature
  database. Complements `analyzing-packed-malware-with-upx-unpacker`, which covers
  UPX and near-variants. Runs `diec --scan --json` in the analysis sandbox via
  `bash`, maps each DIE hit to the `packer` bucket as `kind: fact` Indicators
  (Proto-02) with `indicator_type` and `data` / `data.producer` fields. Activates
  on FR-05 packer-detection work, high-entropy samples with few imports,
  Themida/VMProtect/Enigma-style suspicion, or any request to name commercial
  binary protectors (DIE / `diec` identification).
license: Apache-2.0
compatibility: binary_analysis FR-05 · schema_version 1.0.0
allowed-tools: sandbox_session bash python_exec evidence_chain
metadata:
  id: Gap-03
  batch: C9
  adr: ADR-05, ADR-13
  fr: FR-05
  stability: stable
---

# Detecting Commercial Packers with DIE (Gap-03)

Commercial protectors (Themida, VMProtect, Enigma Protector, Obsidium, Armadillo) have
no reliable generic unpack path: they use anti-debug, virtualisation, and
code-mutation defences. Identifying them early lets FR-07 decide whether to skip
decompilation (per FR-02 AC-8 / FR-07 AC-8), avoiding wasted Ghidra time and
token budget. NFR-05 (round and token limits) is enforced by `agent.md` and
`binary-analysis-e2e-orchestrator`; this skill does not override `{max_rounds}` /
`{token_budget}` / `{threshold_pct}`.

## Routing (upstream / downstream)

| Role | Skill or stage |
|------|-----------------|
| **Invoked by** | `binary-analysis-e2e-orchestrator` Stage **FR-05** (packer / entropy) alongside or after `analyzing-packed-malware-with-upx-unpacker` when the sample is not plain UPX-shaped, the UPX workflow reports no match, or the analyst must name a commercial/VM protector. |
| **Invokes** | `binary-analysis-evidence-chain-protocol` (Proto-02) before appending; optional cross-check facts align with `pe-structural-anomaly-checklist` (Gap-02) section-name heuristics. |
| **Downstream** | FR-07 reads `packer` / `disassembly` handoff (`decompile_input`, `unpack_result`); FR-13 / FR-14 interpret facts (this skill writes **facts** only, not verdicts). |
| **Return to orchestrator** | After DIE + optional section-name pass and `evidence_chain` appends, continue the FR-05 completion signals (`unpack_result` remains owned by the UPX skill when that path runs). |
| **Degrade** | `diec` missing or failing: emit `tool_missing` / `analysis_coverage` and fall back to section-name heuristics; do not block the pipeline. |

## When to Use

- FR-05 entropy work reports a suspiciously uniform high-entropy profile across
  code sections.
- Section names like `.themida`, `.vmp0`, `.enigma`, `.adata`, `.nsp0`, or
  random-looking 4-byte names appear in the PE section table.
- The sample has ≤ 5 imports yet is multiple megabytes in size (classic
  commercial packer shape: IAT reconstructed at runtime).
- FR-02 heuristic triage shows high packer suspicion and the analyst needs to know
  *which* packer to choose unpack vs escalation strategy.
- The upstream UPX specialist (`analyzing-packed-malware-with-upx-unpacker`)
  returned no hit — use this skill next for DIE-based identification.

**Do not use** as a substitute for the UPX workflow on obvious open-source
packer shapes (UPX, MPRESS, ASPack with plain-text sections) that the UPX
specialist already covers. Do not attempt to unpack commercial protectors with
`diec`; it only *identifies* them.

## Prerequisites

- `sandbox_session`: create a session before the first `bash` / `python_exec`
  that touches `/workspace/<analysis_id>/` (orchestrator rule; do not use
  `sandbox_session` to skip `file_identify` first hop).
- `diec` (Detect It Easy CLI) on `$PATH` in the sandbox. Canonical:
  `diec --scan --json <path>`.
- Sample resolvable as `/workspace/<analysis_id>/sample.<ext>` (or the path FR-01
  / FR-05 already fixed for this analysis). No host-side sample reads; all bytes
  stay in the sandbox (ADR-05 / NFR-03).
- `binary-analysis-evidence-chain-protocol` (Proto-02) is understood: this skill
  writes to the `packer` **bucket** only, never into `verdict` / `family` as
  authority facts.

## Workflow

### Step 1: Run DIE in JSON mode

DIE ships with signatures for many packers, protectors, and linkers. Prefer
`--json` — plain text output is human-friendly but unstable across versions.

```bash
# Invoked through bash in the sandbox; never run the sample on the host.
diec --scan --json "/workspace/${ANALYSIS_ID}/sample.exe"
```

The JSON shape is approximately:

```json
{
  "detects": [
    {
      "filetype": "PE32",
      "values": [
        {"type": "packer",    "name": "VMProtect",          "version": "3.x", "options": "indirect jumps"},
        {"type": "protector", "name": "Themida/WinLicense", "version": "3.0.3-3.1.3", "options": "64-bit"},
        {"type": "linker",    "name": "Microsoft Linker",   "version": "14.0"}
      ]
    }
  ]
}
```

**Signal values** `type` can be: `packer`, `protector`, `linker`, `compiler`,
`installer`, `library`, `sign-tool`, `language`, `overlay`. Only `packer` and
`protector` rows feed the `packer` bucket for this skill. Other rows (e.g.
`linker` / `compiler`) are toolchain fingerprints; if captured elsewhere, they
belong in `headers`, not here (see Gap-02 for PE checklist context).

### Step 2: Apply the commercial-packer severity map

Not every hit is equal: a `linker` hit is informational; a `protector` hit usually
means FR-07 should skip or strategically downgrade decompilation. Use this map:

| DIE `name` regex | Category | `severity` | Typical FR-07 decision |
|------------------|----------|------------|------------------------|
| `Themida` / `WinLicense` | protector | `CRITICAL` | Skip FR-07; recommend SANDBOX |
| `VMProtect` | protector | `CRITICAL` | Skip FR-07; recommend SANDBOX + MANUAL_REVERSE |
| `Enigma\s*Protector` | protector | `CRITICAL` | Skip FR-07; recommend SANDBOX |
| `Obsidium` | protector | `CRITICAL` | Skip FR-07 |
| `Armadillo` | protector | `CRITICAL` | Skip FR-07 |
| `MPRESS` | packer | `WARNING` | Attempt unpack; UPX skill may cover partially |
| `ASPack` | packer | `WARNING` | Attempt unpack |
| `PECompact` | packer | `WARNING` | Attempt unpack |
| `Petite` | packer | `WARNING` | Attempt unpack |
| `UPX` (any variant) | packer | `WARNING` | Delegate to `analyzing-packed-malware-with-upx-unpacker` |
| other `type: protector` | protector | `CRITICAL` | Case-by-case |
| other `type: packer` | packer | `WARNING` | Case-by-case |

Use only `INFO` / `WARNING` / `CRITICAL` for `severity` (not `HIGH` / `MEDIUM` /
`LOW` — those belong to `confidence` on *inference* Indicators). DIE hits
written here are `kind: fact`. Mapping to escalation / verdict is done by
FR-13 / FR-14, not in this skill.

### Step 3: Emit `packer` bucket indicators

One `kind: fact` per DIE row with `type` in `{packer, protector}`:

```json
{
  "bucket": "packer",
  "source_fr": "FR-05",
  "indicator_type": "commercial_packer_match",
  "severity": "CRITICAL",
  "kind": "fact",
  "data": {
    "producer": "diec",
    "die_type": "protector",
    "name": "VMProtect",
    "version": "3.x",
    "options": "indirect jumps",
    "die_version": "3.09"
  }
}
```

If DIE emits two rows for the same protector (e.g. shell and stub), emit both;
downstream may de-duplicate.

### Step 4: Handle the "DIE unavailable" downgrade

DIE is optional. When `bash` returns `command_not_found`, empty PATH binary, or
a non-zero exit without parseable JSON:

```json
{
  "bucket": "packer",
  "source_fr": "FR-05",
  "indicator_type": "tool_missing",
  "severity": "WARNING",
  "kind": "fact",
  "data": {
    "producer": "diec",
    "reason": "diec not on PATH",
    "fallback": "section-name heuristics only"
  }
}
```

Also append an `analysis_coverage` convention indicator (Proto-02) with
`data.dimension = "packer_detection"` and `data.status = "DEGRADED"` so FR-15
can surface the gap. Then fall back to section-name heuristics (Step 5).

### Step 5: Cross-check with section-name heuristics

DIE is authoritative, but section names add confidence when signatures lag:

| Section names | Packer hint |
|---------------|-------------|
| `.themida`, `.taz`, section starting with `.boom` | Themida / WinLicense |
| `.vmp0`, `.vmp1`, `.vmp2` | VMProtect |
| `.enigma1`, `.enigma2`, `.data1` (Enigma layout) | Enigma Protector |
| `.obsidium`, random 4-byte uppercase names | Obsidium |
| `.adata`, `.aspack` | ASPack |
| `.nsp0`, `.nsp1`, `.nsp2` | NsPack |
| `.pec1`, `.pec2` | PECompact |
| `.mpress1`, `.mpress2` | MPRESS |

If a section-name hint agrees with a DIE hit, add a corroborating fact with
`indicator_type: section_name_packer_hint` (`INFO`) and
`data.producer = "pefile"` and `evidence_refs: [<commercial_packer_match id>]`
via `evidence_chain`. If they disagree, emit both; FR-13 reconciles.

### Step 6: Record scan metadata once

At the start of the DIE pass, one informational fact in `packer` with
`indicator_type: diec_scan`:

```json
{
  "bucket": "packer",
  "source_fr": "FR-05",
  "indicator_type": "diec_scan",
  "severity": "INFO",
  "kind": "fact",
  "data": {
    "producer": "diec",
    "diec_version": "3.09",
    "sample_filetype": "PE32",
    "hits_total": 4,
    "hits_by_type": {"packer": 0, "protector": 2, "linker": 1, "compiler": 1}
  }
}
```

## Anti-Patterns

- Treating a DIE `linker` / `compiler` hit as a packer match; those are toolchain
  signals and belong in `headers`, not `packer` as a false commercial match.
- Mapping DIE optional probability fields into Proto-02 `confidence` on a `fact`
  (facts omit `confidence` unless the pipeline explicitly requires it per
  Proto-02).
- Unpacking commercial protectors with DIE; v1 does not attempt Themida/VMProtect
  unpacking here.
- Ignoring non-zero `bash` exit codes when no JSON is produced; record
  `tool_missing` or `analysis_coverage` instead.

## Key Concepts

| Term | Definition |
|------|------------|
| **Commercial packer** | Closed-source executable protector sold as a product (Themida, VMProtect, Enigma, Obsidium, Armadillo). |
| **Protector** | Superset of packer: active anti-analysis (anti-debug, VM, licensing). DIE uses `type: protector`. |
| **DIE (Detect It Easy)** | Open-source identifier by horsicq; CLI entry point is `diec` (do not use the `die` GUI in headless sandboxes). |
| **IAT reconstruction** | Runtime rebuild of import table; static view may show only `LoadLibrary` / `GetProcAddress`. |

## Tools (names only; sandbox execution)

- **`diec`** — `--json` for structured output; optional `--deep` (slower). Default
  timeout (IR-10) on the order of 15s unless the orchestrator sets otherwise.
- **`bash`** — approved primitive to invoke `diec` under `/workspace/<aid>/`.
- **`python_exec`** — optional `pefile` / lief section-name heuristics when DIE is
  missing or to corroborate.
- **`evidence_chain`** — append all Indicators; `bucket` is the tool argument, not
  an `Indicator` field in the model.

## Common Scenarios

### High-entropy 8 MB sample with 3 imports

1. `bash("diec --scan --json ...")` with IR-10-class timeout.
2. JSON includes `Themida/WinLicense` as protector: emit one `commercial_packer_match` in
   `packer` with `severity: CRITICAL`.
3. Section cross-check: `.themida` present: add `section_name_packer_hint` with
   `evidence_refs` to the DIE fact.
4. FR-07 consults `packer` and skips decompilation per policy; `analysis_coverage`
   may record decompilation skipped.
5. FR-13 / FR-14 own verdict and escalation; this skill only supplied facts.

**Pitfalls:** skipping DIE on large files (allow time); parsing non-JSON DIE
text; writing `verdict` from this skill (reserved for `scoring` / FR-13 flow).

## Output Shape (completion checklist)

- One `diec_scan` `INFO` fact (provenance and counts when DIE ran).
- N `commercial_packer_match` facts, one per relevant DIE row.
- Optional `section_name_packer_hint` with `evidence_refs` to DIE facts.
- `tool_missing` when `diec` is unavailable, plus `analysis_coverage` for FR-15.
- All records `kind: fact`, `source_fr: "FR-05"`, provenance in `data.producer`
  (`"diec"` or `"pefile"`), not a top-level `tool` field on the Indicator.
