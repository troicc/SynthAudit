from __future__ import annotations

from pathlib import Path

import streamlit as st

from synthaudit.ui.components import configure_page
from synthaudit.ui.workspace import build_benchmark_workspace

configure_page(st, title="Benchmark")
st.write(
    "Run committed offline conformance and contract fixtures. Research-scale model metrics "
    "remain unavailable until licensed data and experiments are configured."
)

root = Path(__file__).resolve().parents[2]
if st.button("Run offline benchmark contracts", use_container_width=True):
    try:
        with st.spinner("Validating content hashes, grouped splits, and conformance fixtures"):
            result = build_benchmark_workspace(root)
    except Exception as exc:
        st.error(f"Benchmark validation failed: {type(exc).__name__}: {exc}")
    else:
        st.session_state["benchmark_workspace"] = result

result = st.session_state.get("benchmark_workspace")
if result is None:
    st.info("No metrics are pre-filled. Run the local contract checks to observe fixture results.")
else:
    counts = st.columns(4)
    counts[0].metric("Counterfactual records", result.counterfactual_record_count)
    counts[1].metric("Prompt cases", result.prompt_case_count)
    counts[2].metric("Prompt variants", result.prompt_variant_count)
    counts[3].metric(
        "ReactSeq exact fixtures",
        f"{result.reactseq.exact_reconstruction_count}/{result.reactseq.fixture_count}",
    )
    st.caption(result.interpretation)

    st.subheader("Conformance")
    st.json(result.reactseq.model_dump(mode="json"), expanded=False)
    st.subheader("Counterfactual and prompt robustness")
    st.write("Counterfactual performance metrics", result.counterfactual_metrics_status)
    st.write("Prompt robustness metrics", result.prompt_metrics_status)
    st.json(result.route_prompt.model_dump(mode="json"), expanded=False)
    st.subheader("Calibration and evaluation slices")
    st.markdown(
        '<div class="sa-empty">Unavailable: no selected research model, adjudicated support '
        "labels, calibration results, high-novelty false-rejection estimate, stereo-subset "
        "performance, or ring-forming-subset performance is bundled.</div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "Download observed benchmark contract JSON",
        data=result.model_dump_json(indent=2) + "\n",
        file_name="synthaudit-benchmark-workspace.json",
        mime="application/json",
        use_container_width=True,
    )
