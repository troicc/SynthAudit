# Model and fingerprint selection

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.

Phase 7 deliberately selects deterministic, inspectable fingerprints as the primary novelty
baseline. Morgan radius 2 / 2,048-bit fingerprints with chirality support structure views;
separated gained/lost Morgan bits support reaction difference; stable hashed edit tokens support
stage-specific semantic views. The numerical definition is `1 - maximum reference-set Tanimoto
similarity` for every available fingerprint view.

This baseline was selected because it is local, reproducible, versionable, and exposes a nearest
reference. It is not claimed to be an optimal chemical-distance model. Hash collisions, corpus
bias, tautomer/protonation choices, RDKit-version effects, and scaffold-free molecules remain
limitations.

## Optional learned and taxonomy providers

- **ReactSeq MEO:** the pinned repository contains extraction code, but no checkpoint is committed
  at the inspected revision. Until a checkpoint, license, SHA-256, environment, preprocessing,
  and inference path are reproduced, the default provider returns `unavailable`.
- **DRFP:** represented as a separate optional view. It is not installed or synthesized from a
  different fingerprint under the DRFP name.
- **ReactionClassifier:** supported through an explicit provider boundary. Its taxonomy label,
  deterministic/template confirmation, and neural raw score must remain distinct. The raw score
  is not a calibrated SynthAudit probability.
- **Other embeddings or named-reaction systems:** require a named provider, model version,
  artifact digest, license status, and provenance. No provider is downloaded or invoked at
  import time.

No learned score is substituted for unavailable deterministic evidence, and no collection of
views is collapsed into a weighted composite until a leakage-controlled benchmark establishes
and documents such a model.
