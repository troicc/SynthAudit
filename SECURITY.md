# Security policy

## Supported versions

The latest tagged release and the default branch receive security fixes.

## Reporting

Please report suspected vulnerabilities privately through GitHub's security-advisory interface.
Do not open a public issue containing credentials, private datasets, malicious pickle artifacts,
or an exploit.

## Important boundaries

- SynthAudit refuses implicit network downloads.
- Downloaded data must be declared by a manifest and verified with SHA-256.
- Python pickle can execute code. Load a model artifact only when its origin and checksum are trusted.
- Optional RXNMapper, ReactionClassifier, forward-model and LLM integrations execute third-party
  code and retain their own licenses and security properties.
- Never place secrets in CLI arguments that may enter shell history; use environment variables or
  provider-specific secret stores where an external provider is enabled.
