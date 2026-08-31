# Optional model integrations

The deterministic SynthAudit core does not install or import heavyweight mapping and
classification models. Add them only in an environment where they are needed.

## RXNMapper

```bash
uv pip install rxnmapper
uv run --no-sync synthaudit-easy map \
  --reaction 'CCO.CC(=O)O>>CCOC(C)=O' \
  --json

uv run --no-sync synthaudit-easy audit \
  --reaction 'CCO.CC(=O)O>>CCOC(C)=O' \
  --map-if-needed \
  --output-dir synthaudit-output
```

`--no-sync` is used after an explicit `uv pip install` so that an optional package which is not in
the core lock file is not removed by a project resynchronization. A separate ordinary Python 3.11
virtual environment with `pip install -e . rxnmapper` is also valid.

## ReactionClassifier

```bash
uv pip install reactionclassifier
uv run --no-sync synthaudit-easy audit \
  --input examples/mapped-reaction.smi \
  --with-classifier \
  --output-dir synthaudit-output
```

A confirmed class means that a shipped template reproduced the declared product. The neural gate
score is preserved as an uncalibrated provider score and is not an experimental-feasibility
probability.

## Why these packages are not core dependencies

Both integrations add large machine-learning runtimes and have separate model, checkpoint,
security and licensing boundaries. Keeping them opt-in preserves a fast offline core and avoids a
hidden model download during installation or import.
