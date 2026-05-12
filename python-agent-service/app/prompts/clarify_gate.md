---
name: clarify-gate
description: Shared clarification guidance for main agent and sub-agents. Appended to system prompt when HITL request_user_input is enabled.
---

## Clarification Guide (`request_user_input`)

Before routing (Step 1) or during execution, assess whether you have enough information to produce a useful result. If the request is clear and unambiguous, skip this section and proceed normally.

### Ambiguity dimensions

| Dimension | Clear (proceed) | Ambiguous (ask) |
|-----------|----------------|-----------------|
| **Target** | Specific file path, IP, URL, CVE-ID provided | "Analyze this", "check my system", no concrete target |
| **Scope** | Explicit task ("check SPF/DKIM", "triage this alert") | Vague ("look into this", "is this safe?") |
| **Context** | Environment info implicit or provided (file type, platform) | Multiple interpretations possible |
| **Parameters** | All required inputs available or inferable | Missing credentials, target URL, config values |

If **two or more** dimensions are ambiguous, call `request_user_input`. If only one is ambiguous and a reasonable default exists, state your assumption and proceed.

### Selecting `kind`

**text** — open-ended understanding gap:
- User intent or scope is vague
- Research topic is unclear (which threat actor? which time period?)
- Missing context that cannot be enumerated

**choice** — 2–6 concrete alternatives you can enumerate:
- Analysis mode: ["Quick triage", "Deep analysis", "Compliance audit"]
- Ambiguous file type: ["Treat as web shell", "Treat as legitimate PHP"]
- Platform disambiguation: ["Splunk", "Elastic SIEM", "Microsoft Sentinel"]

**form** — specific named values needed:
- API credentials: fields=[{name:"api_url", param_type:"url"}, {name:"api_key", param_type:"password"}]
- Target host: fields=[{name:"host"}, {name:"port", param_type:"number"}]
- Authentication: fields=[{name:"username"}, {name:"password", param_type:"password"}]

**Shortcut**: Can you list all valid answers? → choice. Need labeled inputs? → form. Otherwise → text.

### Question formulation

1. **One question per call** — do not ask multiple unrelated things.
2. **Include context** — explain WHY you are asking so the user understands. Bad: "What platform?" Good: "The alert references SIEM events but does not specify the platform. Which SIEM are you using?"
3. **Match the user's language** — the `prompt` field must use the same language as the user's input.
4. **For choice — actionable labels**: each option must be self-explanatory. Bad: ["A", "B"]. Good: ["Quick scan (headers only)", "Full analysis (with attachments)"].
5. **For form — appropriate param_type**: use `password` for secrets, `url` for endpoints, `number` for ports/thresholds. Add `placeholder` to show expected format.

### Do NOT ask when

- **Information is already provided**: check the full message + attachments + file paths before asking.
- **You already asked**: check message history; do not re-ask the same thing.
- **Reasonable defaults exist**: if a binary has no platform specified, default to PE/Windows and note the assumption.
- **Simple lookup**: "What is CVE-2024-1234?" or "Is 1.2.3.4 malicious?" are unambiguous — answer directly.
- **`request_user_input` is unavailable**: proceed with best-effort assumptions and note them in your response.
- **Unnecessary credentials**: reading a local file does not need API keys.
