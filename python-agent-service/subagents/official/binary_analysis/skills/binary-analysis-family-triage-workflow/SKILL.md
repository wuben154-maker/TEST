---
name: binary-analysis-family-triage-workflow
description: |
  Third-person FR-13 workflow: from the first LLM triage on imports,
  strings_iocs, behavior_chain, packer, and triage, gate-matched
  specialists only (Cobalt Strike, Agent Tesla, ransomware, generic C2) to
  save token budget. Loads
  analyzing-malware-family-relationships-with-malpedia first, then
  family specialists (e.g. analyzing-cobalt-strike-beacon-configuration,
  analyzing-cobaltstrike-malleable-c2-profiles,
  extracting-config-from-agent-tesla-rat,
  analyzing-ransomware-encryption-mechanisms,
  reverse-engineering-ransomware-encryption-routine,
  analyzing-command-and-control-communication) plus optional
  analyzing-network-covert-channels-in-malware. Emits
  family_candidate, family_config, and family_divergence into
  llm_inferences (kind inference, evidence_refs, confidence) for
  scoring. Triggers: FR-13, "which malware family", 恶意软件家族, 家族归因, Cobalt Strike, Agent Tesla, ransomware, name-this-family
  prompts, Malpedia-style fingerprinting.
license: Apache-2.0
compatibility: binary_analysis FR-13 · schema_version 1.0.0
allowed-tools: python_exec evidence_chain
metadata:
  id: Workflow-02
  batch: C10
  adr: ADR-04, ADR-11, ADR-14, ADR-15
  fr: FR-13, FR-08
  ir: IR-01, IR-02
  nfr: NFR-05, NFR-11, NFR-14
  stability: stable
---

# Family Triage Workflow (Workflow-02)

> FR-13 asks "which family is this?" — a question that, answered
> naively, tempts the Agent to read every family specialist skill
> up-front and exhaust the skill-detail token budget. This workflow
> enforces the opposite discipline: first scan the evidence chain for
> family-specific fingerprints, then read *only* the specialist(s)
> whose gate condition fired. Verdict ownership stays with the
> rule-engine (ADR-04); this workflow produces inference-grade family
> candidates that the `scoring` tool consumes as weighted signals.

## Route context (upstream / downstream / return)

- **Who triggers this:** `binary-analysis-e2e-orchestrator` at Stage FR-13
  (and the document parent path only when a completed child binary analysis
  supplies family evidence; see `document-analysis-e2e-orchestrator` pointer).
- **Who this triggers:** on-demand load of
  `analyzing-malware-family-relationships-with-malpedia` and the
  family specialists named in the delegation map (progressive disclosure;
  `examples/binary_analysis/skills/<skill-name>/SKILL.md`).
- **When to return to the orchestrator:** after emitting the required
  `llm_inferences` Indicators (or a single `family_absent`) so FR-13
  `scoring` and FR-15 `report_gen` can proceed; this workflow does not
  call `scoring` itself.
- **FR-08 link:** first-hop LLM triage in FR-08 populates the facts this
  workflow reads; on LLM or provider failure, follow the parent orchestrator
  downgrade (`Verdict=UNKNOWN`, stop inferring) instead of inventing
  family names.

## NFR-05 and prompt budget (orchestrator-owned)

Rounds, token ceiling, and convergence are bounded by the parent `agent.md`
and orchestrator (`{max_rounds}`, `{token_budget}`, `{threshold_pct}`).
This workflow should complete gate scan plus specialist load plus
`llm_inferences` writes before those limits; if budget is already exhausted
at hand-off, emit `family_absent` or a LOW-confidence `gap_note` per
orchestrator guidance instead of deep-reading more specialists.

## When to Use

- FR-08's first LLM round has completed and the evidence chain carries
  facts in `imports`, `strings_iocs`, `packer`, `triage`, and
  optionally `behavior_chain`.
- You are about to assign a `family_candidate` to the analysis or need
  to justify one already proposed by the scoring rules.
- Downstream FR-15 will render the family name in the report and the
  analyst expects a traceable "why this family?" paragraph.
- **Document / nested binary:** if the only family evidence is on an
  embedded child that did not complete (`doc_analysis_partial` or
  budget-truncation semantics from the document orchestrator), do not
  force family attribution on the parent; follow that orchestrator’s
  pointer and re-run or defer until child facts exist.

**Do not use** as a substitute for the rule-engine's rule-match
reasoning. The `scoring` tool runs deterministic family-matching
rules from `scoring_rules.yaml` (C11) over the same facts; this
workflow adds the LLM's inference layer beside it, it does not
replace it.

