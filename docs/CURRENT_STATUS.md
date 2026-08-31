# Current status

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

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

## Phase 8 — stage-aware counterfactual benchmark

Status: **accepted on 2026-08-31**.

Branch: `codex/08-counterfactual-benchmark`

Implemented versioned counterfactual record, dataset, split, structural-validity, and validation
schemas. Generated records are restricted to the label `generated_counterfactual`; parents use
`recorded_reaction`. The schema requires parent reaction ID, generation method, seed, category,
difficulty, exact JSON Pointer before/after changes, and an observed structural-validity result.
Malformed payloads retain raw input and validation errors rather than being repaired.

`CounterfactualGenerator` implements all 29 specified methods across representation, reaction-
centre, completion, stereo, and route categories. Every method is seed-deterministic and has a
declared difficulty. Route validation combines per-step `ReactionExecutor` results with declared
dependency order and produced/consumed node availability; later chemical route checks remain a
separate Phase 10 responsibility.

The committed `synthaudit-authored-counterfactual-fixture/1` contains exactly 200 records: 20
authored unmutated parents and 180 generated counterfactuals. It is content-addressed at
`027dcf9b59210b5c1452890072c8eb0da69eafd980857e25475afb03ab200317`, covers all methods and
categories, and regenerates byte-for-byte. Its purpose is `software_verification_fixture`; it is
not an external corpus or experimental evidence and its metrics status is `not_run`.

Grouped split manifests keep descendants atomic by parent, product scaffold, and reaction class.
The fixture materializes parent/in-distribution, scaffold-holdout, and reaction-class-holdout
train/calibration/test partitions. High-novelty membership is computed as one minus maximum
training-product Morgan Tanimoto using a declared 0.70 threshold and content digest; ring-forming
and stereo-sensitive slices are separately tagged. A blank human-review sheet includes nine hard,
structurally valid generated candidates and makes no reviewer-result claim.

Verification:

- `make quality`: ruff and strict mypy passed for 72 source files;
- `make schemas`: generated four Phase 8 data/split/validation schemas and committed-schema
  regression passed;
- `make test`: 208 passed, total coverage 87%; dataset storage 96%, structural validity 97%,
  counterfactual models 88%, generator 83%, grouped splits 82%, and artifact validation 73%;
- 34 focused generator/data tests exercise all 29 methods, exact change traces, both label
  contracts, raw malformed payloads, deterministic regeneration, digest tamper rejection, all
  route mutations, group leakage rejection, and special-slice contracts;
- `make benchmark-small` validated all 200 records, 29 methods, five categories, three grouped
  split strategies, three non-empty special test slices, and nine eligible blank review rows;
- `make smoke` and `make reactseq-conformance-small` passed offline.

The research-scale local MVP targets of 10,000 recorded reactions, 20,000 counterfactuals, and
5,000 hard structurally valid counterfactuals were not run because no licensed corpus is
configured. No performance result or experimental outcome is inferred from the small fixture.

Next: Phase 9 stage-specific logistic/HGB evidence baselines, held-out calibration, bootstrap and
provider uncertainty, missing-evidence flags, and abstention.

## Phase 9 — calibrated stage-specific evidence models

Status: **accepted on 2026-08-31**.

Branch: `codex/09-calibrated-evidence-models`

Implemented strict contracts for reaction-centre support, completion support conditional on a
supported centre, stereo-specification support, and route-context support. The six required roles
remain explicit: corpus familiarity, deterministic structural checking, reaction centre,
completion, stereo, and full evidence ensemble. Corpus-familiarity features are rejected from the
primary plausibility models rather than treated as evidence against a novel reaction.

`EvidenceFeatureEncoder` fits feature order, median imputation, scaling, and parent-group digests
on training examples only while appending visible missing flags. Logistic regression and histogram
gradient boosting train only on `train`; Platt and isotonic calibration use disjoint grouped
`calibration` data. Model manifests preserve feature schema, versions, hyperparameters, random
seed, partition digests, configuration digest, provenance, and distinct raw/calibrated semantics.

Uncertainty combines parent-group bootstrap summaries, provider disagreement, missing-evidence
fraction, and train-standardized OOD diagnostics. Abstention thresholds are prespecified or fitted
only from held-out calibration diagnostics and every abstention has explicit reasons. Evaluation
supports reliability bins, novelty-stratified calibration, scaffold/reaction-class OOD splits,
selective risk/coverage, and report-only feature-group ablations; test data cannot enter fitting or
threshold selection.

