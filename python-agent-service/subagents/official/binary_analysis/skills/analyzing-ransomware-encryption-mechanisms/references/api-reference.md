# Ransomware encryption: reference material

Use this only when a subsection is needed. Do not read end-to-end by default. All sample access in the binary_analysis example stays inside the sandbox and evidence-chain model described in the parent `SKILL.md`—no ad hoc host `open()` on the submitted sample.

## PyCryptodome (conceptual testing math)

`AES`, `ChaCha20`, and `RSA` usage below is for reasoning about **math only**. Any decrypt attempt belongs in offline IR tooling, not in this example’s unbounded tool surface.

### AES

```python
from Crypto.Cipher import AES
# MODE_CBC, MODE_CTR, MODE_ECB, etc. — align mode with decompiler facts
# cipher = AES.new(key, AES.MODE_CBC, iv)
# plaintext = cipher.decrypt(ciphertext)
```

### ChaCha20

```python
from Crypto.Cipher import ChaCha20
# cipher = ChaCha20.new(key=key, nonce=nonce)
```

### RSA (public key inspection)

```python
from Crypto.PublicKey import RSA
# key = RSA.import_key(exported_key_material_from_sandbox_decompress_only)
# key.size_in_bits() — compare with decompiler/wrapper facts
```

## Windows Crypto import names (lookup)

Imports are normally taken from evidence-chain **`imports` facts** (FR-04), not re-parsed on the host. Use this table to label symbols the facts already list:

| API | Role |
|-----|------|
| `CryptAcquireContext` | CryptoAPI init |
| `CryptGenRandom` | CSPRNG |
| `CryptGenKey` / `CryptImportKey` | Key material |
| `CryptEncrypt` / `CryptDecrypt` | CryptoAPI encrypt/decrypt |
| `BCryptOpenAlgorithmProvider` | CNG init |
| `BCryptGenerateSymmetricKey` / `BCryptGenerateKeyPair` | Keys |
| `BCryptEncrypt` | CNG encrypt |

## Entropy heuristics (triage, not proof)

| Shannon band | Typical interpretation (non-exclusive) |
|-------------|----------------------------------------|
| ~0–1 | Empty / very uniform run |
| ~1–5 | Code / text |
| ~5–7 | Compressed / high-variance data |
| ~7.0–7.9 | Block/stream ciphertext-like (many schemes) |
| ~7.9–8.0 | Also consistent with some stream modes |

Tie any entropy story to an evidence fact id, not to raw hexdumps in chat.

## Known-family scheme patterns (illustrative)

| Family (examples) | File cipher | Key wrapping | Note |
|-------------------|------------|-------------|------|
| WannaCry | AES-128-CBC | RSA-2048 | Historical campaign |
| LockBit 3.0 (example class) | AES-256-CTR | RSA-2048 | Per-file key story common |
| REvil (example) | Salsa20 | ECDH (family-dependent) | Verify against fresh facts |
| Hive / BlackCat (examples) | ChaCha20 / AES | RSA-4096 | Check Malpedia + your facts |
| Babuk (example) | ChaCha20 | ECDH | Source leaks changed IR |

Names are **Malpedia-style pointers**; verdict and family ownership remain with the rule engine + Malpedia alias workflow.

## Ransomware file layout patterns (defensive)

Common append / footer layouts (exact offsets are family-specific; confirm with strings/structure facts):

```text
[encrypted_payload][wrapped_symmetric_key][iv_or_nonce][optional_magic]
```

Interpreting trailing blobs belongs in the sandbox and in cited facts, not in pasted sample bytes in LLM text.

## OS-level recovery (out of E2E)

Memory acquisition, `vssadmin`, or full-disk triage are **incident-response** procedures outside the static binary E2E contract. If the session only has partial binary evidence, use `gap_note` and `doc_analysis_partial` per the document orchestrator instead of speculating on volume shadow state.

## NoMoreRansom / ID Ransomware (external, verify offline)

- Identification portal: `https://id-ransomware.malwarehunterteam.com/`
- Decryptor index: `https://www.nomoreransom.org/en/decryption-tools.html`

Cite as research pointers in human-facing prose; this example does not automate uploads.

## Ghidra / static search hints (in-sandbox)

1. String search: `encrypt`, `Crypt`, `BCrypt`, `AES`, `RSA`, `chacha`, `salsa`
2. Byte search: AES S-box lead bytes (as published—compare with policy on constant hunting in `ghidra-priority-queue-workflow`)
3. Xrefs: from `CryptEncrypt` / `BCryptEncrypt` to user functions
4. Key buffer sizes: 16 vs 32 bytes suggests AES-128 vs AES-256 in decompiler output (still cite `decompiled_function` facts)
