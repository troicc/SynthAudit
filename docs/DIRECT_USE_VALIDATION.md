# Direct-use publication and validation record

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.


Updated: 2026-09-01.

## Default-branch publication

The direct-use implementation and user documentation were merged into the repository's default
`main` branch through pull request #2.

Verified default-branch documents:

- [`BEGINNER_GUIDE_ZH.md`](BEGINNER_GUIDE_ZH.md): beginner-oriented Chinese explanation and operating manual;
- [`DIRECT_USE.md`](DIRECT_USE.md): concise command reference for direct use;
- [`DIRECT_USE_VALIDATION.md`](DIRECT_USE_VALIDATION.md): this publication record.

The direct-use code includes the `synthaudit-easy` entry point, single-reaction auditing, CSV/TSV/
JSONL batch auditing, and explicit optional RXNMapper and ReactionClassifier integrations.

## Verification boundary

The repository's maintained GitHub Actions workflows are the authoritative software checks for:

- locked dependency installation;
- Ruff formatting and linting;
- strict mypy checks;
- offline tests and smoke tests;
- wheel/sdist installation checks;
- deterministic small-reproduction checks;
- Docker image construction and startup.

Temporary self-modifying publication workflows have been removed from `main`; they are not part of
the maintained validation surface. After the merged direct-use files were formatted and the wheel
workflow was pinned to Python 3.11, this documentation commit intentionally triggered the normal
`quality` and `package` workflows against the resulting default-branch tree.

This document verifies that the files are published on the default branch and identifies the
software checks that must pass. It does **not** establish experimental feasibility, yield,
selectivity, safety, scalability, or chemistry-model performance.

## Incident correction

An earlier response incorrectly stated that these files were already on `main` while they existed
only on a feature branch, and also supplied a non-working local download link. Pull request #2 was
subsequently merged into `main`, all three document paths were checked on the default branch, and a
new downloadable copy of the beginner manual was generated separately.