## Prerequisites (READ before running)

1. `binary-analysis-evidence-chain-protocol` (Proto-02) — governs the
   Indicator schema. Every indicator emitted here is
   `kind="inference"` with non-empty `evidence_refs`.
2. `binary-analysis-sanitize-untrusted-strings` (Proto-03) — any
   sample-derived snippet (e.g. a decoded Cobalt Strike watermark, an
   AgentTesla exfil URL, a ransom-note template) that lands in a
   `data.rationale` string MUST be sanitised.
3. `analyzing-malware-family-relationships-with-malpedia` — alias /
   synonym graph; read first to avoid proposing `CobaltStrikeBeacon` and
   `CS-Beacon` as separate candidates.

Upstream family specialists are read *only* when their gate fires —
see the delegation map below.

## Operating Principles (hard constraints)

- **Rules engine owns the verdict** (ADR-04). `scoring` tool's rule
  output is authoritative; this workflow emits inferences into
  `llm_inferences`, not into `scoring`. Divergence between this
  inference and the rule engine is recorded as `data.verdict_divergence`
  on the `scoring`-bucket Indicator by C11, not by this workflow.
- **Fact-vs-inference is strict** (ADR-03 · IR-01). Every indicator
  written here is `kind="inference"`; `evidence_refs` is non-empty
  and cites the specific fact indicators (import, string, behavior
  node) that justify the call.
- **Confidence calibration** (NFR-11). HIGH only when ≥ 2 independent
  fingerprint classes converge (e.g. Malleable C2 profile match +
  Rich Header imphash match + XOR watermark byte match). MEDIUM when
  one strong single-class hit (e.g. beacon config block decoded
  cleanly). LOW when the match is a single weak signal (one family
  string, no reinforcing import pattern).
- **Token-budget discipline** (NFR-05). Read at most the
  malpedia-alias skill up-front; read each family specialist only
  when its gate fires; stop at the first family that yields
  HIGH-confidence inference — do not poll every specialist hoping to
  find a better match.

## The 3-Step Pipeline

### Step 1 · Scan the evidence chain for fingerprints

Query the existing evidence chain (via the read-only snapshot exposed
by `evidence_chain`) and compute per-family gate signals. Do this
in a single `python_exec` cell on the snapshot — no sample bytes
are touched.

Specialist gate table:

| Gate | Input buckets | Required facts before loading specialist | Specialist skill(s) to load | Output indicator type | Do not load when |
|------|---------------|------------------------------|-----------------------------|-----------------------|------------------|
| `cobalt_strike` | `triage`, `headers`, `imports`, `sections`, `strings_iocs`, `behavior_chain` | At least two independent signals, or one high-confidence YARA / scoring family hint: Cobalt Strike YARA match; imphash / Rich Header overlap with known Beacon loaders; Malleable C2 user-agent / URI pattern in `strings_iocs`; `module_chain_summary` describing HTTP(S) beacon sleep / jitter; Beacon-like import triad plus suspicious loader sections. | Primary: `analyzing-cobalt-strike-beacon-configuration`; secondary only for profile shaping: `analyzing-cobaltstrike-malleable-c2-profiles`. | `family_candidate`; optional `family_config`; `family_divergence` if another C2 family remains plausible. | Only generic network imports, one suspicious URL, or a generic "beacon" string exists; sample is a packed loader with no decoded config / C2 surface; evidence belongs to a document parent without completed child binary analysis. |
| `agent_tesla` | `triage`, `imports`, `strings_iocs`, `disassembly`, `behavior_chain` | Agent Tesla / stealer YARA or family hint; .NET assembly / namespace facts; SMTP / FTP / Telegram exfil hosts; credential-store paths (`Login Data`, Thunderbird, Outlook, browser profile stores); behavior node for credential collection or exfil. | `extracting-config-from-agent-tesla-rat`. | `family_candidate`; `family_config` when SMTP / FTP / Telegram fields can be cited. | Only a generic SMTP host or email address exists; no .NET / stealer namespace / credential-store evidence; strings are low-confidence leftovers from packed or truncated extraction. |
| `ransomware` | `triage`, `imports`, `strings_iocs`, `disassembly`, `behavior_chain` | Ransomware YARA / family hint; crypto import combo (`BCryptGenRandom` + `BCryptEncrypt`, `CryptAcquireContext` + `CryptEncrypt`, or equivalent); ransom-note filename / extension pattern; mutex / campaign string associated with ransomware; behavior chain showing bulk file traversal + encryption or shadow-copy deletion. | Primary: `analyzing-ransomware-encryption-mechanisms`; secondary only after code evidence exists: `reverse-engineering-ransomware-encryption-routine`. | `family_candidate` for a family or `<pattern class>-like`; optional `family_config` for encryption / key-management details. | Only generic crypto imports are present; only one filename resembles a note; FR-17 was skipped and no file-encryption path is visible; evidence supports "packer uses crypto" rather than victim-file encryption. |
| `generic_c2` | `imports`, `strings_iocs`, `behavior_chain`, `llm_inferences` | Network import cluster (`connect` / `send` / `recv`, WinINet / WinHTTP, CFNetwork, or POSIX sockets) plus at least one non-denoised URL / domain / IP, or a `network_c2` behavior node with evidence refs. | Primary: `analyzing-command-and-control-communication`; secondary for covert channel indicators: `analyzing-network-covert-channels-in-malware`. | `family_candidate` with a generic class such as `GenericHTTPBackdoor`; `family_divergence` if family-specific gates are stronger. | IOC is a benign CDN / update host after denoise; network imports are framework noise with no outbound target; Cobalt Strike / Agent Tesla / ransomware gate already produced a HIGH-confidence family and generic C2 adds no new evidence. |

