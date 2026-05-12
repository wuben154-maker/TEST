"""run_msoffcrypto.py — Encrypted Office password brute-force worker (FR-03 AC-12/14).

Invocation (by host via SandboxClient)::

    python run_msoffcrypto.py --input <json_path>

Input JSON::

    {
        "sample_path": "/workspace/<aid>/sample.docx",
        "password_list": ["infected", "virus", "malware", "password"]
    }

Stdout JSON contract::

    {
        "decrypted": true,
        "attempted": 4,
        "succeeded_password_hash": "sha256:5e884898",
        "metadata": {
            "cipher_algorithm": "AES",
            "key_bits": 128,
            "hash_algorithm": "SHA-1"
        }
    }

On exhaustion without a match::

    {
        "decrypted": false,
        "attempted": 4,
        "succeeded_password_hash": null,
        "metadata": {}
    }

Security notes (NFR-04 / IR-DOC-01)
-------------------------------------
- Password plaintext is **never** stored; only the first 8 hex chars of its
  SHA-256 hash are recorded (FR-03 AC-16 / IMPL-GUIDE §🔐).
- msoffcrypto-tool performs cryptographic decryption without launching Office.
- This worker is the only location that imports ``msoffcrypto``; host code
  must not import it (CI enforces this via AST scan).
- Decrypted bytes are written to a temporary path only if the caller explicitly
  provides ``decrypted_output_path`` in the payload; otherwise they are
  discarded after hash extraction.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path


def _hash_password(password: str) -> str:
    """Return first 8 hex chars of SHA-256 of the password (no plaintext stored)."""
    return "sha256:" + hashlib.sha256(password.encode()).hexdigest()[:8]


def _run(
    sample_path: str, password_list: list[str], decrypted_output_path: str | None = None
) -> dict:
    try:
        import msoffcrypto  # type: ignore[import-untyped]
    except ImportError as exc:
        return {
            "decrypted": False,
            "attempted": 0,
            "succeeded_password_hash": None,
            "metadata": {},
            "error": f"msoffcrypto not available: {exc}",
        }

    path = Path(sample_path)
    if not path.exists():
        return {
            "decrypted": False,
            "attempted": 0,
            "succeeded_password_hash": None,
            "metadata": {},
            "error": f"sample not found: {sample_path}",
        }

    metadata: dict = {}

    try:
        with path.open("rb") as fh:
            office_file = msoffcrypto.OfficeFile(fh)

            # Extract encryption metadata before attempting decryption
            try:
                info = office_file.info()
                metadata = {
                    "cipher_algorithm": getattr(info, "cipher_algorithm", None),
                    "key_bits": getattr(info, "key_bits", None),
                    "hash_algorithm": getattr(info, "hash_algorithm", None),
                }
            except Exception:  # noqa: BLE001
                pass

            for attempt_idx, password in enumerate(password_list):
                try:
                    # Re-open for each attempt since decryption is stateful
                    with path.open("rb") as fh2:
                        of2 = msoffcrypto.OfficeFile(fh2)
                        of2.load_key(password=password)
                        decrypted_buf = io.BytesIO()
                        of2.decrypt(decrypted_buf)

                    # Success — write output if requested
                    if decrypted_output_path:
                        out = Path(decrypted_output_path)
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(decrypted_buf.getvalue())

                    return {
                        "decrypted": True,
                        "attempted": attempt_idx + 1,
                        "succeeded_password_hash": _hash_password(password),
                        "metadata": metadata,
                    }
                except Exception:  # noqa: BLE001
                    continue  # wrong password → try next

    except Exception as exc:  # noqa: BLE001
        return {
            "decrypted": False,
            "attempted": len(password_list),
            "succeeded_password_hash": None,
            "metadata": metadata,
            "error": f"file open failed: {exc}",
        }

    return {
        "decrypted": False,
        "attempted": len(password_list),
        "succeeded_password_hash": None,
        "metadata": metadata,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="msoffcrypto password brute-force worker"
    )
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    args = parser.parse_args()

    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "decrypted": False,
                    "attempted": 0,
                    "succeeded_password_hash": None,
                    "metadata": {},
                    "error": f"bad input: {exc}",
                }
            )
        )
        sys.exit(1)

    result = _run(
        sample_path=payload.get("sample_path", ""),
        password_list=payload.get("password_list", []),
        decrypted_output_path=payload.get("decrypted_output_path"),
    )
    print(json.dumps(result))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
