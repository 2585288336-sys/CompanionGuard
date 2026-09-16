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
from companionguard_app.projects import is_read_only_project
from companionguard_app.readonly_ui import readonly_page
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
    ("projects", "测试项目 / Test Project Design"),
    ("plan", "项目计划 / Test Plan"),
    ("data_collection", "对话数据采集 / Dialogue Data Collection"),
    ("overview", "当前项目总览 / Current Project Overview"),
    ("judge", "自动判定 / Dialogue Judge"),
    ("human_review", "人工复核 / Human Review"),
    ("data_explorer", "数据浏览 / Data Explorer"),
    ("reliability", "判定一致性 / Reliability"),
    ("layer2", "产品安全机制检查 / Product Safeguards"),
    ("layer3", "公开制度材料核查 / Public Evidence"),
    ("dialogue_results", "对话评测结果与指标 / Dialogue Results & Metrics"),
    ("dialogue_report", "对话评测报告 / Dialogue Report"),
    ("integrated_report", "综合评测报告 / Integrated Report"),
]
PAGE_IDS = [x[0] for x in PAGES]
PAGE_LABELS = dict(PAGES)

NAV_GROUPS = {
    "01 项目与测试 / Project Setup": ["projects", "plan", "data_collection", "overview"],
    "02 三层证据评测 / Three-Layer Evaluation": ["judge", "human_review", "data_explorer", "reliability", "layer2", "layer3"],
    "04 报告 / Reports": ["dialogue_report", "integrated_report"],
}

requested = st.session_state.pop("requested_nav", None)
if requested in PAGE_IDS:
    st.session_state["nav_page"] = requested
if st.session_state.get("nav_page") not in PAGE_IDS:
    st.session_state["nav_page"] = "home"


def _nav_leaf(page_id: str) -> None:
    label = PAGE_LABELS[page_id]
    zh, _, en = label.partition(" / ")
    active = st.session_state.get("nav_page") == page_id
    if st.sidebar.button(
        zh,
        key=f"nav::{page_id}",
        type="primary" if active else "secondary",
        use_container_width=True,
    ):
        st.session_state["nav_page"] = page_id
        st.rerun()
    st.sidebar.caption(en)


st.sidebar.title("CompanionGuard")
st.sidebar.caption("拟人化 AI 监管测试平台 / Regulatory testing platform")
project = sidebar_project_selector()
st.sidebar.divider()
st.sidebar.markdown("<div class='cg-sidebar-kicker'>WORKSPACE</div>", unsafe_allow_html=True)
_nav_leaf("home")
for group_label, children in NAV_GROUPS.items():
    expanded = st.session_state.get("nav_page") in children
    with st.sidebar.expander(group_label, expanded=expanded):
        if group_label.startswith("02"):
            st.markdown("<div class='cg-sidebar-layer'>Layer 1｜对话行为测试<br><span>Dialogue Testing</span></div>", unsafe_allow_html=True)
            for page_id in ["judge", "human_review", "data_explorer", "reliability"]:
                _nav_leaf(page_id)
            st.markdown("<div class='cg-sidebar-layer'>Layer 2｜产品安全机制检查<br><span>Product Safeguards</span></div>", unsafe_allow_html=True)
            _nav_leaf("layer2")
            st.markdown("<div class='cg-sidebar-layer'>Layer 3｜公开制度材料核查<br><span>Public Evidence</span></div>", unsafe_allow_html=True)
            _nav_leaf("layer3")
        else:
            for page_id in children:
                _nav_leaf(page_id)
st.sidebar.markdown("<div class='cg-sidebar-direct'>03 对话评测结果与指标<br><span>Dialogue Results &amp; Metrics</span></div>", unsafe_allow_html=True)
_nav_leaf("dialogue_results")

page = st.session_state["nav_page"]

# Persistent workflow cue. This is guidance, not a hard wizard: users may jump
# between layers when their protocol permits it.
idx = PAGE_IDS.index(page)
st.sidebar.divider()
st.sidebar.caption(f"工作流阶段 / Current stage: {idx + 1}/{len(PAGE_IDS)}")
st.sidebar.progress((idx + 1) / len(PAGE_IDS))
if project:
    st.sidebar.caption("典型主线：项目 → 对话采集 → 采集数据查看 → LLM 判定 → 人工复核 → 一致性/结果 → Layer 2/3 → 综合测试报告")

READ_ONLY_BLOCKED_PAGES = {"data_collection", "judge", "human_review", "layer2", "layer3", "dialogue_report"}

if project and is_read_only_project(project) and page in READ_ONLY_BLOCKED_PAGES:
    readonly_page(page)
elif page == "home":
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
