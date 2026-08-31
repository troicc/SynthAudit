# Upstream status

Checked: **2026-08-31**. HEAD values were resolved with `git ls-remote`; ReactSeq was also shallow-cloned to a temporary directory and its actual source/demo files inspected at the listed SHA. Compatibility tests must pin these full SHAs. A later HEAD is not implicitly compatible.

## Status matrix

| Project | Repository / branch / exact commit | License status | Public artifacts and runtime | Integration decision |
|---|---|---|---|---|
| ReactSeq | `jiachengxiong/ReactSeq`, `main`, `9838a3058e32e1c0ee04b2bab0448104dc293384` | LGPL-2.1 for repository code; linked datasets/checkpoints require their own provenance review | Generator/converter code (`e_smiles.py`, `preprocess_data.py`, `transform.py`), OpenNMT fork, configs, USPTO-50K-derived files, demo source/target/output, notebooks, prompt paths, embedding extraction scripts. Repository model directories are placeholders; README links checkpoints/preprocessed data externally. Conversion runtime documents Python 3.7, RDKit 2019.03.2 and `epam.indigo`; inference documents Python 3.8, PyTorch 2.0 and OpenNMT-py 3.4.1. | Do not vendor. Use pinned golden fixtures and an optional isolated JSONL bridge. Main package implements only source-verified, fail-closed parsing semantics. |
| SynthEx | `schwallergroup/synthex`, `main`, `5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f` | Repository contains no license file at checked commit. README says a future release is planned under Apache-2.0; this is not a present code license. | README, figures, paper citation, one two-operation example, and names of ten operations. No package, code, JSON Schema, reference implementation, checkpoint, fixture, dataset download, ReactionJSON spec, or RouteJSON spec in the repository. SynthAtlas is browsable but has no documented API inspected here. | Official adapters are unavailable and must raise `UpstreamSpecificationUnavailable`. Implement only `synthaudit.synthex-paper-draft/0.1`, with assumptions isolated and visibly labelled. Do not scrape SynthAtlas. |
| Synthelite | `schwallergroup/synthelite`, `main`, `45168f8a5846c2fd15a833eddc88bac843b5bbee` | MIT | Source, Poetry lock, configs, benchmark definitions, simple launch example, route exporter/download command, and precomputed routes on Hugging Face. Full planner requires API credentials, stock/templates, policy models, and WandB. Its `routes.llm_query_explorer.json` is an implementation export, not ReactionJSON/RouteJSON. | Optional version-pinned file adapter. Preserve unknown fields and avoid importing planner dependencies into core. No live planner call in offline tests. |
| ReactionClassifier | `schwallergroup/ReactionClassifier`, `main`, `4d26f18a2350dfc9bdba8d57742fd3344545c3a0` | MIT for code and bundled data, per repository | Installable `reactionclassifier`, bundled neural gate/templates/taxonomy, examples/tests; full ~666k labelled database on Zenodo. README notes proprietary NameRXN-derived columns are excluded. Requires RDKit, PyTorch, NumPy. | Optional `classifier` provider; isolate its neural confidence from deterministic template confirmation and from calibrated SynthAudit evidence. Dataset download is explicit. |
| AiZynthFinder | `MolecularAI/aizynthfinder`, `master`, `21ff546d5f22331b078390a2f12dc04defc3f39c` | MIT | Installable PyPI package, docs, tests, stocks and expansion/filter policies via explicit public-data download. Python 3.10-3.12 documented. | No core dependency. Potential route/reference provider in a separate optional environment; pin model and stock artifacts independently. |
| Molecular Transformer | `pschwllr/MolecularTransformer`, `master`, `aeb339daf0a029b391f8307fb3f467f461605dd2` | License file present; exact redistribution obligations must be reviewed before packaging derived artifacts | Legacy OpenNMT-py v0.4.1 code, Python 3.5/PyTorch 0.4.1 instructions, links to datasets/models. Reproducible modern local checkpoint inference was not established. | Keep only a provider interface. Do not select as default or advertise local support until checkpoint, license, and inference reproduction pass. |

