"""Public Home and project workspace presentation pages for UI v0.9."""

from __future__ import annotations

import json
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from .audits import load_jsonl
from .collector_storage import load_raw_cases
from .display_labels import condition_label, criterion_label, module_label, phase_label, scenario_label
from .metrics import label_counts
from .reporting import build_integrated_report, build_integrated_report_context
from .report_pipeline import write_report_artifacts
from .service import criteria_index, run_grounding_validator, run_report_writer
from .storage import build_final_results, load_adjudications, load_final_results, load_judge_results
from .llm_ui import llm_session_id, render_llm_profile_selector
from .ui_theme import card, empty_state, flow, hero, llm_actionbar, pill, section_intro


def _go(page: str) -> None:
    st.session_state["requested_nav"] = page
    st.rerun()


def home_page(project: dict[str, Any] | None = None) -> None:
    st.markdown(
        """<div class="cg-home-hero">
          <div>
            <div class="cg-home-section" style="border-top:0;padding:0">
              <div class="kicker">REGULATORY TESTING &amp; RISK DIAGNOSIS</div>
              <h1>把拟人化 AI 的监管要求，转化为可执行、可复核的测试</h1>
              <p class="lead">CompanionGuard 是一套面向拟人化 AI 服务的监管测试与风险诊断框架。</p>
              <p class="body">项目从《人工智能拟人化互动服务管理暂行办法》的监管要求出发，将抽象的监管规则与义务转化为可以在真实产品上执行、记录和复核的测试要求，重点观察过度迎合、情感依赖、退出挽留、危机应对、未成年人保护、敏感信息诱导等拟人化互动中的风险。</p>
              <p class="body">在测试结果层面，CompanionGuard 建立了面向风险诊断的指标体系，包括风险发现率、压力鲁棒性、多轮鲁棒性、明确触发后的风险转变、专项风险指标和 Judge–Human Reliability。指标不仅记录“是否出现问题”，还用于判断风险集中在哪里、用户施压或多轮互动后模型能否继续保持安全边界。</p>
            </div>
          </div>
          <div class="cg-home-shot">
            <div class="fakebar"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
            <div class="shotbody"><div class="shotside"><div class="hair blue" style="width:80%"></div><div class="mini" style="width:64%"></div><div class="mini" style="width:78%"></div><div class="mini" style="width:70%"></div><div class="mini" style="width:55%;margin-top:28px"></div></div>
              <div class="shotmain"><div class="hair" style="width:175px;background:#344054;height:12px"></div><div class="hair" style="width:245px"></div><div class="cg-home-grid3" style="margin-top:22px"><div class="cg-home-card"><p>Layer 1</p></div><div class="cg-home-card"><p>Layer 2</p></div><div class="cg-home-card"><p>Layer 3</p></div></div><div class="cg-home-card" style="margin-top:12px"><p>Risk Diagnosis · 结果分析</p><div class="hair red" style="width:64%"></div><div class="hair blue" style="width:84%"></div><div class="hair green" style="width:48%"></div></div></div>
            </div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )
    left, right = st.columns([1, 1])
    with left:
        if st.button("进入工作台", type="primary", use_container_width=True, key="home_enter_project"):
            _go("overview" if project else "projects")
    with right:
        if st.button("查看构建与方法", use_container_width=True, key="home_view_methods"):
            _go("plan")

    st.markdown("<div class='cg-note'>Finding 表示在预设监管测试场景中观察到的风险表现，用于定位具体问题和支持后续审核；它不直接等同于法律意义上的不合规认定。</div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='cg-reference'><div class='cg-eyebrow'>PRELOADED REFERENCE PROJECT</div>"
        "<h3>CompanionGuard Formal Full Benchmark 2026-09</h3>"
        "<p>预置的完整参考项目，用于展示从测试设计、三层取证、自动 Judge、人工复核到结果分析的完整流程。</p>"
        "<span class='cg-pill blue'>FORMAL</span> <span class='cg-pill blue'>Layer 1 + Layer 2 + Layer 3</span> "
        "<span class='cg-pill'>自动 Judge + 人工复核</span></div>",
        unsafe_allow_html=True,
    )

    current_name = escape(str((project or {}).get("project_name") or (project or {}).get("project_id") or "当前项目"))
    st.markdown(
        f"""<div class="cg-home-section"><div class="intro"><div class="kicker">Regulation → Testable Evidence</div><h2>从《人工智能拟人化互动服务管理暂行办法》监管要求到真实产品测试</h2><p>监管规范通常以原则和义务的形式提出要求，而产品测试需要把这些要求进一步拆解为能够被观察、记录和复核的具体问题。</p></div><div class="cg-home-grid2"><div class="cg-home-card"><div class="cg-home-grid3" style="grid-template-columns:1fr"><div class="cg-home-card"><h3>模型实际会怎样回应？</h3></div><div class="cg-home-card"><h3>用户进一步施压后，原有边界还能否保持？</h3></div><div class="cg-home-card"><h3>产品是否设置了相应保护机制？</h3></div><div class="cg-home-card"><h3>公开材料能否支持对制度安排的核查？</h3></div></div></div><div class="cg-home-card"><p>CompanionGuard 将监管要求拆解为可观察行为、标准测试场景、产品检查项和公开材料核查项，使抽象规则能够进入真实产品测试。</p><div class="cg-home-flow" style="margin-top:1rem"><span>监管要求</span><i>→</i><span>测试场景</span><i>→</i><span>证据记录</span><i>→</i><span>Finding</span></div></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Three-Layer Regulatory Evaluation</div><h2>三层监管评测框架</h2><p>同一项监管要求，可能分别体现在模型回答、产品功能和企业公开制度中。三层结果可以相互印证，也可能出现差异。</p></div><div class="cg-home-grid3"><div class="cg-home-card"><h3>Layer 1 · 对话行为测试</h3><p>通过标准化测试场景观察模型实际回答，以及标准、压力和多轮条件下的变化。</p></div><div class="cg-home-card"><h3>Layer 2 · 产品安全机制检查</h3><p>检查外部测试人员能够实际观察、操作或触发的产品保护机制。</p></div><div class="cg-home-card"><h3>Layer 3 · 公开制度材料核查</h3><p>核查企业公开正式材料中能够确认的制度信息，并保留证据边界。</p></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Core Regulatory Scope</div><h2>核心测试范围</h2></div><div class="cg-home-grid5"><div class="cg-home-card"><h3>关系安全</h3><p>过度迎合、排他性关系、现实关系替代和退出挽留压力。</p></div><div class="cg-home-card"><h3>极端行为与危机应对</h3><p>暴力支持、自伤自杀安全应对，以及语言暴力和人格伤害。</p></div><div class="cg-home-card"><h3>未成年人保护</h3><p>虚拟亲密关系边界和不安全行为、极端情绪及不良嗜好。</p></div><div class="cg-home-card"><h3>信息与权益保护</h3><p>工作秘密、商业秘密、第三方隐私和个人信息诱导披露。</p></div><div class="cg-home-card"><h3>禁止性内容专项测试</h3><p>通过固定单轮测试检查七类明确禁止内容。</p></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Custom Test Projects</div><h2>支持自定义测试项目</h2><p>用户可以选择产品、测试范围、实验条件、分析指标和证据范围，并通过统一 Project 完成测试、判定、人工复核与结果分析。</p></div><div class="cg-home-grid2"><div class="cg-home-grid3"><div class="cg-home-card"><h3>测试产品</h3><p>选择需要评测的 AI 产品或目标模型。</p></div><div class="cg-home-card"><h3>三层证据范围</h3><p>组合 Layer 1、Layer 2 与 Layer 3 证据。</p></div><div class="cg-home-card"><h3>实验条件</h3><p>配置 C0、C1、C2 和专项测试。</p></div><div class="cg-home-card"><h3>分析指标</h3><p>选择总体、条件鲁棒性、专项风险和一致性指标。</p></div><div class="cg-home-card"><h3>证据范围</h3><p>组合对话测试、产品机制和公开材料核查。</p></div><div class="cg-home-card"><h3>统一工作流</h3><p>在同一 Project 中完成测试、复核和报告。</p></div></div><div class="cg-home-dark"><div class="kicker" style="color:#9bb4ff">REFERENCE CONFIGURATION</div><h3>CompanionGuard Formal Full Benchmark 2026-09</h3><p>统一监管测试方案，覆盖三层证据、自动 Judge、人工复核和结果报告。</p><div class="cg-home-flow" style="margin-top:1rem"><span>FORMAL</span><span>3 个代表性产品</span><span>Layer 1 + 2 + 3</span></div></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Dialogue Conditions</div><h2>对话测试与实验条件</h2><p>三种实验条件分别观察不同问题，因此分别记录和比较，不合并为一种笼统的“高难度测试”。</p></div><div class="cg-home-grid3"><div class="cg-home-card"><h3 style="color:#3156d9">C0 · 标准条件 / Baseline Condition</h3><p>在自然、集中表达的测试场景中观察模型的基本表现。</p></div><div class="cg-home-card"><h3 style="color:#b54708">C1 · 压力条件 / Pressure Condition</h3><p>保持关键事实不变，只增强用户互动压力，观察边界保持能力。</p></div><div class="cg-home-card"><h3 style="color:#6941c6">C2 · 多轮条件 / Sequential Multi-turn Condition</h3><p>将场景信息逐轮呈现，观察上下文累积后的持续安全能力。</p></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Structured Judgment</div><h2>LLM Judge + 人工复核</h2></div><div class="cg-home-grid2"><div class="cg-home-card"><h3>LLM Judge 依据预定义边界判定</h3><p>每项测试在执行前定义 Target Behaviors、Non-target Behaviors 和边界规则，Judge 围绕 Criterion 做结构化初判。</p><div class="cg-home-flow" style="margin-top:1rem"><span>FINDING</span><span>NO_FINDING</span><span>REVIEW</span></div></div><div class="cg-home-card"><h3>自动判定与人工判断可追溯</h3><p>系统同时记录自动判断、人工判断和最终标签，使每一次改判都可以追溯。</p><div class="cg-home-flow" style="margin-top:1rem"><span>Auto Judgment</span><i>→</i><span>Human Review</span><i>→</i><span>Final Label</span></div></div></div></div>
        <div class="cg-home-section"><div class="intro"><div class="kicker">Metrics &amp; Risk Diagnosis</div><h2>如何理解评测结果</h2><p>指标是证据，用于说明问题出现在哪里、在什么条件下更容易出现，以及自动判定本身是否可靠。</p></div><div class="cg-home-grid2"><div class="cg-home-card"><h3>FINDING · 风险发现</h3><p>定位具体场景中的目标风险，不直接等同于法律意义上的“不合规”。</p></div><div class="cg-home-card"><h3>OVERALL MACRO FINDING RATE · 总体风险发现率</h3><p>观察 Finding 是分散出现还是集中于某个模块或准则。</p></div><div class="cg-home-card"><h3>PRESSURE / MULTI-TURN ROBUSTNESS GAP</h3><p>比较 C1、C2 与 C0，观察用户施压或多轮持续后的边界保持能力。</p></div><div class="cg-home-card"><h3>ELICITATION FLIP · 明确触发后的风险转变</h3><p>关注模型从 NO_FINDING 转为 FINDING 的情况。</p></div><div class="cg-home-card"><h3>SPECIALIZED METRICS · 专项指标</h3><p>定位急性风险、关系限制、未成年人内容和禁止性内容等具体安全能力。</p></div><div class="cg-home-card"><h3>JUDGE–HUMAN RELIABILITY · 判定一致性</h3><p>评价自动判定与人工复核之间的一致性和可靠性。</p></div></div></div>
        <div class="cg-home-section" id="method"><div class="intro"><div class="kicker">Construction &amp; Method</div><h2>构建与方法</h2><p>从监管要求到可执行、可复核的 AI 测试。</p></div><div class="cg-home-grid3"><div class="cg-home-card"><h3>01 · 确定测试对象</h3><p>从监管要求确定测试对象与观察边界。</p></div><div class="cg-home-card"><h3>02 · 设计标准化场景</h3><p>把要求转化为可执行测试 Prompt。</p></div><div class="cg-home-card"><h3>03 · 设置实验条件</h3><p>分别设置 C0、C1、C2。</p></div><div class="cg-home-card"><h3>04 · 分别采集三层证据</h3><p>对话行为、产品机制和公开制度材料分开取证。</p></div><div class="cg-home-card"><h3>05 · 自动判定与人工复核</h3><p>保留 Auto、Human、Final 三条记录。</p></div><div class="cg-home-card"><h3>06 · 从指标进入风险分析</h3><p>用指标定位问题，不制造单一排名。</p></div></div><div class="cg-home-dark"><h3>正式方法说明</h3><p>CompanionGuard 的正式项目方法、术语与数据口径以工程内现有方法说明和冻结配置为准。</p></div><div class="cg-micro" style="margin-top:1rem">当前 Test Project · {current_name} · 研究项目数据与公开快照保持分离。</div></div>
        <div class="cg-home-footer"><span>CompanionGuard · Regulatory Testing &amp; Risk Diagnosis</span><span>Layer 1 对话证据 · Layer 2 产品证据 · Layer 3 公开证据</span></div>""",
        unsafe_allow_html=True,
    )


def _date_cutoff(cases: list[dict[str, Any]]) -> str:
    values = [str(c.get("collection_date") or (c.get("metadata") or {}).get("collection_date") or "") for c in cases]
    values = [v for v in values if v]
    return max(values) if values else "—"


def _status_card(title: str, value: str, caption: str, tone: str = "blue") -> None:
    st.markdown(
        f"<div class='cg-card'><div class='cg-eyebrow'>{title}</div><h3 style='margin:.45rem 0;color:var(--cg-{tone if tone in {'brand','green','amber','red'} else 'text'})'>{value}</h3><p>{caption}</p></div>",
        unsafe_allow_html=True,
    )


def project_overview_page() -> None:
    from .platform_ui import active_paths, active_project

    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    st.header("项目总览 / Project Overview")
    st.caption("这里集中展示当前 Test Project 的执行状态；数据状态不代表 CompanionGuard 系统功能的开发完成度。")
    cases = load_raw_cases(paths.raw_cases)
    judges = [r for r in load_judge_results(paths.judge_results) if r.get("status") == "ok"]
    adjudications = load_adjudications(paths.adjudication)
    layer2 = load_jsonl(paths.layer2_records)
    layer3 = load_jsonl(paths.layer3_records)
    formal_cases = [r for r in cases if r.get("phase") == "FORMAL"]
    formal_judges = [r for r in judges if (r.get("metadata") or {}).get("phase", r.get("phase")) == "FORMAL" or r.get("case_id") in {c.get("case_id") for c in formal_cases}]
    cols = st.columns(4)
    for col, args in zip(cols, [
        ("正式对话数据采集", "已完成" if formal_cases else "尚无记录", f"FORMAL records available · {len(formal_cases)} 个", "green"),
        ("自动 Judge 初步判定", "已完成" if formal_judges else "尚无记录", f"auto_label available · {len(formal_judges)} 个", "brand"),
        ("人工复核", "进行中" if formal_judges and len(adjudications) < len(formal_judges) else ("已完成" if formal_judges else "尚无记录"), f"已保存 {len(adjudications)} / {len(formal_judges)} 个复核记录", "amber"),
        ("Layer 2 / Layer 3", f"{len(layer2)} / {len(layer3)} 条", "系统功能已具备；当前 Project 按真实记录显示", "brand"),
    ]):
        with col:
            _status_card(*args)

    st.markdown("<div class='cg-status' style='margin:1rem 0'><strong>当前项目状态</strong><br>系统功能已具备；这里显示的是当前 Project 已录入的数据状态。空数据不代表功能未完成。</div>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        section_intro("项目元数据")
        meta = {
            "project_id": project.get("project_id"),
            "phase": project.get("phase") or "FORMAL（由项目数据与记录确定）",
            "mode": project.get("mode"),
            "products": "、".join(p.get("label") or p.get("name") or p.get("id", "") for p in project.get("products", [])),
            "data_schema_version": project.get("data_schema_version") or project.get("schema_version") or "legacy（内存推断）",
            "data_cutoff": _date_cutoff(cases),
        }
        st.dataframe(pd.DataFrame([meta]).T.rename(columns={0: "当前值"}), use_container_width=True)
    with right:
        section_intro("当前数据口径")
        st.markdown(f"<div class='cg-card'><p>当前项目包含 {len(cases)} 个原始案例、{len(judges)} 个成功自动判定、{len(adjudications)} 条人工复核记录、{len(layer2)} 条 Layer 2 记录和 {len(layer3)} 条 Layer 3 记录。</p><p>正式指标仅由 FORMAL 且满足案例有效性要求的数据驱动；SMOKE / CALIBRATION 不混入正式统计。</p></div>", unsafe_allow_html=True)


def test_plan_page() -> None:
    from .platform_ui import active_paths, active_project

    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    st.header("测试计划 / Test Plan")
    st.caption("冻结协议以只读方式展示；产品与 Test Plan 保持解耦，不会修改 Prompt、条件路由、轮次结构或 case_id。")
    plans: list[dict[str, Any]] = []
    if paths.test_plans.exists():
        try:
            value = json.loads(paths.test_plans.read_text(encoding="utf-8"))
            plans = value if isinstance(value, list) else [value]
        except (OSError, json.JSONDecodeError):
            plans = []
    if not plans:
        empty_state("当前项目暂无测试计划记录", "创建测试计划后，冻结的覆盖范围将在此展示。")
        return
    st.markdown(" ".join([
        pill("Frozen Protocol · Read Only", tone="green"),
        pill(f"phase · {plans[0].get('phase', project.get('phase', '—'))}"),
        pill("machine values unchanged"),
    ]), unsafe_allow_html=True)
    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    for plan in plans:
        criteria_ids = plan.get("criterion_ids") or list((plan.get("selections") or {}).keys())
        st.markdown(f"### {plan.get('product') or plan.get('product_id', '—')} <span class='cg-micro'>· {plan.get('plan_name', plan.get('plan_id', 'Test Plan'))}</span>", unsafe_allow_html=True)
        st.caption(f"plan_id: {plan.get('plan_id', '—')} · coverage_type: {plan.get('coverage_type', '—')} · phase: {plan.get('phase', '—')} · {len(criteria_ids)} 个 criterion")
    st.divider()
    section_intro("冻结条件结构")
    cols = st.columns(3)
    for col, (title, body, tone) in zip(cols, [
        ("C0｜标准条件 / Baseline Condition", "L1–L4 合并输入 → A4；标准 L5 → A5。", "blue"),
        ("C1｜压力条件 / Pressure Condition", "与 C0 相同的 L1–L4；Pressure L5 → A5。", "amber"),
        ("C2｜多轮条件 / Sequential Multi-turn Condition", "L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5。", ""),
    ]):
        with col:
            st.markdown(f"<div class='cg-card'><div>{pill(title, tone=tone)}</div><p style='margin-top:.7rem'>{body}</p></div>", unsafe_allow_html=True)

    section_intro("测试覆盖矩阵", "矩阵由当前 Project 的 Test Plan 记录驱动；不存在的记录不会被伪造为已执行。")
    rows = []
    for plan in plans:
        selections = plan.get("selections") or {}
        for cid in plan.get("criterion_ids") or sorted(selections):
            item = selections.get(cid, {}) if isinstance(selections, dict) else {}
            scenarios = item.get("scenarios") if isinstance(item, dict) else None
            rows.append({
                "产品": plan.get("product") or plan.get("product_id"),
                "测试项目": criterion_label(cid),
                "场景数量": len(scenarios) if isinstance(scenarios, list) else "—",
                "阶段": plan.get("phase"),
                "覆盖类型": plan.get("coverage_type"),
            })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def results_page_v09() -> None:
    """Display automatic results immediately, without pretending they are final."""
    from .platform_ui import active_paths, active_project

    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    st.header("对话评测结果与指标 / Dialogue Results & Metrics")
    st.caption("结果数据按当前 Project 实际记录展示；自动 Judge 结果与人工最终裁定严格分开。")
    raw_cases = {c.get("case_id"): c for c in load_raw_cases(paths.raw_cases)}
    adjudications = {r.get("case_id"): r for r in load_adjudications(paths.adjudication)}
    auto_rows: list[dict[str, Any]] = []
    for row in load_judge_results(paths.judge_results):
        if row.get("status") != "ok" or not row.get("case_id"):
            continue
        case = raw_cases.get(row["case_id"], {})
        metadata = case.get("metadata") or row.get("metadata") or {}
        auto_rows.append({
            **row,
            "scenario_id": case.get("scenario_id") or metadata.get("scenario_id"),
            "condition": case.get("condition", row.get("condition")),
            "phase": case.get("phase") or metadata.get("phase") or row.get("phase"),
            "run_number": case.get("run_number") or metadata.get("run_number"),
            "module": row.get("module"),
            "adjudication_status": "REVIEWED" if row["case_id"] in adjudications else "UNREVIEWED",
        })
    if not auto_rows:
        empty_state("当前项目暂无成功的自动 Judge 记录", "完成自动判定后，FINDING、NO_FINDING 和 REVIEW 将在此按 Project 数据展示。")
        return

    st.markdown("<div class='cg-note'>以下结果均标注为<strong>自动初判</strong>。未人工复核的案例不会显示为人工确认，也不会被写成 final_label。</div>", unsafe_allow_html=True)
    phases = sorted({str(r.get("phase") or "") for r in auto_rows if r.get("phase")})
    default_phase = ["FORMAL"] if "FORMAL" in phases else phases
    selected_phase = st.multiselect("阶段 / Phase", phases, default=default_phase, format_func=phase_label, key="results_v09_phase")
    products = sorted({str(r.get("product") or "") for r in auto_rows if r.get("product")})
    selected_products = st.multiselect("产品 / Product", products, default=products, key="results_v09_products")
    conditions = sorted({str(r.get("condition") or "") for r in auto_rows if r.get("condition")})
    selected_conditions = st.multiselect("条件 / Condition", conditions, default=conditions, format_func=condition_label, key="results_v09_conditions")
    filtered = [r for r in auto_rows if (not selected_phase or r.get("phase") in selected_phase) and (not selected_products or r.get("product") in selected_products) and (not selected_conditions or r.get("condition") in selected_conditions)]
    counts = label_counts(filtered)
    cols = st.columns(4)
    for col, title, value, caption in zip(cols, ["自动初判案例", "FINDING", "NO_FINDING", "REVIEW"], [len(filtered), counts["FINDING"], counts["NO_FINDING"], counts["REVIEW"]], ["当前筛选", "自动初判", "自动初判", "自动初判"]):
        with col:
            st.metric(title, value, help=caption)
    st.caption(f"当前筛选包含 {sum(r.get('adjudication_status') == 'REVIEWED' for r in filtered)} 个已人工复核案例；其余为 UNREVIEWED。")

    display = []
    for row in filtered:
        criterion = criteria_for_result(row)
        display.append({
            "案例编号": row.get("case_id"),
            "产品": row.get("product"),
            "模块": module_label(row.get("module")),
            "测试项目": criterion_label(row.get("criterion_id"), criterion),
            "场景": scenario_label(criterion, row.get("scenario_id")),
            "条件": condition_label(row.get("condition"), template=criterion.get("judge_template")),
            "阶段": phase_label(row.get("phase")),
            "案例有效性": row.get("auto_case_validity") or "VALID",
            "自动风险标签": row.get("auto_label"),
            "人工复核状态": row.get("adjudication_status"),
        })
    st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
    st.download_button("下载当前自动初判 CSV", data=pd.DataFrame(display).to_csv(index=False).encode("utf-8-sig"), file_name="companionguard_auto_results.csv", mime="text/csv")

    final_rows = load_final_results(paths.final_results)
    if final_rows:
        st.markdown("### 正式最终指标 / Final formal metrics")
        st.caption("仅在 final_label 与人工复核数据实际具备时显示；当前页面不会用自动标签伪造最终指标。")
        st.info(f"当前已有 {len(final_rows)} 条 final_results 记录，可进入“判定一致性 / Reliability”或“综合报告”继续分析。")
    else:
        st.markdown("<div class='cg-empty'><strong>正式最终指标暂不显示</strong><br>当前尚未形成可用的 final_label；自动初判结果已在上方展示。</div>", unsafe_allow_html=True)


def criteria_for_result(row: dict[str, Any]) -> dict[str, Any]:
    return criteria_index().get(row.get("criterion_id"), {})


def integrated_report_page_v09() -> None:
    """Current-report view with deterministic summary first and v1.1 writer optional."""
    from .platform_ui import active_paths, active_project

    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    from .projects import is_read_only_project

    read_only = is_read_only_project(project)
    st.header("综合评测报告 / Integrated Report")
    st.caption("当前报告随 Project 数据更新；下游报告产物保存在项目的 reports/ 目录，不改写原始采集数据。")
    criteria = criteria_index()
    if not read_only:
        build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results, policy=project.get("human_adjudication_policy", "FULL_ADJUDICATION"))
    rows = load_final_results(paths.final_results)
    deterministic = build_integrated_report(project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records)
    deterministic_path = paths.reports / "integrated_report_deterministic.md"
    if not read_only:
        paths.reports.mkdir(parents=True, exist_ok=True)
        deterministic_path.write_text(deterministic, encoding="utf-8")
    final_path = paths.reports / "final_report.md"
    context_path = paths.reports / "report_context.json"
    st.markdown(f"<div class='cg-card'><p><strong>Project：</strong>{project.get('project_name', project.get('project_id'))}</p><p><strong>Data cutoff：</strong>{_date_cutoff(load_raw_cases(paths.raw_cases))} · <strong>纳入范围：</strong>FORMAL 阶段有效数据 · <strong>当前报告：</strong>{'已生成' if final_path.exists() else '尚未生成 LLM 版本'}</p></div>", unsafe_allow_html=True)
    st.markdown("### 当前报告")
    if final_path.exists():
        st.markdown(final_path.read_text(encoding="utf-8"))
        st.download_button("下载当前 LLM 综合报告", data=final_path.read_bytes(), file_name=f"{project.get('project_id')}_final_report.md", mime="text/markdown")
    else:
        st.markdown(deterministic)
        st.download_button("下载确定性分析摘要", data=deterministic.encode("utf-8"), file_name=f"{project.get('project_id')}_deterministic_summary.md", mime="text/markdown")
    with st.expander("报告产物与生成链", expanded=False):
        st.caption("FORMAL Project Data → Python deterministic analysis → report_context → Report Writer → Hard Validation → Evidence Grounding → Academic Polish（可选）")
        st.write({"deterministic_summary": str(deterministic_path) if deterministic_path.exists() else "只读快照中不写入派生文件", "report_context": str(context_path) if context_path.exists() else "只读快照中不写入派生文件", "final_report": str(final_path) if final_path.exists() else "尚无已生成 LLM 报告"})
    if read_only:
        st.info("当前为只读公开演示快照。Server API / BYOK 模式仍保留在应用代码中，但不会对公开快照执行写入型 Judge 或报告生成。")
        return
    st.markdown("### 生成 / 更新报告")
    st.caption("生成 v1.1 LLM 综合报告需要分别配置 Integrated Report Writer 与 Evidence Grounding Validator。Academic Polish 本页不自动启用。")
    writer_profile = render_llm_profile_selector("integrated_report", key_prefix="v09_integrated_report_writer")
    grounding_profile = render_llm_profile_selector("grounding_validator", key_prefix="v09_integrated_report_grounding")
    llm_actionbar(title="Integrated Report Writer · LLM", profile=writer_profile, notes=["Hard Validation", "Evidence Grounding"])
    if st.button("生成 / 更新综合评测报告", type="primary", disabled=writer_profile is None or grounding_profile is None, key="v09_generate_integrated_report"):
        try:
            context = build_integrated_report_context(project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records)
            draft = run_report_writer(role="integrated_report", report_context=context, llm_profile=writer_profile, session_id=llm_session_id(), project_id=project.get("project_id"), prompt_version="1.1")
            grounding = run_grounding_validator(draft_report=draft, report_context=context, llm_profile=grounding_profile, session_id=llm_session_id(), project_id=project.get("project_id"), prompt_version="1.1")
            result = write_report_artifacts(report_type="integrated", project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records, reports_dir=paths.reports, draft_text=draft, grounding_validator=lambda _draft, _context: grounding, polish=None, writer_prompt_version="1.1")
            if result["manifest"]["validation_status"] == "PASS":
                st.success("LLM 综合报告已生成并通过校验。")
                st.rerun()
            st.error("报告未通过校验，未发布 final_report.md；请查看 grounding_result.json。")
        except Exception as exc:
            st.error(str(exc))
