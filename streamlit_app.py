import streamlit as st

from companionguard_app.collector_ui import data_collection_page
from companionguard_app.platform_ui import (
    layer2_page,
    layer3_page,
    dialogue_report_page,
    projects_page,
    reliability_page,
    report_page,
    sidebar_project_selector,
)
from companionguard_app.ui import get_criteria, human_review_page, results_page, run_test_page

st.set_page_config(
    page_title="CompanionGuard",
    page_icon="🛡️",
    layout="wide",
)

st.sidebar.title("CompanionGuard")
st.sidebar.caption("Criterion-driven regulatory testing platform")
sidebar_project_selector()
st.sidebar.divider()

pages = [
    "Test Projects",
    "Layer 1 · Data Collection",
    "Layer 1 · LLM Judge",
    "Layer 1 · Human Review",
    "Layer 1 · Reliability",
    "Layer 1 · Dialogue Results",
    "Layer 1 · Dialogue Report",
    "Layer 2 · Product Safeguards",
    "Layer 3 · Public Evidence",
    "Integrated Report",
]
page = st.sidebar.radio("Navigation", pages)

if page == "Test Projects":
    projects_page()
elif page == "Layer 1 · Data Collection":
    data_collection_page()
elif page == "Layer 1 · LLM Judge":
    run_test_page()
elif page == "Layer 1 · Human Review":
    human_review_page()
elif page == "Layer 1 · Reliability":
    reliability_page(get_criteria())
elif page == "Layer 1 · Dialogue Results":
    results_page()
elif page == "Layer 1 · Dialogue Report":
    dialogue_report_page(get_criteria())
elif page == "Layer 2 · Product Safeguards":
    layer2_page()
elif page == "Layer 3 · Public Evidence":
    layer3_page()
else:
    report_page(get_criteria())

st.sidebar.divider()
st.sidebar.caption("Layer 1 Dialogue · Layer 2 Product Evidence · Layer 3 Public Evidence · Human Adjudication")
