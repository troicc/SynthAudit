# SynthAudit — PhD project summary

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit is a representation-agnostic audit layer for reaction-edit retrosynthesis. Modern
retrosynthesis systems emit mapped reaction SMILES, graph edits, custom languages such as
ReactSeq, planner trees, or natural-language-guided candidates. These representations overlap in
chemical meaning but differ in traversal order, identifiers, completeness, stereochemical
expressivity, and failure behavior. SynthAudit asks a narrower and scientifically useful question:
can an independent system normalize, execute, compare, and explain the declared transformation
without assuming that a plausible-looking string is chemically or experimentally correct?

The project introduces a versioned canonical intermediate representation, `ReactionIRV1`, in the
retrosynthetic direction from mapped product to mapped precursor set. Reaction-centre edits,
synthon completion, atom-state changes, and stereo operations are typed separately and use stable
atom-map identities. Transactional RDKit execution works on copies, retains operation-level and
sanitation failures, and never returns a partial modification as success. A companion `RouteIRV1`
represents step dependencies while keeping each embedded reaction in the same canonical
retrosynthetic direction.

The scientific design separates four questions that are often collapsed: representation
consistency, synthon-completion consistency, corpus novelty, and evidence-based plausibility. The
software adds multi-view novelty, six-axis precedent retrieval, stage-specific calibrated evidence
model contracts, uncertainty and abstention, route continuity/condition checks, and a prompt-
robustness framework. Novelty is never used as inverse plausibility, and route step scores are not
multiplied into a success probability.

The implementation is an offline-first Python 3.11 package with generated JSON Schemas, a complete
Typer CLI, five-page Streamlit workspace, embedded standalone HTML/JSON reports, Docker/uv
reproducibility, and more than 270 offline tests. It includes deterministic authored
counterfactual/prompt fixtures and pinned ReactSeq demo cases, all content-addressed and explicitly
limited to software verification.

The v1.0 technical report is intentionally honest about research readiness. One authored
alternate-traversal pair normalizes to equal ReactionIR semantics, three pinned ReactSeq demos
parse/execute/reconstruct, and five authored route perturbation classes are detected. These are
fixture observations, not population results. Large-corpus error distributions, ReactSeq_MEO
novelty complementarity, high-novelty false rejection, prompt-model robustness, calibration
metrics, and cross-system SynthEx/Synthelite/ReactSeq comparisons remain unrun until licensed
datasets, adjudicated labels, checkpoints, providers, and official schemas are available.

As a PhD research platform, SynthAudit offers a reproducible basis for studying representation
invariance, error localization, novelty/plausibility decoupling, calibrated abstention, and route-
level failure detection. Its main contribution is not a claim that retrosynthetic proposals are
experimentally feasible; it is an auditable interface between heterogeneous generative systems
and evidence-driven chemical review.