The gate computation returns a dict: `{family_id: [fact_indicator_id,
...]}` plus the selected specialist list. Empty -> no candidate, emit a
single `family_absent` inference (see Step 3) and stop.

### Step 2 · Load the matching specialist skill(s)

For each family whose gate fired, load each selected specialist `SKILL.md`
**once** (progressive disclosure) and keep the knowledge in context only
for that family's inference. Do not load skills whose "Do not load when"
condition is true; emit a `family_absent` or `family_divergence` inference
instead of spending budget on a weak branch.

Load `analyzing-malware-family-relationships-with-malpedia` once at
the top of Step 2 only after at least one family gate fires. Use its
alias / synonym graph to normalise candidate names before loading the
family-specific specialist. If that skill is ever unavailable (e.g.
deliberately removed or archived), fall back to the family names from
the gate table above verbatim and note the gap by appending an
`analysis_coverage` fact Indicator (`kind: "fact"`, `source_fr: "FR-13"`,
`indicator_type="analysis_coverage"`,
`data={"dimension": "llm_inferences", "status": "DEGRADED",
"reason": "malpedia_unavailable"}`) into the `llm_inferences`
bucket (Proto-02: coverage markers in this bucket are `kind: "fact"`).

### Step 3 · Emit inference indicators into `llm_inferences`

For each surviving candidate, emit one of the four indicator shapes
below by calling `evidence_chain.append_indicator(bucket="llm_inferences", ...)`.
Empty-case handling is explicit (avoid silent drops). The bucket is
passed as the `bucket` argument — it is not a field on the Indicator
itself (see Proto-02).

**Candidate (normal case):**

```json
{
  "source_fr": "FR-13",
  "indicator_type": "family_candidate",
  "severity": "CRITICAL",
  "confidence": "HIGH",
  "kind": "inference",
  "evidence_refs": [
    "<imports_imphash_fact>",
    "<strings_iocs_ua_fact>",
    "<behavior_chain_module_chain_summary_inference>"
  ],
  "data": {
    "family": "CobaltStrikeBeacon",
    "malpedia_id": "win.cobalt_strike",
    "aliases": ["CS-Beacon", "CobaltBeacon"],
    "rationale": "Imphash matches published beacon loader set; Malleable C2 profile user-agent present in strings_iocs; behavior_chain module_chain_summary describes HTTPS beacon with sleep+jitter.",
    "specialist_skill": "analyzing-cobalt-strike-beacon-configuration"
  }
}
```

**Config extraction (when a specialist decodes structured config):**

```json
{
  "source_fr": "FR-13",
  "indicator_type": "family_config",
  "severity": "CRITICAL",
  "confidence": "MEDIUM",
  "kind": "inference",
  "evidence_refs": [
    "<strings_iocs_smtp_host_fact>",
    "<imports_smtp_library_fact>"
  ],
  "data": {
    "family": "AgentTesla",
    "config_schema": "agent_tesla_v3",
    "fields": {
      "exfil_method": "smtp",
      "smtp_host_sanitised": "<untrusted_sample_content>smtp.yandex.ru</untrusted_sample_content>",
      "smtp_port": 587
    }
  }
}
```

**Divergence (when gate + specialist disagree or aliasing is
ambiguous):**

