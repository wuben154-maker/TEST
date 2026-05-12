# Process injection reference (analyst aids)

This file holds **API sequence anchors**, optional **sandbox-only** command
ideas, and **external telemetry** context. It is not an agent tool list.
Runtime tools follow `contracts.md` (this audit run:
`file_identify`, `evidence_chain`, `scoring`, `decision_gate`, `report_gen`,
`bash`, `python_exec`, `file_read`, `sandbox_session`, and `document_extract` on
the document path only).

## Static import / API clusters (map to `imports` / `disassembly` facts)

| Technique family | Typical API / symbol sequence |
|------------------|--------------------------------|
| Classic DLL / remote thread | OpenProcess -> VirtualAllocEx -> WriteProcessMemory -> CreateRemoteThread or NtCreateThreadEx |
| Process hollowing (overview) | CreateProcess (CREATE_SUSPENDED) -> NtUnmapViewOfSection -> VirtualAllocEx -> WriteProcessMemory -> SetThreadContext -> ResumeThread |
| APC injection | OpenProcess / OpenThread -> VirtualAllocEx -> WriteProcessMemory -> QueueUserAPC / NtQueueApcThread |
| Thread hijack | SuspendThread -> GetThreadContext -> SetThreadContext -> ResumeThread (with remote allocation) |
| Section mapping | NtCreateSection -> NtMapViewOfSection (or MapViewOfFile) with suspicious protections |
| Reflective / manual map | VirtualAlloc / VirtualAllocEx + memcpy-style writes + execution without LoadLibrary in same story |

Detail for **hollowing-specific** static checks lives primarily in
`detecting-process-hollowing-technique`; use that skill when suspended-process
and unmap/context patterns dominate.

## Sysmon-style Event IDs (external telemetry context only)

Use this table only when analysts **already** have sanitised, bounded summaries
in the evidence chain. Do **not** treat host log collection as an agent step.

| Event ID | Name | Relevance |
|----------|------|-----------|
| 1 | ProcessCreate | Suspicious parent-child or CREATE_SUSPENDED creates |
| 8 | CreateRemoteThread | Classic cross-process thread start |
| 10 | ProcessAccess | PROCESS_VM_WRITE, PROCESS_CREATE_THREAD combinations |
| 25 | ProcessTampering | Image tampering / hollowing hints |

## Volatility-style commands (sandbox analysts only)

If a memory image is already inside `/workspace/<analysis_id>/` and policy allows,
bounded `bash` inside `sandbox_session` may run analyst frameworks. Do **not**
treat these as mandatory agent steps and do **not** stream dump contents into
the LLM.

```bash
# Example: list suspicious executable regions (bounded output)
vol3 -f /workspace/<analysis_id>/memory.dmp windows.malfind
vol3 -f /workspace/<analysis_id>/memory.dmp windows.hollowfind
vol3 -f /workspace/<analysis_id>/memory.dmp windows.vadinfo --pid <pid>
```

Replace paths and PIDs with values valid **inside** the sandbox workspace.

## MITRE ATT&CK T1055 sub-techniques (mapping aid)

| ID | Label |
|----|-------|
| T1055.001 | Dynamic-link Library Injection |
| T1055.002 | Portable Executable Injection |
| T1055.003 | Thread Execution Hijacking |
| T1055.004 | Asynchronous Procedure Call |
| T1055.012 | Process Hollowing |
| T1055.013 | Process Doppelganging |

Map sub-techniques only when static facts in `evidence_refs` justify the label.
