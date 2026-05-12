# Cobalt Strike Malleable C2 — API and signature reference

## Contract (read first)

- All **install**, **Python**, and **shell** snippets below are **illustrative commands
  for `bash` / `python_exec` inside `sandbox_session`** on artefacts under
  `/workspace/<analysis_id>/`. They are **not** extra agent tools and must not be
  presented as capabilities the host runtime can run without the sandbox.
- **No host-side sample reads**: do not open specimens on the analyst machine; do
  not stream raw bytes or full file contents into the LLM.
- Optional third-party libraries (`dissect.cobaltstrike`, `pyMalleableC2`) may be
  **absent** in a given worker image. If imports fail, stop at string-level and
  **`analysis_coverage`** reasoning per the parent `SKILL.md` downgrade path.

## Optional install (sandbox `bash`)

```bash
pip install dissect.cobaltstrike
pip install 'dissect.cobaltstrike[full]'   # optional extras
pip install pyMalleableC2                   # alternative parser
```

## dissect.cobaltstrike API (sandbox `python_exec`)

Paths must be **workspace-relative** (for example `/workspace/<analysis_id>/profile.profile`).

### Parse beacon configuration

```python
from dissect.cobaltstrike.beacon import BeaconConfig

bconfig = BeaconConfig.from_path("/workspace/<analysis_id>/beacon.bin")
# Use config fields in tool output or bounded prints only; do not paste full blobs to the LLM.
```

### Parse Malleable C2 profile

```python
from dissect.cobaltstrike.c2profile import C2Profile

profile = C2Profile.from_path("/workspace/<analysis_id>/amazon.profile")
config = profile.as_dict()
# Example keys: useragent, http-get.uri, sleeptime (see Key profile settings)
```

### PCAP helper CLIs (optional, sandbox only)

If PCAP is present in the workspace and the image provides the tools, analysts may use
bounded CLI output; the agent does **not** expose `network_capture` or non-contract tools.

```bash
beacon-pcap --extract-beacons /workspace/<analysis_id>/traffic.pcap
# Decrypt flows only when keys are legitimately available in-scope; keep stdout bounded.
```

## pyMalleableC2 API (sandbox `python_exec`)

```python
from malleableC2 import Profile

profile = Profile.from_file("/workspace/<analysis_id>/amazon.profile")
# Accessors vary by version; prefer tool-backed dict / string summaries over huge dumps.
```

## Key profile settings

| Setting | Description | Detection value |
|---------|-------------|-----------------|
| `sleeptime` | Callback interval (ms) | Low values may indicate aggressive beaconing |
| `jitter` | Sleep randomization % | Timing analysis / evasion |
| `useragent` | HTTP User-Agent string | Network / proxy signature |
| `http-get.uri` | GET request URI path | URI-based detection |
| `http-post.uri` | POST request URI path | URI-based detection |
| `spawnto_x86` | 32-bit spawn process | Process-creation detection |
| `spawnto_x64` | 64-bit spawn process | Process-creation detection |
| `pipename` | Named pipe pattern | Named pipe monitoring |
| `dns_idle` | DNS idle IP address | DNS beacon detection |
| `watermark` | License watermark | Operator attribution |

## Suricata rule sketch (human-oriented)

```
alert http $HOME_NET any -> $EXTERNAL_NET any (
  msg:"MALWARE Cobalt Strike C2 URI";
  flow:established,to_server;
  http.uri; content:"/api/v1/status";
  http.header; content:"User-Agent: Mozilla/5.0";
  sid:9000001; rev:1;
)
```

Treat as **documentation** for analysts; deployment is out of scope for the agent.

## Optional packaged helper

If your deployment stages `scripts/agent.py` into the workspace, it may be invoked via
`python_exec` with **bounded** stdout. There is no requirement to use this script.

```bash
python /workspace/<analysis_id>/agent.py --input profile.profile --output report.json
```

## References

- dissect.cobaltstrike: https://github.com/fox-it/dissect.cobaltstrike
- pyMalleableC2: https://github.com/byt3bl33d3r/pyMalleableC2
- Unit42 Analysis: https://unit42.paloaltonetworks.com/cobalt-strike-malleable-c2-profile/
- Config extractor (external): https://github.com/strozfriedberg/cobaltstrike-config-extractor
