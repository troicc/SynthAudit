# Data provenance and redistribution policy

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit does not redistribute an external reaction corpus in the repository and does not
scrape SynthAtlas. A user-supplied reference record must retain its source dataset, source
reaction ID, data-license status, and original reaction evidence. The enclosing index adds a
corpus ID/version, deterministic SHA-256, fingerprint specification, and build provenance.

Repository unit-test reactions and the Phase 7 smoke corpus are authored synthetic fixtures for
software verification. Labels such as `CC0-fixture` describe fixture-only terms and do not imply
that any external chemistry dataset is CC0. They are not a population benchmark and must not be
used to report scientific performance.

The Phase 8 200-record counterfactual artifact is likewise authored and identifies itself as
`software_verification_fixture`. Its source-license string explicitly says that it is not
experimental reaction evidence. The required label `recorded_reaction` identifies an unmodified
parent record inside the data contract; it does not assert a literature report, experimental
success, yield, or feasibility. Its manifest and split files are content-addressed, and its
scientific metrics remain `not_run`.

The three ReactSeq golden examples are copied from public demo files at pinned commit
`9838a3058e32e1c0ee04b2bab0448104dc293384` under the upstream repository's LGPL-2.1 code
license context, with attribution recorded in their fixture manifest. Dataset and checkpoint
links named by upstream require separate provenance and redistribution review; they are not
vendored here.

Before indexing an external corpus, record at least:

- source name, immutable version or release date, and stable record IDs;
- license or access terms for reactions, conditions, yields, and procedures separately;
- acquisition method and date, with any transformations or filters;
- atom-mapping, normalization, deduplication, and split procedures;
- content checksum and record count;
- provenance and checksum for every learned embedding or classification artifact.

Unknown licensing is not permission to copy or redistribute. Procedure text is accepted only
through an explicit local provider whose record includes license status and provenance. Missing
or legally unavailable fields remain unavailable; they are never reconstructed from a retrieved
neighbour or filled from an unrelated source.

## Phase 9 label and model provenance

An evidence-training example must record its parent group, split, stage, support annotation,
annotation source, feature provenance, and overall record provenance. Completion examples must
state that the reaction-centre support condition holds. A recorded reaction is not automatically
assigned a positive support label, and a generated counterfactual is not automatically assigned a
negative experimental label.

The Phase 9 smoke data is authored numeric software-fixture data. It has no experimental source
and cannot be mixed into a scientific evaluation. Real model artifacts must retain the corpus and
label versions, grouped-split manifest, feature schema, estimator/calibrator configuration,
scikit-learn version, random seed, train/calibration group digests, final artifact digest, and
license status. No research model artifact or metric is currently published.

## Phase 10 route and prompt provenance

Route audit results retain the route provenance, per-step ReactionIR provenance, per-step audit,
and provenance for every optional support/uncertainty/novelty value. Literal node IDs and
canonicalized molecular tokens support continuity checks, while atom-map identity is checked
separately and never silently normalized.

The prompt fixture derives from eight eligible `recorded_reaction` parents in the authored Phase 8
software fixture. It contains 40 deterministic variants and is content-addressed at
`d643a37597efc39105be2507a6c587b2f9fd120db8577062990899e43a48274c`. It carries no model output
or experimental label and reports `metrics_status=not_run`. Provider-backed research outputs must
add provider/model versions, prompt version, raw response, confidence semantics, calibration
method when applicable, token/cost metadata where applicable, and artifact provenance.

## Phase 11 product artifacts

`examples/reaction-ir.json`, `examples/route-ir.json`, and `reports/examples/*` are generated from
SynthAudit-authored software examples by `scripts/build_product_examples.py`. They contain no
external corpus record, model output, experimental label, yield, or feasibility assertion. The
HTML reports retain missing corpus/model evidence as unavailable and embed all visual assets.

The data-download CLI accepts only an explicit versioned manifest containing source URI,
destination, SHA-256, media type, license status, and provenance. Remote access is off by default.
The reference-index preparation command accepts strict `ReferenceReactionV1` JSONL and preserves
each caller-supplied source/license field; SynthAudit does not adjudicate whether the caller has
redistribution permission.

## Phase 12 release-evaluation provenance

The v1.0 release evaluation introduces no external reactions, checkpoint, provider output, or
experimental label. `reports/research-evaluation-v1/manifest.json` content-addresses the committed
counterfactual records/manifest/splits/review sheet, prompt cases/manifest, pinned ReactSeq golden
fixture, and evidence-model plan. `SHA256SUMS` covers every generated manifest/table/figure/README
artifact except the checksum list itself, and regression tests require byte-exact regeneration.

Numeric values in `required-metric-status.csv` are restricted by schema to
`software_verification_fixture` observations and state their sample count. Research metrics that
were not run cannot contain a value, numerator, denominator, sample count, or confidence interval.
RQ1 and RQ6 have fixture-only evidence; RQ2-RQ5 and RQ7 remain `not_run`. Future uncertainty
estimates must bootstrap parent reaction or route IDs and retain the new study's data, label,
model, and provider provenance.
