# Archived skills (E2E-01 v1 out of scope)

These directories are skills (originally brought in from upstream)
moved out of the `SkillsMiddleware` discovery path on purpose. Per
ADR-15 v0.7, active skills under `examples/binary_analysis/skills/`
are editable project assets without ownership tiers; archival here
is purely a scoping decision, not a permission layer.

`deepagents.middleware.skills._list_skills` only scans **immediate**
subdirectories of `examples/binary_analysis/skills/` for `SKILL.md`.
Nesting under `_archive/<skill-name>/SKILL.md` keeps the assets in-repo
but drops them from the progressive-disclosure catalog (smaller system
prompt skill summary layer).

## When to restore

Move a skill back to the parent `skills/` directory when E2E-01 scope
expands (e.g. dynamic sandbox analysis, Android, document malware,
memory forensics):

```bash
git mv examples/binary_analysis/skills/_archive/<skill-name> \
       examples/binary_analysis/skills/<skill-name>
```

Then bump `MIN_SKILL_COUNT` in
`tests/unit_tests/skills/test_skills_inventory.py` and record the move
in `skills/CHANGELOG.md`.

## E2E-02 restored document workflows (2026-04-25)

The document malware slice restored these skills to active discovery and rewrote
them as `document_extract`-driven workflows:

| Directory | Active role |
|-----------|-------------|
| `analyzing-macro-malware-in-office-documents` | Office active-content FR-08 workflow |
| `analyzing-pdf-malware-with-pdfid` | Consolidated PDF workflow for PDFiD / pdf-parser / peepdf-style evidence |

The old peepdf-specific PDF entry remains archived because the active PDF
workflow now owns that method surface.

## Current archive (2026-04-25)

| Directory | Rationale |
|-----------|-----------|
| `analyzing-android-malware-with-apktool` | Android — not FR-01 static triage |
| `analyzing-heap-spray-exploitation` | Exploit-focused — out of core pipeline |
| `analyzing-malicious-pdf-with-peepdf` | Superseded by active `analyzing-pdf-malware-with-pdfid` workflow |
| `analyzing-malware-behavior-with-cuckoo-sandbox` | Dynamic sandbox |
| `analyzing-memory-dumps-with-volatility` | Memory forensics |
| `analyzing-network-traffic-of-malware` | PCAP-centric — not static v1 |
| `analyzing-supply-chain-malware-artifacts` | Supply chain — not core E2E-01 |
| `deobfuscating-javascript-malware` | Script malware |
| `deobfuscating-powershell-obfuscated-malware` | Script malware |
| `detecting-rootkit-activity` | Host / memory oriented |
| `performing-automated-malware-analysis-with-cape` | Dynamic sandbox |
| `performing-dynamic-analysis-with-any-run` | Dynamic analysis |
| `performing-firmware-malware-analysis` | Firmware — out of scope |
| `performing-memory-forensics-with-volatility3-plugins` | Memory forensics |
| `reverse-engineering-android-malware-with-jadx` | Android |