Optional forward and independent-critic providers fail closed. Forward evidence requires model or
checkpoint provenance and never labels its raw score as calibrated. The critic is disabled by
default and available outputs require versioned prompts, multiple raw samples, token/cost totals,
provenance, and explicit independence from the generation provider. A local registry resolves
only explicitly fitted models and never downloads an artifact.

Verification:

- `make quality`: ruff and strict mypy passed for 87 source files;
- `make schemas`: generated nine Phase 9 configuration/evidence/provider schemas and the
  committed-schema regression passed;
- `make test`: 226 passed, total coverage 86%; 18 focused Phase 9 tests cover all four stages,
  both estimators, both calibrators, split leakage, conditional completion labels, bootstrap,
  missingness, provider disagreement, OOD, abstention, evaluation, ablations, providers, registry,
  feature extraction, and the versioned plan;
- `make evidence-model-small`: exercised the complete contract on authored numeric data and
  returned `metrics_status=not_reportable_software_fixture` without publishing metric values;
- `make smoke`, `make benchmark-small`, and `make reactseq-conformance-small` passed offline with
  prior artifact digests and fixture-scoped claims unchanged.

No licensed research training corpus, adjudicated support-label set, selected model, forward
checkpoint, serialized research artifact, or reportable performance result exists. Calibrated
outputs remain evidence-support scores, never experimental feasibility probabilities.

Next: Phase 10 route dependencies/continuity/condition ordering and a provider-neutral prompt-
robustness benchmark covering exact, partial, ambiguous, incorrect, and contradictory guidance.

## Phase 10 — route context and prompt robustness

Status: **accepted on 2026-08-31**.

Branch: `codex/10-route-and-prompt-robustness`

Implemented `RouteAuditor` with 18 named route checks and a versioned `RouteAuditResultV1`.
Every step retains its step ID and complete reaction audit. Dependency cycles/order, terminal target
production, declared material and mapped-graph continuity, atom-map continuity, unexplained
intermediates, redundant steps, protection/deprotection timing, fragile-intermediate condition
lifetime, structural/completion/stereo status, step support, uncertainty, and key-step novelty
remain separately visible.

Primary route summaries expose minimum available calibrated step support, maximum uncertainty and
contributing steps, structural blockers, unresolved completion failures, stereo-sensitive steps,
high-novelty key steps, critical condition conflicts, and a priority-sorted expert queue. There is
no route-success-probability field. The naive independence product is opt-in, requires all step
support values, and cannot validate without its explicit “not a route success probability” label.

Implemented a deterministic provider-neutral prompt benchmark for exact, partial, ambiguous,
incorrect-but-structurally-plausible, and contradictory prompts. Cases retain reference semantic
hash, parent group, seed, versioned structured instructions, rendered text, exact mutation trace,
and provenance. Provider outputs preserve raw response, raw versus calibrated confidence
semantics, candidate-or-abstention state, and provenance. Evaluation covers all required prompt
metrics against the reference representation and supports independent multi-provider reliability
summaries without treating any provider or LLM as ground truth.

The committed `synthaudit-authored-prompt-robustness-fixture/1` contains eight eligible authored
Phase 8 parents and 40 prompt variants, eight of each kind. It regenerates byte-for-byte and is
content-addressed at `d643a37597efc39105be2507a6c587b2f9fd120db8577062990899e43a48274c`.
It contains no model outputs or experimental labels and reports `metrics_status=not_run`.

Verification:

- `make quality`: ruff and strict mypy passed for 96 source files;
- `make schemas`: generated nine Phase 10 route/prompt/dataset/provider schemas and the
  committed-schema regression passed;
- `make test`: 249 passed, total coverage 86%; route audit coverage is 91%, prompt dataset 86%,
  prompt evaluation 88%, prompt generator 82%, and prompt contracts 82%;
- 23 Phase 10 tests cover all five route perturbations, cycles/order/target/material/atom-map
  continuity, protection and condition conflicts, opt-in aggregation labeling, all five prompt
  kinds, deterministic generation, provider failure/accounting, all required prompt metrics,
  two-provider comparison, import-order independence, dataset tamper rejection, and byte-exact
  regeneration;
