# Direct-use guide

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.


SynthAudit can be used immediately for deterministic auditing of **mapped reaction SMILES**. No
training corpus, paid API, checkpoint, or GPU is required for this mode.

## Install the normal environment

```bash
git clone https://github.com/troicc/SynthAudit.git
cd SynthAudit
uv sync --frozen --all-extras --dev
uv run synthaudit-easy doctor
```

## Audit one mapped reaction

```bash
uv run synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --output-dir synthaudit-output
```

Outputs:

- `mapped-reaction.smi`: exact mapped input used;
- `reaction-ir.json`: canonical edit representation;
- `audit.json`: complete machine-readable audit;
- `audit.html`: standalone visual report;
- `summary.json`: concise result and review queue.

An exit code of `3` means that the audit completed but found a blocking representation issue. It
is not an infrastructure crash and it is not a claim that the laboratory reaction cannot work.

## Audit a reaction that is not mapped

Install the heavy, optional mapper once:

```bash
uv pip install rxnmapper
```

Then explicitly request mapping:

```bash
uv run synthaudit-easy audit \
  --reaction 'CCO.CC(=O)O>>CCOC(C)=O' \
  --map-if-needed \
  --output-dir synthaudit-output
```

`mapping.json` records the mapper, version and raw confidence. Mapping is model-derived
preprocessing and is never hidden.

## Optional reaction classification

```bash
uv pip install reactionclassifier
uv run synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --with-classifier \
  --output-dir synthaudit-output
```

The generated `classification.json` distinguishes deterministic template confirmation from the
classifier's uncalibrated neural score.

## Batch mode

```bash
uv run synthaudit-easy batch \
  --input examples/reactions.csv \
  --output-dir synthaudit-batch-output \
  --reports
```

Input may be CSV, TSV or JSONL. Default columns are `reaction_id` and `reaction_smiles`. Batch mode
keeps per-record failures visible and continues processing other records.

## Existing advanced interface

The original `synthaudit` command remains available for ReactionIR, RouteIR, ReactSeq, SynthEx
draft input, local precedent indexes, novelty, evidence-model training and route reports. Run:

```bash
uv run synthaudit --help
uv run synthaudit-easy --help
uv run synthaudit ui
```

The direct-use interface composes the same core library; it is not a second chemistry engine.
