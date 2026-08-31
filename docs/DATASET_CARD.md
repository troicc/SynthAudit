# SynthAudit v1.0 dataset and fixture card

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Release data status

SynthAudit v1.0 redistributes **no external reaction corpus and no model checkpoint**. It contains
small authored or source-attributed fixtures for deterministic software verification. These
fixtures are not a chemistry benchmark, do not contain experimental outcome labels, and must not
be used for model selection or population claims.

## Artifact inventory

| Artifact | Composition | Identity and terms | Intended use |
|---|---|---|---|
| Counterfactual fixture | 20 authored unmutated parents and 180 controlled descendants; 29 methods | `synthaudit-authored-counterfactual-fixture/1`, records SHA-256 `027dcf9b59210b5c1452890072c8eb0da69eafd980857e25475afb03ab200317`; Apache-2.0 authored fixture | Generator, schema, split, validation, and review-workflow tests |
| Prompt fixture | 8 cases and 40 deterministic variants | `synthaudit-authored-prompt-robustness-fixture/1`, cases SHA-256 `d643a37597efc39105be2507a6c587b2f9fd120db8577062990899e43a48274c`; derived from the authored counterfactual fixture | Prompt storage/provider/evaluation plumbing without a model |
| ReactSeq golden fixture | 3 pinned public demo examples with locally added stable product maps | Source `ReactSeq@9838a3058e32e1c0ee04b2bab0448104dc293384`; upstream LGPL-2.1 code context and per-record attribution | Safe-subset conformance regression only |
| Product examples | One reaction and one two-step route plus reports | SynthAudit-authored Apache-2.0 software examples | CLI, UI, report, and documentation smoke tests |
| Numeric evidence fixture | Small balanced stage examples generated in code | SynthAudit-authored; no experimental source | Estimator/calibration/uncertainty API verification only |

## Labels and semantics

`recorded_reaction` means an unmodified parent inside the authored fixture contract; it does not
mean experimental success, feasibility, or a guaranteed literature outcome.
`generated_counterfactual` means a deterministic controlled mutation; it does not mean an
experimental failure. Structural validity records what the current parser/executor accepted, not
chemical support or laboratory feasibility.

Prompt kinds describe how an authored instruction relates to a declared ReactionIR reference.
Agreement with that reference is not experimental ground truth. The three ReactSeq cases are
source-attributed examples, not a representative sample.

## Splits and leakage controls

The counterfactual fixture materializes parent/in-distribution, product-scaffold holdout, and
reaction-class holdout partitions. Every derivative stays with its parent. High-novelty,
ring-forming, and stereo-sensitive membership counts test slice plumbing; they are not performance
results. Future confidence intervals must bootstrap parent reaction or route IDs.

No training, calibration, or threshold selection may use the test partition. The committed prompt
variants remain grouped by case and parent. No research model is selected from these fixtures.

## Known biases and limitations

- Authored cases emphasize contract and edit-type coverage rather than real-world frequency.
- The counterfactual category/difficulty distribution is designed, not measured.
- The ReactSeq set has only three cases and no evaluable stereo-retention target.
- Small structures and declared metadata underrepresent organometallic, coordination, complex
  stereo, protecting-group, and condition interactions.
- Adding stable maps locally is necessary for the canonical IR but is not an official ReactSeq
  mapping guarantee.
- No yields, procedures, safety data, laboratory results, or proprietary reaction records exist.

## Appropriate and prohibited uses

Appropriate uses are offline regression, schema validation, deterministic regeneration, UI/report
demonstration, and testing grouped evaluation plumbing. Prohibited uses include training a
chemistry-performance model, reporting accuracy or feasibility, selecting a scientific model,
estimating real error prevalence, or treating generated variants as experimental negatives.

## Provenance and regeneration

The release manifest records SHA-256 digests for all evaluation inputs. Run:

```bash
make counterfactual-fixture
make prompt-fixture
make product-examples
make release-evaluation
```

Regression tests require byte-exact regeneration. See the detailed
[counterfactual card](COUNTERFACTUAL_DATASET_CARD.md),
[prompt card](../benchmarks/prompt-robustness-v1/DATA_CARD.md),
[data provenance policy](DATA_PROVENANCE.md), and
[technical report](TECHNICAL_REPORT.md).