### ReactSeq Phase 4 source findings

At the pinned SHA, `get_b_smiles_forward/backward` defines bond symbols and bracket isotope/symbol composition; `get_lg_forward/backward` defines sorted attachment-point alignment, null records, charge deltas, `:1` leaving-group annotations, and starred multi-attachment regrouping; `merge_smiles_only` and `get_e_smiles` define the public `product>>>header<tail>...` envelope. `demo_tgt.txt` and `demo_output_smiles.txt` provide paired public examples. SynthAudit commits the first three pairs as attributed regression fixtures, adding stable product maps locally; no dataset-derived population statistic is claimed.

`services/reactseq-legacy/server.py` now checks the actual checkout `git rev-parse HEAD`, request SHA, and configured SHA before invoking upstream through JSONL. It does not make network calls. The exact legacy runtime and Indigo installation are still not reproduced on this host.

### Synthelite Phase 5 source findings

The exact pinned repository was shallow-cloned and inspected locally. Its
`ReactionTree.to_dict` serializer emits a nested bipartite tree of `mol` and `reaction` nodes,
not ReactionJSON or RouteJSON. Reaction metadata can carry `mapped_reaction_smiles`; other
exports may contain only unmapped reaction SMILES. SynthAudit supports a single fixed nested
tree only when every normalized step supplies that explicit mapped artifact. It preserves
unknown fields and planner scores as source metadata, does not import the planner, and never
maps atoms implicitly.

## Phase 0 required answers

1. **Is the official ReactSeq converter runnable?** The converter source is public and structurally runnable in the upstream-pinned legacy environment. It is not compatible with the SynthAudit Python 3.11 environment as documented: upstream calls for Python 3.7, RDKit 2019.03.2, and Indigo. On this Apple Silicon host that exact environment was not established in Phase 0, so no conformance claim is made. The bridge remains isolated and optional.
2. **Which ReactSeq artifacts are public?** LGPL-2.1 source for generation, conversion, preprocessing, training/inference and the OpenNMT fork; configs; demo inputs/predictions/outputs; notebooks; USPTO-50K-derived directories; prompt workflows; vocabulary/data links; embedding extraction code; and external checkpoint/preprocessed-data links.
3. **Can ReactSeq_MEO embeddings be extracted from a released checkpoint?** The repository contains extraction code (`embedding/1_extract_emebddings.py` and notebooks), but the checked Git tree does not contain a checkpoint in `trained_models`. Because the externally linked checkpoint was not checksum-pinned and loaded here, reproducible extraction is currently **unverified/unavailable**, never fabricated.
4. **Does ReactSeq require isolation?** Yes for pinned official conversion/inference. Conversion and model inference specify mutually different legacy environments, both outside the Python 3.11 core contract.
5. **Is an official SynthEx ReactionJSON schema available?** No, not at the checked commit.
6. **Is an official RouteJSON schema available?** No, not at the checked commit.
7. **Which SynthEx semantics remain undocumented?** Container/version fields; required/optional fields; exact meaning and validation of every parameter; absolute versus delta bond order; fragment syntax and attachment indexing; fresh map allocation; operation ordering; atom changes; explicit-H/charge behavior; stereo neighbour conventions; errors; route step/dependency/intermediate identifiers; condition schema; and round-trip guarantees.
8. **What can be implemented without guessing?** Canonical IR, mapped-reaction graph differencing, deterministic execution/audits, an official-adapter failure boundary, and a visibly namespaced draft parser limited to the operation names/example documented by the README plus user-supplied fields validated under declared draft rules.
9. **Minimum fully reproducible v0.1?** Offline ReactionIR/RouteIR schemas, mapped-reaction adapter, staged execution, structural/centre/completion/stereo audits, safe ReactSeq adapter subset with pinned fixtures and optional legacy bridge, semantic comparison, CLI, standalone report, and tests. Official SynthEx and model inference are not release blockers.
10. **Which licenses govern artifacts?** SynthAudit: Apache-2.0. ReactSeq repository code: LGPL-2.1. Synthelite, ReactionClassifier, and AiZynthFinder code: MIT. SynthEx currently has no repository license; its README only announces a planned Apache-2.0 release. Molecular Transformer and every external checkpoint/dataset must be reviewed separately. USPTO-derived and third-party datasets retain their source terms and are not redistributed by default.

