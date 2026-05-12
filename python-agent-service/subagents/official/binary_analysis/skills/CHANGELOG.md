# Skills CHANGELOG

> Optional audit log for `examples/binary_analysis/skills/` per ADR-15
> v0.5 (single flat directory) and ADR-15 v0.7 (ownership tier / vendor-in
> immutability removed — all skills under this directory are editable
> project assets).
>
> Writing a new entry is **recommended**, not required, whenever you:
> (a) re-sync from upstream, (b) edit any skill body, (c) bump a
> project-initiated skill's version. The goal is auditability and to help
> future upstream-diff reviews — not to gate edits.

The layout is deliberately lightweight — one section per event, newest at
the top. Schema is markdown prose; no YAML frontmatter (this file is not a
skill).

## 2026-04-26 — skills overnight audit P0 contracts

**Scope:** `src/binary_analysis/prompts/agent.md` ·
`skills/binary-analysis-e2e-orchestrator/SKILL.md` ·
`skills/document-analysis-e2e-orchestrator/SKILL.md` ·
`skills/binary-analysis-evidence-chain-protocol/SKILL.md` ·
`skills/binary-analysis-sanitize-untrusted-strings/SKILL.md`.

**Motivation.** The P0 contracts phase synchronized the thin runtime prompt,
binary/document orchestrators, Proto-02, and Proto-03 with current E2E-01 /
E2E-02 contracts before lower-level workflow audits fan out.

**Changes.**

- Added `sandbox_session` to the pre-`file_identify` prompt ban and to both
  orchestrators' `allowed-tools` plus operating boundaries, preserving
  `file_identify` as the first hop.
- Updated Proto-02 evidence-chain wording for v1.1 document buckets while
  keeping the Indicator schema at v1.0.0.
- Expanded Proto-03 sanitization coverage for document-derived text and aligned
  the chain example with `data.raw_sanitised`.

**Audit artifacts.** See `audit-runs/20260426T095022Z/` for contracts, rubric,
audit notes, P0 phase report, and progress state.

## 2026-04-26 — FR-07 audit pass 2 (P0-4 + P0-5)

**Scope:** `skills/binary-analysis-evidence-chain-protocol/SKILL.md` ·
`skills/performing-static-malware-analysis-with-pe-studio/SKILL.md` ·
`skills/analyzing-elf-structure/SKILL.md` ·
`skills/analyzing-macho-structure/SKILL.md` ·
`skills/ghidra-priority-queue-workflow/SKILL.md` ·
`skills/binary-analysis-e2e-orchestrator/SKILL.md`.

**Motivation.** Pass 1 (above) closed 13/15 audit items but explicitly
deferred P0-4 (FR-04 `imports.data.callers`) and P0-5 (format-aware
priority signal registry). The two together fix the "every Step 0
priority entry resolves to a thunk stub and Ghidra reports
`status="not_found"`" failure mode that made the priority queue
near-useless on real samples. This pass closes both.

**Changes.**

- **`suspicious_import` schema is now format-neutral and
  caller-aware.** `binary-analysis-evidence-chain-protocol` documents
  the canonical payload — `data.module` (format-neutral library /
  DLL name), `data.symbol` (imported function), optional
  `data.capability`, optional `data.thunk_addr` (PE IAT entry / ELF
  PLT stub / Mach-O `__la_symbol_ptr` slot — the import stub
  address, **not** the user function), and optional `data.callers`
  (list of `{"addr": "0x...", "name": "<func or null>"}`, the user
  functions that reference the import). PE retains an optional `dll`
  alias for backward compatibility; new consumers SHOULD prefer
  `module`. The Minimal Examples block carries both a basic and a
  full `suspicious_import` fact for reference. (P0-4)
- **Per-format producers now emit `suspicious_import` per
  high-risk symbol.** `performing-static-malware-analysis-with-pe-studio`
  Step 4 grew a "Caller xref recipe" using `pefile` + `capstone` to
  walk `.text` for instructions whose target is an IAT entry, mapping
  each match back to the containing function via best-effort
  function-start estimates (entry point + exports). The same shape
  was added to `analyzing-elf-structure` Step 4 (POSIX shortlist,
  `.rela.plt` walk for `thunk_addr`, executable `PT_LOAD` scan for
  callers — multi-arch via `capstone`) and `analyzing-macho-structure`
  Step 4 (Mach-O shortlist with `_`-prefixed symbol names,
  `LC_DYLD_INFO_ONLY.bind_off` walk for `thunk_addr`, executable
  segment scan keyed by `hdr.cpu_type` for x86_64 / ARM64).
  `data.callers` is best-effort: when `capstone` / relocation table /
  bind table is unavailable the producer omits the field and FR-07
  falls back to bare-symbol tokens with the documented `not_found`
  failure mode. The capability aggregates (`elf_capability` /
  `macho_capability`) are kept for capability summaries; they are no
  longer the FR-07 priority feed. (P0-4)
- **`ghidra-priority-queue-workflow` Step 0 is format-aware.** The
  reference code now reads `file_meta.data.format` first and
  dispatches against `HIGH_RISK_APIS_BY_FORMAT` (PE →
  `HIGH_RISK_APIS_WIN32`, ELF → `HIGH_RISK_APIS_POSIX`, Mach-O →
  `HIGH_RISK_APIS_MACH`). The token grammar changed from raw symbol
  names to user-function references: `<caller_name>@<caller_addr>`
  when `data.callers[i].name` is populated, `FUN_<addr>@<caller_addr>`
  when the producer could not name the caller, with bare `<symbol>`
  reserved for the legacy fallback path. The signal table grew rows
  for high-risk imports (caller-aware + name-only fallback),
  format-specific pre-`main` initialisers
  (`tls_callback` / `macho_mod_init_func` / `elf_init_array_entry`),
  and Mach-O structural anomalies
  (`macho_writable_executable_segment` / `macho_rpath_anomaly`).
  Managed assemblies (`.NET` / `CIL` / `ManagedPE`) now refuse the
  Ghidra path explicitly: Step 0 emits `analysis_coverage` with
  `data.reason="managed_assembly_routed_to_fr07b"` and exits, letting
  FR-07b own the path. Go / Rust currently fall through to the host
  format's provider — pclntab / crate-metadata signals are still
  pending FR-04 producer work and tracked under P1-10. (P0-5)
- **Failure-mode table updated.** The "every entry `status="not_found"`"
  row now points at the FR-04 `data.callers` contract (producer either
  did not run `capstone` or is older than P0-4) instead of the
  obsolete "use `<name>@<address>` tokens manually" advice. Two new
  rows cover the explicit `managed_assembly_routed_to_fr07b` and
  `no_signal_provider_for_format` `analysis_coverage` exits.
- **Orchestrator note refreshed.** `binary-analysis-e2e-orchestrator`
  FR-07a now describes the active format-aware signal registry and
  the format-neutral `suspicious_import` schema in one sentence,
  pointing at the priority-queue skill and Proto-02 as the canonical
  references; the previous P0-4 / P0-5 deferral note is removed.

**Not changed.**

- Mach-O hand-off table prose / structure (Pass 1) — only the
  signal-table rows were rewritten to mention `suspicious_import`
  instead of name-only tokens.
- The strategic-skip cancel link mechanic (P1-6, Pass 1) — Step 0
  still emits `data.cancels_strategic_skip` and lists the skip
  indicator id under `evidence_refs`.
- The derived `top_n` budget formula (P1-9, Pass 1) — Step 0 still
  computes `TOP_N = max(8, int((BASH_TIMEOUT_S * 0.8) // PER_FN_TIMEOUT_S))`
  and records the `bash_timeout_s` / `per_fn_timeout_s` / `top_n`
  triple under `decompile_priority.data.budget`.
- The deferred FR-06 `xref_function` boost (P0-3) is still a
  forward-compatible no-op; it activates the moment FR-06 starts
  emitting `data.xref_function` on `strings_iocs` facts.

**Open follow-ups.**

- **P1-10 (Go / Rust priority signal providers).** Go (pclntab
  `function_class` boost) and Rust (`crate_metadata` symbol-prefix
  boost) signal providers are wired up at the orchestrator level but
  inactive at the producer level — `analyzing-golang-malware-with-ghidra`
  and `reverse-engineering-rust-malware` do not yet emit `suspicious_import`
  with `data.callers`. Until they do, Go / Rust samples on those host
  formats fall through to the host format's POSIX / Win32 / Mach
  provider, which is correct but suboptimal for static-linked Go where
  the runtime fans out from `runtime.main`.

## 2026-04-26 — FR-07 audit pass 1 (Wave 1 + Wave 2, P0/P1/P2 except P0-4/P0-5)

**Scope:** `skills/binary-analysis-e2e-orchestrator/SKILL.md` ·
`skills/ghidra-priority-queue-workflow/SKILL.md` ·
`skills/analyzing-packed-malware-with-upx-unpacker/SKILL.md` ·
`skills/analyzing-macho-structure/SKILL.md` ·
`skills/reverse-engineering-dotnet-malware-with-dnspy/SKILL.md` ·
`specs/e2e01-backend/SPEC.md` (v0.3 → v0.3.1).

**Motivation.** Audit of the FR-07 orchestrator stage and its referenced
specialist skills surfaced 15 inconsistencies. This pass closes 13 of
them (all P0/P1/P2 items except P0-4 / P0-5, which require an FR-04
`imports.data.callers` schema extension and a format-aware priority
signal registry; deferred to a follow-up session).

**Changes.**

- **FR-07 split into FR-07a (native) / FR-07b (managed)** in the
  orchestrator. Native path keeps the Ghidra + `analyzeHeadless` +
  `DecompileByList.py` contract; managed (.NET) path no longer has to
  pretend it produces `decompile_priority` or `callgraph_edge` to
  satisfy the completion signal. Each sub-path now has its own
  required indicator set, and the downgrade table is matched by
  sub-path. (P0-1, P1-8)
- **`unpack_result.status` enum extended from 4 → 6 values** in SPEC
  FR-05 AC-9 to match the UPX skill's actual decision tree:
  `success` / `failed` / `not_attempted` / `skipped_not_whitelisted`
  + new `skipped_commercial_protector` (DIE-detected commercial / VM
  protector) and `tool_missing` (UPX binary absent from sandbox).
  `scoring_rules.yaml` does not branch on `status` so the extension
  has no scoring regression. (P0-2)
