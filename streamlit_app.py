import streamlit as st

from companionguard_app.collector_ui import data_collection_page
from companionguard_app.platform_ui import (
    data_explorer_page,
    layer2_page,
    layer3_page,
    dialogue_report_page,
    projects_page,
    reliability_page,
    sidebar_project_selector,
)
from companionguard_app.ui import get_criteria, human_review_page, run_test_page
from companionguard_app.ui_theme import inject_theme
from companionguard_app.workspace_ui import home_page, integrated_report_page_v09, project_overview_page, results_page_v09, test_plan_page

st.set_page_config(
    page_title="CompanionGuard",
    page_icon="🛡️",
    layout="wide",
)
inject_theme()

PAGES = [
    ("home", "首页 / Home"),
    ("projects", "项目 · 测试项目 / Test Projects"),
    ("overview", "项目 · 项目总览 / Project Overview"),
    ("plan", "项目 · 测试计划 / Test Plan"),
    ("data_collection", "项目 · 数据采集 / Data Collection"),
    ("judge", "评测 · 自动判定 / Dialogue Judge"),
    ("human_review", "评测 · 人工复核 / Human Review"),
    ("data_explorer", "评测 · 数据浏览 / Data Explorer"),
    ("layer2", "分析 · 产品安全机制 / Product Safeguards"),
    ("layer3", "分析 · 公开合规证据 / Public Evidence"),
    ("dialogue_results", "分析 · 评测结果 / Results"),
    ("dialogue_report", "报告 · 对话报告 / Dialogue Report"),
    ("integrated_report", "报告 · 综合报告 / Integrated Report"),
    ("reliability", "分析 · 判定一致性 / Reliability"),
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
    st.session_state["nav_page"] = "home"
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

if page == "home":
    home_page(project)
elif page == "projects":
    projects_page()
elif page == "overview":
    project_overview_page()
elif page == "plan":
    test_plan_page()
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
    results_page_v09()
elif page == "dialogue_report":
    dialogue_report_page(get_criteria())
elif page == "layer2":
    layer2_page()
elif page == "layer3":
    layer3_page()
elif page == "integrated_report":
    integrated_report_page_v09()
else:
    raise RuntimeError(f"Unknown navigation page: {page}")

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
