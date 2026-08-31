# ADR 0002: Isolate the official ReactSeq runtime

- Status: Accepted
- Date: 2026-08-31

## Context

Pinned ReactSeq conversion documents Python 3.7, RDKit 2019.03.2, and Indigo, while its inference environment documents Python 3.8/PyTorch 2.0/OpenNMT-py 3.4.1. SynthAudit targets Python 3.11 and a current RDKit. Downgrading the project would compromise maintainability and other providers.

## Decision

Do not vendor LGPL upstream code or import it into core. Use a separately built `services/reactseq-legacy` process with a stable, versioned JSONL stdin/stdout protocol. Golden fixtures record the upstream SHA and runtime versions. Core contains a traversal-aware, fail-closed adapter only for source-verified syntax.

## Consequences

Offline core stays modern; official conversion is optional and legally/runtime isolated. Cross-runtime startup has overhead, and official conformance remains unavailable until the legacy image is built and fixtures pass.
