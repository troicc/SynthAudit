# SynthAudit agent rules

Read `docs/PROJECT_SPEC.md` and `docs/CURRENT_STATUS.md` before changing code. Keep the canonical direction `mapped product -> mapped precursor set`, preserve atom-map identity, and keep reaction-centre, completion, stereo, novelty, and plausibility evidence separate.

At the start of a phase, inspect the implementation and tests, confirm its acceptance criteria, and update the plan. At the end, run formatting, lint, typing, relevant tests, coverage, and a smoke example; then update `CURRENT_STATUS.md`, `KNOWN_LIMITATIONS.md`, and upstream records when relevant.

The coding agent must not:

1. Fabricate benchmark numbers.
2. Call generated counterfactuals experimental failures.
3. Call recorded reactions guaranteed successes.
4. Equate novelty with infeasibility.
5. Claim official SynthEx compatibility without a verified specification.
6. Compare ReactSeq strings as if string equality implied chemical equality.
7. Treat SMILES token position as an atom-map number.
8. Silently map unmapped reactions.
9. Silently repair invalid structures.
10. Hide RDKit sanitation failures.
11. Auto-download models at import time.
12. Access the network in unit tests.
13. Store API keys in repository files.
14. Copy upstream code without license review.
15. Use a notebook as the only implementation.
16. Put core algorithms in Streamlit files.
17. Remove failing tests to obtain a passing build.
18. Use the test set for calibration or threshold selection.
19. Report uncalibrated confidence as probability.
20. Multiply step scores and call the value route success probability.
21. Use one LLM critic as ground truth.
22. Build a polished UI before core conformance tests pass.
23. Invent undocumented ReactSeq or ReactionJSON semantics.
24. Swallow exceptions and return empty successful results.
25. Modify unrelated repository areas without explanation.

Every public report and methodology page must display:

> SynthAudit estimates representation validity, corpus novelty and evidence-based plausibility. It does not establish experimental feasibility, yield, selectivity, safety or scalability.
