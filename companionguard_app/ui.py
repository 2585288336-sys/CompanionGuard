from __future__ import annotations

import json
import random
from typing import Any

import pandas as pd
import streamlit as st

from .cases import (
    build_case,
    build_conversation_template,
    conversation_json,
    flatten_single_turn_scenarios,
    parse_conversation_json,
)
from .adjudication import (
    SAMPLED_ADJUDICATION,
    adjudication_policy,
    build_sampling_plan,
    load_sampling_plan,
    review_case_ids,
    save_sampling_plan,
)
from .collector_storage import load_raw_cases
from .config import CASE_VALIDITIES, MODULE_LABELS, OVERRIDE_REASONS, VALIDITY_REASONS
from .metrics import case_validity_counts, label_counts, module_finding_rates, overall_macro_finding_rate, robustness_gap, valid_case_rows
from .platform_ui import active_project, active_paths
from .llm_ui import llm_session_id, render_llm_profile_selector
from .service import criteria_index, run_batch_cases, run_single_case
from .ui_helpers import condition_label, render_case_validity, render_evidence_files, render_judge_result
from .storage import (
    build_final_results,
    load_adjudications,
    load_final_results,
    load_judge_results,
    save_adjudication,
)


@st.cache_data(show_spinner=False)
def get_criteria() -> dict[str, dict[str, Any]]:
    return criteria_index()


def _criterion_label(item: tuple[str, dict[str, Any]]) -> str:
    cid, obj = item
    return f"{cid} · {obj.get('criterion_name_zh', '')}"


def _judge_result_card(row: dict[str, Any]) -> None:
    render_judge_result(row, compact=False)


def _run_collected_single_case(*, project: dict[str, Any], paths, criteria: dict[str, dict[str, Any]], llm_profile) -> None:
    cases = load_raw_cases(paths.raw_cases)
    if not cases:
        st.info("data/raw_cases.jsonl 还没有已完成的采集case。请先到 Data Collection 完成至少一个case，或切换到手动 / Ad-hoc 输入。")
        return

    cases = sorted(cases, key=lambda case: str(case.get("case_id", "")))
    labels = {
        case.get("case_id"): (
            f"{case.get('case_id')} · {case.get('product') or '—'} · "
            f"{case.get('criterion_id')} · {case.get('condition') or 'N/A'} · "
            f"{case.get('phase') or (case.get('metadata') or {}).get('phase') or '—'}"
        )
        for case in cases
    }
    selected_id = st.selectbox(
        "已采集 Case / Collected Case",
        [case.get("case_id") for case in cases],
        format_func=lambda value: labels.get(value, str(value)),
    )
    case = next(case for case in cases if case.get("case_id") == selected_id)
    metadata = case.get("metadata") or {}
    st.caption(
        f"Product: {case.get('product') or '—'} · Criterion: {case.get('criterion_id') or '—'} · "
        f"Condition: {case.get('condition') or 'N/A'} · Phase: {case.get('phase') or metadata.get('phase') or '—'}"
    )
    with st.expander("预览已采集对话 / Preview collected conversation", expanded=True):
        for message in case.get("conversation") or []:
            st.markdown(f"**{message.get('turn', '')} · {message.get('role', '')}**")
            st.code(message.get("content", ""), language=None)
        for index, step in enumerate(case.get("collection_trace") or []):
            render_evidence_files(
                step.get("evidence_files"),
                project_root=paths.root,
                key_prefix=f"judge-collected::{selected_id}::{index}",
            )
    with st.expander("Raw Case JSON", expanded=False):
        st.json(case)

    prior = [
        row for row in load_judge_results(paths.judge_results)
        if row.get("case_id") == selected_id and row.get("status") == "ok"
    ]
    if prior:
        st.info("该 case 已有成功 Judge 结果；为避免重复实验记录，当前不重复写入。")
        _judge_result_card(prior[-1])
        return

    if st.button("对已采集 Case 运行 Judge / Run Judge", type="primary", key="run_collected_case"):
        if not llm_profile:
            st.error("请先配置 Dialogue Judge LLM。")
            return
        try:
            with st.spinner("Running criterion-bound LLM Judge..."):
                row = run_single_case(
                    case=case,
                    criteria=criteria,
                    llm_profile=llm_profile,
                    persist=True,
                    judge_path=paths.judge_results,
                    session_id=llm_session_id(),
                    project_id=project.get("project_id"),
                )
            st.session_state["last_judge_result"] = row
        except Exception as exc:
            st.error(str(exc))

    if st.session_state.get("last_judge_result", {}).get("case_id") == selected_id:
        _judge_result_card(st.session_state["last_judge_result"])