- `make prompt-benchmark-small` validated 8 cases, 40 variants, parent-group atomicity, and the
  committed digest without running metrics;
- `make route-prompt-small` exercised 18 route checks, detected all five route perturbation classes,
  emitted all five prompt variants, kept the default provider unavailable, and reported
  `metrics_status=not_run`;
- prior offline version, counterfactual, evidence-model, and ReactSeq smoke contracts remain
  unchanged.

No prompt-capable model, LLM, checkpoint, paid API, or network service was invoked. Reference
agreement is not experimental truth; protection/condition rules are transparent declared-context
checks rather than comprehensive synthetic-chemistry adjudication.

Next: Phase 11 complete CLI workflows, Streamlit interface, expanded standalone reports, and
committed example outputs after applying the required UI/UX and diagram skills.

## Phase 11 — CLI, interactive product, and standalone reports

Status: **accepted on 2026-08-31**.

Branch: `codex/11-cli-ui-and-reports`

Implemented a shared application layer and complete Typer command tree for declared
representation normalization, ReactSeq parsing, reaction execution and comparison, reaction and
route audits, benchmark construction/validation, counterfactual and prompt contracts, local
precedent and novelty workflows, explicit data transfer/preparation, stage-model training and
held-out evaluation, report generation, and UI launch/validation. Machine-readable commands use a
versioned success/error envelope where appropriate, fail with nonzero status on blocking audits or
invalid inputs, and never map, repair, download, or trust serialized models implicitly.

Added checksum- and license-gated local/HTTP data manifests with network disabled by default.
Serialized evidence models require an exact SHA-256 manifest match and an explicit
`--trust-artifact` acknowledgement before trusted-local pickle loading. Training accepts only
train plus disjoint calibration partitions; evaluation accepts a held-out partition and cannot
refit the model or its abstention policy.

The five-page Streamlit product now contains Representation Explorer, Single Reaction Audit,
Route Audit, Benchmark, and Methodology and Limitations pages. The pages call package workflows
rather than carrying chemistry algorithms in Streamlit files. They expose stage-specific results,
token-to-atom traversal, graph edits, route continuity, local precedent/novelty, missing-evidence
states, and downloadable artifacts without synthesizing unavailable scores. The UI uses local
system fonts/assets, visible keyboard focus, 44-pixel controls, reduced-motion handling, and a
responsive dark data-workspace layout.

Standalone reaction and route reports are responsive, print-friendly, serverless HTML documents
with embedded RDKit/SVG structures, versioned JSON sidecars, provenance, model/corpus versions,
limitations, and the required scientific boundary notice. Missing corpus, provider, or calibrated
model evidence is rendered as unavailable rather than zero or negative evidence. Committed
reaction/route examples and an accessible architecture SVG regenerate byte-for-byte through
`make product-examples`; editable Mermaid source and a task-oriented product guide are also
included.

Verification:

- `make quality`: ruff formatting/lint and strict mypy passed for 108 source files;
- `make schemas`: generated nine Phase 11 schemas and committed-schema regression passed;
- `make test`: 270 passed, total branch coverage 86%; application workflows 73%, data transfer
  82%, trusted artifacts 90%, report models 83%, standalone rendering 92%, and UI helpers 80%;
- 22 focused product/regression tests cover application normalization, CLI success and structured
  failures, reaction/route reports, XSS escaping, sidecar collision prevention, local data/index,
  explicit artifact trust, benchmark workspace facts, all five Streamlit page startups, every new
  schema, required notices, and byte-exact example regeneration;
- `make reproduce-small` passed offline, including version, five-page UI, reaction/route CLI,
  200-record counterfactual validation, evidence-model contract, 40 prompt variants, route/prompt
  contract, and three pinned ReactSeq examples;
- the architecture SVG rendered successfully through the diagram toolchain and the five pages
  also started under `streamlit.testing.v1.AppTest`.

The committed benchmark and reports remain authored software fixtures. No licensed research
corpus, official SynthEx schema, selected research model, paid provider, browser-compatibility
certification, experimental feasibility result, or reportable population metric is claimed.

Next: Phase 12 reproducible research/evaluation package, technical report, cards, release
materials, and PhD-application narrative without fabricating unavailable scientific results.

