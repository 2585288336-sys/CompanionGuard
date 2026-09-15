"""Public Home and project workspace presentation pages for UI v0.9."""

from __future__ import annotations

import json
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
from .ui_theme import card, empty_state, flow, hero, pill, section_intro


def _go(page: str) -> None:
    st.session_state["requested_nav"] = page
    st.rerun()


def home_page(project: dict[str, Any] | None = None) -> None:
    hero(
        eyebrow="Regulatory Testing & Risk Diagnosis",
        title="把拟人化 AI 的监管要求，转化为可执行、可复核的测试。",
        body="CompanionGuard 是一套面向拟人化 AI 服务的监管测试与风险诊断框架。项目从监管要求出发，将抽象义务转化为真实产品上可以执行、记录和复核的测试要求，重点观察过度迎合、情感依赖、退出挽留、危机应对、未成年人保护和敏感信息诱导等过程性风险。",
    )
    left, right = st.columns([1, 1])
    with left:
        if st.button("进入 Test Project", type="primary", use_container_width=True, key="home_enter_project"):
            _go("overview" if project else "projects")
    with right:
        st.markdown("<div class='cg-note'>Finding 表示在预设监管测试场景中观察到的风险表现，用于定位问题和支持后续审核，不等同于正式的法律不合规认定。</div>", unsafe_allow_html=True)

    if project:
        st.markdown(
            f"<div class='cg-micro' style='margin-top:1rem'>当前 Test Project · 结果数据将随 {project.get('project_name', project.get('project_id'))} 持续更新。</div>",
            unsafe_allow_html=True,
        )

    section_intro("三层评测框架", "三层证据分别回答不同问题，可以相互印证，也可能出现差异；系统不将其压缩为单一安全分或合规分。")
    cols = st.columns(3)
    layers = [
        ("Layer 1", "对话行为证据", "通过标准化场景观察模型实际回应、目标风险及其出现时点。"),
        ("Layer 2", "产品安全机制检查", "检查外部研究者能够观察、操作和触发的产品保护机制。"),
        ("Layer 3", "公开合规证据核查", "核查公开正式材料能够支持到什么程度，并保留证据边界。"),
    ]
    for col, (code, title, text) in zip(cols, layers):
        with col:
            card(f"{code}｜{title}", text)

    section_intro("评测范围", "首页使用自然中文说明；具体 criterion_id、scenario_id 与机器值仍由 Project 数据和冻结配置驱动。")
    scope = [
        ("关系安全", "过度迎合、排他性关系、现实关系替代，以及用户退出和现实事务冲突中的挽留压力。"),
        ("极端行为与危机应对", "暴力支持、自伤自杀安全应对，以及语言暴力和人格伤害。"),
        ("未成年人保护", "虚拟亲密关系边界，以及不安全行为、极端情绪和不良嗜好等内容保护。"),
        ("信息与权益保护", "工作或商业秘密、第三方隐私、个人信息和国家秘密相关的诱导披露。"),
        ("禁止性内容生成专项测试", "通过固定单轮场景检查七类明确禁止内容，作为传统内容安全测试的补充。"),
    ]
    cols = st.columns(5)
    for col, (title, text) in zip(cols, scope):
        with col:
            card(title, text)

    section_intro("从监管要求到可追溯结论")
    flow(["监管要求", "可观察要求", "测试场景 / 产品检查", "证据记录", "结构化判定", "人工复核", "Finding"])

    section_intro("构建与方法", "从监管要求到可执行、可复核的 AI 测试。完整定义仍以正式方法说明为准。")
    methods = [
        ("01", "从监管要求出发设计测试", "把监管义务转化为可观察行为或产品机制。"),
        ("02", "用标准化场景观察真实对话表现", "通过 C0、C1、C2 比较标准、压力与多轮条件。"),
        ("03", "覆盖五类核心监管问题", "关系安全、危机应对、未成年人、信息权益和禁止性内容。"),
        ("04", "三层证据分别取证", "对话行为、产品机制和公开制度材料分开观察。"),
        ("05", "受准则约束的自动 Judge + 人工复核", "Judge 依据冻结标准，人工负责确认、改判和边界处理。"),
        ("06", "指标用于定位问题，不制造单一排名", "指标回答问题集中在哪里、何种条件下增加及判定是否可靠。"),
    ]
    cols = st.columns(3)
    for index, (num, title, text) in enumerate(methods):
        with cols[index % 3]:
            st.markdown(f"<div class='cg-card' style='margin-bottom:1rem'><div class='cg-eyebrow'>{num}</div><h3>{title}</h3><p>{text}</p></div>", unsafe_allow_html=True)

    section_intro("冻结条件结构")
    cols = st.columns(3)
    condition_text = [
        ("C0｜标准条件 / Baseline Condition", "L1–L4 合并发送 → A4；再发送普通 L5 → A5。"),
        ("C1｜压力条件 / Pressure Condition", "与 C0 相同的 L1–L4，仅增强 L5 互动压力 → A5。"),
        ("C2｜多轮条件 / Sequential Multi-turn Condition", "L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5。"),
    ]
    for col, (title, text) in zip(cols, condition_text):
        with col:
            card(title, text)


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
    st.header("评测结果 / Results")
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
    st.header("综合报告 / Integrated Report")
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
    if st.button("生成 / 更新 LLM 综合报告", type="primary", disabled=writer_profile is None or grounding_profile is None, key="v09_generate_integrated_report"):
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
