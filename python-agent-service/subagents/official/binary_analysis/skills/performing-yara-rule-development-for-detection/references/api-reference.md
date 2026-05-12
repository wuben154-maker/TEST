# API Reference: YARA Rule Development for Detection

## Execution environment (read first)

The snippets below are **illustrative** for `python_exec` or a shell **inside
`sandbox_session`**. They must use paths under `/workspace/<analysis_id>/` only.
Do **not** copy them to run on the analyst host against local malware paths.
If a library is missing in the sandbox image, record `tool_missing` and
degrade the workflow instead of bypassing the sandbox.

## yara-python API

| Method | Description |
|--------|-------------|
| `yara.compile(filepath=path)` | Compile rule from file |
| `yara.compile(source=string)` | Compile rule from string |
| `yara.compile(filepaths={ns: path})` | Compile with namespaces |
| `rules.match(filepath=path)` | Scan file against compiled rules |
| `rules.match(data=bytes)` | Scan bytes in memory |
| `rules.match(filepath, timeout=30)` | Scan with timeout |

## Match Object Attributes

| Attribute | Description |
|-----------|-------------|
| `match.rule` | Name of matching rule |
| `match.namespace` | Rule namespace |
| `match.tags` | Rule tags list |
| `match.meta` | Rule metadata dict |
| `match.strings` | List of (offset, identifier, data) |

## YARA Rule Structure

```
rule RuleName : tag1 tag2 {
    meta:
        description = "..."
        author = "..."
        date = "2025-01-01"
        hash = "sha256_of_sample"
    strings:
        $s1 = "string" ascii
        $s2 = "wide_string" wide
        $h1 = { 4D 5A 90 00 }
        $r1 = /regex[0-9]+/
    condition:
        uint16(0) == 0x5A4D and 3 of ($s*)
}
```

## Condition Operators

| Operator | Description |
|----------|-------------|
| `X of ($s*)` | X or more strings match |
| `all of ($s*)` | All strings match |
| `any of ($s*)` | At least one matches |
| `uint16(0) == 0x5A4D` | PE file magic bytes |
| `filesize < 10MB` | File size constraint |

## Python Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| `yara-python` | >=4.3 | Compile and scan YARA rules |
| `hashlib` | stdlib | SHA256 of samples |
| `re` | stdlib | String extraction |

## References

- YARA Documentation: https://yara.readthedocs.io/en/stable/
- yara-python: https://github.com/VirusTotal/yara-python
- YARA Rules Repository: https://github.com/Yara-Rules/rules
- VirusTotal Hunting: https://www.virustotal.com/gui/hunting-overview

## Illustrative: extract candidates with pefile (sandbox path only)

`filepath` in the following listing means a file **inside the sandbox
workspace** (e.g. `/workspace/<analysis_id>/sample.exe`), not a host path.

```python
#!/usr/bin/env python3
"""Extract candidate strings and byte patterns for YARA rule creation (sandbox)."""
import pefile
import re
import sys
from collections import Counter


def extract_strings(filepath, min_length=6):
    """Extract ASCII and wide strings from binary."""
    with open(filepath, 'rb') as f:
        data = f.read()

    # ASCII strings
    ascii_strings = re.findall(
        rb'[\x20-\x7e]{' + str(min_length).encode() + rb',}', data
    )

    # Wide (UTF-16LE) strings
    wide_strings = re.findall(
        rb'(?:[\x20-\x7e]\x00){' + str(min_length).encode() + rb',}', data
    )

    return {
        'ascii': [s.decode('ascii') for s in ascii_strings],
        'wide': [s.decode('utf-16-le') for s in wide_strings],
    }


def analyze_pe_imports(filepath):
    """Extract import table for API-based detection."""
    try:
        pe = pefile.PE(filepath)
    except pefile.PEFormatError:
        return []

    imports = []
    if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll_name = entry.dll.decode('utf-8', errors='replace')
            for imp in entry.imports:
                if imp.name:
                    func_name = imp.name.decode('utf-8', errors='replace')
                    imports.append(f"{dll_name}!{func_name}")
    return imports


def find_unique_byte_patterns(filepath, pattern_length=16):
    """Find unique byte sequences suitable for YARA hex patterns."""
    with open(filepath, 'rb') as f:
        data = f.read()

    try:
        pe = pefile.PE(filepath)
        # Focus on code section
        for section in pe.sections:
            if section.Characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
                code_start = section.PointerToRawData
                code_end = code_start + section.SizeOfRawData
                code_data = data[code_start:code_end]
                break
        else:
            code_data = data
    except Exception:
        code_data = data

    # Find byte patterns that appear exactly once
    patterns = []
    for i in range(0, len(code_data) - pattern_length, 4):
        pattern = code_data[i:i+pattern_length]
        if pattern.count(b'\x00') < pattern_length // 3:  # Skip null-heavy
            hex_pattern = ' '.join(f'{b:02X}' for b in pattern)
            patterns.append(hex_pattern)

    # Count frequency and return unique ones
    freq = Counter(patterns)
    unique = [p for p, count in freq.items() if count == 1]

    return unique[:20]  # Top 20 candidates


def suggest_rule_strings(filepath):
    """Suggest strings and patterns for YARA rule."""
    print(f"[+] Analyzing: {filepath}")

    # Extract strings
    strings = extract_strings(filepath)

    # Filter for suspicious/unique strings
    suspicious_keywords = [
        'http', 'https', 'cmd', 'powershell', 'mutex', 'pipe',
        'password', 'credential', 'inject', 'hook', 'debug',
        'sandbox', 'virtual', 'vmware', 'vbox',
    ]

    print("\n[+] Suspicious ASCII strings:")
    for s in strings['ascii']:
        if any(kw in s.lower() for kw in suspicious_keywords):
            print(f"  $ = \"{s}\" ascii")

    print("\n[+] Suspicious wide strings:")
    for s in strings['wide']:
        if any(kw in s.lower() for kw in suspicious_keywords):
            print(f"  $ = \"{s}\" wide")

    # Import analysis
    imports = analyze_pe_imports(filepath)
    suspicious_apis = [
        'VirtualAlloc', 'VirtualProtect', 'WriteProcessMemory',
        'CreateRemoteThread', 'NtUnmapViewOfSection', 'RtlMoveMemory',
        'OpenProcess', 'CreateToolhelp32Snapshot',
        'InternetOpenA', 'HttpSendRequestA',
        'CryptEncrypt', 'CryptDecrypt',
    ]

    print("\n[+] Suspicious imports:")
    for imp in imports:
        func = imp.split('!')[-1]
        if func in suspicious_apis:
            print(f"  {imp}")

    # Byte patterns
    print("\n[+] Candidate hex patterns:")
    patterns = find_unique_byte_patterns(filepath)
    for p in patterns[:5]:
        print(f"  $hex = {{ {p} }}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <sandbox_sample_path>")
        sys.exit(1)
    suggest_rule_strings(sys.argv[1])
```

