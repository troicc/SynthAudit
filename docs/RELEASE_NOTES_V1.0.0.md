# SynthAudit v1.0.0 release notes

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit v1.0.0 completes the reproducible software architecture defined by the master execution
specification: canonical reaction/route IR, transactional staged graph execution, representation
adapters, independent audit/evidence layers, route and prompt contracts, complete CLI, five-page
interactive demo, standalone reports, and a release research package.

## Release highlights

- `ReactionIRV1` keeps mapped product-to-precursor semantics independent of source syntax.
- Transactional execution retains RDKit failures and never returns a partially edited structure as
  success.
- ReactSeq traversal positions resolve through graph atoms to stable maps; symmetric ambiguity
  remains explicit.
- Novelty, precedent, structural validity, calibrated evidence, and uncertainty remain separate.
- Route output exposes blockers, minimum available step support, maximum uncertainty, condition
  conflicts, and review priority without a route success probability.
- CLI and five Streamlit pages share package workflows; HTML reaction/route reports are embedded,
  serverless, print-friendly, and paired with JSON sidecars.
- Offline release evaluation produces a typed manifest, three CSV tables, two accessible figures,
  and checksums with no pre-filled research metrics.

## Research status at release

The committed observations are software-fixture evidence only. One authored traversal pair has
equal ReactionIR semantic hashes, three pinned ReactSeq demos parse/execute/reconstruct, and five
authored route perturbation classes are detected. These observations are not population estimates.

RQ2-RQ5 and RQ7, completion accuracy, stereo retention, AUROC, AUPRC, Brier score, Expected
Calibration Error, false rejection/acceptance, selective risk, coverage, and high-novelty false
rejection remain `not_run`. See the [technical report](TECHNICAL_REPORT.md).

## Install and verify

```bash
make install
make schemas
make product-examples
make release-evaluation
make reproduce-small
```

Python 3.11, `uv.lock`, and Docker define the reference environment. Core verification uses no
network, paid API, large dataset, or model download.

The release sdist and wheel were built successfully in a temporary directory. The wheel includes
the Streamlit theme and five pages; an isolated target installation returned version `1.0.0` and
passed `synthaudit ui --check` outside the source tree. Docker was unavailable on the build host,
so image execution remains an environment-specific publication check.

## Publication boundary

This checkout has no configured Git remote. The v1.0.0 commit and local release artifacts can be
prepared and verified here, but pushing a branch/tag or creating a hosted release requires a
real repository URL and separate authorization. No placeholder publication URL is advertised.