- **Strategic-skip cancel is now explicit, not inferred.** When a
  prior `analysis_coverage` fact carries
  `data.reason="fr02_ac8_strategic_skip"`, the first FR-07 fact
  (FR-07a's `decompile_priority` or FR-07b's `managed_metadata`)
  must set `data.cancels_strategic_skip=true` and list that skip
  indicator's id under `evidence_refs`. Documented in orchestrator
  downgrade table, priority-queue Step 0 reference code, and dnSpy
  skill's FR-07b completion signal section. (P1-6)
- **`top_n` is now a derived budget**, not a hardcoded `40`. Step 0
  reference code computes
  `TOP_N = max(8, int((BASH_TIMEOUT_S * 0.8) // PER_FN_TIMEOUT_S))`
  and records the chosen `bash_timeout_s` / `per_fn_timeout_s` /
  `top_n` triple under `decompile_priority.data.budget` for audit.
  Default is 8 functions worst-case (was 40 with a 20-min worst-case
  contradicting the 4-min BashTool ceiling). (P1-9)
- **xref_function loop marked DEFERRED in priority-queue Step 0.**
  `binary-analysis-ioc-extraction-workflow` v1 does not write
  `data.xref_function` on string IOC facts, so the medium-weight
  string-xref boost was dead code. Flagged in the priority signal
  table and code comment; full activation tracked under P0-4. (P0-3)
- **Mach-O FR-07 hand-off table** added to the bottom of
  `analyzing-macho-structure/SKILL.md`. Until a dedicated
  `analyzing-macho-malware-with-ghidra` skill exists (P1-10), Mach-O
  reuses `reverse-engineering-malware-with-ghidra` plus this table to
  seed the priority queue with `macho_mod_init_func`,
  `macho_writable_executable_segment`, `macho_capability`
  (`process_manipulation` / `dynamic_loading` / `network` / `crypto`)
  and `macho_rpath_anomaly`. (P1-10 — partial)
- **Dedupe key clarified** in priority-queue Step 0 (`scored` keyed by
  symbol; cross-DLL collisions rare in practice for HIGH_RISK_APIS;
  comment explains promotion path to `(module, symbol)` if FR-04
  starts emitting same-name symbols from different modules). (P2-13)
- **Orchestrator hygiene fixes**: PE skills carry an explicit
  "PE / 默认 →" prefix to match the other architecture markers;
  `binary-analysis-evidence-chain-protocol` now appears in FR-07's
  recommended skills list; SPEC FR-02 AC-9's SEVERE formula is
  inlined into the `fr02_ac8_strategic_skip` row of the FR-07
  downgrade table; `decompile_input` write/read responsibility is
  now a "shared prelude" step before the FR-07a / FR-07b split,
  matching the underlying `EvidenceChainTool.query` →
  `EvidenceChainTool.append` two-call shape. (P1-7, P2-11, P2-12,
  P2-15)

**Deferred to a follow-up session (P0-4 / P0-5).**

- FR-04 `imports` fact schema extension to carry `data.callers` (user
  function addresses that reference each import), so priority-queue
  Step 0 can emit `<caller_name>@<caller_addr>` tokens instead of raw
  thunked import names that resolve to import stubs and produce
  `status="not_found"` on first run.
- Format-aware `SIGNAL_PROVIDERS` dispatch in priority-queue Step 0,
  so ELF (POSIX syscalls + main fan-out + .init_array), Mach-O
  (capabilities + mod_init_func), Go (pclntab function classes), Rust
  (crate metadata), and .NET (managed metadata) all contribute
  priority signals — currently only the Win32 `HIGH_RISK_APIS` set is
  consulted.

## 2026-04-26 — Sync FR-07 specialist runtime contracts

**Scope:** `skills/binary-analysis-e2e-orchestrator/SKILL.md` ·
`skills/ghidra-priority-queue-workflow/SKILL.md` ·
`skills/reverse-engineering-dotnet-malware-with-dnspy/SKILL.md` ·
`skills/analyzing-linux-elf-malware-with-ghidra/SKILL.md` ·
`skills/analyzing-golang-malware-with-ghidra/SKILL.md` ·
`skills/reverse-engineering-rust-malware/SKILL.md`.

**Motivation.** The FR-07 orchestrator now selects an explicit
`decompile_input` and distinguishes unpacked artifacts from original packed
samples. Related specialist skills needed to consume that contract and stop
presenting GUI/debugger or alternate-decompiler paths as runtime steps.

**Changes.**

- Updated the priority-queue Ghidra workflow to consume `decompile_input`,
  carry `input_path` / `input_sha256` into `decompile_priority`, and import the
  selected path instead of hard-coding `sample.bin`.
- Split FR-07 decompilation coverage reasons into `decompiler_unavailable`,
  `manifest_missing`, `decompile_all_failed`, and `callgraph_unavailable`.
- Reworked the .NET skill as a static evidence-chain workflow: no dnSpy
  debugger, no sample execution, no recompilation, no plaintext credential
  output.
- Added runtime contracts to ELF / Go / Rust specialist skills so they remain
  interpretation layers over the sanctioned Ghidra workflow and write FR-07
  facts instead of reports.

## 2026-04-26 — Tighten FR-07 decompile gate

**Scope:** `skills/binary-analysis-e2e-orchestrator/SKILL.md`.

**Motivation.** FR-07 sits between FR-05 unpacking and FR-17 behavior-chain
reconstruction. Its orchestrator text needed to distinguish successful unpacking
from the mandatory single `unpack_result` marker, and to make the FR-17 call
surface explicit.

**Changes.**

- Added FR-07 input selection over `unpack_result.status="success"` and
  `data.unpacked_path`, with failed / skipped unpack states explicitly excluded
  from the success path.
- Tightened the completion signal to require `decompile_priority`,
  `decompiled_function`, `function_tag`, and `callgraph_edge` facts, or an
  explicit coverage gap when call graph export is unavailable.
- Replaced the downgrade sentence with a trigger/action/reason table preserving
  `decompiler_unavailable` and `fr02_ac8_strategic_skip`.
- Routed ELF decompilation to the FR-07-scoped
  `analyzing-linux-elf-malware-with-ghidra` skill.

## 2026-04-26 — Runtime-safe PEStudio FR-04 rewrite

**Scope:** `skills/performing-static-malware-analysis-with-pe-studio/SKILL.md`.

**Motivation.** The inherited PEStudio guide read like a human workstation
manual and mixed FR-04 structure, FR-05 packer detection, FR-06 strings/IOCs,
reputation lookup, and default dynamic-analysis next steps. Runtime skills must
stay sandbox-safe and emit deterministic evidence-chain facts.

**Changes.**

- Rewrote the skill as the FR-04 PE structural parsing workflow over
  `file_meta`, the sandbox sample path, and Proto-02.
- Restricted outputs to `headers`, `imports`, `sections`, `resources`, and
  `debug_info` facts.
- Routed strings/IOCs to FR-06, packer identity to FR-05 / DIE / UPX, and
  inference/escalation to downstream FR-08 / FR-13 / FR-14 stages.
- Removed external reputation guidance, local GUI prerequisites, ad hoc strings
  filtering, raw resource byte extraction, and default detonation/rule-writing
  next steps.

## 2026-04-26 — Tighten specialist skill gates

**Scope:** `skills/binary-analysis-family-triage-workflow/SKILL.md` ·
`skills/two-phase-behavior-chain-reconstruction/SKILL.md`.

**Motivation.** Specialist skills should be loaded only when evidence-chain
facts justify their token cost. The prior delegation maps named specialists but
did not state the input buckets, minimum facts, output indicator shapes, or
negative conditions clearly enough.

**Changes.**

- Replaced the family fingerprint table with explicit gates for Cobalt Strike,
  Agent Tesla, ransomware, and generic C2 family/class triage.
- Replaced the FR-17 delegation table with specialist gates for process
  injection, DLL sideloading, fileless execution, persistence, generic C2,
  ransomware behavior, and sandbox evasion.
- Each gate now declares input buckets, required facts before `Read`, output
  indicator types, and when not to read the specialist skill.

## 2026-04-26 — Clarify FR-07 to FR-17 call-graph interface

**Scope:** `skills/ghidra-priority-queue-workflow/SKILL.md` ·
`skills/two-phase-behavior-chain-reconstruction/SKILL.md`.

**Motivation.** FR-17 assumed `callgraph_edge`, `function_tag`, and
`decompiled_function` facts existed, but FR-07's workflow did not explicitly
own that fact surface or define the downgrade path when Ghidra cannot export
a call graph.

**Changes.**

- Made FR-07 responsible for writing `decompiled_function`, `function_tag`,
  and `callgraph_edge` facts into `disassembly` before FR-17 runs.
- Required `analysis_coverage` with `reason="callgraph_unavailable"` when
  the call graph cannot be exported.
- Updated FR-17 guidance to consume only FR-07 call-graph facts and skip
  behavior-chain reconstruction instead of guessing caller / callee edges.

## 2026-04-26 — Add FR-08 binary signal matrix reference

**Scope:** `skills/binary-analysis-e2e-orchestrator/SKILL.md` ·
`skills/binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md`.

**Motivation.** FR-08 needed an explicit signal matrix for mapping evidence-chain
facts to LLM hypotheses without expanding `agent.md` or turning the top-level
orchestrator into a long methodology document.

**Changes.**

- Added a child reference covering fact triggers, hypothesis labels,
  on-demand specialist reads, and `llm_inferences` indicator shapes.
- Updated binary Stage FR-08 to point at the reference while keeping the
  prompt control plane unchanged.

## 2026-04-25 — Restore Office/PDF document workflows for E2E-02

**Scope:** `skills/document-analysis-e2e-orchestrator/SKILL.md` ·
`skills/analyzing-macro-malware-in-office-documents/SKILL.md` ·
`skills/analyzing-pdf-malware-with-pdfid/SKILL.md` ·
`skills/_archive/analyzing-malicious-pdf-with-peepdf/SKILL.md` ·
`skills/_archive/README.md` ·
`src/binary_analysis/tools/document_extract.py` ·
`src/binary_analysis/sandbox/document_workers/run_peepdf.py` ·
`config/scoring_rules.yaml` ·
`tests/unit_tests/skills/test_skills_inventory.py` ·
`tests/unit_tests/sandbox/test_document_workers.py` ·
`tests/unit_tests/tools/test_document_extract.py` ·
`tests/unit_tests/tools/test_scoring.py`.

**Motivation.** E2E-02 introduced `document_extract` and a document
orchestrator, so Office macro and PDF malware skills can be active again, but
only as evidence-driven workflows under the document Stage Map. The previous
vendor-style bodies taught direct parser execution and duplicated PDF entry
points, which conflicted with sandbox-only parsing and document bucket
ownership.

**Changes.**