def _run_manual_single_case(*, project: dict[str, Any], paths, criteria: dict[str, dict[str, Any]], llm_profile) -> None:
    criterion_items = sorted(criteria.items())
    selected = st.selectbox(
        "Criterion",
        options=criterion_items,
        format_func=_criterion_label,
        key="manual_judge_criterion",
    )
    criterion_id, criterion = selected
    template = criterion["judge_template"]
    product = st.text_input("Product / Model", value="", key="manual_judge_product")

    condition = None
    scenario_id = None
    category = None
    if template in ("core_l1_l5", "hr02_crisis"):
        conditions = ["C0"]
        if (criterion.get("pressure_variant") or {}).get("L5"):
            conditions.append("C1")
        conditions.append("C2")
        condition = st.selectbox("Condition", conditions, key="manual_judge_condition")
        if "C1" not in conditions:
            st.caption("该criterion当前没有冻结的C1 pressure prompt，因此单条构造器不提供C1；批量输入仍可运行你已另行冻结的合法C1 case。")
    elif template == "mr_minor_relationship":
        scenarios = list((criterion.get("canonical_scenario") or {}).keys())
        scenario_id = st.selectbox("Scenario", scenarios, key="manual_judge_scenario")
    else:
        scenarios = flatten_single_turn_scenarios(criterion)
        scenario_id = st.selectbox("Scenario", list(scenarios), key="manual_judge_scenario")
        category = criterion_id if scenario_id == criterion_id else scenario_id.rsplit("-", 1)[0]

    template_key = f"conversation_template::{criterion_id}::{condition}::{scenario_id}"
    if st.session_state.get("conversation_template_key") != template_key:
        st.session_state["conversation_editor"] = conversation_json(
            build_conversation_template(criterion, condition=condition or "C0", scenario_id=scenario_id)
        )
        st.session_state["conversation_template_key"] = template_key

    st.caption("把 `<PASTE_MODEL_RESPONSE>` 替换为真实模型输出。C2需要保留完整A1–A5上下文。")
    conversation_text = st.text_area("Conversation JSON", key="conversation_editor", height=360)
    default_case_id = f"{scenario_id or criterion_id}_{condition or 'default'}_{product or 'product'}_run1"
    case_id = st.text_input("Case ID", value=default_case_id, key="manual_judge_case_id")

    if st.button("Run Ad-hoc Judge", type="primary", key="run_manual_case"):
        if not llm_profile:
            st.error("请先配置 Dialogue Judge LLM。")
        elif not product.strip():
            st.error("请填写Product / Model。")
        else:
            try:
                conversation = parse_conversation_json(conversation_text)
                case = build_case(
                    case_id=case_id.strip(), criterion_id=criterion_id, product=product.strip(),
                    condition=condition, conversation=conversation, category=category,
                    metadata={"source": "streamlit_single_ad_hoc"},
                )
                with st.spinner("Running criterion-bound LLM Judge..."):
                    row = run_single_case(
                        case=case, criteria=criteria, llm_profile=llm_profile, persist=True,
                        judge_path=paths.judge_results, session_id=llm_session_id(),
                        project_id=project.get("project_id"),
                    )
                st.session_state["last_judge_result"] = row
            except Exception as exc:
                st.error(str(exc))

    if st.session_state.get("last_judge_result"):
        _judge_result_card(st.session_state["last_judge_result"])


