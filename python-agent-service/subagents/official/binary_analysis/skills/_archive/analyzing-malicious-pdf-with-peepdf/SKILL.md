---
name: analyzing-malicious-pdf-with-peepdf
description: Archived PDF peepdf workflow. Superseded by the active E2E-02 skill `analyzing-pdf-malware-with-pdfid`, which consolidates PDFiD, pdf-parser, and peepdf-style PDF malware analysis under document_extract.
domain: cybersecurity
subdomain: malware-analysis
tags:
- malware-analysis
- pdf
- peepdf
- archived
version: '1.0'
author: mahipal
license: Apache-2.0
archived: true
superseded_by: analyzing-pdf-malware-with-pdfid
---

# Archived: Analyzing Malicious PDF with peepdf

This upstream-style skill has been removed from active `SkillsMiddleware` discovery because E2E-02 uses one PDF workflow entry point:

- Active workflow: `analyzing-pdf-malware-with-pdfid`
- Parser owner: `document_extract`
- Orchestrator owner: `document-analysis-e2e-orchestrator`

Historical peepdf concepts that still matter, such as JavaScript extraction, stream/object reasoning, encoded payloads, shellcode hints, and suspicious object triage, are folded into the active PDF workflow. Do not restore this skill as a second active PDF entry unless the orchestrator and inventory tests are updated to intentionally support multiple PDF workflows.
