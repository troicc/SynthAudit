# Current status

## Phase 0 — upstream and research specification

Status: **accepted on 2026-08-31**.

Branch: `codex/00-upstream-and-research-spec`

Completed:

- inspected the initially empty repository;
- fixed scientific terminology and non-claims;
- defined ReactionIR/RouteIR, staged execution, audit, novelty, evidence, and provider boundaries;
- recorded official upstream branches and exact HEAD SHAs;
- inspected ReactSeq source/example/runtime and identified its isolated-runtime boundary;
- verified that current SynthEx does not publish official ReactionJSON/RouteJSON schemas;
- documented draft-only SynthEx semantics and fail-closed official adapters;
- fixed research questions, split/leakage rules, reproducible v0.1 scope, and agent prohibitions;
- accepted ADRs 0001–0003.

Acceptance evidence:

- no unsupported official compatibility claim;
- no invented benchmark result;
- exact upstream commits and license status recorded in `UPSTREAM_STATUS.md`;
- unsupported and undocumented semantics named explicitly;
- v0.1 can proceed without SynthEx schemas or ReactSeq checkpoint.

## Phase 1 — project bootstrap

Status: **accepted on 2026-08-31**.

Branch: `codex/01-project-bootstrap`

Implemented a Python 3.11 src-layout package, uv lock, Apache-2.0 licensing, Make/Docker/Compose/CI entry points, typed Typer CLI, Streamlit entry point, offline-test markers, and reproducibility/claim notices.

Verification:

- `make quality`: ruff check/format and strict mypy passed;
- `make test`: 2 passed; bootstrap package coverage 67%;
- `make smoke`: version JSON emitted with mandatory notice;
- `make benchmark-small`: validated two fixture records and reported `metrics=not_run` rather than inventing results;
- locked CPython 3.11.15 and 72 resolved packages in `uv.lock`.

No network access occurs in tests. No model or dataset is downloaded at import time.

Next: Phase 2 ReactionIR/RouteIR, generated JSON Schemas, semantic hashing, and serialization/property tests.
