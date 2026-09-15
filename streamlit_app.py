import streamlit as st

from companionguard_app.collector_ui import data_collection_page
from companionguard_app.platform_ui import (
    data_explorer_page,
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

PAGES = [
    ("projects", "测试项目 / Test Projects"),
    ("data_collection", "Layer 1 · 对话采集 / Data Collection"),
    ("data_explorer", "Layer 1 · 采集数据查看 / Data Explorer"),
    ("judge", "Layer 1 · LLM 判定 / LLM Judge"),
    ("human_review", "Layer 1 · 人工复核 / Human Review"),
    ("reliability", "Layer 1 · 判定一致性 / Reliability"),
    ("dialogue_results", "Layer 1 · 对话测试结果 / Dialogue Results"),
    ("dialogue_report", "Layer 1 · 对话测试报告 / Dialogue Report"),
    ("layer2", "Layer 2 · 产品安全机制 / Product Safeguards"),
    ("layer3", "Layer 3 · 公开合规证据 / Public Evidence"),
    ("integrated_report", "综合测试报告 / Integrated Report"),
]
PAGE_IDS = [x[0] for x in PAGES]
PAGE_LABELS = dict(PAGES)

st.sidebar.title("CompanionGuard")
st.sidebar.caption("拟人化 AI 监管测试平台 / Regulatory testing platform")
project = sidebar_project_selector()
st.sidebar.divider()

requested = st.session_state.pop("requested_nav", None)
if requested in PAGE_IDS:
    st.session_state["nav_page"] = requested
if st.session_state.get("nav_page") not in PAGE_IDS:
    st.session_state["nav_page"] = "projects"
page = st.sidebar.radio(
    "导航 / Navigation",
    PAGE_IDS,
    format_func=lambda pid: PAGE_LABELS[pid],
    key="nav_page",
)

# Persistent workflow cue. This is guidance, not a hard wizard: users may jump
# between layers when their protocol permits it.
idx = PAGE_IDS.index(page)
st.sidebar.divider()
st.sidebar.caption(f"工作流阶段 / Current stage: {idx + 1}/{len(PAGE_IDS)}")
st.sidebar.progress((idx + 1) / len(PAGE_IDS))
if project:
    st.sidebar.caption("典型主线：项目 → 对话采集 → 采集数据查看 → LLM 判定 → 人工复核 → 一致性/结果 → Layer 2/3 → 综合测试报告")

if page == "projects":
    projects_page()
elif page == "data_collection":
    data_collection_page()
elif page == "data_explorer":
    data_explorer_page()
elif page == "judge":
    run_test_page()
elif page == "human_review":
    human_review_page()
elif page == "reliability":
    reliability_page(get_criteria())
elif page == "dialogue_results":
    results_page()
elif page == "dialogue_report":
    dialogue_report_page(get_criteria())
elif page == "layer2":
    layer2_page()
elif page == "layer3":
    layer3_page()
else:
    report_page(get_criteria())

st.divider()
nav_left, nav_mid, nav_right = st.columns([1, 2, 1])
with nav_left:
    if idx > 0 and st.button("← 上一阶段 / Previous stage", use_container_width=True, key=f"global_prev::{page}"):
        st.session_state["requested_nav"] = PAGE_IDS[idx - 1]
        st.rerun()
with nav_mid:
    if project:
        st.caption(f"当前项目 / Active project：{project.get('project_name')} · {project.get('project_id')}")
    else:
        st.caption("当前未进入任何测试项目。")
with nav_right:
    if idx < len(PAGE_IDS) - 1 and st.button("下一阶段 / Next stage →", use_container_width=True, type="primary", key=f"global_next::{page}"):
        st.session_state["requested_nav"] = PAGE_IDS[idx + 1]
        st.rerun()

st.sidebar.divider()
st.sidebar.caption("Layer 1 对话证据 · Layer 2 产品证据 · Layer 3 公开证据 · 人工复核")
