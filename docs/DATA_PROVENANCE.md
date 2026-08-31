# Data provenance and redistribution policy

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit does not redistribute an external reaction corpus in the repository and does not
scrape SynthAtlas. A user-supplied reference record must retain its source dataset, source
reaction ID, data-license status, and original reaction evidence. The enclosing index adds a
corpus ID/version, deterministic SHA-256, fingerprint specification, and build provenance.

Repository unit-test reactions and the Phase 7 smoke corpus are authored synthetic fixtures for
software verification. Labels such as `CC0-fixture` describe fixture-only terms and do not imply
that any external chemistry dataset is CC0. They are not a population benchmark and must not be
used to report scientific performance.

The three ReactSeq golden examples are copied from public demo files at pinned commit
`9838a3058e32e1c0ee04b2bab0448104dc293384` under the upstream repository's LGPL-2.1 code
license context, with attribution recorded in their fixture manifest. Dataset and checkpoint
links named by upstream require separate provenance and redistribution review; they are not
vendored here.

Before indexing an external corpus, record at least:

- source name, immutable version or release date, and stable record IDs;
- license or access terms for reactions, conditions, yields, and procedures separately;
- acquisition method and date, with any transformations or filters;
- atom-mapping, normalization, deduplication, and split procedures;
- content checksum and record count;
- provenance and checksum for every learned embedding or classification artifact.

Unknown licensing is not permission to copy or redistribute. Procedure text is accepted only
through an explicit local provider whose record includes license status and provenance. Missing
or legally unavailable fields remain unavailable; they are never reconstructed from a retrieved
neighbour or filled from an unrelated source.