def run_test_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.header("LLM 判定 / LLM Judge")
    st.caption(f"Active Project: {project.get('project_name')} ({project.get('project_id')})")
    st.caption("Benchmark Mode：选择冻结criterion，输入真实模型回复，通过可配置LLM Provider运行 criterion-bound Judge。")
    criteria = get_criteria()
    llm_profile = render_llm_profile_selector("judge", key_prefix="run_test_judge")

    single_tab, batch_tab = st.tabs(["单条测试", "批量JSONL"])

    with single_tab:
        source_mode = st.radio(
            "单条输入来源 / Single-case source",
            ["已采集 Case", "手动 / Ad-hoc"],
            horizontal=True,
            key="single_judge_source_mode",
        )
        if source_mode == "已采集 Case":
            _run_collected_single_case(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)
        else:
            _run_manual_single_case(project=project, paths=paths, criteria=criteria, llm_profile=llm_profile)

    with batch_tab:
        source = st.radio(
            "Case source",
            ["Collected raw_cases.jsonl", "Upload JSONL"],
            horizontal=True,
        )
        cases: list[dict[str, Any]] = []
        try:
            if source == "Collected raw_cases.jsonl":
                cases = load_raw_cases(paths.raw_cases)
                if not cases:
                    st.info("data/raw_cases.jsonl 还没有已完成的采集case。先到 Data Collection 完成至少一个case。")
                else:
                    phases = sorted({str(c.get("phase") or (c.get("metadata") or {}).get("phase") or "") for c in cases})
                    phase_filter = st.multiselect("Phase", [p for p in phases if p], default=[p for p in phases if p])
                    if phase_filter:
                        cases = [c for c in cases if (c.get("phase") or (c.get("metadata") or {}).get("phase")) in phase_filter]
                    st.success(f"从 data/raw_cases.jsonl 读取到 {len(cases)} 个case。")
            else:
                uploaded = st.file_uploader("上传cases JSONL", type=["jsonl", "json"])
                if uploaded is not None:
                    raw = uploaded.getvalue().decode("utf-8")
                    cases = [json.loads(line) for line in raw.splitlines() if line.strip()]
                    st.success(f"读取到 {len(cases)} 个case。")

            if cases:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "case_id": c.get("case_id"),
                            "criterion_id": c.get("criterion_id"),
                            "product": c.get("product"),
                            "condition": c.get("condition"),
                            "phase": c.get("phase") or (c.get("metadata") or {}).get("phase"),
                        }
                        for c in cases
                    ]),
                    use_container_width=True,
                    hide_index=True,
                )
                if st.button("Run Batch", type="primary"):
                    if not llm_profile:
                        st.error("请先配置 Dialogue Judge LLM。")
                    else:
                        progress_bar = st.progress(0.0)
                        status_box = st.empty()

                        def progress(i: int, total: int, case_name: str) -> None:
                            progress_bar.progress(i / max(total, 1))
                            status_box.caption(f"{i}/{total} · {case_name}")

                        with st.spinner("Running batch..."):
                            results = run_batch_cases(
                                cases=cases,
                                criteria=criteria,
                                llm_profile=llm_profile,
                                progress=progress,
                                judge_path=paths.judge_results,
                                session_id=llm_session_id(),
                                project_id=project.get("project_id"),
                            )
                        ok = sum(r.get("status") == "ok" for r in results)
                        st.success(f"完成：{ok}/{len(results)} 成功。结果已写入 data/judge_results.jsonl")
        except Exception as e:
            st.error(str(e))


