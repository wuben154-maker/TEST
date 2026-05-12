# API Reference: Reverse Engineering Ransomware Encryption (binary_analysis)

Long tables for this skill. Execution stays inside the sandbox and project tool
surface; do not use this file to justify host-side sample reads or non-contract
agent tools.

## Cryptographic algorithm constants

| Algorithm | Signature | Description |
|-----------|-----------|-------------|
| AES | S-Box starting `0x63 0x7C 0x77` | AES Rijndael substitution box |
| RSA | DER `0x30 0x82` prefix | ASN.1 RSA key structure |
| ChaCha20/Salsa20 | `expand 32-byte k` | Stream cipher constant |
| RC4 | Sequential 0-255 state | Key scheduling algorithm init |

## Encryption analysis (contract-aligned)

| Technique | Contract surface | Purpose |
|-----------|------------------|---------|
| Entropy and structure | FR-05 / `python_exec` heuristics in sandbox | High-level encrypted-region hints |
| Constant scanning | `strings_iocs` facts from FR-06 plus paginated decompiler text via `file_read` | Find embedded constants and markers |
| Import surfaces | `imports` facts from FR-04; optional static helpers via `python_exec` | Map API families before deep decompile read |
| Call-path tracing | FR-07 `file_read` pages + `function_tag` | Tie APIs to file encryption routines |

Ransomware-specific dynamic tracing on analyst workstations (debuggers, host
tracers) is **out of scope** for the runtime agent; describe it only as
non-authoritative background for human analysts.

## Ransomware encryption patterns

| Pattern | Indicator |
|---------|-----------|
| Full encryption | Entropy > 7.9 across entire file (fact-backed) |
| Intermittent | High entropy blocks with gaps |
| Header-only | First N bytes encrypted, rest plain |
| Appended metadata | File larger than original (key/IV at end) |

## Common ransomware crypto (illustrative)

| Family | Algorithm | Key Mgmt |
|--------|-----------|----------|
| LockBit 3.0 | AES-256-CBC + RSA-2048 | Per-file AES key, RSA-encrypted |
| BlackCat/ALPHV | ChaCha20 + RSA-4096 | Rust implementation |
| Royal | AES-256-CBC + RSA-2048 | Intermittent encryption |
| Akira | ChaCha20 | Partial file encryption |

## Python (stdlib) in sandbox

| Library | Purpose |
|---------|---------|
| `hashlib` | SHA256 hashing |
| `struct` | Binary data parsing |
| `re` | Pattern extraction |
| `math` | Shannon entropy (bounded outputs only) |

Use `python_exec` only for **bounded** metrics and structured results — not for
dumping full sample content into the model context.

## References

- ID Ransomware: https://id-ransomware.malwarehunterteam.com/
- No More Ransom decryptors: https://www.nomoreransom.org/en/decryption-tools.html
- Ghidra: https://ghidra-sre.org/
