# API Reference: Agent Tesla RAT Configuration Extraction

Use this file to **map existing** `strings_iocs` and `disassembly` facts to
Agent Tesla–style exfil and settings. Any regex or Python that touches sample
bytes runs **only** in the analysis sandbox (for example `python_exec` /
`bash` under `/workspace/<analysis_id>/` after `SandboxSessionTool` upload), per
E2E-01 **zero raw bytes in host LLM context**. Do not use host-side `open()`
on the specimen path.

## Agent Tesla Overview
- **Type**: .NET RAT / Information Stealer
- **Exfiltration**: SMTP, FTP, Telegram, HTTP POST
- **Capabilities**: Keylogging, clipboard, screenshots, credential theft

## String Extraction

### Python Regex for ASCII Strings
`binary_data` must come from an allowlisted sandbox read of the workspace
object, not from the analyst host.

```python
re.finditer(rb'[\x20-\x7e]{6,}', binary_data)
```

### Wide Strings (UTF-16LE)
```python
re.finditer(rb'(?:[\x20-\x7e]\x00){6,}', binary_data)
```

## Configuration Indicators

### SMTP Exfiltration
| Field | Pattern |
|-------|---------|
| Server | `smtp.gmail.com`, `smtp.yandex.com` |
| Port | 587, 465, 25 |
| Email | `[\w.+-]+@[\w-]+\.[\w.]+` |
| Password | Base64 or XOR encoded |

### FTP Exfiltration
| Field | Pattern |
|-------|---------|
| Server | `ftp.\w+\.\w+` |
| URI | `ftp://user:pass@host/path` |

### Telegram Bot
| Field | Pattern |
|-------|---------|
| Bot Token | `\d{8,12}:[A-Za-z0-9_-]{35}` |
| Chat ID | `\d{9,13}` |
| API URL | `api.telegram.org/bot{token}/sendDocument` |

## .NET Decompilation

### dnSpy
```bash
# Human analyst: open sample in dnSpy. Runtime agent: use FR-07b exports and
# file_read on paginated decompiler text under the workspace policy.
# Navigate to namespace: AgentTesla / WebMonitor / etc.
# Look for hardcoded credentials in static fields
```

### ILSpy / dotPeek
Alternative .NET decompilers for config extraction (analyst or FR-07b
pipeline output — not separate agent tool names).

## YARA Rule

YARA is **out of band** to the 5+3+1 + `document_extract` tool surface unless
the deployment exposes it via an allowlisted sandbox command. Example
signature for human threat-intel or offline scanning:

```yara
rule AgentTesla {
    meta:
        description = "Agent Tesla keylogger/RAT"
    strings:
        $smtp = "SmtpPort" ascii wide
        $hook = "KeyboardHook" ascii wide
        $clip = "GetClipboardData" ascii wide
        $ns1 = "AgentTesla" ascii
        $ns2 = "WebMonitor" ascii
    condition:
        uint16(0) == 0x5A4D and 3 of them
}
```

## File Hashing

Prefer **`file_meta` / tool-produced hashes** in the evidence chain. If a
new hash is required, compute in the **sandbox** on the workspace path with
`python_exec`, not with host `open()`.

```python
import hashlib
# Example only: path is /workspace/<analysis_id>/... in sandbox, not the analyst machine.
# sha256 = hashlib.sha256(binary_data).hexdigest()
```

## VirusTotal API — Sample Lookup (human / bulk use)

**Not** a `binary_analysis` agent tool. Human analysts with API keys can use
HTTP lookups outside the project tool surface; do not name `VirusTotal` as an
invented agent capability.

```http
GET https://www.virustotal.com/api/v3/files/{sha256}
x-apikey: {API_KEY}
```

### Response Fields
| Field | Description |
|-------|-------------|
| `data.attributes.popular_threat_classification` | Malware family |
| `data.attributes.last_analysis_stats` | AV detection counts |
| `data.attributes.sandbox_verdicts` | Sandbox analysis results |

## Human sandbox services (not agent tools)
- **ANY.RUN**, **Hybrid Analysis**, **Joe Sandbox** — third-party services for
  interactive or automated detonation. The runtime uses **`SandboxSessionTool`**
  and the allowlisted 5+3+1 + `document_extract` set; do not substitute these
  brand names as project tools.
