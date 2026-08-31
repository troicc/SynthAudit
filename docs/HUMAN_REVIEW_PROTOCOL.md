# Counterfactual human-review protocol

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

The committed review sheet is a blank workflow artifact, not completed evidence. It includes only
generated counterfactuals whose generator difficulty is `hard` and whose candidate passed the
deterministic structural validator. Structural validity does not imply that the mutation is
chemically supported.

For each row, a reviewer should inspect the parent and candidate payloads in
`benchmarks/counterfactual-v1/records.jsonl`, confirm the exact changed fields, and complete:

- `reviewer_id`: a pseudonymous or study-specific reviewer identifier;
- `chemistry_support_judgement`: one of `supported`, `unsupported`, `indeterminate`, or
  `not_assessable` under the declared evidence available to the study;
- `ambiguity_reason`: symmetry, missing conditions, missing stereo, incomplete precedent,
  representation ambiguity, or another explicit reason;
- `review_notes`: concise evidence and any disagreement with the assigned category/difficulty.

Reviewers must not replace `generated_counterfactual` with “experimental failure,” and must not
replace `recorded_reaction` with “guaranteed success.” A later research run should prespecify
reviewer expertise, blinding, sampling, adjudication, agreement statistics, and conflict handling.
At least two independent reviewers are recommended for reported human-evaluation results, but no
such review has been performed or claimed for the committed fixture.
