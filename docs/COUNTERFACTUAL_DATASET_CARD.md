# SynthAudit counterfactual fixture dataset card

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Artifact identity

- Dataset ID: `synthaudit-authored-counterfactual-fixture`
- Dataset version: `1`
- Purpose: `software_verification_fixture`
- Generator: `synthaudit.counterfactual-generator/1`
- Global seed: `20260831`
- Records SHA-256: `027dcf9b59210b5c1452890072c8eb0da69eafd980857e25475afb03ab200317`
- Metrics status: `not_run`

The committed artifact contains exactly 200 small examples: 20 unmutated parent records labelled
`recorded_reaction` and 180 controlled descendants labelled `generated_counterfactual`. These are
authored software-verification fixtures under Apache-2.0, not an external reaction corpus and not
experimental outcome evidence. Here, `recorded_reaction` means the unmodified parent side of the
benchmark contract; it does not mean guaranteed success, observed yield, or laboratory validation.

## Composition

The 180 generated records cover all 29 declared methods and all five stage categories:

| Category | Records |
|---|---:|
| representation | 69 |
| reaction centre | 28 |
| completion | 21 |
| stereo | 44 |
| route | 18 |

Difficulty metadata contains 100 easy, 46 medium, and 34 hard generated examples. Difficulty is
a generator-design annotation, not a measured human or model difficulty result. The supplied
human-review sheet selects the nine hard generated candidates that also passed deterministic
structural validation; its reviewer judgement cells are intentionally blank.

Each generated record retains its parent reaction ID, route ID when applicable, enumerated method,
seed, category, difficulty, exact JSON Pointer changes with before/after values, candidate payload,
and an observed structural-validity result. Invalid schema payloads are retained as raw payloads
with their validation errors. They are not silently repaired.

## Labels and appropriate claims

The only labels are `recorded_reaction` and `generated_counterfactual`. A counterfactual is a
controlled mutation, not an experimental failure. Structural validity states whether the current
ReactionIR/route validator and executor accepted the candidate; a structurally valid candidate can
still lack chemical support, and a recorded parent is not asserted to be feasible.

This fixture is suitable for:

- schema, serialization, hash, generator, and audit-pipeline regression tests;
- checking that stage labels and exact changed fields survive processing;
- testing grouped split and calibration plumbing without network access;
- exercising a human-review workflow before licensed research data are supplied.

It is not suitable for scientific performance claims, model selection, threshold selection,
reaction feasibility training, yield prediction, or population-level error estimates.

## Generation coverage

Representation mutations cover duplicate/dangling maps, malformed edits, absent attachment
references, impossible ordering, and invalid leaving-group syntax. Centre mutations cover wrong
break/order/site/ring choices, class-preserving centre decoys, and omitted graph changes.
Completion mutations cover leaving-group identity/presence/duplication, attachment site, missing
handles, charge-only errors, and multi-attachment topology. Stereo mutations cover inversion,
omission, E/Z, invalid centres, and cyclic corruption. Route mutations cover dependency order,
protection/deprotection timing, declared fragile-condition conflicts, and unproduced precursors.

## Split policy

All descendants of one parent remain atomic in every split. Three independently materialized
strategies use groups based on parent reaction, product Murcko scaffold, and reaction class:

| Strategy | Train | Calibration | Test |
|---|---:|---:|---:|
| parent/in-distribution | 140 | 30 | 30 |
| scaffold holdout | 170 | 10 | 20 |
| reaction-class holdout | 120 | 40 | 40 |

Special test slices contain 50 high-novelty, 40 ring-forming, and 80 stereo-sensitive records.
These are membership counts, not accuracy results. High novelty is computed—not hand-entered—as
`1 - maximum training-product Morgan Tanimoto` with radius 2, 2,048 bits, chirality enabled, and a
predeclared 0.70 threshold. The training reference manifest digest is
`3860e557d5dc0d642b446e95a2617833ef669f851bc09173dac586db303f978e`.

## Files and regeneration

- `benchmarks/counterfactual-v1/records.jsonl`: canonical content-addressed records;
- `benchmarks/counterfactual-v1/manifest.json`: counts, purpose, terms, seed, and digest;
- `benchmarks/counterfactual-v1/splits.json`: assignments and novelty-slice provenance;
- `benchmarks/counterfactual-v1/human-review.csv`: blank review worksheet for hard valid cases.

Run `make counterfactual-fixture` to regenerate all four files and `make benchmark-small` to
validate digest, schema, method/category coverage, grouped splits, required slices, and review-row
eligibility. Regression tests require byte-for-byte regeneration.

## Research-scale status

The local MVP targets of at least 10,000 recorded reactions, 20,000 counterfactuals, and 5,000
hard structurally valid counterfactuals have not been run because no licensed research corpus was
configured in this offline repository. Those targets must not be inferred from or extrapolated
from this 200-record software fixture.
