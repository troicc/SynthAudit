# Route-context audit and prompt-robustness protocol

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

Phase 10 adds deterministic route-context auditing and a provider-neutral prompt benchmark. The
route layer summarizes independent evidence and creates a review queue. The prompt layer compares
model outputs with a declared reference representation. Neither layer supplies experimental truth.

## Route interpretation

`RouteIRV1.steps` is an ordered dependency plan in forward synthesis order. Each embedded
`ReactionIRV1` retains SynthAudit's canonical retrosynthetic direction from mapped product to
mapped precursor set. This distinction is intentional: dependencies describe when a synthetic
step can run, while the reaction object describes how that step is audited.

`RouteAuditor` runs the complete four-stage reaction audit for every step, preserving each step ID
beside its result. It then reports named route checks for:

- unique step IDs and valid dependency references already guaranteed by RouteIR validation;
- dependency cycles and declared ordering;
- target production by a terminal step;
- declared material flow and mapped precursor/intermediate continuity;
- atom-map identity for repeated intermediate graphs;
- unexplained intermediates and duplicate/redundant steps;
- protection/deprotection timing;
- condition-sensitive intermediate lifetime;
- structural blocking and unresolved completion failures;
- stereo-sensitive steps;
- minimum available calibrated step support and maximum available uncertainty;
- high-novelty key-step location; and
- the separately labelled exploratory independence product boundary.

Material tokens match first by exact identifier and, when parseable as SMILES, by canonical
unmapped molecular graph. This supports explicit node IDs and inspected Synthelite-style molecule
tokens without silently changing atom maps. Atom-map continuity is a separate check: conflicting
maps for a repeated intermediate fail rather than being renumbered.

## Conditions and protecting groups

Protection timing uses explicit step `strategy_text` labels (`protection`/`deprotection`) and
optional metadata keys `protection_groups` and `requires_protected_groups`. If a group is not
named, the check visibly applies a single `__unspecified__` bookkeeping group. It is a transparent
ordering rule, not a comprehensive protecting-group expert system.

Condition-sensitive lifetime uses intermediate `route_node_id` or `name`, the metadata key
`fragile_to_condition_tags`, optional step `condition_tags`, and structured reaction conditions.
The Phase 8 counterfactual marker `counterfactual_incompatible_condition` is also recognized as an
explicit declared conflict. No compatibility is inferred when constraints are absent; the result
is `unavailable`.

## Route outputs and non-aggregation

Primary outputs remain separate:

- minimum available calibrated step-support score;
- maximum uncertainty and contributing step IDs;
- structural blocking steps;
- unresolved completion failures;
- stereo-sensitive steps;
- high-novelty key steps;
- critical condition conflicts; and
- a priority-sorted expert-review queue.

There is no `route_success_probability` field. By default there is no product of step scores. A
caller can opt in to `exploratory_naive_independence_score` only when every step has calibrated
support evidence. Its required interpretation is “not a route success probability,” and the
schema rejects an unlabeled value.

## Prompt cases

A reaction is eligible when it has at least one reaction-centre operation and at least two total
declared edit operations. The generator then emits exactly one deterministic case for each prompt
quality:

1. **Exact:** all correct edit types and atom-map sites.
2. **Partial:** one correct edit, with every omitted reference instruction named.
3. **Ambiguous:** the edit family is retained while site identity is removed.
4. **Incorrect but structurally plausible:** an existing alternative product bond is selected, or
   a wrong bond-order instruction is applied to a verified product bond.
5. **Contradictory:** an explicit inverse/negating instruction is appended to a correct prompt.

Each variant stores a semantic hash of the unchanged reference reaction, seed, versioned prompt
ID, structured instructions, rendered text, exact mutation trace, relation to the reference, and
provenance. Atom maps are graph identities, never token positions. Ineligible reactions fail with
a reason instead of receiving fabricated prompt semantics.

## Provider and evaluation boundary

`PromptModelProvider` is optional. The default returns `unavailable`; unit tests and small
reproduction commands make no network request and invoke no external model. An available result
must preserve provider/model IDs, raw response, provenance, candidate-or-abstention state, and raw
confidence semantics. A calibrated evidence confidence requires an explicit calibration method.

For each provider/model independently, evaluation can report reaction-centre exact accuracy,
precursor exact match, completion accuracy, stereo accuracy, structural validity, prompt
obedience, recovery from an incorrect prompt, abstention, and confidence drop under contradiction.
Reliability summaries are split by calibrated versus raw confidence semantics. They measure
agreement with the reference representation and do not retroactively calibrate a raw score.
Multiple providers can be compared, but no provider or LLM becomes the truth label.

## Committed software fixture

The content-addressed prompt fixture contains eight eligible authored Phase 8 parent
representations and 40 prompt variants, eight of each kind. Its cases SHA-256 is
`d643a37597efc39105be2507a6c587b2f9fd120db8577062990899e43a48274c`. These counts and the
digest are artifact facts, not model results. `metrics_status` is `not_run`.

Run `make prompt-fixture` to regenerate it, `make prompt-benchmark-small` to verify the digest and
variant contract, and `make route-prompt-small` to exercise all five route perturbations and five
prompt kinds. Expensive/provider-backed prompt experiments must be separate integration or
research runs.