- Rewrote the Office macro skill around `document_extract` facts, FR-08
  hypotheses, FR-06 IOC handoff, and confidence downgrade handling.
- Rewrote `analyzing-pdf-malware-with-pdfid` as the single active PDF workflow,
  folding in PDFiD, pdf-parser, and peepdf-style object / JavaScript reasoning.
- Archived the peepdf-specific duplicate entry and updated inventory tests so
  the two active document workflows are discoverable while the duplicate is not.
- Added Office/PDF workflow recommendations to the document orchestrator's
  FR-08 stage; FR-03 remains owned by `document_extract`.
- Follow-up detection alignment: `document_extract` now tags Office triggers,
  macro simulation events, PDF action chains, and PDF embedded-file format hints
  with the exact fields consumed by document scoring rules.
- Follow-up macro recall boost: `run_olevba.py` now keeps full VBA source inside
  the sandbox worker, derives bounded deobfuscated previews, static
  `macro_action_call` events, and URL/IOC strings, then lets `document_extract`
  map those outputs into existing evidence-chain and `strings_iocs` flows.
- Follow-up PDF recall boost: `run_peepdf.py` now emits PDFiD-style keyword /
  structure summaries, bounded JavaScript exploit / obfuscation markers, URI /
  SubmitForm targets, and magic-based embedded-payload format hints.  Document
  scoring consumes these as deterministic PDF exploit and phishing signals.

## 2026-04-25 — `agent.md` 文档路由并入 §1（Scope A+B，模式 3）

**Scope:** `src/binary_analysis/prompts/agent.md` · `tests/unit_tests/test_agent.py` · `tests/integration_tests/test_orchestrator_skill_routing.py` · `.cursor/skills/binary-analysis-prompt-optimizer/{SKILL.md,references/build-contracts.md,references/refactoring-playbook.md}`.

**Motivation.** §5 在瘦身后只剩两条 bootstrap guard，已不再承担独立“文档模式章节”的职责。为了让 `agent.md` 的结构更自上而下，文档首跳、路径互斥与 `document_extract` 禁用合并回 §1 路由；文档 Stage Map、四桶、置信度下调与递归细节继续由 `document-analysis-e2e-orchestrator` 持有。

**Changes.**

- 删除独立 `## 5. 文档模式` 章节；§1 文档路径条直接指向文档编排器并说明文档细节由其持有。
- §1 互斥段新增 `document_extract` 禁用于 PE / ELF / Mach-O 的门闩，保持二进制/文档首跳决策在同一处。
- 测试与 prompt optimizer 契约从“§5 两条 bootstrap guard”同步为“§1 文档路由守卫”，并锁定不再复建尾部 §5。

## 2026-04-25 — `agent.md` 文档模式门闩瘦身（Scope A+B，模式 3）

**Scope:** `src/binary_analysis/prompts/agent.md` · `skills/document-analysis-e2e-orchestrator/SKILL.md` · `tests/unit_tests/test_agent.py` · `tests/integration_tests/test_orchestrator_skill_routing.py` · `.cursor/skills/binary-analysis-prompt-optimizer/{SKILL.md,references/build-contracts.md}`.

**Motivation.** 重新从首跳控制面分层看，`agent.md` §5 不应持有文档 Stage Map、四桶归属、置信度下调或嵌入样本递归细则；这些内容在模型读取文档编排器后才需要。`agent.md` 只需要解决读取编排器之前的 bootstrap 问题：先读哪个技能，以及文档/二进制路径如何互斥。

**Changes.**

- `agent.md` §5 由 5 条压缩为 2 条：先读 `document-analysis-e2e-orchestrator/SKILL.md`；文档路径与二进制路径互斥且 `document_extract` 不得用于 PE / ELF / Mach-O。细节改为指向文档编排器持有。
- `document-analysis-e2e-orchestrator` 在运行原则中明确文档父会话仅走本文 Stage Map，不进入 e2e01 的 triage / disassembly / behavior_chain；嵌入二进制仍只经 FR-30 递归子会话处理。
- 测试与优化器构建契约同步从“五条文档模式规则”改为“两条 bootstrap guard”，避免未来把细阶段表重新拉回 `agent.md`。

## 2026-04-25 — 互斥与降级枚举收紧（Scope A+B，模式 2）

**Scope:** `src/binary_analysis/prompts/agent.md` · `skills/binary-analysis-e2e-orchestrator/SKILL.md` · `skills/document-analysis-e2e-orchestrator/SKILL.md`.

**Motivation.** 从运行时 agent 视角复审后发现三类可执行性风险：(a) `agent.md` 提到不存在的 `file_write` 工具；(b) 文档编排器一边禁止文档样本使用 `bash` / `python_exec`，一边在降级与 IOC 阶段显式允许有限调用；(c) 文档递归二进制子样本的“互斥”边界与 `unknown_downgrade_reason` 枚举大小写需要更确定。

**Changes.**

- `agent.md` 删除 `file_write` 指针，改为禁止依赖 shell 组合副作用；§5.5 明确嵌入 PE / ELF / Mach-O 只经宿主递归协议创建独立子会话，父文档会话不直接执行二进制 Stage Map。
- 二进制编排器并行化约定补充 FR-07 门控：反编译前必须消费 FR-04 结构事实与 FR-05 `packer` / `unpack_result` 结论。
- 文档编排器收紧父会话 / 子会话互斥措辞，允许本文明确列出的文档降级与 FR-06 IOC 辅助调用，并将 `oneNote_parser_unavailable` 统一为 schema 枚举值 `onenote_parser_unavailable`。

## 2026-04-25 — `agent.md` 低风险二连压缩（Scope A，模式 1）

**Scope:** `src/binary_analysis/prompts/agent.md`.

**Motivation.** 上一条切分移除完成后审阅 `agent.md` 时发现两处仍可在不破坏 A.2 冻词、不改测试期望的前提下进一步瘦身：(a) §3 阶段 2 的「结构 / 熵 / 字符串 / 反编译 / 行为链或文档解析与宏仿真」是一段**技法枚举**，与 §1 「Stage Map / 推荐子技能 / 降级表都在编排器中」的指针定位**互相重复**——枚举一半（漏写常用项如 `ioc_extract` / `pe_metadata`）反而比不枚举更易误导；(b) §5.4 同时复述了 §2.7 的「文档四桶 LLM 不写」与文档编排器 Stage FR-08 的 `vba_simulation_gap` / `doc_analysis_partial` 置信度下调契约（编排器 line 153/181/224/236 已**多处**owns 该信号），构成跨文件三重冗余。两处都属于 R.5 单源原则下的纯**指针化**机会。

**Changes.**

- **§3 阶段 2 技法词压缩。** `结构 / 熵 / 字符串 / 反编译 / 行为链或文档解析与宏仿真` → `按所选编排器 Stage Map 顺序推进`。`evidence_chain` 快照核对子句保留（A.2 冻词）。语义等价但不再与 §1 编排器指针重复。
- **§5.4 置信度下调因素下推。** `…由工具与规则引擎拥有；LLM 推理写 llm_inferences，并把 vba_simulation_gap / doc_analysis_partial 作为置信度下调因素` → `…写入归属遵循 §2.7；置信度下调与自洽细则由文档编排器 Stage FR-08 处理`。删除两个具体信号字面（`vba_simulation_gap` / `doc_analysis_partial`）——它们的正本在 `examples/binary_analysis/skills/document-analysis-e2e-orchestrator/SKILL.md` 第 153/181 行（FR-08 AC-5 「保子砍父」感知 + Stage FR-08 自洽性轮）。文档四桶名单保留作为指针锚点（提升可读性）。

**Verification.**

- `BINARY_ANALYST_SYSTEM_PROMPT` 长度 3791 字符（上次切分移除后约 3870；本次进一步省 ~80 字符），≤ 4500 字符上限有余量。
- 5 编号项（§5.1–§5.5）结构保持，`test_section_contains_five_guideline_points` 通过。
- 受影响的 20 个测试（`TestSystemPrompt` ×10 + `TestDocumentModeSection` ×6 + `TestSystemPromptDocumentRouting` ×4）全绿。
- 无 Python 源文件改动；无新增导入或 `__all__` 变化；无文档跨文件契约变更。

**Non-changes.**

- §1 路由对称结构、§2 七条横切、§3 阶段 1/3、§4 预算/降级/审计、§5.1/§5.2/§5.3/§5.5 均未触动。
- `document-analysis-e2e-orchestrator/SKILL.md` 未修改（其 Stage FR-08 line 181 已经owns相同契约，无需新增）。
- A.2 冻词全部保留：`evidence_chain` / `behavior_chain` / 自洽 / 降级 / `document_extract` / `analysis_id` / `document_tier` / 5-points 编号 / 编排器精确路径 ≥ 2 次。

## 2026-04-25 — 移除 `agent.md` base/patch 切分（Scope A，模式 2/3）

**Scope:** `src/binary_analysis/prompts/agent.md` · `src/binary_analysis/prompts/system_prompt.py` · `src/binary_analysis/agent.py` · `tests/unit_tests/test_agent.py` · `tests/integration_tests/test_orchestrator_skill_routing.py` · `PROJECT_OVERVIEW.md` · `.cursor/skills/binary-analysis-prompt-optimizer/{SKILL.md,references/build-contracts.md,references/refactoring-playbook.md}`.

**Motivation.** 同日早些的整文重写（见下条）保留了 `<!-- system_prompt:document_mode_patch -->` 切分以维持 A.1 历史契约，但用户在审阅时指出：(a) §1 路由用「见下方文档模式 patch」单向指针、与二进制路径**不对称**；(b) base/patch 在运行时**只**为「让 patch 段免于 `str.format` 转义」一个目的服务，但代价是**两段独立测试 + 一处隐式契约 + 文末 `<!--…-->` 异味注释**——对 LLM 阅读体验是**额外**结构噪声；(c) `DOCUMENT_MODE_PROMPT_PATCH` / `FULL_BINARY_ANALYST_SYSTEM_PROMPT` 两个常量**只**在 `agent.py` 单点拼接处使用，对 `BINARY_ANALYST_SYSTEM_PROMPT` 是**冗余**接口面。Mode 3 重构：单源化 + 对称化 + 消除「补丁味」。

**Changes.**

