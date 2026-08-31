# SynthAudit

**A representation-agnostic audit layer for reaction-edit retrosynthesis**

SynthAudit normalizes mapped reactions and reaction-edit languages into a stable `ReactionIR`, executes edits in explicit reaction-centre and synthon-completion stages, and reports structural consistency, corpus novelty, precedent support, evidence-based plausibility, and uncertainty as separate results.

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Why this exists

ReactSeq, agent-authored graph edits, mapped reaction SMILES, and route-planner exports encode overlapping chemistry with different identifiers and failure modes. SynthAudit provides an independent, deterministic layer for asking whether they mean the same graph transformation and where a proposal requires expert review.

The central pipeline is:

```text
external representation -> ReactionIRV1 -> staged transactional execution
                        -> centre/completion/stereo/structural audits
                        -> novelty + precedent + calibrated evidence
```

Novelty is not treated as the inverse of plausibility.

## Install

The reference environment uses Python 3.11 and [uv](https://docs.astral.sh/uv/):

```bash
make install
make quality
make test
make smoke
```

Core tests are offline and do not require model downloads, paid APIs, or large datasets.

## Quick start

```bash
uv run synthaudit version --json
uv run synthaudit normalize-reaction --reaction-smiles reaction.smi --json reaction-ir.json
uv run synthaudit audit-reaction --input reaction-ir.json --html audit.html --json audit.json
```

Run `synthaudit --help` for all commands. Optional integrations are explicit extras and providers; no model downloads occur at import time.

## Scientific and interoperability status

Start with:

- [Project specification](docs/PROJECT_SPEC.md)
- [Scientific claims](docs/SCIENTIFIC_CLAIMS.md)
- [Exact upstream status](docs/UPSTREAM_STATUS.md)
- [Current implementation status](docs/CURRENT_STATUS.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)

At the 2026-08-31 pinned upstream revision, SynthEx has not released official ReactionJSON or RouteJSON schemas. SynthAudit therefore exposes a clearly named paper-draft adapter and makes no official-compatibility claim. ReactSeq's official converter is handled through an optional legacy-runtime boundary.

## License

SynthAudit is licensed under Apache-2.0. External code, checkpoints, and datasets retain their own terms and are not vendored by default.
