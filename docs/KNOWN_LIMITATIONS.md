# Known limitations

Updated: 2026-08-31.

- The official ReactSeq converter requires a legacy isolated runtime. Reproduction on this Apple Silicon host has not yet been established, so safe-subset parser results are not labelled official conformance.
- ReactSeq checkpoints are linked externally rather than committed at the pinned source revision. MEO embedding and token-probability support is unavailable until a checkpoint is checksum-pinned and inference is reproduced.
- Official SynthEx ReactionJSON and RouteJSON specifications are absent at the checked commit. Only the visibly named `synthaudit.synthex-paper-draft/0.1` adapter can be implemented; official adapters fail closed.
- Synthelite route exports are implementation artifacts rather than a stable cross-project schema and may change. Unknown data is preserved and unsupported cases are reported.
- The deterministic graph engine checks representation and structure, not laboratory outcome, kinetics, selectivity, safety, yield, or scale.
- RDKit sanitation and CIP assignment have representation/version-dependent edge cases, especially aromatic/Kekulé, organometallic, pseudo-asymmetric, atropisomeric, and cyclic stereo chemistry. Diagnostic mode never upgrades these cases to valid.
- Fragment participation in mapped reaction SMILES can be ambiguous when reagents are atom-mapped or atoms are unbalanced. The adapter warns and does not silently map or repair.
- Novelty values depend on corpus composition, preprocessing, fingerprints, and time. Missing reference data returns unavailable evidence, not a score.
- Precedent similarity is not experimental validation. Reported yield/conditions, when legally available, may be noisy or context-dependent.
- Initial evidence models are baselines. Calibration is conditional on declared data and may not transfer out of distribution.
- Route condition compatibility and protecting-group timing begin with transparent rules and review flags; they are not comprehensive synthetic-chemistry reasoning.
- Large MVP/full datasets, paid-provider prompt experiments, GPU models, and laboratory validation are outside offline tests and are not claimed complete without artifacts.
