# Standards Reference - extracting-config-from-agent-tesla-rat

## Applicable Standards
- MITRE ATT&CK Framework
- NIST SP 800-83 Guide to Malware Incident Prevention
- NIST SP 800-86 Guide to Integrating Forensic Techniques

## Related MITRE ATT&CK Techniques (illustrative)

Map at most when `llm_inferences` or FR-15 narrative references ATT&CK; do not
invent T-codes without evidence-backed rationale.

| Technique | Theme |
|-----------|--------|
| T1005 / T1056 / T1539 (examples) | Data from local system, input capture, steal web session cookie |
| T1071 | Application layer command and control (exfil over SMTP, HTTPS, or messaging APIs) |
| T1041 | Exfiltration over C2 channel |

## Proto alignment

- **Proto-02** (`binary-analysis-evidence-chain-protocol`) — `llm_inferences`
  inferences use `source_fr: "FR-13"`, `evidence_refs`, and allowed
  `indicator_type` values from the family triage examples (`family_config`,
  `family_candidate`, etc.).
- **Proto-03** (`binary-analysis-sanitize-untrusted-strings`) — all
  sample-originated strings in indicators or report text pass through
  `sanitize` and `{open_tag}` / `{close_tag}` as required.

See `SKILL.md` for the authoritative routing and downgrade table.
