# Stage-specific evidence model contract

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

Status: **software contract implemented; no research model artifact selected or released**.

This card describes the Phase 9 modelling, calibration, uncertainty, evaluation, and provider
boundaries. The committed numeric fixture exists only to exercise those boundaries. It is not a
licensed reaction corpus, a chemistry study, or evidence of model performance.

## Intended outputs

SynthAudit models four quantities independently:

| Stage | Target annotation | Required interpretation |
|---|---|---|
| Reaction centre | `reaction_centre_supported` | Support for the declared centre and edits |
| Completion | `completion_supported_given_reaction_centre` | Support for leaving-group/attachment completion, conditional on centre support |
| Stereo | `stereo_specification_supported` | Support for the declared stereochemical specification |
| Route | `route_context_supported` | Support from route context, continuity, dependencies, and conditions |

Targets are binary evidence-support annotations. They are not experimental successes or failures,
and their scores are not feasibility, yield, selectivity, safety, or scale probabilities. The
completion schema rejects examples that do not explicitly declare the centre-support condition.

## Baselines and feature boundaries

The versioned plan declares all six required roles:

1. corpus-familiarity baseline;
2. deterministic structural-check baseline;
3. reaction-centre evidence model;
4. completion evidence model;
5. stereo evidence model;
6. full evidence ensemble.

Corpus familiarity is reported separately from plausibility. It can contain nearest-neighbour
similarity, reaction-class frequency/recognition, embedding distance, and corpus percentile.
Primary plausibility models reject the `corpus_familiarity` feature group rather than penalizing a
reaction merely for being novel. Their possible evidence groups are structural, reaction centre,
completion, stereo, condition, precedent, forward model, provider agreement, and route context.

Every feature carries an availability state, interpretation, and provenance when numeric. Missing
values remain visible as named flags. Train-derived median imputation and standardization never
erase those flags.

## Training and calibration protocol

- Base estimators are `LogisticRegression` and `HistGradientBoostingClassifier`; no neural model is
  selected by default.
- The feature schema, medians, means, and scales are fitted only on `train` examples.
- Parent-group overlap between training and calibration is rejected.
- Platt scaling and isotonic regression are fitted only on the held-out `calibration` split.
- The `test`, `ood_scaffold`, and `ood_reaction_class` splits cannot be passed to fitting APIs.
- Test data is evaluation-only and must not select a calibrator, model, threshold, or ablation.
- Every manifest records the estimator family, calibration method, feature schema, random seed,
  scikit-learn version, hyperparameters, parent-group digests, configuration digest, and provenance.
- Raw estimator output is named `uncalibrated_model_score`. Only a held-out calibrated output can
  use the name `calibrated_evidence_support_score`, and even that is not an experimental
  probability.

The committed plan is
[`configs/evidence-models-v1.json`](../configs/evidence-models-v1.json). Its
`model_selection_status` is `not_run`; it does not designate a scientific winner.

## Uncertainty and abstention

Bootstrap ensembles resample whole parent groups. Predictions can expose member count, mean,
standard deviation, and a 90% empirical interval. Provider disagreement is a separate range and
standard-deviation record and requires at least two available providers. Missing-feature fraction
and maximum train-standardized absolute z-score are explicit diagnostics.

An abstention policy combines bootstrap uncertainty, missing evidence, OOD diagnostics, missing
calibration, and provider disagreement. Data-derived policy thresholds may be fitted only from
held-out calibration diagnostics and retain a digest of those parent groups. Every abstention
contains human-readable reasons; the system never converts absent evidence into a successful
empty result.

## Evaluation and ablations

The evaluator supports AUROC, average precision, Brier score, expected calibration error,
selective risk, coverage, and reliability-bin data. It creates low-, middle-, high-, and
unavailable-novelty calibration slices. Scaffold and reaction-class OOD splits are represented
explicitly. Feature-group ablations keep test results report-only and reject attempts to
reintroduce corpus familiarity into the primary plausibility model.

No research-scale evaluation has run. The authored smoke fixture suppresses metric values in its
CLI summary and reports `metrics_status=not_reportable_software_fixture`.

## Optional provider boundary

`ForwardReactionProvider` accepts mapped precursors, optional conditions, target product, and
top-k. Available evidence must return ranked products, target rank/similarity when known, model
uncertainty when known, and checkpoint/model provenance. Raw provider confidence is explicitly
not calibrated. The default provider returns `unavailable`; no checkpoint is downloaded.

`IndependentCriticProvider` is disabled by default. Available evidence requires multiple samples,
versioned prompt IDs, raw responses, rationales, token accounting, reported cost, provenance, and
an explicit assertion that the critic is independent of the generation provider. It is forbidden
as the sole plausibility source.

The in-memory registry resolves only models explicitly fitted and registered in the current
process. Unknown IDs fail closed and cannot trigger a network or artifact download. The CLI can
also persist a trusted local model as an environment-sensitive pickle plus a SHA-256 descriptor;
loading requires explicit trust, digest equality, type validation, and model-manifest equality.
No serialized research model is bundled or loaded automatically.

## Reproduction boundary

Run `make evidence-model-small` to exercise all four stage contracts, both estimator families,
both calibrators, grouped bootstrap, missingness, disagreement, abstention, OOD evaluation, and
ablations on authored numeric data. Run `make test` for leakage and invariant tests. Neither
command trains a publishable chemistry model or produces a reportable scientific metric.

## Limitations before research use

A real study still requires a licensed, content-addressed reaction corpus; documented support-label
protocol and reviewer agreement; frozen grouped splits; class/scaffold coverage analysis; model
selection that is independent of test data; complete calibration and OOD reports; artifact
serialization and checksum verification; and external or prospective validation. Performance and
calibration may shift with corpus, label source, mapper, RDKit version, fingerprint, provider,
reaction class, novelty stratum, and missing-evidence pattern.
