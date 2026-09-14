import streamlit as st

from companionguard_app.collector_ui import data_collection_page
from companionguard_app.ui import human_review_page, results_page, run_test_page

st.set_page_config(
    page_title="CompanionGuard",
    page_icon="🛡️",
    layout="wide",
)

st.sidebar.title("CompanionGuard")
st.sidebar.caption("Executable regulatory evaluation for anthropomorphic AI")
page = st.sidebar.radio("Navigation", ["Run Test", "Data Collection", "Human Review", "Results"])

if page == "Run Test":
    run_test_page()
elif page == "Data Collection":
    data_collection_page()
elif page == "Human Review":
    human_review_page()
else:
    results_page()

st.sidebar.divider()
st.sidebar.caption("Collector · Benchmark Mode · DeepSeek Judge · Human Adjudication")
