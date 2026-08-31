from __future__ import annotations

from pathlib import Path

import streamlit as st

from synthaudit.precedent.index import ReferenceIndex
from synthaudit.reports import molecule_svg, render_reaction_report_html
from synthaudit.schema.reaction_ir import ReactionIRV1
from synthaudit.ui.components import configure_page, render_stage
from synthaudit.ui.workspace import demo_reaction, reaction_report_workspace

configure_page(st, title="Single Reaction Audit")
st.write(
    "Inspect product-to-synthon, completion, stereo, novelty, precedent, and evidence status "
    "without collapsing them into one answer."
)

with st.form("single-reaction-audit"):
    payload = st.text_area(
        "ReactionIR JSON",
        value=demo_reaction().model_dump_json(indent=2),
        height=310,
    )
    index_text = st.text_input(
        "Optional local reference-index path",
        help="The app never downloads a corpus. Supply a content-addressed local index explicitly.",
    )
    submitted = st.form_submit_button("Run stage-specific audit", use_container_width=True)

if submitted:
    try:
        reaction = ReactionIRV1.model_validate_json(payload)
        reference_index = ReferenceIndex.load(Path(index_text)) if index_text else None
        report = reaction_report_workspace(reaction, reference_index=reference_index)
    except Exception as exc:
        st.error(f"Audit failed explicitly: {type(exc).__name__}: {exc}")
    else:
        st.session_state["reaction_report"] = report

report = st.session_state.get("reaction_report")
if report is None:
    st.info("Run the authored software example or paste a strict ReactionIR document.")
else:
    audit = report.audit
    columns = st.columns(4)
    columns[0].metric("Structural", audit.structural_audit.status.value)
    columns[1].metric("Reaction centre", audit.reaction_centre_audit.status.value)
    columns[2].metric("Completion", audit.completion_audit.status.value)
    columns[3].metric("Stereo", audit.stereo_audit.status.value)

    st.subheader("Product and declared precursors")
    structures = (
        report.reaction.product.mapped_smiles,
        *(item.mapped_smiles for item in report.reaction.expected_precursors),
    )
    st.html(molecule_svg(structures))
    st.code("\n".join(structures), language=None)

    stage_tabs = st.tabs(("Structural", "Reaction centre", "Completion", "Stereo"))
    with stage_tabs[0]:
        render_stage(st, audit.structural_audit, title="Structural checks")
    with stage_tabs[1]:
        render_stage(st, audit.reaction_centre_audit, title="Reaction-centre checks")
    with stage_tabs[2]:
        render_stage(st, audit.completion_audit, title="Completion checks")
    with stage_tabs[3]:
        render_stage(st, audit.stereo_audit, title="Stereo checks")

    st.subheader("Multi-view novelty")
    if report.novelty is None:
        st.markdown(
            '<div class="sa-empty">Unavailable: no declared local corpus. Novelty is not '
            "inferred from structural validity.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.json(report.novelty.model_dump(mode="json"), expanded=False)

    st.subheader("Precedent retrieval")
    if report.precedents is None:
        st.markdown(
            '<div class="sa-empty">Unavailable: no precedent index. Missing retrieval is not '
            "negative evidence.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.dataframe(
            [item.model_dump(mode="json") for item in report.precedents.hits],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Evidence support and uncertainty")
    st.markdown(
        '<div class="sa-empty">Unavailable: the demo ships no selected calibrated research '
        "model. No confidence value is synthesized.</div>",
        unsafe_allow_html=True,
    )
    html_report = render_reaction_report_html(report)
    downloads = st.columns(2)
    downloads[0].download_button(
        "Download standalone HTML",
        data=html_report,
        file_name=f"{report.reaction.reaction_id}.html",
        mime="text/html",
        use_container_width=True,
    )
    downloads[1].download_button(
        "Download JSON sidecar",
        data=report.model_dump_json(indent=2) + "\n",
        file_name=f"{report.reaction.reaction_id}.json",
        mime="application/json",
        use_container_width=True,
    )