```json
{
  "source_fr": "FR-13",
  "indicator_type": "family_divergence",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "kind": "inference",
  "evidence_refs": ["<relevant fact indicator ids>"],
  "data": {
    "candidates": [
      {"family": "CobaltStrikeBeacon", "confidence": "HIGH"},
      {"family": "Brute Ratel", "confidence": "LOW"}
    ],
    "selection": "CobaltStrikeBeacon",
    "rationale": "Rich Header imphash overlap with CS; Brute Ratel would require the BRc4 watermark byte which is absent."
  }
}
```

**Absent case (explicit negative result):**

```json
{
  "source_fr": "FR-13",
  "indicator_type": "family_absent",
  "severity": "INFO",
  "confidence": "MEDIUM",
  "kind": "inference",
  "evidence_refs": ["<at-least-one-fact-the-scan-considered>"],
  "data": {
    "rationale": "None of the v1 family gates fired; sample presents as generic backdoor. Recommend MANUAL_REVERSE.",
    "gates_evaluated": ["cobalt_strike", "agent_tesla", "ransomware", "generic_c2"]
  }
}
```

The `family_absent` indicator still requires `evidence_refs` — cite
the broadest fact(s) the scan considered (e.g. the imports bucket
summary fact or a scoring input note). Empty `evidence_refs` on an
`inference` is rejected by `schema.indicator._enforce_inference_rules`
at Indicator construction time — the store never sees the bad
payload.

Severity mapping recap (do not confuse with `confidence`):
`CRITICAL` for family identification with strong multi-signal
evidence; `WARNING` for divergence / ambiguity needing analyst
judgement; `INFO` for the explicit absent case.

## Interaction with the scoring tool (C11)

- This workflow emits into `llm_inferences`. The `scoring` tool (C11)
  reads both `llm_inferences` and the underlying `fact`s and assigns
  the final `family_candidate` weight in the `scoring` bucket.
- If the rule-engine's family pick differs from this workflow's HIGH
  inference, the `scoring` tool records `data.verdict_divergence` on
  its `scoring`-bucket Indicator citing both. This workflow does
  **not** write to `scoring` and does **not** resolve the divergence —
  that is ADR-04 territory.

## Anti-Patterns

- **Blanket pre-read:** loading every family specialist skill before the gate
  scan. Blanket loads defeat the token-budget discipline and the NFR-05
  assertion that Progressive Disclosure is demand-driven.
- **Wrong `kind` for family claims:** writing `kind="fact"` for
  `family_*` into `llm_inferences`. The bucket carries family findings as
  `kind: inference` (plus `analysis_coverage` / `audit_gap` *fact* markers
  per Proto-02). A `kind: fact` family indicator here would confuse the
  scoring tool's rule inputs.
- **Unreferenced inference:** emitting a `family_candidate` with empty
  `evidence_refs`. Without references the inference is unattributable and the
  `schema.indicator` inference validator rejects it at construction
  time.
- **Verdict overreach:** overriding the rule engine's verdict by raising this
  workflow's `severity` to `CRITICAL` on a weak inference. Severity here
  expresses the *finding's* potency paired with `confidence`; the
  verdict is owned by the rule engine.
- **Severity vs confidence mix-up:** using `severity: "HIGH"` / `"MEDIUM"`
  / `"LOW"`. The 3-level severity enum is `INFO` / `WARNING` / `CRITICAL`;
  HIGH / MEDIUM / LOW belong to `confidence`.
- **Unsanitised C2 text:** stuffing a raw decoded Cobalt Strike Malleable C2
  profile body directly into `data.rationale`. Run Proto-03 `sanitize()` and
  wrap the snippet in `<untrusted_sample_content>` first.
- **Depth creep:** continuing to load secondary specialists after the primary
  specialist has yielded a HIGH-confidence inference. Stop and let
  FR-15 request deeper dives on demand.

## Key Concepts

| Term | Definition |
|------|------------|
| **Gate signal** | A fact-level pattern in the evidence chain whose presence opens the door to a specific family hypothesis. |
| **Specialist skill** | A skill (e.g. `analyzing-cobalt-strike-beacon-configuration`) that encodes detection and config-extraction methodology for one family. |
| **Candidate** | A family hypothesis backed by ≥ 1 gate signal; stored as `family_candidate` inference. |
| **Divergence** | Two or more roughly-equal candidates; recorded so analyst + the scoring tool see the ambiguity. |
| **Config extraction** | Structured payload decoded by the specialist (beacon config, AgentTesla SMTP settings, ransomware key-derivation parameters); stored as `family_config` inference. |

## Tools & Systems

- **Skill loading (ADR-15)** — specialist methodology lives under
  `examples/binary_analysis/skills/<name>/SKILL.md`. Load on demand when a
  gate matches; the runtime whitelist for mutating tools on this path is
  `python_exec` and `evidence_chain` (see frontmatter). Other tools
  named here (`scoring`, `report_gen`) are invoked by the orchestrator,
  not by this workflow.