- **`agent.md`：** 删除 `<!-- system_prompt:document_mode_patch -->` 切分行；将文档模式从尾部 patch 提升为正文 §5（标题 `## 5. 文档模式（ADR-DOC-10）`），与 §1–§4 同走一次 `str.format`。§1 路由改为对称二选一：「文档路径 → 文档编排器 + 遵守 §5」「二进制路径 → 二进制编排器」（不再「见下方 patch」式不对称指针）。§5 中所有大括号已 `{{ }}` 转义（`{{P0, P1, P2}}`、`{{ooxml_*, ole2_*, pdf, rtf, hta, onenote, encrypted_office}}`），与 §2 中的 `{{HIGH, MEDIUM, LOW}}` 风格一致。
- **`system_prompt.py`：** 删除 `_read_agent_md_parts`、`AGENT_MD_DOCUMENT_PATCH_MARKER`、`DOCUMENT_MODE_PROMPT_PATCH`、`FULL_BINARY_ANALYST_SYSTEM_PROMPT` 共 4 个符号；改为 `_PROMPT_TEMPLATE = _AGENT_MD_PATH.read_text(...).rstrip("\n")` 整文一次 `format(...)`。`__all__` 减少 3 项；模块 docstring 更新说明此次架构变更与 §5 内联约定。
- **`agent.py`：** `enhanced_system_prompt = FULL_BINARY_ANALYST_SYSTEM_PROMPT` → `BINARY_ANALYST_SYSTEM_PROMPT`；`from binary_analysis.prompts.system_prompt import` 与 `__all__` 中移除两个已删常量。
- **测试侧：** `test_agent_md_template_matches_frozen_prompt` 改为整文 `format(...)` 比对（不再 `split(marker, 1)`）。`TestDocumentModePromptPatch` (7) → `TestDocumentModeSection` (6)：所有断言对象由 `DOCUMENT_MODE_PROMPT_PATCH` 改为 `BINARY_ANALYST_SYSTEM_PROMPT`，并删除「patch 词数 < 150」一项（其上界由整篇 ≤ 4500 字符替代）。`TestSystemPromptPatchRouting` → `TestSystemPromptDocumentRouting`；`test_patch_is_under_200_tokens_approx`（≤ 800 char patch）→ `test_prompt_is_within_summary_layer_budget`（≤ 4500 char 整篇，约 1100 token）。`test_document_tier_p0_routes_to_document_orchestrator` 改为更精准的计数断言：文档编排器路径 ≥ 2 次（§1 + §5），二进制编排器路径 = 1 次（§1 二进制路由）。`TestSkillsMiddlewareInjection` 改为 `system_prompt == BINARY_ANALYST_SYSTEM_PROMPT` 等值断言（之前是 `startswith` + `in` 双重断言）。
- **优化器技能（`.cursor/skills/binary-analysis-prompt-optimizer/`）：** `references/build-contracts.md` §A.1 重写为「整文一次 `str.format` + 五占位 + 大括转义」单条契约（删切分契约，但保留迁移说明，便于读到旧 commit 的 reviewer 对得上）；§A.2 合并原「Base 段 / Patch 段」两组冻词为「§1–§4 + §5 文档模式 + 整篇 ≤ 4500 字符」三组；§A.4 不再要求 CN 镜像保留 marker 行。`SKILL.md` 同步更新：范围 A 表格 / A.1–A.4 摘要 / 验证命令 / 审阅清单 / 常见失败表的相关行。`refactoring-playbook.md` R.2/R.3/R.4 中提及 marker 与「800 字 patch」的 5 处行措辞改为「§5 文档模式」与「整篇 ≤ 4500 字符」。
- **`PROJECT_OVERVIEW.md`：** 3 处 `DOCUMENT_MODE_PROMPT_PATCH` 引用改为 `BINARY_ANALYST_SYSTEM_PROMPT` / 「§5 文档模式」。

**Verification.**

- Smoke import：`BINARY_ANALYST_SYSTEM_PROMPT` 长度 **3854 字符**（4500 上限留 ~14% 余量；系合并后整篇，与重写前 base 2983 + patch 736 + 节标题/拼接合计基本持平）。
- `tests/unit_tests/test_agent.py::TestSystemPrompt` (10/10)、`::TestDocumentModeSection` (6/6)、`::TestSkillsMiddlewareInjection` (1/1)、`tests/integration_tests/test_orchestrator_skill_routing.py::TestSystemPromptDocumentRouting` (4/4)、`::TestAgentRoutingTrigger` (4/4) — **25/25 全绿**。
- 全工作区 ripgrep 扫描确认 `DOCUMENT_MODE_PROMPT_PATCH` / `AGENT_MD_DOCUMENT_PATCH_MARKER` / `FULL_BINARY_ANALYST_SYSTEM_PROMPT` 已无运行代码 / 测试 / 活跃文档引用（`specs/e2e02-documents/IMPL-{PROGRESS,PLAYBOOK}.md` 中的历史完成记录按惯例不追溯改）。

**Cross-checked invariants.**

- A.1：文中**仅**五占位 `{open_tag}` / `{close_tag}` / `{max_rounds}` / `{token_budget}` / `{threshold_pct}`；其余大括号已 `{{ }}` 转义；`str.format` 在 import 时不抛错。
- A.2：§1–§4 13 个冻词全部命中；§5 文档模式新增 6 个冻词（`文档模式` / `document_tier` / `P0` / `triage`|`disassembly` / `document_extract` + `pe`|`elf`|`mach-o` / `analysis_id` / 5 条编号项 / 精确 SKILL 路径 ≥ 2 次）全部命中。
- A.3：§1–§4 每节 ≤ 5–8 行；§5 仅 5 条短祈使句（首跳后硬约束）；细阶段表与降级表仍只在编排器技能中。
- A.4：`agent_cn.md` 仍缺失（自上一次重写以来），未引入新中译漂移；切分标记契约**已废**，未来恢复 CN 时不需要重新插入 marker。
- R.5 单源：每条文档模式硬约束在 `agent.md` 仅有一处正本（§5）；§1 文档路径条只承担**触发**（指向编排器与 §5），不复述 §5 的 5 条规则——避免补丁结构产生的「双向重复」异味。
- 无指针腐烂：`binary-analysis-e2e-orchestrator/SKILL.md` 与 `document-analysis-e2e-orchestrator/SKILL.md` 两条路径仍指向存在的目录；测试计数断言锁定二者出现次数（文档 ≥ 2、二进制 = 1）以防未来误改。

## 2026-04-25 — `agent.md` 整文重写（Scope A，模式 2/3）

**Scope:** `src/binary_analysis/prompts/agent.md`（仅 Scope A — 未触及任何 `SKILL.md` / `SKILL_cn.md` 正文）。

**Motivation.** 既有 `agent.md` 是多次「打补丁」演化出来的版本：`task` 委派禁令以**长解释段落**置于编号外、与编号 1 的 first-hop 路由混在「运行原则」一节（**单责违反**）；阶段 1 / 阶段 2 仍带有可被编排器 Stage Map 完整覆盖的细节（A.3 ≤5 行/FR 阈值已超）；预算护栏 / 失败降级 / 审计纪律分散为三节，**实质都是「宿主控制信号 + 运行时退化行为」同一类**；文档 patch #6（schema 白名单）属编排器层，且当前措辞**未直接表述** non-negotiables 中的「LLM 不直接写文档四桶」硬约束（**覆盖缺口**）。

**Changes.**

- 完全重写 base 段为四节单责结构（与重构剧本 R.3 落点决策树一致）：
  1. **§1 路由** — `file_identify` first-hop + 二编排器互斥；指针指向编排器与文档 patch。
  2. **§2 不可违背约束** — 7 条短祈使句，新增「LLM 不直接写文档四桶」明确条目（补 non-negotiables 覆盖缺口）；`task` 委派禁令从长段落压为一行。
  3. **§3 三阶段** — 阶段 1 / 阶段 2 各 1 行，指向编排器 Stage Map；阶段 3 保留 prompt-only 契约（`behavior_chain` 整合、自洽性 + `evidence_refs` 交叉核对、`scoring` → `decision_gate` → `report_gen` 收尾）。
  4. **§4 预算 / 降级 / 审计** — 三段合并为统一的「宿主控制信号」表述（`<budget-warning>` / `<llm-degraded>`），五个占位符（`{open_tag}` / `{close_tag}` / `{max_rounds}` / `{token_budget}` / `{threshold_pct}`）落在此节。
- Patch 段 6 项 → 5 项；旧 #6（schema 枚举白名单）合并到新 #4（文档四桶 LLM 写入归属），同时保留所有测试要求子串（`document_tier`、`P0`、`triage`/`disassembly`、`PE/ELF/Mach-O`、`analysis_id`、精确 SKILL 路径、5 个编号点）。
- 范围内仅 `agent.md`：`agent_cn.md` 当前已删除，本次按 A.4「仅在显式要求时同步」未恢复；编排器与所有运行时技能正文均**未**改动；`MIN_SKILL_COUNT` / `ARCHIVED_SKILL_DIRS` / `WORKFLOW_SKILLS` / `GAP_SKILLS` 等测试侧常数**无需**更新。

**Verification.**

- Smoke import：`FULL_BINARY_ANALYST_SYSTEM_PROMPT` 长度 3721；`BINARY_ANALYST_SYSTEM_PROMPT` 长度 2983；`DOCUMENT_MODE_PROMPT_PATCH` 736 字 / 86 词（≤ 800 字硬顶 + < 150 词代理上限）。
- A.2 冻词 grep：base 段 13 个 + patch 段 5 个全部命中（`快速扫描` / `深入分析` / `综合研判` / `evidence_chain` / `raw sample` + `sample.bin` / `evidence_refs` / `HIGH` / `MEDIUM` / `LOW` / `gap_note` / `behavior_chain` / `自洽` / `降级` / `<untrusted_sample_content>` / `scoring` / `权威` / `token_budget` 占位 → `50000`；patch 中 `document_tier` / `P0` / `triage` / `analysis_id` / 精确 SKILL 路径）。
- `tests/unit_tests/test_agent.py::TestSystemPrompt` (10/10)、`TestDocumentModePromptPatch` (7/7)、`tests/integration_tests/test_orchestrator_skill_routing.py::TestSystemPromptPatchRouting` (4/4) — 全部绿。
- `TestDocumentSkillFile::test_skill_cn_file_exists` 与 `TestBinaryOrchestratorGuard::test_binary_skill_cn_also_has_guard` 仍失败 — 经 `git stash` 双向核对属**预先存在**（两个 `SKILL_cn.md` 文件本就缺失，属范围 B 的中文镜像，不在本次范围 A 任务内）。

**Cross-checked invariants.**

