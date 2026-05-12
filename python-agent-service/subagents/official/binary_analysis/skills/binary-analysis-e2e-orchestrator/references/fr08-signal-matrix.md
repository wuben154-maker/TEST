# FR-08 Signal Matrix

This reference is owned by `binary-analysis-e2e-orchestrator`. Use it during Stage FR-08 after the evidence-chain snapshot is available and before loading family or behavior specialists. It maps deterministic facts to hypotheses, the specialist skills worth reading, and the `llm_inferences` indicators to append.

Do not read every specialist up front. Scan the matrix against existing `fact` indicators, load only specialists whose trigger fired, and cite every triggering fact through `evidence_refs`.

## Operating Rules

- Treat matrix matches as hypotheses, not facts. Write them to `llm_inferences` with `kind="inference"` and non-empty `evidence_refs`.
- Use `indicator_type="threat_class"` for broad behavior or class labels, `indicator_type="family_candidate"` only when a family or class-specific workflow supports attribution, and `indicator_type="gap_note"` when the signal is promising but coverage is missing.
- Keep `data.classes` compatible with scoring/report consumers when writing `threat_class`; use labels such as `Backdoor`, `RAT`, `Dropper`, `Ransomware`, `InfoStealer`, `Downloader`, or `Wiper`.
- If specialist output contradicts the trigger, append `self_consistency_downgrade` or lower the confidence rather than deleting earlier indicators.
- Sample-derived strings in `data.rationale`, URLs, paths, ransom-note names, mutexes, and domains must already be sanitized per `binary-analysis-sanitize-untrusted-strings`.

## Matrix

| Triggering facts | Hypothesis | Read specialist(s) | Append to `llm_inferences` |
|------------------|------------|--------------------|-----------------------------|
| `imports` contains `VirtualAllocEx` + `WriteProcessMemory` + `CreateRemoteThread`; optional `OpenProcess`, `NtCreateThreadEx`, RWX section, or FR-17 remote-thread node. | Process injection or remote thread loader. | `detecting-process-injection-techniques`; if hollowing APIs such as `CreateProcess` + `GetThreadContext` + `SetThreadContext` also appear, read `detecting-process-hollowing-technique`. | `threat_class` with `data.classes=["Dropper", "Backdoor"]` or `["RAT"]` when C2 facts also exist; `data.hypotheses=["process_injection"]`; confidence HIGH for the full API triad, MEDIUM when one API is missing but FR-17 confirms the chain. |
| `strings_iocs` contains a C2 URL, domain, IP, user-agent, or beacon path, and `imports` contains network APIs such as `InternetOpen`, `InternetConnect`, `HttpSendRequest`, `WinHttpSendRequest`, `connect`, `send`, or `recv`. | C2 channel or beacon capability. | `analyzing-command-and-control-communication`; read `analyzing-network-covert-channels-in-malware` only for DNS tunneling, ICMP, custom binary protocol, or covert-channel indicators. | `threat_class` with `data.classes=["Backdoor", "RAT"]`; `data.hypotheses=["c2_beacon"]`; include sanitized `data.protocol_hint`, `data.transport`, and `data.ioc_summary`. If family-specific C2 fingerprints emerge, defer family attribution to FR-13. |
| `imports` or `disassembly` contains crypto APIs/constants, `behavior_chain` or `disassembly` shows bulk file iteration over document/media/source extensions, and `strings_iocs` contains ransom-note filenames or extension rewrite markers. | Ransomware encryption workflow. | `analyzing-ransomware-encryption-mechanisms`; read `reverse-engineering-ransomware-encryption-routine` only when FR-07 exposes enough crypto routine detail to reason about key flow. | `threat_class` with `data.classes=["Ransomware"]`; `family_candidate` only when a specialist finds a family-like watermark or scheme; include `data.hypotheses=["ransomware_encryption"]`, sanitized note/path evidence, and confidence HIGH for all three signal groups. |
| `strings_iocs` contains credential-store paths, browser profile files, wallet paths, SMTP/FTP endpoints, or webhook URLs; `imports` contains file, registry, clipboard, screenshot, or network upload APIs. | Credential theft or exfiltration. | `binary-analysis-ioc-extraction-workflow`; if `.NET` or Agent Tesla-like facts appear, FR-13 may later read `extracting-config-from-agent-tesla-rat`. | `threat_class` with `data.classes=["InfoStealer"]`; `data.hypotheses=["credential_theft", "exfiltration"]`; cite both target-store facts and exfil/network facts. |
| `imports`, `strings_iocs`, or `behavior_chain` contains registry autorun paths, Startup folder writes, service creation, scheduled task commands, launch agents, or Mach-O/ELF persistence locations. | Persistence installation. | `analyzing-malware-persistence-with-autoruns`; pair with platform structural skill already loaded for PE/ELF/Mach-O context. | `threat_class` only when paired with another malicious capability; otherwise `gap_note` with `data.hypotheses=["persistence"]` and the exact missing evidence needed to raise confidence. |
| `imports` or `disassembly` contains anti-debug, VM, sandbox, timing, CPUID, or sleep-loop checks; `strings_iocs` includes sandbox process names, debugger names, or analysis-tool markers. | Sandbox evasion or analyst avoidance. | `analyzing-malware-sandbox-evasion-techniques`. | `threat_class` only when evasion supports a broader malicious hypothesis; otherwise `gap_note` or `self_consistency_downgrade` if evasion claims lack executable-path evidence. |
| `resources`, `sections`, or `behavior_chain` shows embedded PE/shellcode, high-entropy resource extraction, temp-file writes, or process creation; `strings_iocs` contains dropped filenames or LOLBin commands. | Dropper, loader, or staged payload delivery. | `pe-structural-anomaly-checklist`; if process injection follows, also read `detecting-process-injection-techniques`. | `threat_class` with `data.classes=["Dropper", "Downloader"]` when network retrieval exists, or `["Dropper"]` for embedded payloads; `data.hypotheses=["staged_payload"]`. |
| `imports` contains destructive file APIs, raw disk/volume access, service termination, backup deletion commands, or shadow-copy deletion strings without a ransom-note/extension-encryption pattern. | Wiper or destructive malware. | `conducting-malware-incident-response`; read ransomware specialists only if encryption and ransom-note signals also exist. | `threat_class` with `data.classes=["Wiper"]`; `data.hypotheses=["destructive_actions"]`; confidence depends on whether FR-17 confirms the destructive sequence. |

