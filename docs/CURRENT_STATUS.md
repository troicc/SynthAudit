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

## Phase 2 — canonical reaction and route IR

Status: **accepted on 2026-08-31**.

Branch: `codex/02-reaction-ir`

Implemented frozen/strict Pydantic v2 models for `ReactionIRV1`, `RouteIRV1`, provenance, conditions, evidence, audit checks, and semantic comparison. Core, attachment, atom-state, and stereo operations are discriminated unions covering every v1 edit type, including null and charge-only completion. Generated five committed JSON Schemas and a deterministic schema exporter.

`reaction_ir_semantic_hash` canonicalizes mapped graphs, normalizes undirected edit endpoints, ignores source traversal/IDs/provenance, and makes precursor/edit ordering invariant while preserving meaningful stereo order.

Verification:

- `make quality`: ruff and strict mypy passed;
- `make test`: 18 passed; total coverage 89%; ReactionIR 90%, RouteIR 92%, edit schemas 85%, semantic hash 84%;
- property tests cover deterministic JSON round trips and precursor-order invariance;
- regression test verifies committed JSON Schemas match runtime models;
- `make schemas` regenerates schemas deterministically.

Next: Phase 3 staged transactional RDKit execution, atom-map policy, sanitation, graph diff, rollback, and execution result schemas.

## Phase 3 — staged transactional graph execution

Status: **accepted on 2026-08-31**.

Branch: `codex/03-execution-engine`

Implemented `CoreGraphExecutor`, `AttachmentCompletionExecutor`, `StereoExecutor`, and `ReactionExecutor`. Every stage edits a copy, returns the original structures on failure, exposes partial structures only through diagnostic fields, records operation index/type/maps and RDKit errors, and enforces success/error invariants in Pydantic results.

The atom-map policy rejects missing/duplicate/reused maps and requires introduced fragment atoms to occupy the next deterministic sequential range. GraphDiff reports atoms, atom properties, bonds/orders, tetrahedral/bond stereo, fragments, and rings. Strict and diagnostic sanitation share one fail-closed result protocol. Symmetric absolute stereocentres and ambiguous E/Z neighbours are explicitly rejected rather than assigned using atom-map-influenced ranking.

Verification:

- `make quality`: ruff and strict mypy passed;
- `make test`: 75 passed, total coverage 92%; core executor 95%, completion executor 94%, stereo executor 92%, full executor 91%, graph diff 97%, atom-map helpers 94%;
- property tests cover deterministic execution and transactional rollback;
- tests cover every core edit, single/multi attachment, fresh maps, detach/null/charge-only completion, atom-state edits, sanitation modes, tetrahedral set/invert/clear, E/Z set/clear, symmetry/ambiguity, and stage short-circuiting;
- `make schemas` generated the versioned full-execution JSON Schema and regression verification passed;
- `make smoke` passed.

Next: Phase 4 ReactSeq traversal normalization, safe parser, official legacy bridge protocol, fixtures, and conformance runner.

## Phase 4 — ReactSeq integration

Status: **accepted on 2026-08-31**.

Branch: `codex/04-reactseq-integration`

Implemented a source-preserving ReactSeq tokenizer, `ReactSeqTraversalContext`, indexed/unique-isomorphism traversal resolution, safe header and tail parsers, canonical adapter, optional model-provider protocol, pinned official subprocess bridge, and measured conformance runner. Stable atom maps are resolved only after traversal-to-RDKit mapping. Symmetric non-indexed assignments are indeterminate.

The parser covers all seven source-observed MEO families, combined atom edits, bond/E-Z markers, direct-H capacity, null and charge-only records, deterministic fresh fragment maps, one-to-many and distinct-atom multi-attachment groups, and half-open token ranges. A full transaction may carry a sanitation-failed diagnostic synthon into completion; the failed core result and RDKit message remain visible, and only a sanitized final graph can succeed.

Verification:

- `make quality`: ruff and strict mypy passed;
- `make test`: 100 tests passed after Phase 4 additions; total coverage 90%, ReactSeq adapter package above the 85% adapter target;
- `make reactseq-conformance-small`: 3/3 pinned upstream demo fixtures parsed, executed, and reconstructed exactly; this is explicitly fixture-scoped, not a general benchmark result;
- randomized traversal tests normalize two equivalent strings to the same semantic hash;
- malformed syntax, tail-count mismatch, ambiguous symmetry/add-bond pairing, bridge response failure, charge/null, order decrease, multi-attachment, cyclic stereo and aromatic/Kekulé paths are covered;
- `make schemas` exports five ReactSeq adapter/bridge/conformance schemas;
- `make smoke` passed.

Upstream assumptions remain pinned to `ReactSeq@9838a3058e32e1c0ee04b2bab0448104dc293384`. The official legacy runtime and checkpoint were not reproduced, so no full official compatibility, MEO embedding, or model-probability claim is made.

Next: Phase 5 mapped-reaction, SynthEx draft/fail-closed official, Synthelite route, and cross-representation adapters.
