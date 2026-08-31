from __future__ import annotations

import streamlit as st

from synthaudit.application.models import ReactionSourceKind
from synthaudit.application.workflows import normalize_reaction_source
from synthaudit.evaluation.cross_representation import compare_representations
from synthaudit.graph.semantic_hash import reaction_ir_semantic_hash
from synthaudit.ui.components import configure_page
from synthaudit.ui.workspace import DEMO_REACTION_SMILES, edit_rows

configure_page(st, title="Representation Explorer")
st.write(
    "Normalize declared source formats into ReactionIR while keeping traversal, atom-map, "
    "warning, and unsupported-field evidence visible."
)

labels = {
    "Mapped reaction SMILES": ReactionSourceKind.MAPPED_REACTION_SMILES,
    "ReactSeq safe subset": ReactionSourceKind.REACTSEQ,
    "ReactionIR JSON": ReactionSourceKind.REACTION_IR,
    "SynthEx paper-draft namespace": ReactionSourceKind.SYNTHEX_PAPER_DRAFT,
}
with st.form("representation-normalization"):
    label = st.selectbox("Declared representation", tuple(labels))
    source = st.text_area(
        "Source payload",
        value=DEMO_REACTION_SMILES,
        height=150,
        help="No atom mapping or invalid-structure repair is performed implicitly.",
    )
    product = st.text_input(
        "Mapped product for ReactSeq or paper-draft input",
        help="Required only when the selected representation does not contain its mapped product.",
    )
    submitted = st.form_submit_button("Normalize representation", use_container_width=True)

if submitted:
    try:
        normalized = normalize_reaction_source(
            labels[label],
            source,
            mapped_product_smiles=product or None,
            reaction_id="streamlit-representation-explorer",
        )
    except Exception as exc:
        st.error(f"Normalization failed without repair: {type(exc).__name__}: {exc}")
    else:
        st.session_state["representation_result"] = normalized

normalized = st.session_state.get("representation_result")
if normalized is None:
    st.info("Submit the authored mapped-reaction example or provide an explicitly declared source.")
else:
    reaction = normalized.reaction_ir
    summary = st.columns(4)
    summary[0].metric("Core edits", len(reaction.core_edits))
    summary[1].metric("Completion edits", len(reaction.attachment_edits))
    summary[2].metric("Atom-state edits", len(reaction.atom_state_edits))
    summary[3].metric("Stereo edits", len(reaction.stereo_edits))
    st.subheader("Normalized ReactionIR")
    st.json(reaction.model_dump(mode="json"), expanded=False)
    st.download_button(
        "Download ReactionIR JSON",
        data=reaction.model_dump_json(indent=2) + "\n",
        file_name=f"{reaction.reaction_id}.reaction-ir.json",
        mime="application/json",
        use_container_width=True,
    )
    st.subheader("Token-to-atom mapping")
    if normalized.traversal_context is None:
        st.markdown(
            '<div class="sa-empty">Not applicable to this representation. No token position is '
            "being treated as an atom-map number.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.json(normalized.traversal_context, expanded=False)
    st.subheader("Graph edits by stage")
    rows = edit_rows(reaction)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("This representation declares no edit operation.")
    st.subheader("Semantic round-trip check")
    round_trip = type(reaction).model_validate_json(reaction.model_dump_json())
    comparison = compare_representations(
        reaction,
        round_trip,
        left_representation=normalized.source_kind.value,
        right_representation="ReactionIR JSON round-trip",
    )
    st.caption(
        "This checks serialization stability only; it is not evidence of cross-model or "
        "experimental agreement."
    )
    st.json(comparison.model_dump(mode="json"), expanded=False)
    st.code(reaction_ir_semantic_hash(reaction), language=None)
    with st.expander("Warnings, unsupported fields, and provenance"):
        st.write("Warnings", normalized.warnings or ("none",))
        st.write("Unsupported fields", normalized.unsupported_fields or ("none",))
        st.json([item.model_dump(mode="json") for item in normalized.provenance], expanded=False)
