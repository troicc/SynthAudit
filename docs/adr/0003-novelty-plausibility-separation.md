# ADR 0003: Keep novelty separate from plausibility evidence

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

- Status: Accepted
- Date: 2026-08-31

## Context

Corpus distance measures familiarity, not whether a proposal is chemically supported. Collapsing the two rejects creative but supported chemistry and can accept familiar malformed reactions.

## Decision

Return independent structure, reaction-difference, edit-semantic, optional learned-embedding, and taxonomy novelty views. The first scalar baseline is `1 - max(Tanimoto)` for a named reference set. Plausibility uses separate deterministic, precedent, condition, forward-provider, and consistency features, with stage-specific calibration and abstention. Novelty is never an automatic negative term.

## Consequences

Reports are more verbose but scientifically interpretable. A composite score may be introduced only after a declared benchmark and ablation demonstrate its meaning; it can never be named experimental feasibility.