- A.1：切分标记 `<!-- system_prompt:document_mode_patch -->` 唯一一次；base 段五个 `{...}` 占位、其它大括号（`{{P0,P1,P2}}`、`{{HIGH, MEDIUM, LOW}}`）已转义；`_read_agent_md_parts` 与 `str.format` 在 import 时**未**抛错。
- A.3：每节正文 ≤ 5–8 行，每条不可违背一行；细 FR 阶段表全部留在编排器。
- A.4：未触动 `agent_cn.md`（当前缺失状态保持），不引入新中译漂移。
- R.5 单源：`task` 委派禁令、零执行字节、不可信边界、`scoring` 权威、文档四桶 LLM 写入禁令各**只有一处**正本（在 `agent.md` §2）；编排器中**保持**复述、未新增重复。
- 无指针腐烂：仍引用 `binary-analysis-e2e-orchestrator/SKILL.md` 与 `document-analysis-e2e-orchestrator/SKILL.md` 两个仍存在的目录；patch 不含 `binary-analysis-e2e-orchestrator`（互斥要求 — `test_document_tier_p0_routes_to_document_orchestrator` 通过）。

## 2026-04-25 — E2E 编排器 `SKILL.md` 与 `SKILL_cn` 中文化（Proto-01/02）

**Scope:** `document-analysis-e2e-orchestrator/{SKILL,SKILL_cn}.md` · `binary-analysis-e2e-orchestrator/{SKILL,SKILL_cn}.md` · `tests/integration_tests/test_orchestrator_skill_routing.py`.

**Summary.** 运行时主表面 `SKILL.md` 与技能镜像 `SKILL_cn.md` 对齐为**中文**正文；文档编排器补全了 Schema 正/反例块；二进制编排器标题改为中文、FR-17 补全与 `binary-analysis` 英文 `SKILL` 对等的**完成信号**与 ADR-07 两阶段硬约束。集成测试改为可识别 `## 何时使用` 等中文章节标题，并继续校验互斥/降级/Proto 等不变量。

## 2026-04-25 — `agent.md` / `agent_cn.md` thinned; per-FR detail pushed to orchestrator

**Batch:** prompt-surface optimization · **Scope:**
`prompts/{agent,agent_cn}.md` (Scope A only — no skill bodies modified).

**Motivation.** The system prompt duplicated content the binary
orchestrator already owns: the host-vs-sandbox I/O block (already in
`binary-analysis-e2e-orchestrator` Stage FR-15), the Phase 1 file-identify
and FR-02 heuristic triage detail (already in FR-01 / FR-02 + the "Recommended path by
triage level" subtable), the Phase 2 FR-07 priority-queue gate (already
in Stage FR-07 + `ghidra-priority-queue-workflow`), the FR-02 AC-8
strategic-skip pointer (a pure dead pointer to the orchestrator FR-07
downgrade table), and the FR-17 two-phase order rule (already in Stage
FR-17 + `two-phase-behavior-chain-reconstruction`). Each duplicate
violated A.3 prompt boundary (per-FR mechanics in `agent.md`) and R.5
single-source-of-truth.

**Changes.**

- Compressed Operating Principle 2 (zero execution of sample bytes):
  removed the "Host vs sandbox I/O" sub-paragraph; kept the unique
  "`bash` is not a shell — `>` / `|` / `&&` do NOT create files" caveat
  inline; pushed the full host-path table to the orchestrator pointer in
  Principle 1.
- Compressed Phase 1 / Phase 2 into thin pointers to the orchestrator's
  Stage Map and downgrade tables. Phase 3 unchanged — it carries the
  cross-cutting LLM behaviour rules (`behavior_chain` integration,
  self-consistency / `自洽`, `scoring` → `decision_gate` → `report_gen`)
  whose A.2 frozen tokens are owned by `agent.md`.
- Re-stated Principle 1 to mention both orchestrators (binary primary;
  document handed off via the existing patch) and the host-vs-sandbox
  pointer once.
- Brought `agent_cn.md` into structural parity (R.5 EN/CN): same six
  principles, same three phases, same Budget Guard / Failure Degradation
  / Audit Discipline structure; patch unchanged.
- No change to `binary-analysis-e2e-orchestrator/SKILL{,_cn}.md` or
  `document-analysis-e2e-orchestrator/SKILL{,_cn}.md` — every migrated
  paragraph already had a single canonical home there. No skill set,
  `MIN_SKILL_COUNT`, `ARCHIVED_SKILL_DIRS`, `WORKFLOW_SKILLS`, or
  `GAP_SKILLS` constants needed updating.

**Verification.**

- Smoke import: `FULL_BINARY_ANALYST_SYSTEM_PROMPT` length 7683;
  `DOCUMENT_MODE_PROMPT_PATCH` length 714 (≤ 800 hard cap, A.3).
- A.2 frozen tokens grep: all 16 base-section tokens + 5 patch-section
  tokens present.
- `tests/unit_tests/test_agent.py::TestSystemPrompt` (10/10),
  `TestDocumentModePromptPatch` (7/7),
  `tests/integration_tests/test_orchestrator_skill_routing.py` (28/28)
  — all green.

**Cross-checked invariants.**

- A.1 single split marker, five `{...}` placeholders, all other braces
  escaped — confirmed by `_read_agent_md_parts` not raising at import.
- A.3 per-FR block ≤ 5 lines in `agent.md`: each Phase block is now 4–8
  lines; FR-specific mechanics live in the orchestrator only.
- Cross-cutting non-negotiables intact: `file_identify` first, binary /
  document orchestrators mutually exclusive, no `task` delegation, no
  raw sample bytes, fact / inference tagging, rule-engine verdict
  authority, `scoring` → `decision_gate` → `report_gen` order, LLM
  degradation = facts-only.

## 2026-04-25 — Document orchestrator schema rules compacted

**Batch:** prompt-surface optimization · **Scope:**
`document-analysis-e2e-orchestrator/{SKILL,SKILL_cn}.md`

**Motivation.** The document orchestrator duplicated the full
`indicator_types_v1_1.py` allowlist inline, creating a second schema source
to maintain. The runtime source of truth remains
`src/binary_analysis/schema/indicator_types_v1_1.py`.

**Changes.**

- Replaced the expanded document-bucket `indicator_type` whitelist with a
  short pointer to the schema constants plus the preserved
  `analysis_coverage` routing rule (`strings_iocs` / `llm_inferences` /
  inherited domain buckets only).
- Kept one valid parser-failure few-shot and converted the invalid anti-example
  to text so JSON-fence validation cannot mistake it for a schema example.
- Added the same compact rule to the Chinese mirror and updated its FR-09
  stage note to reference the local section.

## 2026-04-25 — Binary orchestrator FR-02 detail de-duplication

**Batch:** prompt-surface optimization · **Scope:**
`binary-analysis-e2e-orchestrator/{SKILL,SKILL_cn}.md` · **FR:** FR-02

**Motivation.** The FR-02 stage block duplicated the SPEC FR-02 AC-9
`packing_severity_hint` threshold formula and format-specific packer brand
lists. The SPEC and scoped structure skills are the better authority for
those details; the orchestrator should carry the routing contract and output
shape without mirroring every threshold.

**Changes.**

- Replaced the inline FR-02 AC-9 formula with a pointer to the current SPEC
  aggregation contract, while preserving the required `threshold-version`
  recording requirement for reproducibility.
- Replaced the PE / ELF / Mach-O brand-list expansion under
  `signals.section_name_hits` with a pointer to the scoped format skill
  selected earlier in the FR-02 block.
- Kept the FR-04 / FR-07 ELF routing split unchanged:
  `analyzing-elf-structure` remains the FR-04 structural skill, while
  `analyzing-linux-elf-malware` remains routed to FR-07.

## 2026-04-25 — ADR-15 v0.7: remove skill ownership tiers; all skills editable

**Batch:** policy · **Scope:** DESIGN + rules + tests + prompt-optimizer
skill · **ADR:** ADR-15 (v0.7 rewrite of §9.5.2 / §9.5.3 / §9.5.4)

**Motivation.** The v0.6-era split between "project-initiated" and
"vendor-in upstream" skills turned out to be more overhead than signal.
ADR-15 §9.5.3 forbade in-place edits to upstream bodies and forced every
local tweak through either the orchestrator or a mandatory CHANGELOG +
scope-limiter ceremony. For a project-scale flat directory of ~38 active
skills this friction outweighed the audit benefit. v0.7 collapses the
tier into a single class: any `SKILL.md` / `SKILL_cn.md` under
`skills/` is a freely editable project asset. CHANGELOG entries become
*recommended*, not *required*.

**Changes.**

- `specs/e2e01-backend/DESIGN.md`:
  - History table: added v0.7 row with full rationale.
  - ADR-15 "冲突与修改策略" table relaxed: "保持原样" / "无需同名覆盖" /
    "必须登记 CHANGELOG" wording replaced with neutral engineering
    guidance.
  - §9.5.2 merge-rule table: "两个被引用 skill 保持原样" → "默认不改，
    也可按需改".
  - §9.5.3 "原地修改 vendor-in skill 的红线" → fully replaced with
    "(v0.7 起无硬约束)" prose.
  - §9.5.4 upstream-sync strategy demoted from mandatory quarterly
    diff + CHANGELOG to optional engineering practice.
  - §9.5.1 mermaid node "CHANGELOG 登记源 commit 与修改摘要" →
    "（v0.7 起无权限限制；CHANGELOG 登记为推荐）".
  - §7 "Skills Directory" dependency row relabelled to
    "source-tree project-owned asset".
  - §9.3 heading "项目自写 skill" → "项目初创 skill"; §9.6 flat
    listing comment softened; ADR-15 decision +  consequences sections
    reworded accordingly.
- `.cursor/rules/50-binary-analysis.mdc`: line 19 "上游 vendor-in 的
  39 个 skill 不可修改" → "目录下所有 skill 统一视为项目自有资产，
  可自由编辑；推荐（非强制）在 CHANGELOG 记录".
- `.cursor/skills/binary-analysis-prompt-optimizer/SKILL.md` +
  `SKILL_cn.md`: B.1 "Skill Ownership Tiers" deleted; replaced with
  B.1 "Edit Permission (v0.7: uniform, no ownership tiers)". B.4
  "Vendor-in Discipline" replaced with B.4 "Upstream-sync Hygiene
  (optional)". Review checklist + failure→root-cause map updated.
- `tests/unit_tests/skills/test_gap_skills.py`: removed
  `TestElfStructureScopeLimiter::test_upstream_elf_skill_body_unmodified`;
  updated class + module docstring. The other four methods (FR-04 vs
  FR-07 orchestrator routing) are retained — the workflow split is
  unchanged, only the body-immutability assertion is gone.
- `skills/CHANGELOG.md` (this file): header reworded from "vendor-in
  audit trail … update this file on every (a)/(b)/(c)" to "optional
  audit log … writing a new entry is **recommended**".
