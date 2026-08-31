# Scientific claims and terminology

## Mandatory notice

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Claims the software may support

Subject to named inputs, corpus versions, provider versions, and uncertainty, SynthAudit may report:

- structural validity or a structured sanitation failure;
- reaction-centre consistency;
- synthon-completion consistency;
- stereo consistency or indeterminacy;
- corpus novelty under a declared fingerprint/metric/reference set;
- precedent support and condition-transfer evidence;
- evidence-based plausibility and calibrated uncertainty;
- expert-review priority.

## Claims the software must not make

SynthAudit does not prove experimental feasibility, experimental success, yield, chemo-/regio-/stereoselectivity, scalability, safety, or laboratory validation. Fields such as `reaction_will_work`, `experimentally_feasible`, `validated_feasibility`, `guaranteed_success`, and `route_success_probability` are prohibited.

Recorded corpus entries are labelled `recorded_reaction`, not guaranteed successes. Controlled negatives are labelled `generated_counterfactual`, not experimental failures. Retrieved reactions provide precedent evidence for specific dimensions; they do not validate the query.

## Novelty and plausibility

Novelty and plausibility are separate axes. `plausibility = 1 - novelty` is forbidden. A result can be familiar but inconsistent, novel but strongly supported, or novel and uncertain. Missing novelty evidence is not low novelty, and missing plausibility evidence is not evidence of implausibility.

Raw model confidence is not a calibrated probability. A calibrated value must name its target event, calibration method, fit split, corpus/model version, coverage, and uncertainty. Route step values are not multiplied and called route success probability.

## Evidence hierarchy

1. Deterministic representation/schema and graph-execution checks.
2. Declared structural and reaction-centre similarity metrics.
3. Versioned corpus precedent and condition evidence.
4. Independently versioned forward/classification providers.
5. Calibrated statistical evidence models.
6. Optional independent LLM criticism, never used as sole ground truth.

All reports distinguish unavailable, indeterminate, unsupported, warning, and failure states.