## Availability vocabulary

- **available**: present, licensed, and inspected at the pinned commit;
- **optional**: reproducible only with an explicitly installed extra/artifact;
- **unverified**: referenced upstream but not reproducibly loaded or executed here;
- **unavailable**: required specification/artifact is absent;
- **unsupported**: intentionally rejected by the current adapter.

## Recheck protocol

Run `scripts/check_upstreams.py` explicitly with network access, review diffs manually, update exact SHAs and licenses, regenerate official fixtures only through the isolated bridge, and add a compatibility test before changing any availability status.

## Phase 7 provider boundary

Phase 7 adds no upstream download, vendored dataset, checkpoint, or model claim. ReactSeq MEO
remains unavailable because the external checkpoint has not been checksum-pinned and reproduced.
ReactionClassifier remains an optional provider whose model/taxonomy provenance and raw score
must be returned explicitly. DRFP is an optional independent view and is not installed by the
core package. Local reference indexes accept only caller-supplied records with source and license
metadata; SynthAtlas is not scraped. No upstream status or pinned SHA changed in this phase.

## Phase 8 data boundary

Phase 8 adds no upstream corpus or model artifact and changes no pinned upstream status. The
committed 200-record counterfactual set is authored specifically for offline software
verification under Apache-2.0. Its source metadata explicitly states that it is not experimental
reaction evidence. Research-scale generation remains unavailable until a separately licensed,
versioned, content-addressed mapped-reaction corpus is configured and reviewed.

## Phase 9 model-provider boundary

Phase 9 changes no pinned upstream SHA or availability claim. No forward-model, ReactSeq,
ReactionClassifier, Molecular Transformer, LLM, dataset, or checkpoint artifact was downloaded,
selected, or redistributed. The forward-provider interface fails closed until a checkpoint has a
verified license, digest, documented input format, preprocessing record, and reproducible local
inference. The independent critic remains disabled by default and requires explicit generation-
provider independence, raw responses, multiple samples, token/cost accounting, and provenance.

The logistic-regression and histogram-gradient-boosting implementations use the locally locked
scikit-learn dependency against authored software fixtures. This verifies API and leakage guards,
not scientific performance or upstream model compatibility.

## Phase 10 route and prompt boundary

Phase 10 changes no upstream SHA, license, or compatibility status. Prompt cases are generated
locally from authored Phase 8 reference representations; no ReactSeq checkpoint, SynthEx service,
Synthelite planner, LLM, or other prompt-capable provider was invoked. The provider interface
fails closed without an explicitly configured versioned model and preserves raw responses and
confidence semantics when enabled.

Route checks operate only on canonical RouteIR, embedded ReactionIR, and declared metadata. They
do not add an official SynthEx RouteJSON claim or reinterpret Synthelite implementation exports as
a stable upstream schema.

## Phase 11 product boundary

Phase 11 changes no pinned upstream SHA, license, schema, or compatibility claim. The CLI,
Streamlit workspace, standalone reports, diagrams, and authored examples consume only existing
canonical APIs and committed fixtures. They do not call a live ReactSeq model, SynthEx service,
Synthelite planner, external corpus, or LLM. Optional data transfer is user-invoked, manifest-
declared, checksum-verified, and network-disabled unless explicitly enabled.