def human_review_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.header("人工复核 / Human Review")
    st.caption(f"Active Project: {project.get('project_name')}")
    criteria = get_criteria()
    judge_rows = [r for r in load_judge_results(paths.judge_results) if r.get("status") == "ok"]
    adjudicated = {r["case_id"]: r for r in load_adjudications(paths.adjudication)}

    if not judge_rows:
        st.info("还没有可复核的Judge结果。先在 Run Test 运行至少一个case。")
        return

    policy = adjudication_policy(project)
    if project.get("mode") == "BENCHMARK" and policy == SAMPLED_ADJUDICATION:
        st.info("Benchmark Mode：本项目使用预注册抽样人工复核。所有 FORMAL case 仍由 LLM Judge 全量判定；自动 risk label=REVIEW 或 auto validity=REVIEW 的 case 强制人工复核。")
        sampling_plan = load_sampling_plan(paths.adjudication_sampling)
        if sampling_plan is None:
            preview_plan = build_sampling_plan(judge_rows=judge_rows, project=project)
            st.warning("抽样方案尚未冻结。先检查候选数量，再冻结方案；冻结后固定 case ID、比例、分层维度和随机种子。")
            st.write(
                f"预计人工复核：{len(preview_plan['selected_case_ids'])} / "
                f"{preview_plan['formal_judge_case_count']} 个 FORMAL case；"
                f"其中强制复核 {len(preview_plan['forced_case_ids'])} 个。"
            )
            if preview_plan["selected_case_ids"]:
                st.dataframe(
                    [{"case_id": case_id, "forced": case_id in preview_plan["forced_case_ids"]} for case_id in preview_plan["selected_case_ids"]],
                    use_container_width=True,
                    hide_index=True,
                )
            if st.button(
                "冻结抽样方案 / Freeze Sampling Plan",
                type="primary",
                disabled=preview_plan["formal_judge_case_count"] == 0,
            ):
                save_sampling_plan(preview_plan, paths.adjudication_sampling)
                st.success("抽样方案已冻结。")
                st.rerun()
            if preview_plan["formal_judge_case_count"] == 0:
                st.caption("当前还没有成功的 FORMAL Judge 结果；完成 FORMAL Judge 后再冻结抽样方案。")
        else:
            st.caption(
                f"Sampling plan frozen · {sampling_plan.get('sampling_method')} · "
                f"rate={sampling_plan.get('sample_rate')} · seed={sampling_plan.get('random_seed')} · "
                f"selected={len(sampling_plan.get('selected_case_ids') or [])}"
            )
        review_ids = review_case_ids(judge_rows=judge_rows, project=project, sampling_plan=sampling_plan)
        pending = [
            r for r in judge_rows
            if r.get("case_id") in review_ids
            and (
                r.get("case_id") not in adjudicated
                or not adjudicated.get(r.get("case_id"), {}).get("final_case_validity")
                and not adjudicated.get(r.get("case_id"), {}).get("case_validity")
            )
        ]
        mode = st.radio("显示", ["待复核", "已纳入方案"], horizontal=True)
        candidates = pending if mode == "待复核" else [r for r in judge_rows if r.get("case_id") in review_ids]
    elif project.get("mode") == "BENCHMARK":
        st.info("Benchmark Mode：本项目使用全量人工复核；每个 FORMAL case 都需要人工 risk label adjudication。Case validity 正常情况下自动为 VALID，只有异常筛查结果需要重点确认。")
        pending = [
            r for r in judge_rows
            if r.get("case_id") not in adjudicated
            or not adjudicated.get(r.get("case_id"), {}).get("final_case_validity")
            and not adjudicated.get(r.get("case_id"), {}).get("case_validity")
        ]
        mode = st.radio("显示", ["待复核", "全部"], horizontal=True)
        candidates = pending if mode == "待复核" else judge_rows
    else:
        review_scope = st.radio("Review scope", ["全部待复核", "随机抽样", "按Criterion分层抽样", "全部结果"], horizontal=True)
        if review_scope == "全部结果":
            candidates = judge_rows
        elif review_scope == "随机抽样":
            n = int(st.number_input("Sample size", min_value=1, max_value=max(len(pending), 1), value=min(10, max(len(pending), 1))))
            candidates = random.Random(42).sample(pending, min(n, len(pending))) if pending else []
        elif review_scope == "按Criterion分层抽样":
            per_criterion = int(st.number_input("Cases per criterion", min_value=1, max_value=20, value=1))
            grouped = {}
            for row in pending:
                grouped.setdefault(row.get("criterion_id"), []).append(row)
            candidates = []
            rng = random.Random(42)
            for cid in sorted(grouped, key=str):
                group = grouped[cid]
                candidates.extend(rng.sample(group, min(per_criterion, len(group))))
        else:
            candidates = pending
    if not candidates:
        st.success("当前没有待复核case。")
        return

    selected_id = st.selectbox(
        "Case",
        [r["case_id"] for r in candidates],
    )
    row = next(r for r in candidates if r["case_id"] == selected_id)
    criterion = criteria.get(row.get("criterion_id"), {})
    result = row.get("result") or {}

    st.subheader(f"{row.get('criterion_id')} · {criterion.get('criterion_name_zh', '')}")
    st.caption("先查看 LLM Judge 的结构化判定，再进行人工 Confirm / Override。")
    render_judge_result(row, compact=True)
    auto_case_validity = row.get("auto_case_validity") or "VALID"
    prior = adjudicated.get(selected_id, {})
    render_case_validity(auto_case_validity, title="Auto Case Validity / 自动有效性筛查")
    if prior.get("final_case_validity") or prior.get("case_validity"):
        render_case_validity(prior.get("final_case_validity") or prior.get("case_validity"), title="Final Case Validity / 最终有效性")

    auto = row.get("auto_label", "NO_FINDING")
    default_label = prior.get("human_label") or auto
    labels = ["FINDING", "NO_FINDING", "REVIEW"]
    default_validity = prior.get("final_case_validity") or prior.get("case_validity") or auto_case_validity

    with st.form("adjudication_form"):
        human_label = st.selectbox(
            "人工标签 / Human Label",
            labels,
            index=labels.index(default_label) if default_label in labels else 0,
        )
        override_reason = ""
        if human_label != auto:
            override_reason = st.selectbox("Override 原因 / Override Reason", OVERRIDE_REASONS, help="Override = 人工判定与 LLM 自动标签不一致时，用人工标签覆盖自动标签，并记录原因。")
        case_validity = st.selectbox(
            "Case 有效性 / Case Validity",
            CASE_VALIDITIES,
            index=CASE_VALIDITIES.index(default_validity) if default_validity in CASE_VALIDITIES else 2,
            help="有效性独立于 FINDING / NO_FINDING / REVIEW 风险标签。INVALID 和 REVIEW 不进入正式风险指标，但会保留审计记录。",
        )
        validity_reason = ""
        if case_validity != "VALID":
            validity_reason = st.selectbox("有效性原因 / Validity Reason", VALIDITY_REASONS, index=VALIDITY_REASONS.index(prior.get("validity_reason")) if prior.get("validity_reason") in VALIDITY_REASONS else 0)
        validity_note = st.text_area("有效性备注 / Validity Note", value=prior.get("validity_note", ""))
        review_note = st.text_area("复核备注 / Review Note", value=prior.get("review_note", ""))
        submitted = st.form_submit_button("保存人工复核 / Save Adjudication", type="primary")

    if submitted:
        save_adjudication(
            case_id=selected_id,
            auto_label=auto,
            human_label=human_label,
            override_reason=override_reason,
            review_note=review_note,
            case_validity=case_validity,
            auto_case_validity=auto_case_validity,
            final_case_validity=case_validity,
            validity_reason=validity_reason,
            validity_note=validity_note,
            path=paths.adjudication,
        )
        build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results, policy=policy)
        st.success("已保存人工复核，并更新 data/final_results.csv。")
        st.rerun()

    with st.expander("完整Judge JSON"):
        st.json(result)


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _pp(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.1f} pp"


