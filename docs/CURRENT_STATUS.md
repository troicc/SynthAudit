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

## Phase 5 — reaction and route adapters

Status: **accepted on 2026-08-31**.

Branch: `codex/05-reactionjson-and-route-adapters`

Implemented a fail-closed mapped-reaction-SMILES adapter, the explicitly unofficial
`synthaudit.synthex-paper-draft/0.1` reaction namespace, the separate local
`synthaudit.synthex-paper-draft-route/0.1` route namespace, permanently fail-closed official
SynthEx entry points, and a version-pinned Synthelite nested-tree adapter. Source payloads,
warnings, unsupported fields, exact upstream commits, and license availability remain visible.
No adapter silently maps atoms or guesses an ambiguous fragment.

Cross-representation comparison now operates on normalized product graphs, edit stages, and
executed precursor sets. It aligns pure atom-map renumbering through bounded product-graph
isomorphism, reports symmetric competing correspondences as `indeterminate`, and separates
unspecified stereo, partial representability, unsupported semantics, and chemical difference.

Verification:

- `make quality`: ruff and strict mypy passed;
- `make test`: 126 passed, total coverage 88%; the complete adapters package is 85%, mapped
  reaction adapter 90%, and cross-representation comparison modules together 83%;
- `make schemas`: generated adapter-result, route-adapter-result, and representation-
  conformance JSON Schemas; committed-schema regression passed;
- `make smoke` and `make benchmark-small`: passed offline; the small benchmark continues to
  report `metrics=not_run` rather than invented measurements;
- `make reactseq-conformance-small`: the same 3/3 pinned demo fixtures reconstructed exactly,
  still explicitly fixture-scoped;
- 26 Phase 5 tests cover mapped graph differencing, fragment completion, rejection paths,
  all documented draft operations, draft routes, official unavailability, actual Synthelite
  tree shape, map-renumbering alignment, stereo information loss, unsupported cases, and
  symmetric indeterminacy.

Official SynthEx ReactionJSON/RouteJSON remain unavailable at
`5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f`. Synthelite support remains pinned to
`45168f8a5846c2fd15a833eddc88bac843b5bbee` and requires explicit mapping metadata.

Next: Phase 6 structural, reaction-centre, synthon-completion, and stereo audits with
stage-specific standalone HTML output.

## Phase 6 — stage-specific reaction audit

Status: **accepted on 2026-08-31**.

Branch: `codex/06-stage-specific-audit`

Implemented `StructuralAudit`, `ReactionCentreAudit`, `SynthonCompletionAudit`, `StereoAudit`,
and `ReactionAuditor` on the shared `CheckResultV1` protocol. The full executor runs once and
its core, completion, and stereo evidence remains separated. `StageAuditResultV1` and
`ReactionAuditResultV1` enforce stage/category, blocking, and structural-validity invariants
and have a committed JSON Schema.

The structural stage covers map uniqueness and references, sanitation/valence, formal charge,
aromatic/Kekule consistency, connectivity, empty/single-atom fragments, atom conservation,
unexplained graph changes, no-ops, and transparent edit complexity. Centre audit checks
sequential bond state, exact core diff, rings, symmetry, and expected-precursor reconstruction.
Completion audit checks fragment parsing and identity, multi-attachment, atom attribution,
retention, charge/valence, and precursor reconstruction. Stereo audit checks topology, CIP
intent, E/Z neighbours, silent erasure, new centres, symmetry, and cyclic paths.

The standalone report renderer embeds CSS and RDKit SVG, shows product → synthon → completion →
stereo stages, displays every unavailable/indeterminate check, includes provenance and the
mandatory scientific notice, and writes a versioned JSON sidecar.

Verification:

- `make quality`: ruff and strict mypy passed;
- `make schemas`: generated `reaction-audit-result-v1.schema.json`; committed-schema regression
  passed;
- `make test`: 157 passed, total coverage 88%; structural audit 96%, completion audit 85%,
  reaction-centre audit 82%, stereo audit 82%, and audit HTML renderer 94%;
- 31 Phase 6 tests cover success, invalid maps/valence/fragments, dangling references,
  disconnected graphs, excessive edits, no-ops, unexplained changes, add/change/detach/state
  edits, multi-attachment, unusual fragments, centre mismatch, symmetry, rings, tetrahedral
  inversion/R/S, E/Z neighbours, cyclic stereo, embedded SVG, and JSON sidecars;
- `make smoke`, `make benchmark-small`, and `make reactseq-conformance-small` passed offline;
- report smoke wrote `/private/tmp/synthaudit-phase6-report.html` (73,726 bytes) and its JSON
  sidecar with `blocking=false` and `structurally_valid=true` for the declared example only.

No audit result is experimental validation. Corpus-based leaving-group novelty remains
unavailable until a versioned reference index exists, and advanced stereo/coordination cases
remain explicit limitations.

Next: Phase 7 multi-view novelty, versioned precedent index, optional ReactSeq MEO and taxonomy
providers, and evidence-preserving retrieval.

## Phase 7 — multi-view novelty and precedent

Status: **accepted on 2026-08-31**.

Branch: `codex/07-novelty-and-precedent`

Implemented independent product/precursor Morgan and scaffold views, SynthAudit reaction-
difference and changed-bond/changed-atom views, normalized edit/centre/ring/fragment/attachment
views, optional ReactSeq MEO and taxonomy-provider boundaries, a content-addressed local reference
index, and six-axis precedent retrieval. Every available fingerprint metric is exactly one minus
the maximum reference-set Tanimoto similarity; learned MEO distance remains separate. No
weighted novelty or plausibility composite exists.

Reference indexes record corpus identity/version, record count and SHA-256, fingerprint/RDKit
versions, source license statuses, and provenance. Stored learned embeddings require artifact
provenance. Precedents separately expose substrate, product, transformation, reaction-centre,
leaving-group, and stereo similarities plus metric versions, conditions/yield when supplied,
missing evidence, and source/license provenance. Procedure and condition providers fail closed
unless explicit licensed local evidence is configured.

Verification:

- `make quality`: ruff and strict mypy passed for 65 source files;
- `make schemas`: generated five Phase 7 schemas and committed-schema regression passed;
- `make test`: 172 passed, total coverage 88%; novelty engine 80%, novelty fingerprints 90%,
  novelty models 85%, novelty providers 92%, precedent models 87%, and retrieval 84%;
- import-order subprocess regressions prove the lazy `novelty` and `precedent` package APIs do
  not form a runtime cycle;
- `make smoke`, `make benchmark-small`, and `make reactseq-conformance-small` passed offline;
- a two-record authored smoke index returned exact self-match novelty 0.0 for product,
  reaction-difference, and changed-bond/changed-atom views, ranked the declared substitution
  fixture first, and kept ReactSeq MEO unavailable. This is calculation plumbing evidence only,
  not a population benchmark.

Phase 7 adds no external corpus, model, checkpoint, download, or SynthAtlas scrape. Novelty is
corpus-relative, precedent is support rather than experimental validation, and the documented
0.5/0.7 interpretation thresholds are descriptive defaults rather than fitted boundaries.

Next: Phase 8 deterministic stage-aware counterfactual generation, grouped leakage-resistant
splits, dataset card, and human-review sheet.