## Minimal Indicator Shapes

Use these shapes as templates; replace placeholders with actual fact IDs and sanitized summaries.

`threat_class`:

```json
{
  "source_fr": "FR-08",
  "indicator_type": "threat_class",
  "severity": "WARNING",
  "confidence": "HIGH",
  "kind": "inference",
  "evidence_refs": ["<fact-id-1>", "<fact-id-2>"],
  "data": {
    "classes": ["Backdoor", "RAT"],
    "hypotheses": ["process_injection", "c2_beacon"],
    "rationale": "Remote-thread injection API triad plus sanitized C2 URL and WinHTTP imports."
  }
}
```

`family_candidate`:

```json
{
  "source_fr": "FR-08",
  "indicator_type": "family_candidate",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "kind": "inference",
  "evidence_refs": ["<fact-id-1>", "<fact-id-2>", "<fact-id-3>"],
  "data": {
    "family": "generic-ransomware-like",
    "rationale": "Crypto API pair, document-extension traversal, and sanitized ransom-note filename converge on ransomware behavior.",
    "specialist_skill": "analyzing-ransomware-encryption-mechanisms"
  }
}
```

`gap_note`:

```json
{
  "source_fr": "FR-08",
  "indicator_type": "gap_note",
  "severity": "INFO",
  "confidence": "LOW",
  "kind": "inference",
  "evidence_refs": ["<fact-id-1>"],
  "data": {
    "hypotheses": ["persistence"],
    "missing_evidence": ["no process creation or write target confirming installation path"],
    "rationale": "Autorun path string is present, but no write or command execution fact supports actual persistence."
  }
}
```