- `skills/_archive/README.md`: opening line reframed — archive is a
  scoping decision, not a permission tier.
- `binary-analysis-e2e-orchestrator/{SKILL,SKILL_cn}.md`:
  Out-of-Main-Path Skills heading prose "upstream skills" /
  "vendored-in skill" → neutral "skills" wording.
- `binary-analysis-ioc-extraction-workflow/SKILL.md` and
  `binary-analysis-family-triage-workflow/SKILL.md`: stale
  `*(if vendor-in)*` conditionals removed (both referenced skills are
  in fact always present in the flat directory); pattern consistent
  with the 2026-04-22 "removed 6 stale (if vendor-in) annotations"
  batch.
- `analyzing-elf-structure/{SKILL,SKILL_cn}.md` and
  `analyzing-macho-structure/SKILL.md`: rationale prose reworded —
  scope-limiter is still a workflow contract, but the "upstream
  vendor-in" label no longer carries edit-permission weight.

**Not changed.**

- The flat single-directory layout (ADR-15 v0.5) itself.
- The FR-04 vs FR-07 orchestrator routing for ELF skills (the
  workflow split between `analyzing-elf-structure` and
  `analyzing-linux-elf-malware`).
- The list of active skills; `MIN_SKILL_COUNT` unchanged.
- Any skill body was touched in this batch only insofar as its
  prose described the former tier system. No behavioral / method /
  schema changes to any skill.

**Source commit SHA reference.** The initial vendor-in snapshot from
upstream `Anthropic-Cybersecurity-Skills` recorded in the 2026-04-19
entry below is still the reference starting point for anyone who
wants to do a manual upstream diff. It is no longer a "compliance
anchor" — just a convenience marker.

## 2026-04-23 — Orchestrator sync for SPEC FR-02 routing refactor + FR-05 auto-unpack (cross-FR)

**Batch:** C8 (follow-up) · **FR:** FR-02, FR-04, FR-05, FR-07 · **ADR:** ADR-04, ADR-11

### SPEC deltas (`specs/e2e01-backend/SPEC.md`)

- **FR-02 · Fast triage — recast as routing function.** Description now
  states FR-02 is a *routing function*, not a fact producer; AC-4 adds the
  `derived_from FR-04` contract (basic signals MUST reference FR-04 facts
  rather than re-parse). AC-1 explicitly branches the parser (pefile for
  PE, lief for ELF / Mach-O) to resolve the prior "effectively PE-only"
  gap. AC-5 / AC-6 / AC-7 are now **format-aware**: AC-5 emits
  `applicable:false` for ELF / Mach-O (no standard timestamp field);
  AC-6 carries separate brand lists per format (PE UPX/ASPack/Themida/
  VMProtect/Enigma/MPRESS vs. ELF single-`PT_LOAD` + `p_info` marker vs.
  Mach-O `__XHDR` + UPX magic); AC-7 picks the correct counter per
  format. **New AC-9** freezes the `packing_severity_hint` aggregator
  formula (`SEVERE = entropy≥7.2 AND (name_hits OR sparsity≥0.8)` etc.)
  so FR-07 proactive-skip is deterministic.
- **FR-04 · Structural parsing — no-duplication contract.** Description
  now names FR-04 as the authoritative producer of AC-1 / AC-2 / AC-3
  facts and states FR-02 MUST `derived_from` them instead of re-writing.
  No AC renumbering (backward-compatible with external references).
- **FR-05 · Entropy & packer — adds auto-unpack (AC-8 / AC-9).** New
  **AC-8** defines an automated-unpack attempt gated on a UPX-family
  whitelist (`unpack_rules.yaml`) AND FR-02
  `packing_severity_hint ≠ SEVERE`: `upx -t` → `upx -d` → SHA256 check;
  timeout default 30 s (IR-10); artifact path
  `/workspace/<analysis_id>/unpacked/<sha256>.bin`. Whitelist misses
  (Themida / VMProtect / Enigma / custom) skip straight to AC-7
  coverage-limit path. New **AC-9** fixes the
  `indicator_type="unpack_result"` schema
  (`status ∈ {success, failed, not_attempted, skipped_not_whitelisted}`,
  `original_sha256`, `unpacked_sha256`, `unpacked_path`, `tool`,
  `tool_version`, `reason`, `elapsed_ms`) — the single source of truth
  for FR-07 input selection and FR-02 AC-8 proactive-skip cancellation.
- **FR-07 · Decompilation — unpacked-artifact input.** AC-1 now requires
  FR-07 to inspect `packer` bucket for `unpack_result.status="success"`
  and switch input to `unpacked_path` when present; the scope widens
  from "PE" to "sample" to match FR-01 AC-3 (ELF / Mach-O routing).
  Dependency updated to `FR-04, FR-05` (was `FR-04` only) — the AC-8
  unpack-result is now a read dependency.

### Orchestrator changes (`skills/binary-analysis-e2e-orchestrator/SKILL.md`)

- **FR-02 section rewritten** to reflect the SPEC refactor:
  - Added a "Charter" preamble: routing function, `derived_from FR-04`
    contract, only non-redundant outputs are `recommended_strategy` and
    `packing_severity_hint`.
  - Format-aware main tools (PE → pefile primary / lief fallback;
    ELF / Mach-O → lief only).
  - Recommended skills split per format
    (`pe-structural-anomaly-checklist` / `analyzing-elf-structure` /
    `analyzing-macho-structure`) — all scope-limited to the three
    triage dimensions, with FR-04 re-consuming the full checklists.
  - `signals.timestamp_anomaly` / `signals.section_name_hits` /
    `signals.section_count_anomaly` / `signals.import_sparsity` each
    documented per-format.
  - `packing_severity_hint` aggregator formula inlined from SPEC AC-9.
  - Downgrade row generalised: "pefile / lief raises" → "parser raises
    (pefile for PE; lief for ELF / Mach-O)".
- **FR-05 section renamed** to "Entropy, packer detection & automated
  unpacking". Completion signal now requires the `unpack_result`
  Indicator (3 items vs. previous 2). Added an "Unpacking gate" block
  (whitelist + `packing_severity_hint ≠ SEVERE` + `upx -t` + timeout)
  and three new downgrade rows (`upx_unavailable`,
  `<packer_family>_not_whitelisted`, `upx_timeout`).
- **FR-07 section** gained an "Input selection" clause before Step 0:
  check `packer` bucket for `unpack_result.status="success"` → switch
  to `unpacked_path`; emit `decompile_input` fact; cancel FR-02 AC-8
  proactive-skip on this path. Proactive-skip cancellation list now
  has two entries (FR-05 `packer_none` rebuttal OR FR-05 auto-unpack
  success).
- **`binary-analysis-e2e-orchestrator/SKILL_cn.md` synced** to the same
  FR-02 / FR-05 / FR-07 semantics (Chinese prose parity with `SKILL.md`).

### Motivation

Audit of the FR-02 AC list showed 6 of 8 ACs overlap FR-04 / FR-05
signals, producing redundant facts and inflating token cost. The
refactor keeps FR-02's two architectural levers (`recommended_strategy`
routing + `packing_severity_hint` proactive-skip gate) while delegating
all basic signals to FR-04 via `derived_from`. In parallel, SPEC
FR-05 AC-7 had a dangling "reliable unpack path" concept with no
implementing AC — FR-05 AC-8 / AC-9 now formalise automated UPX-family
unpacking, reusing the already-vendored
`analyzing-packed-malware-with-upx-unpacker` skill. The FR-07 input
switch completes the loop: successfully unpacked samples now flow into
decompilation instead of being proactively skipped.

### Backward compatibility

- AC numbering preserved for FR-02 (AC-1…AC-8), FR-04, and FR-07 AC-1;
  only additions are FR-02 AC-9, FR-05 AC-8 / AC-9.
- The `triage` bucket schema is unchanged (same field names); only the
  provenance convention tightened (`derived_from` preferred over
  re-parse).
- Samples analysed on the prior pipeline still satisfy the new ACs
  (unpack-absent path is the documented default via
  `unpack_result.status="not_attempted"`).

---

## 2026-04-23 — Add `analyzing-linux-elf-malware-with-ghidra` (Gap-06, batch C11); FR-07 ELF scope-limiter removed

**Batch:** C11 · **Gap:** Gap-06 · **FR:** FR-07 · **ADR:** ADR-05, ADR-13, ADR-15

### New skill: `analyzing-linux-elf-malware-with-ghidra`

Added `skills/analyzing-linux-elf-malware-with-ghidra/SKILL.md`.

**Motivation.** The upstream vendored `analyzing-linux-elf-malware` covers a wide scope
(strace/ltrace, GDB, Ghidra, UPX, string IOC extraction) that spans FR-05/FR-06/FR-07.
At FR-07, the other language-specific Ghidra skills (`analyzing-golang-malware-with-ghidra`,
`reverse-engineering-dotnet-malware-with-dnspy`, `reverse-engineering-rust-malware`) are
tightly scoped to their respective FR-07 surfaces. ELF had no equivalent — only the broad
`analyzing-linux-elf-malware`, which required a workaround scope-limiter note in the
orchestrator. `analyzing-linux-elf-malware-with-ghidra` fills this gap in parity with the
other language-specific Ghidra skills.

**Coverage (FR-07 scope only):**

- Multi-architecture calling conventions and correct Ghidra Language ID selection
  (x86_64, ARM32, ARM64, MIPS32 LE/BE)
- PLT/GOT resolution in stripped and partially-corrupted ELF samples
- Statically-linked binary de-noising strategy (musl/uclibc function noise, priority queue seed)
- Direct Linux syscall annotation (`syscall`/`svc` instruction → syscall name comments)
- `.init_array` / `.fini_array` pre-main hook labeling
- Pre-analysis Python script (`pyelftools`-based metadata extraction + PLT relocation dump)
- Ghidra post-analysis script (`AnalyzeLinuxELF.py`: PLT label recovery, syscall annotation,
  `.init_array` tagging)

### Orchestrator changes (Proto-01)

- **`binary-analysis-e2e-orchestrator/SKILL.md` and `SKILL_cn.md` updated.**
  - **FR-07 recommended skills:** ELF entry replaced — `analyzing-linux-elf-malware`
    (with its multi-line scope caveat) → `analyzing-linux-elf-malware-with-ghidra`
    (clean single-line entry, parallel to Go/Rust/.NET entries).
  - **FR-04 scope-limiter note removed** (EN lines 157–163, CN lines 100–104). The note
    existed solely to warn agents not to use the broad `analyzing-linux-elf-malware` at FR-04.
    Now that FR-04 uses `analyzing-elf-structure` and FR-07 uses the new scoped Ghidra skill,
    the warning has no referent and was deleted.

