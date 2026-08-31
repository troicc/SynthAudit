# Known limitations

Updated: 2026-08-31.

- The official ReactSeq converter requires a legacy isolated runtime. Reproduction on this Apple Silicon host has not yet been established. Three committed golden cases are copied from pinned official repository demo input/output files, but the local adapter remains labelled a source-inspected safe subset rather than full official compatibility.
- ReactSeq checkpoints are linked externally rather than committed at the pinned source revision. MEO embedding and token-probability support is unavailable until a checkpoint is checksum-pinned and inference is reproduced.
- Official SynthEx ReactionJSON and RouteJSON specifications are absent at the checked commit. Only the visibly named `synthaudit.synthex-paper-draft/0.1` adapter can be implemented; official adapters fail closed.
- Synthelite route exports are implementation artifacts rather than a stable cross-project schema and may change. The current adapter accepts one fixed nested `ReactionTree.to_dict` tree only when each reaction carries explicit mapped reaction SMILES. Route sets, alternative reaction branches, and unmapped nodes are rejected; unknown data is preserved and unsupported cases are reported.
- The deterministic graph engine checks representation and structure, not laboratory outcome, kinetics, selectivity, safety, yield, or scale.
- RDKit sanitation and CIP assignment have representation/version-dependent edge cases, especially aromatic/Kekulé, organometallic, pseudo-asymmetric, atropisomeric, and cyclic stereo chemistry. Diagnostic mode never upgrades these cases to valid.
- Fragment participation in mapped reaction SMILES can be ambiguous when reagents are atom-mapped or atoms are unbalanced. The adapter warns and does not silently map or repair.
- Novelty values depend on corpus composition, preprocessing, fingerprints, and time. Missing reference data returns unavailable evidence, not a score.
- Precedent similarity is not experimental validation. Reported yield/conditions, when legally available, may be noisy or context-dependent.
- Initial evidence models are baselines. Calibration is conditional on declared data and may not transfer out of distribution.
- Route condition compatibility and protecting-group timing begin with transparent rules and review flags; they are not comprehensive synthetic-chemistry reasoning.
- Large MVP/full datasets, paid-provider prompt experiments, GPU models, and laboratory validation are outside offline tests and are not claimed complete without artifacts.
- The Phase 1 CLI contains only bootstrap/version and small-manifest validation commands; reaction commands are implemented after the canonical schemas and execution engine.
- IR schema validation intentionally checks representation shape, edit invariants, roles, IDs, and dependency references; SMILES parsing, atom-map uniqueness, valence, sanitation, and chemistry-aware no-op checks belong to the graph/audit stages and are not implied by successful Pydantic validation.
- Introduced external fragments must already carry the exact next sequential atom maps in ReactionIR. Adapters allocate them; the executor rejects rather than renumbering an ambiguous IR payload.
- Absolute tetrahedral assignment is conservative: duplicate canonical substituent ranks are marked indeterminate. Advanced pseudo-asymmetric and cyclic cases require dedicated audit evidence rather than forced configuration.
- A full transaction may carry an explicitly diagnostic, unsanitized synthon into completion when the sole core-stage failure is sanitation and completion later yields a sanitized graph. The nested core result remains failed and retains the RDKit error. Null ReactSeq completion uses integral lost bond-order capacity to materialize hydrogen with a warning; fractional aromatic, metal, radical, and unusual valence cases remain review items.
- ReactSeq attachment bond order follows the pinned upstream valence rules because the tail string does not encode that bond order directly. The rule and warning are preserved; broader conformance requires more official fixtures.
- The three-case ReactSeq demo fixture has 100% local parse/execution/exact-reconstruction only as a regression observation for those three cases. It is not reported as general ReactSeq accuracy, and it contains no stereo case.
- Cross-representation comparison aligns atom-map renumbering through product-graph isomorphism. If a symmetric product admits correspondences with different edit meanings, the result is `indeterminate`; it is never resolved by arbitrary canonical ranks. “Equivalent except unspecified stereo” describes information loss, not proof that either stereochemical outcome is chemically supported.
- The SynthEx route namespace is the local `synthaudit.synthex-paper-draft-route/0.1` envelope. It is not official RouteJSON, and no conversion to a future official schema is promised.
