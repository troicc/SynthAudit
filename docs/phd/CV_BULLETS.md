# SynthAudit — CV bullets

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

- Designed and implemented a representation-agnostic reaction/route auditing architecture with
  versioned Pydantic schemas, stable atom-map identity, and transactional RDKit execution from
  mapped product to mapped precursor set.
- Built traversal-aware ReactSeq normalization, mapped-reaction and draft-only SynthEx adapters,
  inspected Synthelite route integration, semantic graph comparison, and fail-closed boundaries for
  undocumented formats and unavailable checkpoints.
- Separated reaction-centre, completion, stereo, structural, novelty, precedent, calibrated
  evidence, uncertainty, and route-context outputs; prohibited inverse-novelty plausibility and
  route-success-probability claims by schema and tests.
- Delivered a complete Typer CLI, five-page Streamlit research workspace, standalone embedded
  reaction/route reports, Docker/uv environment, generated JSON Schemas, and 270+ offline unit,
  property, conformance, regression, and UI startup tests.
- Created content-addressed 200-record counterfactual and 40-variant prompt software fixtures with
  exact mutation traces, parent-grouped splits, data cards, deterministic regeneration, and
  leakage checks without calling them experimental outcomes.
- Published a typed v1.0 evaluation manifest, accessible figures, metric/RQ status tables, model
  and dataset cards, and a technical report that reports unavailable experiments as `not_run`
  instead of fabricating performance.
