# Prompt-robustness software fixture data card

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Identity and purpose

- Dataset: `synthaudit-authored-prompt-robustness-fixture`, version `1`.
- Purpose: deterministic software verification of prompt generation, storage, and validation.
- Cases: 8; variants: 40, with 8 exact, partial, ambiguous, incorrect-but-structurally-
  plausible, and contradictory variants each.
- Cases SHA-256: `568bda2e9e90559200b74e2955fafe5b3c9e33c9cc79f52871fe78c642cacfa5`.
- Metrics status: `not_run`.

## Source and selection

Cases derive only from the authored
`synthaudit-authored-counterfactual-fixture/1` software fixture at records SHA-256
`932c04d282f3b72a9587c0247f2045c8b11df8c3b6a3034d4eaf0bb9ec9d0c99`. The source label
`recorded_reaction` means an unmutated reference representation, not guaranteed experimental
success. No external corpus, procedure, yield, or experimental outcome is included.

Eligible parents have at least one declared reaction-centre edit and at least two total edit
operations. All five variants remain embedded in one case with the source parent-group ID.

## Generation

`scripts/build_prompt_fixture.py` uses global seed `20261800` plus the sorted eligible-record index.
Every prompt preserves the reference semantic hash, prompt version, mutation trace, structured
instructions, rendered text, and provenance. Incorrect-site prompts use an existing mapped product
bond or a verified product bond with a wrong order instruction. No model generated these prompts.

## Intended and prohibited uses

The fixture may test deterministic regeneration, schema validation, provider adapters, metric
plumbing, and UI/report layout. It must not be used to claim prompt-model accuracy, calibration,
chemical correctness, experimental feasibility, or comparative model quality. Research use
requires a separately licensed corpus, frozen grouped splits, registered models, and a predeclared
evaluation protocol.
