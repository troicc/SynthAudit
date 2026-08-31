# SynthAudit: representation-aware auditing for trustworthy AI retrosynthesis

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Motivation

AI retrosynthesis is usually evaluated at the level of a predicted reaction string, template, or
route. Yet the same intended transformation can be expressed as mapped reaction SMILES, a graph-
edit program, a traversal-dependent language such as ReactSeq, a planner tree, or a prompt-guided
model response. These formats do not merely differ syntactically: they encode atom identity,
leaving groups, charge, hydrogens, stereo, and route dependencies with different conventions and
different unsupported cases. A model can therefore appear wrong because of representation
mismatch, appear right after an invalid silent repair, or pass a string comparison while encoding
a different graph transformation.

My proposed research direction is to treat representation auditing as an independent layer between
generation and chemical assessment. SynthAudit provides the software foundation. Its canonical
`ReactionIRV1` expresses the retrosynthetic direction from a mapped product through reaction-centre
edits to synthons, through explicit completion to mapped precursors, and finally through stereo
verification. Every operation uses atom-map identity. A `RouteIRV1` adds dependency and material-
flow structure without changing the direction of each reaction object.

## Technical approach

Execution is transactional. Reaction-centre, fragment-completion, atom-state, and stereo executors
work on graph copies; failures report the exact operation index, affected maps, graph diff, and
RDKit sanitation evidence. Strict mode rolls back, while diagnostic mode can retain an invalid
intermediate for inspection without calling it valid. Representation comparison operates on
normalized edits and executed precursor graphs, not raw ReactSeq/SMILES equality. Symmetric mapping
or incomplete stereo can therefore produce an explicit indeterminate result.

The audit layer separates deterministic structural checks from corpus and model evidence.
Reaction-centre and completion consistency remain distinct, stereo has its own stage, and novelty
is measured against a declared versioned corpus through multiple visible views. Precedent retrieval
separates substrate, product, transformation, centre, leaving group, and stereo similarity.
Stage-specific evidence models can use held-out calibration, parent-group bootstrap, missingness,
provider disagreement, OOD diagnostics, and abstention, while corpus familiarity is excluded from
the primary plausibility feature set. This prevents novelty from becoming a hidden penalty.

At route level, the system checks dependencies, ordering, material and atom-map continuity,
unexplained intermediates, protecting-group timing, fragile-condition lifetimes, and per-step audit
status. It summarizes minimum available step support and maximum uncertainty without multiplying
step values into a route success probability. A provider-neutral prompt benchmark preserves exact,
partial, ambiguous, incorrect-but-plausible, and contradictory instructions alongside raw model
responses and provenance.

## Research questions and evaluation plan

The planned study asks whether traversal variants normalize to equal ReactionIR semantics; how
errors distribute across centre, completion, stereo, and representation stages; whether
ReactSeq_MEO complements deterministic novelty views; whether novelty/plausibility separation
reduces high-novelty false rejection; how prompt-guided models react to degraded advice; whether
route audits detect failures missed by independent step audits; and how SynthEx, Synthelite, and
ReactSeq outputs differ once compatible data exist.

Metrics include parse and exact-reconstruction success, centre precision/recall/F1, completion and
leaving-group accuracy, stereo retention, AUROC, AUPRC, Brier score, Expected Calibration Error,
false rejection/acceptance, selective risk, coverage, and high-novelty false rejection. Splits keep
all descendants of one parent together and include scaffold and reaction-class holdouts. Bootstrap
resampling uses parent reaction or route IDs. Test data cannot select models, calibrators,
thresholds, or ablations.

The present v1.0 release deliberately distinguishes software readiness from completed science. It
contains 200 authored counterfactual records, 40 authored prompt variants, three pinned ReactSeq
demos, and five route perturbation classes. One traversal pair has equal semantic hashes, the three
demos reconstruct, and all five authored route perturbations are detected. Those observations test
contracts only. Error prevalence, MEO complementarity, false rejection, prompt-model robustness,
calibration, and cross-system comparisons remain `not_run` because their licensed data, labels,
checkpoints, providers, or official schemas are not yet available.

## Research contribution and next steps

SynthAudit turns heterogeneous retrosynthesis outputs into inspectable evidence rather than a
single opaque score. The immediate research program is to acquire a legally usable mapped corpus,
freeze an annotation protocol, measure reviewer agreement, reproduce eligible checkpoints, and
preregister grouped evaluation. I would then study which errors are representational versus
chemical, when the system should abstain, and whether stage separation improves expert review of
novel proposals.

The broader contribution is methodological: trustworthy AI for chemistry needs interfaces that
preserve uncertainty, provenance, and failure semantics across model boundaries. SynthAudit is a
reproducible platform for testing that claim without treating recorded data, generated
counterfactuals, or one model critic as experimental ground truth.
