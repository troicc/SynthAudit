# Direct-use hardening changelog

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.


This document records the practical-use layer added after the original v1.0 research-software
release.

## User-facing workflows

- Added `synthaudit-easy doctor` for environment diagnostics.
- Added direct mapped-reaction auditing without manually authoring `ReactionIR`.
- Added explicit optional atom mapping through RXNMapper.
- Added explicit optional reaction classification through ReactionClassifier.
- Added CSV, TSV and JSONL batch auditing with per-record errors and outputs.
- Added ready-to-run single and batch examples.
- Added standalone direct-use and Chinese beginner documentation.

## Reproducibility and packaging

- Pinned the same uv version in Docker and CI.
- Added direct-use smoke tests to the primary quality workflow.
- Added clean-wheel installation, Docker-build and full small-reproduction workflows.
- Added a one-click Python 3.11 dev container for GitHub Codespaces.
- Added contribution and security policies.

## Preserved scientific boundaries

- Atom mapping is never implicit.
- Optional providers are not imported or downloaded by the deterministic core.
- Missing evidence remains unavailable rather than being converted to zero.
- Classifier confidence is retained as a raw, uncalibrated provider score.
- A blocking audit is a representation-level finding, not proof of laboratory failure.
- No model training is required for deterministic execution and auditing.
