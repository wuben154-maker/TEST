# Reference: C2-Oriented Sandbox Patterns

This file is **not** an agent tool list. Runtime tools follow
`audit-runs/<run_id>/contracts.md` (5+3+1 plus `document_extract` on the
document path only).

Use this reference for **optional** `bash` / `python_exec` snippets inside
**`sandbox_session`** when analysts already uploaded bounded artefacts (for
example a small PCAP) to `/workspace/<analysis_id>/`. Keep stdout **short**;
never stream full packet payloads or raw bytes into the LLM. Prefer evidence
already materialised in **`strings_iocs`** / **`disassembly`** before running
extra parsers.

## Scapy - Packet Analysis Library (Python)

### Reading PCAPs (sandbox path)

```python
from scapy.all import rdpcap, IP, TCP, UDP, DNS, DNSQR
packets = rdpcap("/workspace/<analysis_id>/capture.pcap")
```

### Filtering Packets

```python
# TCP SYN packets (connection initiation)
syn_pkts = [p for p in packets if TCP in p and (p[TCP].flags & 0x02)]

# DNS queries
dns_pkts = [p for p in packets if DNS in p and p[DNS].qr == 0]

# Access fields
pkt[IP].src        # Source IP
pkt[IP].dst        # Destination IP
pkt[TCP].sport     # Source port
pkt[TCP].dport     # Destination port
pkt[TCP].flags     # TCP flags (0x02 = SYN)
float(pkt.time)    # Packet timestamp
```

## dpkt - Packet Parsing Library (Python)

### Reading PCAPs (sandbox path)

```python
import dpkt
with open("/workspace/<analysis_id>/capture.pcap", "rb") as f:
    pcap = dpkt.pcap.Reader(f)
    for timestamp, buf in pcap:
        eth = dpkt.ethernet.Ethernet(buf)
        ip = eth.data
        tcp = ip.data
```

### HTTP Request Parsing

```python
http = dpkt.http.Request(tcp.data)
http.method     # GET, POST
http.uri        # /path
http.headers    # dict of headers
http.body       # POST body
```

## tshark (CLI packet capture analysis)

### Beacon Analysis

```bash
tshark -r /workspace/<analysis_id>/capture.pcap -T fields -e ip.dst -e tcp.dstport -e frame.time_epoch \
  -Y "tcp.flags.syn==1" > syn_times.csv
```

### HTTP Extraction

```bash
tshark -r /workspace/<analysis_id>/capture.pcap -Y "http.request" -T fields \
  -e http.request.method -e http.host -e http.request.uri -e http.user_agent
```

### DNS Extraction

```bash
tshark -r /workspace/<analysis_id>/capture.pcap -Y "dns.qr==0" -T fields \
  -e dns.qry.name -e dns.qry.type -e ip.src
```

### JA3 TLS Fingerprinting

```bash
tshark -r /workspace/<analysis_id>/capture.pcap -Y "tls.handshake.type==1" -T fields \
  -e ip.src -e tls.handshake.ja3
```

## CobaltStrikeParser - Beacon Config Extraction

Use only when a **sandbox-local** copy of the parser is available; do not treat
`pip install` or host paths as agent requirements.

### Usage

```python
from cobalt_strike_parser import BeaconConfig
config = BeaconConfig.from_file("/workspace/<analysis_id>/suspect.exe")
for key, value in config.items():
    print(f"{key}: {value}")
```

### Key Config Fields

| Field | Description |
|-------|-------------|
| `BeaconType` | HTTP, HTTPS, DNS, SMB |
| `C2Server` | Primary C2 URL |
| `SleepTime` | Beacon interval (ms) |
| `Jitter` | Jitter percentage |
| `UserAgent` | HTTP User-Agent string |
| `Watermark` | License watermark ID |

## Suricata - Network IDS Rules

### Rule Syntax

```
alert <proto> <src> <port> -> <dst> <port> (msg:""; <options>; sid:N; rev:N;)
```

### Key Keywords

| Keyword | Purpose |
|---------|---------|
| `http.method` | Match HTTP method |
| `http.uri` | Match request URI |
| `http.header` | Match header content |
| `ja3.hash` | Match JA3 TLS fingerprint |
| `dns.query` | Match DNS query name |
| `tls.cert_subject` | Match TLS certificate CN |
| `threshold` | Rate-based detection |