---

## 2026-04-23 — Add `analyzing-elf-structure` (Gap-05, batch C10); FR-04 ELF scope-limiter

**Batch:** C10 · **Gap:** Gap-05 · **FR:** FR-04 · **IR:** IR-09 · **ADR:** ADR-05, ADR-13, ADR-15

### New skill: `analyzing-elf-structure`

Added `skills/analyzing-elf-structure/SKILL.md` (EN) and
`skills/analyzing-elf-structure/SKILL_cn.md` (CN).

**Motivation.** The upstream vendored `analyzing-linux-elf-malware` covers a
wide scope (dynamic tracing · strace / ltrace, GDB debugging, Ghidra
decompilation, UPX unpacking, string IOC extraction) that overlaps FR-05,
FR-06, and FR-07 surfaces. No scope-limited FR-04 structural-parsing skill
existed for ELF, leaving IR-09 ("ELF / Mach-O 结构解析深度必须与 PE 对等") and
FR-04 AC-16 partially unmet. `analyzing-elf-structure` fills this gap in exact
parity with Gap-01 (`analyzing-macho-structure`) and Gap-02
(`pe-structural-anomaly-checklist`).

**Coverage (7 workflow steps, scope: FR-04 only):**

1. ELF Header parse — `e_type`, `e_machine`, `e_entry`, stripped check.
2. Program Headers — `PT_LOAD` WX flags, `PT_GNU_STACK` / `PT_GNU_RELRO`
   presence, `PT_INTERP` (static-link detection).
3. Section Headers — catalogue, `SHF_WRITE | SHF_EXECINSTR` WX, stripped
   table, entropy seed for FR-05, nonstandard section names.
4. Dynamic Section — `DT_NEEDED` capability grouping, `DT_RPATH` /
   `DT_RUNPATH` library-hijack surface, `DT_BIND_NOW` + RELRO Full-RELRO
   check.
5. Entry-point placement — maps `e_entry` to owning `PT_LOAD` and section;
   emits `elf_entry_point_*` facts for FR-07 priority queue (IR-05 / ADR-06).
6. `.init_array` / `.fini_array` pre-main initialisers — pointer-slot count;
   emits `elf_init_array_entry` facts for FR-07 priority queue.
7. `readelf` cross-check (best-effort).

**Evidence-chain indicator tags introduced:**
`elf_header`, `elf_stripped`, `elf_shared_object_pie`, `elf_et_rel_fragment`,
`elf_wx_load_segment`, `elf_segment_size_mismatch`, `elf_no_pt_gnu_stack`,
`elf_executable_stack`, `elf_no_pt_gnu_relro`, `elf_missing_pt_interp`,
`elf_section_table_stripped`, `elf_section`, `elf_wx_section`,
`elf_section_size_mismatch`, `elf_nonstandard_section`,
`elf_section_high_entropy`, `elf_rpath_anomaly`, `elf_missing_bind_now`,
`elf_no_dynamic_section`, `elf_import_count`, `elf_entry_point_zero`,
`elf_entry_point_oob`, `elf_entry_point_wx_segment`,
`elf_entry_point_odd_section`, `elf_init_array_entry`.

### Orchestrator changes (Proto-01)

