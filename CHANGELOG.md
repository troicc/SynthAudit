# Changelog

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

All notable changes to SynthAudit are documented here.

## 1.0.0 — 2026-08-31

### Added

- Versioned representation-agnostic `ReactionIRV1` and `RouteIRV1` contracts with generated JSON
  Schemas and provenance.
- Transactional product-to-precursor execution with separate reaction-centre, completion, stereo,
  sanitation, rollback, and graph-diff evidence.
- Safe traversal-aware ReactSeq support, isolated official-runtime bridge, pinned conformance
  fixtures, mapped-reaction adapter, draft-only SynthEx boundary, and inspected Synthelite route
  adapter.
- Structural, reaction-centre, completion, stereo, novelty, precedent, evidence-model, uncertainty,
  abstention, route-context, and prompt-robustness layers.
- Complete CLI, five-page Streamlit workspace, standalone reaction/route HTML reports, JSON
  sidecars, diagrams, and reproducible product examples.
- Deterministic counterfactual and prompt software fixtures with grouped splits, cards, digests,
  and regression tests.
- Typed v1.0 release-evaluation manifest, generated RQ/metric tables, accessible figures,
  technical report, model/dataset cards, and PhD-application materials.

### Scientific status

- RQ1 and RQ6 have only explicitly scoped software-fixture observations.
- RQ2-RQ5 and RQ7 remain `not_run` because required licensed data, labels, checkpoints, providers,
  or official schemas are unavailable.
- No result establishes experimental feasibility, yield, selectivity, safety, scalability, or
  route success.

### Changed

- Package version advanced from `0.1.0` to `1.0.0` and the development classifier advanced from
  Alpha to Beta.
- The Docker image now includes the UI, examples, Schemas, benchmark fixtures, reports, configs,
  docs, and offline release scripts.
- Placeholder repository URLs were removed because this checkout has no configured Git remote.

### Compatibility boundary

Official SynthEx ReactionJSON/RouteJSON remains unavailable at the pinned upstream revision. The
v1.0 release therefore provides an explicitly named paper-draft adapter and a fail-closed official
adapter, as permitted by the project specification; it makes no official SynthEx compatibility
claim.
