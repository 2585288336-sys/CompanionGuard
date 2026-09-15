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
from .collector_storage import load_raw_cases
from .config import MODULE_LABELS, OVERRIDE_REASONS
from .metrics import label_counts, module_finding_rates, overall_macro_finding_rate, robustness_gap
from .platform_ui import active_project, active_paths
from .llm_ui import llm_session_id, render_llm_profile_selector
from .service import criteria_index, run_batch_cases, run_single_case
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
    if row.get("status") != "ok":
        st.error(row.get("error") or "Judge运行失败")
        return
    result = row.get("result") or {}
    label = row.get("auto_label")
    c1, c2, c3 = st.columns(3)
    c1.metric("Auto Label", label)
    c2.metric("Criterion", row.get("criterion_id", ""))
    c3.metric("Judge Template", row.get("judge_template", ""))
    tcodes = result.get("matched_target_behaviors") or []
    if tcodes:
        st.write("Matched T-code:", ", ".join(tcodes))
    evidence = result.get("evidence") or []
    if evidence:
        st.write("Evidence")
        for item in evidence:
            st.code(item.get("quote", ""), language=None)
    if result.get("rationale"):
        st.write("Rationale:", result["rationale"])
    with st.expander("完整Judge JSON"):
        st.json(result)


def run_test_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.header("Run Test")
    st.caption(f"Active Project: {project.get('project_name')} ({project.get('project_id')})")
    st.caption("Benchmark Mode：选择冻结criterion，输入真实模型回复，通过可配置LLM Provider运行 criterion-bound Judge。")
    criteria = get_criteria()
    llm_profile = render_llm_profile_selector("judge", key_prefix="run_test_judge")

    single_tab, batch_tab = st.tabs(["单条测试", "批量JSONL"])

    with single_tab:
        criterion_items = sorted(criteria.items())
        selected = st.selectbox(
            "Criterion",
            options=criterion_items,
            format_func=_criterion_label,
        )
        criterion_id, criterion = selected
        template = criterion["judge_template"]
        product = st.text_input("Product / Model", value="")

        condition = None
        scenario_id = None
        category = None
        if template in ("core_l1_l5", "hr02_crisis"):
            conditions = ["C0"]
            if (criterion.get("pressure_variant") or {}).get("L5"):
                conditions.append("C1")
            conditions.append("C2")
            condition = st.selectbox("Condition", conditions)
            if "C1" not in conditions:
                st.caption("该criterion当前没有冻结的C1 pressure prompt，因此单条构造器不提供C1；批量输入仍可运行你已另行冻结的合法C1 case。")
        elif template == "mr_minor_relationship":
            scenarios = list((criterion.get("canonical_scenario") or {}).keys())
            scenario_id = st.selectbox("Scenario", scenarios)
        else:
            scenarios = flatten_single_turn_scenarios(criterion)
            scenario_id = st.selectbox("Scenario", list(scenarios))
            category = criterion_id if scenario_id == criterion_id else scenario_id.rsplit("-", 1)[0]

        template_key = f"conversation_template::{criterion_id}::{condition}::{scenario_id}"
        if st.session_state.get("conversation_template_key") != template_key:
            st.session_state["conversation_editor"] = conversation_json(
                build_conversation_template(
                    criterion,
                    condition=condition or "C0",
                    scenario_id=scenario_id,
                )
            )
            st.session_state["conversation_template_key"] = template_key

        st.caption("把 `<PASTE_MODEL_RESPONSE>` 替换为真实模型输出。C2需要保留完整A1–A5上下文。")
        conversation_text = st.text_area(
            "Conversation JSON",
            key="conversation_editor",
            height=360,
        )
        default_case_id = f"{scenario_id or criterion_id}_{condition or 'default'}_{product or 'product'}_run1"
        case_id = st.text_input("Case ID", value=default_case_id)

        if st.button("Run Judge", type="primary"):
            if not llm_profile:
                st.error("请先配置 Dialogue Judge LLM。")
            elif not product.strip():
                st.error("请填写Product / Model。")
            else:
                try:
                    conversation = parse_conversation_json(conversation_text)
                    case = build_case(
                        case_id=case_id.strip(),
                        criterion_id=criterion_id,
                        product=product.strip(),
                        condition=condition,
                        conversation=conversation,
                        category=category,
                        metadata={"source": "streamlit_single"},
                    )
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
                except Exception as e:
                    st.error(str(e))

        if st.session_state.get("last_judge_result"):
            _judge_result_card(st.session_state["last_judge_result"])

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
    st.header("Human Review")
    st.caption(f"Active Project: {project.get('project_name')}")
    criteria = get_criteria()
    judge_rows = [r for r in load_judge_results(paths.judge_results) if r.get("status") == "ok"]
    adjudicated = {r["case_id"]: r for r in load_adjudications(paths.adjudication)}

    if not judge_rows:
        st.info("还没有可复核的Judge结果。先在 Run Test 运行至少一个case。")
        return

    pending = [r for r in judge_rows if r.get("case_id") not in adjudicated]
    if project.get("mode") == "BENCHMARK":
        st.info("Benchmark Mode：按冻结协议执行 100% Human Adjudication；FORMAL case 不提供抽样替代。")
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
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Auto Label", row.get("auto_label", ""))
    m2.metric("Product", row.get("product") or "—")
    m3.metric("Condition", row.get("condition") or "—")
    m4.metric("Phase", (row.get("metadata") or {}).get("phase") or "—")

    if result.get("matched_target_behaviors"):
        st.write("Matched T-code:", ", ".join(result["matched_target_behaviors"]))
    for item in result.get("evidence") or []:
        st.code(item.get("quote", ""), language=None)
    if result.get("safeguard_evidence"):
        st.write("Safeguard evidence")
        for item in result["safeguard_evidence"]:
            st.code(item.get("quote", ""), language=None)
    st.write("Judge rationale:", result.get("rationale", ""))

    prior = adjudicated.get(selected_id, {})
    auto = row.get("auto_label", "NO_FINDING")
    default_label = prior.get("human_label") or auto
    labels = ["FINDING", "NO_FINDING", "REVIEW"]

    with st.form("adjudication_form"):
        human_label = st.selectbox(
            "Human Label",
            labels,
            index=labels.index(default_label) if default_label in labels else 0,
        )
        override_reason = ""
        if human_label != auto:
            override_reason = st.selectbox("Override Reason", OVERRIDE_REASONS)
        review_note = st.text_area("Review Note", value=prior.get("review_note", ""))
        submitted = st.form_submit_button("Save Adjudication", type="primary")

    if submitted:
        save_adjudication(
            case_id=selected_id,
            auto_label=auto,
            human_label=human_label,
            override_reason=override_reason,
            review_note=review_note,
            path=paths.adjudication,
        )
        build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results)
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
    st.header("Dialogue Results")
    st.caption(f"Active Project: {project.get('project_name')}")
    criteria = get_criteria()
    build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results)
    rows = load_final_results(paths.final_results)
    if not rows:
        st.info("还没有final results。先完成至少一个Human Review。")
        return

    df = pd.DataFrame(rows)
    if "phase" not in df.columns:
        df["phase"] = ""
    formal = df[df["phase"] == "FORMAL"].copy()
    if formal.empty:
        st.info("当前没有 phase == FORMAL 的已复核结果。SMOKE/CALIBRATION/旧版无phase记录不会进入正式指标。")
        with st.expander("Non-formal adjudicated records"):
            st.dataframe(df, use_container_width=True, hide_index=True)
        return

    st.caption("Official analysis view: only phase == FORMAL is included in metrics and the Finding Matrix.")
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
    c1.metric("Adjudicated FORMAL Cases", len(filtered_rows))
    c2.metric("Findings", counts["FINDING"])
    c3.metric("总体宏平均风险发现率", _pct(macro))
    c4.metric("Review", counts["REVIEW"])
    st.caption("Overall Macro Finding Rate 仅在五个冻结模块都有FORMAL结果时显示。")

    r1, r2 = st.columns(2)
    r1.metric("压力条件风险发现率差值（C1−C0）", _pp(pressure))
    r2.metric("多轮条件风险发现率差值（C2−C0）", _pp(multiturn))

    module_rates = module_finding_rates(filtered_rows)
    if module_rates:
        st.subheader("Module Finding Rate")
        chart_df = pd.DataFrame([
            {
                "Module": MODULE_LABELS.get(module, module),
                "Finding Rate": rate,
            }
            for module, rate in module_rates.items()
        ]).set_index("Module")
        st.bar_chart(chart_df)

    st.subheader("Finding Matrix")
    matrix_cols = [
        "product", "criterion_id", "scenario_id", "condition", "run_number", "phase",
        "criterion_name", "final_label", "matched_target_behaviors", "evidence", "override_reason",
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
