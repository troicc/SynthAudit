from __future__ import annotations

import streamlit as st

from synthaudit.ui.components import configure_page

configure_page(st, title="Methodology and Limitations")

st.header("Four independent audit questions")
st.markdown(
    """
1. **Reaction-centre consistency** — do declared atom and bond edits match the intended graph change?
2. **Synthon-completion consistency** — are leaving groups, fragments, attachments, and atom states coherent?
3. **Corpus novelty** — how distant is each declared view from a versioned reference corpus?
4. **Evidence-based plausibility** — what independent structural, precedent, condition, forward, and consistency evidence exists, and where should the system abstain?
"""
)

st.header("Novelty is not plausibility")
st.write(
    "A reaction can be novel and supported, familiar and inconsistent, or missing evidence in "
    "one view while supported in another. SynthAudit never computes plausibility as one minus novelty."
)

st.header("Data and model provenance")
st.markdown(
    """
- Core demonstrations use authored, content-addressed software fixtures under their declared licenses.
- ReactSeq conformance is pinned to inspected public source and three committed demo fixtures.
- Official SynthEx ReactionJSON and RouteJSON remain unavailable; only the visibly named SynthAudit paper-draft namespace is supported.
- No research model checkpoint, licensed large corpus, paid provider, or network service is bundled or downloaded on import.
- Generated counterfactuals are not experimental failures, and recorded reactions are not guaranteed successes.
"""
)

st.header("Known limitations")
st.markdown(
    """
- RDKit and the supported edit schema do not cover every organometallic, coordination, aromatic, isotope, or stereo edge case.
- Precedent retrieval supports evidence transfer, not experimental validation of a query.
- Route protection and condition rules require explicit structured metadata and are not an exhaustive chemistry oracle.
- Calibrated evidence scores require separately supplied train/calibration/test data with parent-group separation.
- Prompt-model experiments remain `not_run` until an explicit provider and provenance are supplied.
"""
)

st.header("Reproducibility boundary")
st.write(
    "Python 3.11, the committed uv lock, Docker definition, versioned JSON Schemas, content "
    "digests, and offline tests define the reproducible package boundary."
)
