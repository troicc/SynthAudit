# SynthAudit v1.0 model card

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Status

**No research model is selected, published, or bundled in v1.0.** This card describes the model
interfaces, training safeguards, and unavailable evaluation state. The release exercises four
stage-model contracts on authored numeric software fixtures, but those outputs are not model-
selection or chemistry-performance evidence.

## Intended model quantities

| Stage | Target quantity | Required interpretation |
|---|---|---|
| Reaction centre | `reaction_centre_supported` | Evidence support for declared centre/edit consistency |
| Completion | `completion_supported_given_reaction_centre` | Evidence support for completion conditional on centre support |
| Stereo | `stereo_specification_supported` | Evidence support for the declared stereo specification |
| Route context | `route_context_supported` | Evidence support from declared dependencies, continuity, and conditions |

Even when held-out calibrated, these are evidence-support scores, not experimental feasibility,
yield, selectivity, safety, scalability, or route-success probabilities.

## Candidate architecture

- Base estimators: logistic regression and histogram gradient boosting.
- Calibration: Platt or isotonic fit only on a parent-disjoint calibration partition.
- Features: separately versioned structural, centre, completion, stereo, condition, precedent,
  forward, provider-agreement, and route-context evidence with explicit missingness flags.
- Novelty boundary: corpus-familiarity features are excluded from primary plausibility models and
  remain separate outputs.
- Uncertainty: parent-group bootstrap, provider disagreement, missingness, and train-standardized
  OOD diagnostics.
- Abstention: explicit reasons and thresholds fitted only from calibration data when data-derived.

## Training and evaluation data

No licensed research training set or adjudicated support-label dataset is included. The only
numeric model fixture is SynthAudit-authored software data that exercises estimator, calibrator,
bootstrap, OOD, ablation, missingness, disagreement, and abstention APIs. Recorded reactions are
not automatically positive labels; generated counterfactuals are not experimental negatives.

The v1.0 release evaluation records AUROC, AUPRC, Brier score, Expected Calibration Error, false
rejection, false acceptance, selective risk, coverage, and high-novelty false rejection as
`not_run`. No confidence interval is published. Future intervals must resample parent reaction or
route IDs.

## Artifact and security boundary

The CLI can persist a locally trained `TrainedEvidenceModel` as an environment-sensitive pickle
plus a versioned SHA-256 descriptor. Loading requires an explicit `--trust-model-artifact` flag,
checksum equality, type validation, and model-manifest equality. Pickle can execute code and is
not a portable public checkpoint format. No artifact is loaded or downloaded at import time.

Optional forward and independent-critic providers fail closed. Available outputs must retain
model/checkpoint version, license, raw confidence semantics, uncertainty, raw responses where
applicable, and provenance. An LLM critic cannot be the sole ground truth.

## Intended uses

- leakage-controlled research on evidence-support annotations;
- comparison of transparent baselines under frozen grouped splits;
- uncertainty, calibration, abstention, and OOD studies;
- optional evidence feeding a human review queue.

## Out-of-scope uses

- predicting whether a reaction will work in a laboratory;
- reporting yield, selectivity, safety, scale, or route success;
- treating corpus novelty as negative plausibility evidence;
- loading untrusted pickle artifacts;
- selecting thresholds or models using a test set;
- using one LLM or one generated reference as experimental truth.

## Reproduction and detailed contract

Run `make evidence-model-small` to exercise the software contract and `make release-evaluation` to
regenerate its release status. See [the detailed evidence-model contract](EVIDENCE_MODEL_CARD.md),
[model selection](MODEL_SELECTION.md), and the
[technical report](TECHNICAL_REPORT.md). Research deployment requires a new model card naming the
actual dataset, labels, splits, selection protocol, metrics, intervals, artifact digest, license,
and external validation.