## Phase 12 — research evaluation and v1.0 release package

Status: **accepted on 2026-08-31**.

Branch: `codex/12-research-evaluation-and-release`

Released the software architecture as v1.0.0 while keeping research availability fail-closed.
`ReleaseEvaluationManifestV1` records source SHA-256 digests, RQ1-RQ7 status, all 17 required
metric statuses, nested offline contract observations, provenance, and the mandatory notice. Its
validators permit numerical values only for explicitly scoped software-fixture observations;
`not_run` research metrics cannot contain a value, count, sample size, or confidence interval.
Future intervals are required to bootstrap parent reaction or route IDs.

`scripts/build_release_evaluation.py` runs all justified offline experiments and deterministically
generates a manifest, RQ table, metric table, fixture-observation table, two accessible SVG
figures, README, and `SHA256SUMS`. RQ1 has one alternate-traversal pair with equal ReactionIR
semantic hashes plus three pinned conformance cases; RQ6 has five authored route perturbation
classes detected by the 18-check route contract. These are fixture-only observations. RQ2-RQ5 and
RQ7 remain `not_run`. Completion accuracy, stereo retention, AUROC, AUPRC, Brier score, Expected
Calibration Error, false rejection/acceptance, selective risk, coverage, and high-novelty false
rejection have no release value.

The v1.0 provenance migration regenerated the authored counterfactual and prompt fixtures without
changing their labels, composition, or intended use. Their current content digests are
`027dcf9b59210b5c1452890072c8eb0da69eafd980857e25475afb03ab200317` and
`d643a37597efc39105be2507a6c587b2f9fd120db8577062990899e43a48274c` respectively; both still
report research metrics as `not_run` and regenerate byte-for-byte.

Added the complete technical report, release-level model and dataset cards, changelog, release
notes/checklist, and the five required PhD application documents. All public Markdown reports,
methodology documents, cards, ADRs, and examples now display the exact scientific boundary, with a
regression test enforcing it. Placeholder repository URLs were removed because this checkout has
no configured remote.

Package, lock, runtime, and citation metadata now identify v1.0.0. The wheel force-includes the
Streamlit theme and five UI pages; the CLI resolves the source application first and bundled wheel
resources otherwise. Docker now includes app, benchmark, config, docs, examples, reports, schemas,
and scripts rather than only the package.

Verification:

- `uv lock --check`: resolved the existing 72-package lock without changes;
- `make quality`: ruff lint/format and strict mypy passed for 109 source files;
- `make schemas`: generated `release-evaluation-v1.schema.json`, and committed-schema regression
  passed;
- `make test`: 277 passed, total branch coverage 86%; release evaluation 84%, core executor 96%,
  completion executor 94%, stereo executor 93%, structural audit 96%, mapped-reaction adapter 92%,
  route audit 91%, standalone reports 92%, and ReactSeq conformance 91%;
- release tests reject pre-filled `not_run` metrics, enforce all RQ/metric entries and scientific
  notices, verify metadata/UI packaging, validate all source/output hashes, and regenerate the
  release package byte-for-byte;
- `make reproduce-small` passed the full quality/test gate plus version, five-page UI, reaction and
  route CLI, 200-record counterfactual validation, four-stage evidence-model contract, 40 prompt
  variants, route/prompt contract, three ReactSeq demos, and release-evaluation generation;
- `uv build` produced `synthaudit-1.0.0.tar.gz` and `synthaudit-1.0.0-py3-none-any.whl` in a
  temporary directory; the archives exclude local caches, the wheel contains all five pages and
  theme, and an isolated target installation reported v1.0.0 with `ui --check` page count five;
- both Phase 12 SVGs passed the diagram rendering tool, byte comparison, PNG conversion, and
  visual inspection; Compose and citation YAML parsed successfully.

One environment warning remains: joblib cannot query physical core count in this restricted host
and falls back to logical cores. Docker is not installed, so image build/runtime validation was
unavailable; the release wheel and YAML were validated separately. No licensed external corpus,
official SynthEx schema, ReactSeq checkpoint, prompt provider, GPU experiment, laboratory result,
Git remote, push, or hosted release exists.

Next: configure a verified Git remote and publish only when authorized; run the uncompleted
research questions only under a separately licensed, preregistered, parent-grouped protocol.