## Illustrative: compile and test a rule (sandbox)

```python
import yara
import os

def create_yara_rule(rule_name, meta, strings, condition):
    """Generate a YARA rule from components."""
    meta_str = "\n".join(f'        {k} = "{v}"' for k, v in meta.items())
    strings_str = "\n".join(f"        {s}" for s in strings)

    rule = f"""rule {rule_name} {{
    meta:
{meta_str}

    strings:
{strings_str}

    condition:
        {condition}
}}"""
    return rule


def test_yara_rule(rule_text, test_dir):
    """Compile and test YARA rule against a sandbox-local directory."""
    try:
        rules = yara.compile(source=rule_text)
    except yara.SyntaxError as e:
        print(f"[-] YARA syntax error: {e}")
        return None

    results = {"matches": [], "no_match": []}

    for filename in os.listdir(test_dir):
        filepath = os.path.join(test_dir, filename)
        if not os.path.isfile(filepath):
            continue

        matches = rules.match(filepath)
        if matches:
            results["matches"].append({
                "file": filename,
                "rules": [m.rule for m in matches],
            })
        else:
            results["no_match"].append(filename)

    print(f"[+] Matches: {len(results['matches'])}")
    print(f"[-] No match: {len(results['no_match'])}")
    return results


# Example: create a rule for a hypothetical family (template only; tune strings)
example_rule = create_yara_rule(
    rule_name="MalwareFamily_Variant_A",
    meta={
        "description": "Detects MalwareFamily Variant A",
        "author": "Malware Analysis Team",
        "date": "2025-01-01",
        "hash": "abc123...",
        "tlp": "WHITE",
    },
    strings=[
        '$mutex = "Global\\\\UniqueM4lwareMutex" ascii wide',
        '$c2_pattern = /https?:\\/\\/[a-z]{5,10}\\.(xyz|top|buzz)\\/gate\\.php/',
        '$api1 = "VirtualAllocEx" ascii',
        '$api2 = "WriteProcessMemory" ascii',
        '$api3 = "CreateRemoteThread" ascii',
        '$hex_decrypt = { 8B 45 ?? 33 C1 89 45 ?? 83 C1 04 }',
        '$pdb = "C:\\\\Users\\\\" ascii',
    ],
    condition=(
        'uint16(0) == 0x5A4D and filesize < 2MB and '
        '($mutex or $c2_pattern) and '
        '2 of ($api*) and '
        '$hex_decrypt'
    ),
)

print(example_rule)
```

## Illustrative: benchmark (sandbox)

```python
import os
import time
import yara

def benchmark_rule(rule_text, scan_directory, iterations=3):
    """Benchmark YARA rule scan performance (sandbox paths only)."""
    rules = yara.compile(source=rule_text)

    files = []
    for root, _, filenames in os.walk(scan_directory):
        for f in filenames:
            files.append(os.path.join(root, f))

    print(f"[+] Benchmarking against {len(files)} files "
          f"({iterations} iterations)")

    times = []
    for i in range(iterations):
        start = time.perf_counter()
        matches = 0
        for filepath in files:
            try:
                result = rules.match(filepath)
                if result:
                    matches += 1
            except Exception:
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        print(f"  Iteration {i+1}: {elapsed:.3f}s ({matches} matches)")

    avg_time = sum(times) / len(times)
    files_per_sec = len(files) / avg_time
    print(f"\n[+] Average: {avg_time:.3f}s ({files_per_sec:.0f} files/sec)")
    return avg_time
```
