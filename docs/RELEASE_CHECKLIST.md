# SynthAudit v1.0.0 release checklist

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

## Artifact and metadata

- [x] Package, runtime, lockfile, and citation versions are `1.0.0`.
- [x] Placeholder repository URLs are absent.
- [x] Changelog and release notes describe the scientific boundary.
- [x] Docker includes the CLI, five-page UI, examples, Schemas, benchmarks, reports, and scripts.
- [x] Built `synthaudit-1.0.0.tar.gz` and `synthaudit-1.0.0-py3-none-any.whl` in a temporary directory.
- [x] Wheel contains the Streamlit theme and all five pages; an isolated target install passes `ui --check` outside the source tree.
- [x] Technical report, model card, dataset card, and five PhD documents exist.
- [x] Evaluation manifest records source SHA-256 digests and all RQ/metric statuses.
- [x] Generated evaluation tables/figures reproduce byte-for-byte.

## Scientific claims

- [x] Fixture observations are labelled `software_verification_fixture`.
- [x] Unrun research metrics contain no numerical values.
- [x] Counterfactuals are not described as experimental failures.
- [x] Recorded reactions are not described as guaranteed successes.
- [x] Novelty is not treated as infeasibility or inverse plausibility.
- [x] No official SynthEx compatibility is claimed.
- [x] No route success probability is emitted.
- [x] Public reports and methodology pages display the mandatory notice.

## Verification

- [x] `uv lock --check` passes for the release metadata.
- [x] Formatter and ruff lint pass.
- [x] Strict mypy passes.
- [x] Full offline tests and coverage pass.
- [x] Schema generation and committed-schema regression pass.
- [x] Product examples and release evaluation regenerate byte-for-byte.
- [x] CLI, UI, benchmark, model-contract, route/prompt, and ReactSeq smokes pass.
- [x] Compose and citation YAML parse successfully; Docker-engine validation is recorded as unavailable on this host.

## Publication operations

- [x] Configure the verified `https://github.com/troicc/SynthAudit` remote and record its URL in package and citation metadata.
- [ ] Push `main` when authorized.
- [ ] Push the `v1.0.0` tag when authorized.
- [ ] Create a hosted release and attach/checksum artifacts when authorized.

Unchecked publication operations are external-state actions, not missing local software features.