- **`binary-analysis-e2e-orchestrator/SKILL.md` and `SKILL_cn.md` updated.**
  - **FR-04 recommended skills:** `analyzing-linux-elf-malware` replaced by
    `analyzing-elf-structure` (Gap-05). A scope-limiter blockquote is added
    immediately after the recommended-skills list, explicitly forbidding
    `analyzing-linux-elf-malware` at FR-04 and explaining why (dynamic-tracing
    / Ghidra / UPX / strings surfaces belong to FR-05 / FR-06 / FR-07).
  - **FR-07 recommended skills:** `analyzing-linux-elf-malware` re-routed
    here with an inline annotation ("FR-07 scope: strace / ltrace methodology,
    Ghidra-for-Linux-ELF, Linux persistence patterns; re-routed from FR-04").

**ADR-15 §9.5.3 compliance:** the upstream vendored body of
`analyzing-linux-elf-malware/SKILL.md` was **not modified**. The re-routing is
achieved solely via the project-written orchestrator. No other upstream skill
body was touched.

## 2026-04-23 — FR-17 / FR-06 skill catalog de-duplication (audit fix)

**Batch:** maintenance · **Scope:** Proto-01 (FR-06, FR-17) + Gap-04 · **ADR:** ADR-07, ADR-11, ADR-15

Audit of `binary-analysis-e2e-orchestrator/SKILL.md` against its own
"read-wrapper-before-specialists" discipline (§"Reading Discipline")
revealed two stages — FR-17 and FR-06 — were flat-listing the
specialist / upstream skills already owned by their project wrappers,
giving the LLM no prioritisation signal and inviting unconditional
reads of 7 skills (FR-17) / 4 skills (FR-06) per session. Corrections:

- **FR-17 stage** now lists `two-phase-behavior-chain-reconstruction`
  as the *only* default-read skill. The six specialist skills
  (`detecting-process-injection-techniques`,
  `detecting-process-hollowing-technique`,
  `detecting-dll-sideloading-attacks`,
  `analyzing-malware-persistence-with-autoruns`,
  `detecting-fileless-malware-techniques`,
  `analyzing-network-covert-channels-in-malware`) are re-expressed as
  a "Phase 1 capability label → triggered specialist" table, mirroring
  FR-13's "family specialists loaded only when the workflow triggers
  them" pattern. The wrapper's Phase-2 delegation map remains the
  authoritative source; the orchestrator table is an index so the
  Agent can budget Phase-2 reads before entering the wrapper.
- **FR-17 stage table** adds two rows that were missing from the flat
  list but present in the wrapper's delegation map:
  `network_c2 → analyzing-command-and-control-communication` and
  `crypto+file_io_exfil → analyzing-ransomware-encryption-mechanisms`
  (the latter flagged as out-of-main-path consistent with its existing
  entry in the "Out-of-Main-Path Skills" catalogue).
- **FR-06 stage** now lists `binary-analysis-ioc-extraction-workflow`
  (Workflow-01) and `binary-analysis-sanitize-untrusted-strings`
  (Proto-03) as the two default-read skills. The two upstream
  specialists (`extracting-iocs-from-malware-samples`,
  `performing-malware-ioc-extraction`) are re-expressed as "loaded
  on-demand by the wrapper" — Workflow-01 already `Read`s them in its
  Step 1 only when the classifier branches fire.
- **`two-phase-behavior-chain-reconstruction/SKILL.md` delegation map**
  cleanup — removed two stale `*(if vendor-in)*` annotations on
  `detecting-process-hollowing-technique` and
  `detecting-dll-sideloading-attacks` (both vendored-in since
  2026-04-19; the 2026-04-22 entry below removed the same stale
  annotations from the orchestrator but missed the wrapper).

No upstream vendored skill bodies were modified. No skills were added
or removed. Pure orchestrator reshape + one-line cleanup in Gap-04
wrapper to close the "wrapper owns specialist routing" contract gap.

**Impact on prompts / specs / tests:** none.
`src/binary_analysis/prompts/agent*.md` do not reference the moved
skill names by name. `specs/e2e01-backend/DESIGN.md`,
`IMPL-PLAYBOOK.md`, `IMPL-PROGRESS.md`, and `PROJECT_OVERVIEW.md`
retain their existing design-time references to the specialist /
upstream skill names (they describe which skills exist, not which
skills the orchestrator Stage Map must flat-list). `tests/unit_tests/
skills/test_workflow_skills.py` is unaffected — its `WORKFLOW_SKILLS`
fixture only tracks the wrapper skill names, and its docstring
reference to the upstream FR-06 composition remains accurate.

## 2026-04-22 — FR-02 stage spec-alignment (audit fix)

**Batch:** maintenance · **Scope:** Proto-01 (FR-02, FR-04, FR-07) · **ADR:** ADR-11, ADR-15 · **Spec:** SPEC.md §FR-02 AC-1..AC-8

Audit of `binary-analysis-e2e-orchestrator/SKILL.md` against SPEC FR-02
revealed the "Fast triage" stage had collapsed to a signature-only recipe,
silently dropping AC-5 (timestamp anomaly), AC-6 (section-name
heuristics), AC-7 (section-count anomaly), and partially AC-1 / AC-3 /
AC-8. Corrections:

- **FR-02 main tools** re-ordered: `python_exec (pefile/lief)` promoted
  to primary (covers 4 of 5 AC-1 dimensions); signature scanning is not
  part of the baseline FR-02 route.
- **FR-02 time budget** now explicit (`seconds-level`, citing NFR-01)
  with a Do-not list (no FLOSS / Ghidra / `strings -a` at this stage)
  to prevent overruns.
- **FR-02 completion signal** expanded from a single `risk_level` fact
  into a structured signal set covering AC-1 / AC-3 / AC-5 / AC-6 /
  AC-7 / AC-8 — `risk_level`, `recommended_strategy`,
  `packing_severity_hint`, and six named `signals.*` fields. A
  non-empty `signals.section_name_hits` now MUST lift `risk_level` to
  ≥ `HIGH` per AC-6.
- **FR-02 downgrade** rewritten: heuristic parser / entropy failures are
  logged as coverage gaps, but FR-02 keeps producing `risk_level` from
  remaining heuristic signals. Only total heuristic failure (no parser
  signal and no entropy signal) falls through to FR-04/05/06.
- **FR-02 anti-pattern** added: "no signature match ⇒ `risk_level=LOW`"
  is now explicitly flagged as incorrect — optional signature absence is
  not a verdict.
- **FR-07 proactive-skip trigger (AC-8)** re-anchored to FR-02: the
  skip now reads `risk_level="CRITICAL" AND packing_severity_hint="SEVERE"`
  (both from FR-02's own fact) instead of requiring the `packer` bucket
  (FR-05 output). FR-05 runs in parallel as confirmation — a later
  `packer_none` in the `packer` bucket cancels the skip and re-invokes
  FR-07. This aligns with SPEC AC-8's wording ("FR-02 给出 CRITICAL 等级
  且推断为严重加壳").
- **FR-04 stage** gained a "Do not re-detect" bullet telling the Agent
  to reference FR-02's timestamp / section-name / section-count facts
  via `derived_from` instead of recomputing them, avoiding double-work
  on the same `pe-structural-anomaly-checklist` dimensions.

No upstream vendored skill bodies were modified. Pure orchestrator
reshape to close the SPEC-vs-skill gap.

## 2026-04-22 — Orchestrator skill catalog sync & cleanup (maintenance)

**Batch:** maintenance · **Scope:** Proto-01 + System Prompt · **ADR:** ADR-11, ADR-14, ADR-15

Audit-driven cleanup of `binary-analysis-e2e-orchestrator/SKILL.md` after
the 2026-04-21 vendor-in batch and archive pass. No new skills were added
or removed; all changes are editorial or structural, and no upstream
vendored skill bodies were touched. Paired with prompt dedup in
`src/binary_analysis/prompts/agent.md` and `agent_cn.md`.

**Factual fixes (frontmatter + catalog):**

- `description` now lists the 12 E2E-01 FRs explicitly (FR-01, FR-02,
  FR-04-FR-09, FR-13-FR-15, FR-17) instead of the misleading "FR-01 to
  FR-15" range.
- `metadata.fr` widened from `FR-08, FR-09` to the full 12-FR set;
  `metadata.role: orchestrator` and `metadata.version: 1.0.0` added so
  future versions can be detected by the skill catalog.
- `stability` normalised from `stable-frontmatter, draft-prose` to
  `stable`, matching the other 5 project-written protocol/workflow
  skills.
- Removed 6 stale `*(if vendor-in)*` annotations — the skills they
  guarded (`performing-malware-ioc-extraction`,
  `detecting-process-hollowing-technique`,
  `detecting-dll-sideloading-attacks`,
  `analyzing-malware-family-relationships-with-malpedia`,
  `conducting-malware-incident-response`,
  `building-automated-malware-submission-pipeline`) have been present
  since the 2026-04-19 vendor-in.

**Structural refinements:**

- Stage Map gained a "Parallelisation contract" subsection making
  explicit which stages may batch in a single LLM round (FR-04 / FR-05 /
  FR-06) vs. which remain strictly sequential, aligned with the SPEC
  dependency graph.
- FR-02 triage-level table reworded the `HIGH` row to "Expand FR-05
  budget and gate FR-07 on a non-packed verdict" (previous "Prioritise
  FR-05 before FR-07" was tautological against the default order).
- FR-07 downgrade bullets converted to a 3-column decision table
  (trigger / mode / `data.reason`) that keeps `decompiler_unavailable`
  and `fr02_ac8_strategic_skip` as the two authoritative
  `analysis_coverage` reason codes.
- FR-08 stage description de-recursed — it no longer reads "Main tool:
  the Agent LLM itself" and now declares the stage *is* the current LLM
  loop, deferring round sequencing to `prompts/agent.md`.
- Every stage (FR-01, FR-02, FR-04-FR-09, FR-13-FR-15, FR-17) gained a
  "Completion signal" bullet so the Agent has an explicit
  evidence-chain shape to check before advancing.
- FR-09 stage followed by a note clarifying that the `audit_gaps`
  bucket is populated by the Python audit layer, not by any FR skill.

**Maintainability additions:**

- New "Out-of-Main-Path Skills" section catalogues vendored-in skills
  that are not wired into the main Stage Map
  (`reverse-engineering-ransomware-encryption-routine`,
  `analyzing-bootkit-and-rootkit-samples`,
  `analyzing-cobaltstrike-malleable-c2-profiles`,
  `analyzing-command-and-control-communication`) and the gate
  conditions that trigger them via `family-triage-workflow` or
  `two-phase-behavior-chain-reconstruction`.
- Token Budget subsection annotated that the 55 / 20 / 10 / 15 split is
  editorial until IMPL-GUIDE formalises it; only NFR-05's 50,000-token
  ceiling is load-bearing.
- "Reading Discipline" session-start rule scoped to messages that
  reference a binary sample or carry analysis-intent keywords, to
  avoid burning detail-layer budget on pure architecture queries.

**Prompt dedup (single source of truth for FR-02 AC-8):**

`prompts/agent.md` and `prompts/agent_cn.md` no longer re-encode the
full FR-02 AC-8 strategic-skip trigger conditions. They now reference
the orchestrator's "Stage FR-07 downgrade table" as the authoritative
definition and retain only the mandatory `analysis_coverage` indicator
instruction. This removes the divergence risk flagged in the audit.

## 2026-04-21 — Archive 17 skills under `skills/_archive/` (E2E-01 v1)

**Batch:** maintenance · **ADR:** ADR-14, ADR-15 · **NFR:** NFR-05

Moved seventeen upstream vendored skills from the flat `skills/` root into
`skills/_archive/<name>/` so `SkillsMiddleware` (single-level directory scan)
no longer injects their metadata into the system prompt. Assets are retained
for a future v2 scope expansion; see `_archive/README.md` for restore
instructions.

**Archived directories:** `analyzing-android-malware-with-apktool`,
`analyzing-heap-spray-exploitation`, `analyzing-macro-malware-in-office-documents`,
`analyzing-malicious-pdf-with-peepdf`, `analyzing-malware-behavior-with-cuckoo-sandbox`,
`analyzing-memory-dumps-with-volatility`, `analyzing-network-traffic-of-malware`,
`analyzing-pdf-malware-with-pdfid`, `analyzing-supply-chain-malware-artifacts`,
`deobfuscating-javascript-malware`, `deobfuscating-powershell-obfuscated-malware`,
`detecting-rootkit-activity`, `performing-automated-malware-analysis-with-cape`,
`performing-dynamic-analysis-with-any-run`, `performing-firmware-malware-analysis`,
`performing-memory-forensics-with-volatility3-plugins`,
`reverse-engineering-android-malware-with-jadx`.

No `SKILL.md` content was edited inside those trees — `git mv` only.

## Format conventions

- **Dates** are ISO-8601 (`YYYY-MM-DD`) in the project's local timezone.
- **Commit SHAs** are full 40-character Git hashes so future `git show` works
  without ambiguity.
- **Skill names** match the directory name (== YAML `name`) of the SKILL.md.
- **"Source"** for vendored-in skills is the upstream
  `Anthropic-Cybersecurity-Skills` repository.

## 2026-04-20 — Add three project protocol skills (C8)

**Batch:** C8 · **FR:** FR-06, FR-08, FR-09 · **ADR:** ADR-11, ADR-14, ADR-15

Added the three protocol skills required by ADR-15 §9.3:

- `binary-analysis-e2e-orchestrator` (Proto-01) — top-level orchestrator;
  LLM-first-read; maps E2E-01 stages FR-01 → FR-15 to recommended subskills,
  evidence-chain buckets, and downgrade paths.
- `binary-analysis-evidence-chain-protocol` (Proto-02) — Indicator schema +
  bucket routing + fact-vs-inference contract.
- `binary-analysis-sanitize-untrusted-strings` (Proto-03) — Prompt-injection
  defence protocol; declares the `<untrusted_sample_content>` tag contract
  consumed by FR-06 / FR-08.

No upstream skills were modified. No upstream skills were added or removed.
The 39 `subdomain: malware-analysis` skills vendored-in on 2026-04-19 remain
unchanged.

## 2026-04-19 — Initial vendor-in of upstream malware-analysis skills

**Batch:** pre-C8 (DESIGN v0.5 snapshot) · **ADR:** ADR-11, ADR-15

- **Upstream repository:** `Anthropic-Cybersecurity-Skills`
- **Upstream HEAD at time of import:**
  `888bbe4c6e4e54e026874cbf6072e84f0cfd3b7a` (2026-04-18,
  `"Delete star.yml"`).
- **Local import commit:**
  `a0fa5a54f83dc1c0a0ab528b79c3e5c53e494429`
  (`docs(examples): e2e01-backend design v0.5 and vendor-in binary analysis
  skills`).
- **Scope:** all 39 skill subdirectories whose upstream frontmatter declared
  `subdomain: malware-analysis`. No filtering or editing — each directory
  was copied verbatim, including `LICENSE`, `references/`, and `scripts/`
  subdirectories where present.
- **Sync policy (ADR-15 §9.5.4):** v1 does **not** auto-sync. Quarterly
  manual review — diff upstream HEAD against our local tree, cherry-pick
  relevant updates as ordinary Git commits, log each update as a new
  section in this file.
- **Editing policy:** per ADR-15 §9.5.3 we prefer wrapping an upstream skill
  in a project-written `*-workflow` skill over modifying the upstream copy
  in place. In-place edits are the last resort and MUST be logged here
  with the original upstream commit SHA and a diff summary.

### Imported skill directories (39)

```text
analyzing-android-malware-with-apktool
analyzing-bootkit-and-rootkit-samples
analyzing-cobalt-strike-beacon-configuration
analyzing-cobaltstrike-malleable-c2-profiles
analyzing-command-and-control-communication
analyzing-golang-malware-with-ghidra
analyzing-heap-spray-exploitation
analyzing-linux-elf-malware
analyzing-macro-malware-in-office-documents
analyzing-malicious-pdf-with-peepdf
analyzing-malware-behavior-with-cuckoo-sandbox
analyzing-malware-persistence-with-autoruns
analyzing-malware-sandbox-evasion-techniques
analyzing-memory-dumps-with-volatility
analyzing-network-covert-channels-in-malware
analyzing-network-traffic-of-malware
analyzing-packed-malware-with-upx-unpacker
analyzing-pdf-malware-with-pdfid
analyzing-ransomware-encryption-mechanisms
analyzing-supply-chain-malware-artifacts
deobfuscating-javascript-malware
deobfuscating-powershell-obfuscated-malware
detecting-fileless-malware-techniques
detecting-process-injection-techniques
detecting-rootkit-activity
extracting-config-from-agent-tesla-rat
extracting-iocs-from-malware-samples
performing-automated-malware-analysis-with-cape
performing-dynamic-analysis-with-any-run
performing-firmware-malware-analysis
performing-malware-triage-with-yara
performing-memory-forensics-with-volatility3-plugins
performing-static-malware-analysis-with-pe-studio
performing-yara-rule-development-for-detection
reverse-engineering-android-malware-with-jadx
reverse-engineering-dotnet-malware-with-dnspy
reverse-engineering-malware-with-ghidra
reverse-engineering-ransomware-encryption-routine
reverse-engineering-rust-malware
```

## Future sync checklist (template)

When performing a quarterly upstream re-sync, add a new section at the top
of the file with:

1. **Upstream HEAD** at the moment of review (full SHA + ISO date + subject
   line).
2. **Previous local HEAD** the re-sync started from.
3. **Skills added / removed / modified** — one bullet each with a one-line
   rationale.
4. **Impact on project-written skills** — which wrappers (if any) must
   follow up.
5. **Regression status** — E2E-01 regression suite + prompt-injection suite
   re-run pass/fail summary.