- **`python_exec`** — runs the gate scan over the evidence-chain
  snapshot inside the sandbox; pure-Python logic, no sample bytes.
- **`evidence_chain` / `evidence_chain.append_indicator`** — sole writer
  into `llm_inferences` for this workflow; append-only per ADR-02.
- **`binary_analysis.prompts.sanitize`** — required for any
  sample-derived snippet embedded in `data.rationale` or
  `data.fields.*` before this indicator becomes LLM input on a
  subsequent round.

## Common Scenarios

### Scenario: Cobalt Strike Beacon with a Malleable C2 profile

**Context**: PE32+ loader. `imports` bucket contains a
`suspicious_import` fact triad (`InternetConnectW`,
`HttpSendRequestW`, `VirtualAllocEx`). `strings_iocs` carries a
user-agent string matching a published Malleable C2 profile.
Rich Header imphash appears on the CS loader set.

**Approach**:

1. Gate scan fires Cobalt Strike (3 signals) and the generic C2 gate
   (1 signal, lower priority).
2. Load `analyzing-malware-family-relationships-with-malpedia` / `SKILL.md`
   for the alias graph.
3. Load `analyzing-cobalt-strike-beacon-configuration` / `SKILL.md` for
   detection fingerprints + config-extraction recipe.
4. Specialist confirms the watermark byte at expected offset → HIGH
   confidence.
5. Emit `family_candidate` with `confidence: HIGH` (cites 3 facts).
6. Optionally load `analyzing-cobaltstrike-malleable-c2-profiles` to
   decode the profile and emit a `family_config` inference.
7. Generic C2 gate downgraded to a note in `family_divergence` with
   rationale "superseded by CS HIGH match".

### Scenario: Ransomware with no Malpedia skill available

**Context**: PE32 sample with `BCryptGenRandom` + `BCryptEncrypt`
import pair, a `README_TO_DECRYPT.txt` path in `strings_iocs`, and a
bulk `CreateFileW` loop in `behavior_chain`.

**Approach**:

1. Gate scan fires ransomware (3 signals).
2. If `analyzing-malware-family-relationships-with-malpedia` is
   unavailable (e.g. deliberately archived or absent in a cut-down
   deployment) → emit an `analysis_coverage` fact Indicator
   (`kind: "fact"`, `source_fr: "FR-13"`, `indicator_type="analysis_coverage"`,
   `data={"dimension": "llm_inferences", "status": "DEGRADED",
   "reason": "malpedia_unavailable"}`) into the `llm_inferences`
   bucket. In the default full deployment the skill is present, so this
   step is skipped.
3. Load `analyzing-ransomware-encryption-mechanisms` / `SKILL.md` and match
   Globe Imposter-style AES-in-CBC + RSA-2048 envelope pattern.
4. Emit `family_candidate` with `family: "Globe Imposter-like"`,
   `confidence: MEDIUM` (no family-specific watermark; just the
   pattern class).
5. Load `reverse-engineering-ransomware-encryption-routine` / `SKILL.md`
   only if FR-08 requests a later key-recovery analysis.

**Pitfalls**:

- Misclassifying generic ransomware as a specific family without
  watermark evidence. Prefer `data.family: "<pattern class>-like"`
  with `confidence: "MEDIUM"` until a specialist skill yields a
  watermark.
- Leaking the raw ransom-note body into `data.rationale`. Sanitise
  + wrap; otherwise the note text flows back into the next LLM round
  unwrapped.

## Output Format

Successful application is visible as a stable shape in the evidence
chain:

- ≥ 1 `inference` indicator in `llm_inferences` whose `indicator_type`
  is one of `family_candidate`, `family_config`, `family_divergence`,
  or `family_absent`.
- At most one `family_candidate` per distinct family; additional
  alternatives fold into a `family_divergence` indicator.
- At most one `family_absent` per run (only when every gate was
  empty).
- Optionally one `analysis_coverage` fact Indicator
  (`data.reason="malpedia_unavailable"`) in `llm_inferences` when the
  alias-graph skill is missing.
- Zero writes into `scoring` — the `scoring` tool (C11) owns that
  bucket.

Every family Indicator is `kind="inference"`, `source_fr="FR-13"`,
with a non-empty `evidence_refs` list citing the facts the gate scan
matched, a 3-level `severity ∈ {"INFO", "WARNING", "CRITICAL"}`, and
a `confidence` drawn from Proto-02's HIGH / MEDIUM / LOW calibration
(NFR-11).
