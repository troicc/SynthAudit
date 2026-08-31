# Multi-view novelty and precedent methodology

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

SynthAudit reports independent, corpus-relative views. It does not combine novelty into an
unbenchmarked weighted score and it never treats novelty as the inverse of plausibility.

## Primary numerical baseline

For each available fingerprint view, the first numerical baseline is exactly:

```text
novelty = 1 - max(Tanimoto(query, reference_i))
```

The result records the maximum similarity, every tied nearest reference ID, corpus ID and
version, fingerprint implementation and parameters, and the reference-record SHA-256. An empty
or incomparable corpus yields `unavailable` or `indeterminate`, never a fabricated number.

The fixed local baseline uses RDKit Morgan fingerprints with radius 2, 2,048 bits, and
chirality. SynthAudit reaction-difference fingerprints use separate gained/lost Morgan bit
spaces. Semantic profiles use stable SHA-256 token hashing. Atom maps identify edits during
execution but are replaced by product-environment descriptors in normalized semantic tokens,
so a pure map renumbering does not create novelty.

## Independent views

1. **Structure:** product Morgan, precursor Morgan, product scaffold, and precursor scaffold.
2. **Reaction difference:** SynthAudit reaction difference and an explicit changed-bond/changed-
   atom profile. DRFP is a separate optional provider and remains unavailable when absent.
3. **Edit semantics:** normalized edit signature, reaction-centre neighbourhood, ring-change,
   fragmentation, and attachment profiles.
4. **Learned transformation:** ReactSeq MEO only through an explicitly configured provider and
   artifact provenance. It uses one minus maximum normalized cosine similarity and is not the
   primary Tanimoto baseline.
5. **Taxonomy:** optional ReactionClassifier or another named provider. A provider raw score is
   labelled as such and is not called a calibrated probability.

Interpretations use declared thresholds: 0.5 for structural/transformation familiarity and
0.7 for a close reaction-centre precedent. They are descriptive labels, not validated chemical
decision boundaries. The result can say structurally familiar and transformation-familiar,
structurally novel but transformation-familiar, structurally familiar but transformation-novel,
novel with a close centre precedent, novel with no close precedent, or unavailable evidence.

## Reference index

`ReferenceIndex` is local, deterministic, and versioned. Records are ordered by source dataset
and source reaction ID. The manifest includes corpus identity/version, record count, content
SHA-256, fingerprint specification, source license statuses, and build provenance. Loading
recomputes the digest and rejects tampering. No network request, corpus download, model download,
or atom mapping occurs during indexing.

Stored ReactSeq MEO vectors require model/artifact provenance. Source reaction identity is the
pair `(source_dataset, source_reaction_id)`, which prevents unrelated datasets from colliding
while preserving their own identifiers.

## Precedent evidence

Precedent retrieval keeps six similarities separate:

- substrate Morgan similarity;
- product Morgan similarity;
- transformation-difference similarity;
- reaction-centre similarity;
- leaving-group/attachment similarity;
- stereo-edit similarity.

Hits are ranked transparently and lexicographically in that order of evidence priority:
transformation, centre, product, substrate, leaving group, then stereo. Missing axes sort below
available axes and remain visible. There is no hidden aggregate similarity. Each hit records the
source dataset and reaction ID, license status, metric names, fingerprint version, conditions and
reported yield when supplied legally, missing evidence, and provenance.

A strong transformation match with a weak substrate match is explicitly distinguished from a
close substrate analogue. Procedure and condition providers expose only configured, licensed
local evidence; their default implementation fails closed. Retrieved procedures, conditions,
or yields are contextual precedent support, not validation or a claim that transfer will work.

## Reproducibility contract

To compare results, retain the complete result JSON and reference-index manifest. A numeric
value without its corpus digest and fingerprint specification is not a reproducible SynthAudit
novelty result. Updating RDKit, hashing parameters, preprocessing, records, model artifacts, or
provider implementations creates a distinct evidence context and must not silently overwrite an
earlier result.
