# API Reference: Detecting Process Hollowing Technique

## Runtime scope (`binary_analysis`)

This skill supports **static** mapping of the sequences below to **`imports`**, **`strings_iocs`**, and **`disassembly`** facts in the project evidence chain. The tables are **analyst** aids for pattern recognition; the agent **must** follow the tool boundary in the active run’s `audit-runs/<run_id>/contracts.md` (5+3+1 + `document_extract` on the document path only). The sections **Sysmon** / **Splunk** / **CLI** below are **not** project agent tools, **unless** a command is explicitly run with bounded output **inside** `sandbox_session` per orchestrator policy.

## Process Hollowing API Sequence

| Step | API Call | Purpose |
|------|----------|---------|
| 1 | CreateProcess(SUSPENDED) | Create target suspended |
| 2 | NtUnmapViewOfSection | Unmap legitimate code |
| 3 | VirtualAllocEx | Allocate for payload |
| 4 | WriteProcessMemory | Write malicious code |
| 5 | SetThreadContext | Redirect execution |
| 6 | ResumeThread | Execute payload |

## Commonly Hollowed Processes

| Process | Reason |
|---------|--------|
| svchost.exe | Trusted, always running |
| explorer.exe | UI process |
| notepad.exe | Simple, rarely monitored |
| dllhost.exe | COM surrogate |

## Sysmon Detection Events

| Event ID | Detection |
|----------|-----------|
| 1 | Suspicious parent-child |
| 8 | CreateRemoteThread into hollowed target |
| 10 | Process Access with PROCESS_ALL_ACCESS |

## Splunk SPL

```spl
index=sysmon EventCode=10
| where TargetImage IN ("*\svchost.exe","*\explorer.exe")
| where GrantedAccess IN ("0x1FFFFF","0x1F3FFF")
| table _time SourceImage TargetImage GrantedAccess Computer
```

## CLI usage (illustrative / non-agent)

The script below is a **local** helper shipped with this skill directory for **offline** experiments; it is **not** part of the `binary_analysis` runtime tool list. The agent does not invoke it unless a future product explicitly wires it through **sandboxed** execution per orchestrator policy.

```bash
python agent.py --sysmon-log Sysmon.evtx
```
