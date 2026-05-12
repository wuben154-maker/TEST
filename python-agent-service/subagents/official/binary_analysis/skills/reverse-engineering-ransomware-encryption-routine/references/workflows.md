# Ransomware Encryption Analysis Workflows

These ASCII diagrams describe **human analyst** training context and high-level
methodology. The binary_analysis runtime agent does **not** execute decryptors,
host-side debuggers, or destructive “test on sample files” steps; it stays inside
the sandbox tool contract (`bash` / `python_exec` / `file_read` /
`sandbox_session` plus the five project tools).

## Workflow 1: Encryption Routine Identification
```
[Ransomware Sample] --> [Import Analysis] --> [Find Crypto APIs]
                                                    |
                                                    v
                                           [Identify Algorithm]
                                                    |
                                                    v
                                           [Trace Key Generation]
                                                    |
                                                    v
                                           [Assess Decryption Feasibility]
```

## Workflow 2: Key Recovery Assessment
```
[Encrypted Files] --> [Analyze File Structure] --> [Locate Encrypted Key]
                                                          |
                                                          v
                                                 [Check for PRNG Weaknesses]
                                                          |
                                                          v
                                                 [Attempt Key Recovery]
```

## Workflow 3: Decryptor Development
```
[Identified Flaw] --> [Extract Parameters] --> [Build Decryption Logic]
                                                        |
                                                        v
                                               [Test on Sample Files]
                                                        |
                                                        v
                                               [Release Decryptor Tool]
```
