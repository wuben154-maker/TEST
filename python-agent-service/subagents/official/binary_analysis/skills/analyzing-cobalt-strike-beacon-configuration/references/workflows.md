# Cobalt Strike Beacon Analysis Workflows

Reference flows for **FR-13** beacon-config work. Each step assumes artefacts
already live under `/workspace/<analysis_id>/` and that
`binary-analysis-evidence-chain-protocol` / Proto-03 apply before any
sample-derived text is re-embedded in prompts.

## Workflow 1: PE file configuration extraction

```
[Suspicious PE] --> [file_identify / packer facts] --> [unpack_with_upx if scheduled]
        --> [strings_iocs + binary_view + disasm facts] --> [Sandbox TLV / XOR parse]
                    --> [llm_inferences: family_config + evidence_refs]
```

### Steps

1. **Triage** — Use existing `triage` / YARA-backed facts from FR-02; do not
   claim a new YARA engine on the host.
2. **Unpacking** — If `packer` indicates UPX and the orchestrator schedules
   **`unpack_with_upx`**, consume that output; otherwise record
   **`analysis_coverage`** and stop short of full TLV claims.
3. **Section / string surface** — Rely on `headers`, `sections`, and
   `strings_iocs` already sanitised upstream.
4. **XOR / TLV** — Apply keys **`0x2e`** / **`0x69`** heuristics inside the
   sandbox helper path (see `api-reference.md`); partial parses downgrade
   explicitly.
5. **IOC extraction** — Promote domains, URIs, pipes, watermark **numbers**
   as facts when tool-backed; keep actor attribution as **`inference`**.

## Workflow 2: Memory or injected-region extraction

```
[Child dump under workspace] --> [string_extract / binary_view on region files]
        --> [signature scan in sandbox only] --> [TLV parse same as Workflow 1]
```

### Steps

1. **Ingest** — Analysts stage extracted regions into the workspace; the
   agent never reads raw memory from the analyst workstation directly.
2. **Scan** — Use sandbox `python_exec` for malfind-style helpers **only**
   when packaged in the worker image; otherwise cite static facts only.
3. **Parse** — Reuse TLV tables in `standards.md` / this directory.

## Workflow 3: Watermark attribution

```
[Multiple beacon facts] --> [numeric watermark fact rows] --> [inference: cluster / license hypothesis]
```

### Steps

1. Collect watermark integers from decoded configs or tool outputs.
2. Group by value in **`llm_inferences`** with **`evidence_refs`** to each
   supporting fact id.
3. External watermark databases are **human reference** only unless a tool
   fact records a vendor mapping.

## Workflow 4: C2 traffic correlation (defensive hints)

```
[family_config inference] --> [human-readable signature sketches in report]
```

### Steps

1. Derive Suricata/Snort-style hints from **sanitised** URI / User-Agent facts.
2. Do not assert sensor deployment or PCAP collection as automated agent work.
