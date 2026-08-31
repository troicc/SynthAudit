# Research questions and evaluation contract

## Questions

- **RQ1:** Can ReactSeq strings generated from different valid product-SMILES traversals normalize to equivalent ReactionIR semantics?
- **RQ2:** How often do detected errors originate in reaction-centre selection, synthon completion, stereochemistry, or representation integrity?
- **RQ3:** When a reproducible checkpoint is available, does ReactSeq_MEO add novelty information beyond molecular, reaction-difference, and edit-semantic fingerprints?
- **RQ4:** Does separating corpus novelty from plausibility evidence reduce false rejection of high-novelty recorded reactions?
- **RQ5:** How robust are prompt-guided models to exact, partial, ambiguous, plausible-but-incorrect, and contradictory prompts?
- **RQ6:** Can route auditing identify dependency and condition-order failures invisible to independent single-step auditing?
- **RQ7:** When compatible data exist, how do SynthEx, Synthelite, and corpus-trained ReactSeq outputs differ in template recognition, edit novelty, ring formation, precedent support, structural failure, completion uncertainty, and stereo uncertainty?

## Outcomes and metrics

Representation outcomes include parse success, exact precursor reconstruction, centre precision/recall/F1, attachment accuracy, leaving-group exact match, charge consistency, map preservation, stereo retention, ring-change consistency, and structured failure category.

Evidence-model outcomes include AUROC, AUPRC, Brier score, Expected Calibration Error, false rejection/acceptance rates, selective risk, coverage, and high-novelty false rejection rate. Confidence intervals bootstrap parent reaction or route IDs.

## Split and leakage contract

All derivatives of one recorded parent remain in the same split. Evaluations include grouped parent-reaction, product-scaffold, and reaction-class splits plus high-novelty, ring-forming, and stereo-sensitive subsets. Calibration/threshold fitting never uses a test split. Corpus construction dates and all artifact hashes are recorded.

## Counterfactual labels

Positive corpus records are `recorded_reaction`; controlled alternatives are `generated_counterfactual`. Counterfactuals retain parent ID, generator/version, seed, changed fields, deterministic structural result, and difficulty. Neither label is an experimental outcome.

## Result policy

This repository provides evaluation pipelines and empty result-table templates until a versioned dataset experiment is actually run. No numerical result is pre-filled. Optional model/prompt experiments are excluded from unit tests.
