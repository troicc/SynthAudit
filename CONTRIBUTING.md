# Contributing to SynthAudit

SynthAudit separates deterministic representation checks from evidence-based research claims.
Contributions are welcome when they preserve that boundary.

## Local setup

```bash
uv sync --frozen --all-extras --dev
make quality
make test
make easy-smoke
```

Heavy optional integrations are installed explicitly in the active environment:

```bash
uv pip install rxnmapper reactionclassifier
```

## Pull-request rules

- Add tests for every new edit, adapter branch, audit rule, or CLI behavior.
- Never treat a missing provider as a score of zero.
- Never call a recorded reaction guaranteed successful or a counterfactual an experimental failure.
- Keep atom mapping explicit and preserve provenance.
- Update `docs/CURRENT_STATUS.md` and `docs/KNOWN_LIMITATIONS.md` for material changes.
- Do not commit downloaded corpora, checkpoints, API keys, local model pickle files, or generated caches.

## Scientific results

Any reported metric must name its dataset version, split, parent grouping, target semantics,
calibration protocol, confidence interval method, and artifact checksum. Test data may not be used
for model selection or threshold fitting.