def results_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.header("对话测试结果 / Dialogue Results")
    st.caption(f"Active Project: {project.get('project_name')}")
    criteria = get_criteria()
    build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results, policy=adjudication_policy(project))
    rows = load_final_results(paths.final_results)
    if not rows:
        st.info("还没有final results。先完成至少一个Human Review。")
        return

    df = pd.DataFrame(rows)
    if "phase" not in df.columns:
        df["phase"] = ""
    formal_all = df[df["phase"] == "FORMAL"].copy()
    formal = pd.DataFrame(valid_case_rows(formal_all.to_dict("records")))
    validity = case_validity_counts(formal_all.to_dict("records"))
    if formal.empty:
        st.info("当前没有 phase == FORMAL 的有效分析结果。SMOKE/CALIBRATION/旧版无phase记录不会进入正式指标。")
        if not formal_all.empty:
            st.warning(f"FORMAL 记录存在，但没有 VALID case。INVALID: {validity['INVALID']}；REVIEW: {validity['REVIEW']}。")
        with st.expander("Excluded or non-formal adjudicated records"):
            st.dataframe(df, use_container_width=True, hide_index=True)
        return

    st.caption("Official analysis view: only phase == FORMAL and Case Validity == VALID are included in metrics and the Finding Matrix.")
    if validity["INVALID"] or validity["REVIEW"]:
        st.info(f"Validity exclusion: INVALID {validity['INVALID']}；REVIEW {validity['REVIEW']}。这些 case 保留在 final_results.csv 和审计视图中。")
    st.sidebar.markdown("### Results Filters")
    products = sorted(x for x in formal["product"].dropna().unique() if x)
    modules = sorted(x for x in formal["module"].dropna().unique() if x)
    conditions = sorted(x for x in formal["condition"].dropna().unique() if x)
    selected_products = st.sidebar.multiselect("Product", products, default=products)
    selected_modules = st.sidebar.multiselect("Module", modules, default=modules)
    selected_conditions = st.sidebar.multiselect("Condition", conditions, default=conditions)

    filtered = formal.copy()
    if selected_products:
        filtered = filtered[filtered["product"].isin(selected_products)]
    if selected_modules:
        filtered = filtered[filtered["module"].isin(selected_modules)]
    if selected_conditions:
        filtered = filtered[filtered["condition"].isin(selected_conditions)]
    filtered_rows = filtered.to_dict("records")

    counts = label_counts(filtered_rows)
    macro = overall_macro_finding_rate(filtered_rows)
    pressure = robustness_gap(filtered_rows, "C1")
    multiturn = robustness_gap(filtered_rows, "C2")

    c1, c2, c3, c4 = st.columns(4)
    reviewed_count = sum((row.get("adjudication_status") or "REVIEWED") == "REVIEWED" for row in filtered_rows)
    c1.metric("FORMAL Cases in Analysis", len(filtered_rows))
    c2.metric("Findings", counts["FINDING"])
    c3.metric("总体宏平均风险发现率", _pct(macro))
    c4.metric("Review", counts["REVIEW"])
    st.caption(f"Analysis labels: REVIEWED {reviewed_count}；UNREVIEWED {len(filtered_rows) - reviewed_count}。未人工复核 case 使用 analysis_label=auto_label，不填充 human_label。")
    st.caption("Overall Macro Finding Rate 仅在五个冻结模块都有FORMAL结果时显示。")

    r1, r2 = st.columns(2)
    r1.metric("压力条件风险发现率差值（C1−C0）", _pp(pressure))
    r2.metric("多轮条件风险发现率差值（C2−C0）", _pp(multiturn))

    module_rates = module_finding_rates(filtered_rows)
    if module_rates:
        st.subheader("模块风险发现率 / Module Finding Rate")
        chart_df = pd.DataFrame([
            {
                "Module": MODULE_LABELS.get(module, module),
                "Finding Rate": rate,
            }
            for module, rate in module_rates.items()
        ]).set_index("Module")
        st.bar_chart(chart_df)

    st.subheader("风险发现矩阵 / Finding Matrix")
    matrix_cols = [
        "product", "criterion_id", "scenario_id", "condition", "run_number", "phase", "final_case_validity",
        "criterion_name", "analysis_label", "adjudication_status", "final_label", "matched_target_behaviors", "evidence", "override_reason",
    ]
    matrix_cols = [c for c in matrix_cols if c in filtered.columns]
    st.dataframe(filtered[matrix_cols], use_container_width=True, hide_index=True)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Download filtered FORMAL CSV",
        data=csv_bytes,
        file_name="companionguard_final_results_formal.csv",
        mime="text/csv",
    )

    nonformal = df[df["phase"] != "FORMAL"]
    if not nonformal.empty:
        with st.expander("Non-formal records (excluded from official metrics)"):
            st.dataframe(nonformal, use_container_width=True, hide_index=True)
    excluded_formal = formal_all[~formal_all["case_validity"].isin(["VALID"])]
    if not excluded_formal.empty:
        with st.expander("Invalid or unresolved FORMAL records (excluded from official metrics)"):
            st.dataframe(excluded_formal, use_container_width=True, hide_index=True)
