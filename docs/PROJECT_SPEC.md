# SynthAudit v2 project specification

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Mission

SynthAudit is a representation-agnostic audit layer for reaction-edit retrosynthesis. It normalizes mapped reaction SMILES, ReactSeq, the explicitly named `synthaudit.synthex-paper-draft/0.1` format, supported Synthelite route exports, and future adapters into versioned canonical models.

The canonical retrosynthetic direction is:

```text
mapped product -> reaction-centre edits -> synthons
               -> atom-state/attachment completion -> precursors
               -> stereo verification -> normalized result
```

Four independent questions are retained throughout the schema, API, CLI, reports, and models:

1. Is the reaction-centre representation internally consistent?
2. Is synthon completion internally consistent?
3. How familiar is the transformation relative to a declared corpus?
4. What independent evidence supports its plausibility, and what remains uncertain?

Novelty is never the inverse of plausibility. No output establishes experimental feasibility, yield, selectivity, safety, or scalability.

## Canonical domain model

`ReactionIRV1` is independent of all source formats and contains a mapped product, optional expected precursor set, typed core edits, typed attachment edits, typed atom-state edits, typed stereo edits, conditions, stage metadata, provenance, source payload reference, and open metadata. All operations use stable atom-map numbers.

`RouteIRV1` is an ordered dependency graph of `RouteStepIRV1` objects, each containing a `ReactionIRV1`. Route outputs expose blocking steps and review priorities, not a route success probability.

Pydantic v2 discriminated unions define:

- core edits: break, add, and change bond order;
- attachment edits: attach and detach explicit fragments, including null and charge-only completion;
- atom-state edits: charge, explicit hydrogen, isotope, aromaticity, and supported atomic-number changes;
- stereo edits: set/invert/clear tetrahedral configuration and set/clear bond stereo.

## Execution and comparison

Execution is transactional and stage-specific. `CoreGraphExecutor`, `AttachmentCompletionExecutor`, and `StereoExecutor` operate on copies, retain intermediate structures, and report operation index, affected maps, warnings, graph diff, and structured RDKit errors. Strict sanitation fails the operation; diagnostic sanitation preserves the graph for inspection while never labelling it structurally valid.

Representation comparison uses normalized graph edits and reconstructed precursor sets. Raw ReactSeq strings and raw SMILES strings are not semantic equality keys. Symmetry or incomplete stereo information can produce an explicit `indeterminate` comparison.

## Auditing

All checks implement a shared result protocol: `check_id`, category, severity, status, message, affected atom maps, evidence, references, and whether the result is deterministic. Primary components are structural, reaction-centre, synthon-completion, stereo, and route audits.

## Novelty, precedent, and evidence

Novelty returns separate structure, reaction-difference, edit-semantic, optional learned-embedding, and taxonomy views. The primary numeric baseline is `1 - maximum reference-set Tanimoto similarity`; no unbenchmarked weighted composite is presented.

Precedent retrieval separates substrate, product, transformation, reaction-centre, leaving-group, and stereo similarity with source and license provenance. A retrieved reaction is precedent support, not experimental validation of the query.

Stage-specific evidence models estimate support for reaction centre, completion, stereo, and route context. Outputs are evidence-model quantities. Initial learnable baselines are logistic regression and histogram gradient boosting, with held-out calibration, bootstrap/provider uncertainty, missing-evidence flags, and abstention.

## Adapter boundaries

- Mapped reaction SMILES must already be mapped. Mapping is never implicit.
- ReactSeq parsing is traversal-aware and resolves traversal positions through RDKit atoms to stable maps. The official legacy converter is isolated behind a JSONL subprocess boundary.
- No official SynthEx adapter delegates to the draft adapter. Until official schemas exist, it raises `UpstreamSpecificationUnavailable`.
- The draft adapter supports only documented operation names and rejects ambiguous fragments.
- Synthelite support targets inspected, version-pinned exported route structures and reports unsupported fields.

## Offline and reproducibility contract

Core install, schemas, deterministic execution, audit, small fixtures, CLI smoke tests, and standalone reports run without a paid API, model checkpoint, large dataset, or network. Optional providers never download at import time. Network, upstream, slow, and GPU tests are explicitly marked.

Python 3.11, RDKit, Pydantic v2, NumPy, Pandas, PyArrow, scikit-learn, Typer, Rich, Jinja2, NetworkX, Streamlit, pytest, Hypothesis, ruff, and mypy form the reference stack. `uv.lock` and Docker are the reproducibility boundaries.

## Release acceptance

### v0.1 reproducible core

- versioned ReactionIR/RouteIR and JSON Schemas;
- mapped-reaction adapter and staged transactional executor;
- safe ReactSeq subset plus official bridge and conformance fixtures;
- structural, centre, completion, and stereo audits;
- semantic comparison, CLI, and standalone HTML report;
- offline unit/property tests and a small reproducible example.

### v0.2 research layer

- multi-view novelty and precedent index;
- controlled counterfactuals with grouped splits;
- calibrated stage-specific evidence models, uncertainty, and abstention.

### v1.0 interoperability and route layer

- official ReactionJSON/RouteJSON only if released and pinned;
- otherwise explicitly draft-only SynthEx support;
- Synthelite route support, route audit, prompt robustness framework;
- cross-representation benchmark, five-page demo, technical and PhD materials.

Large-corpus and provider-backed experiments remain reproducible research runs, not unit-test or release-install requirements. Results are never pre-filled.
