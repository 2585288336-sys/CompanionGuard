from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from companionguard_judge.pipeline import dry_run

from .collector import (
    allowed_criteria_for_product,
    available_conditions,
    build_queue_items,
    build_queue_items_from_selections,
    build_raw_case,
    create_collection_queue,
    create_collection_session,
    load_collector_config,
    make_case_id,
    mark_session_complete,
    next_queue_item,
    previous_step,
    product_config,
    save_step_draft,
    save_step_response,
    scenario_ids,
)
from .collector_storage import (
    append_raw_case,
    get_collection_queue,
    get_collection_session,
    get_raw_case,
    in_progress_queues,
    in_progress_sessions,
    make_queue_id,
    raw_case_ids,
    reconcile_collection_queue,
    save_evidence_files,
    update_queue_item_status,
    upsert_collection_queue,
    upsert_collection_session,
)
from .service import criteria_index, run_single_case
from .llm_ui import llm_session_id, render_llm_profile_selector
from .testplans import upsert_test_plan
from .platform_ui import active_project, active_paths
from .storage import completed_case_ids
from .config import OFFICIAL_MODULE_ORDER
from .display_labels import criterion_label, module_label, scenario_label, structure_label, turn_label
from .ui_helpers import condition_label, phase_label, render_condition_banner, render_judge_result, render_case_conversation
from .ui_theme import golden_card_head, golden_page_head


def _criterion_label(item: tuple[str, dict[str, Any]]) -> str:
    cid, obj = item
    return criterion_label(cid, obj)


def _dom_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value)


def _copy_prompt_component(text: str, key: str, *, auto_copy: bool = False) -> None:
    dom_key = _dom_key(key)
    text_js = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
    auto_js = "attemptCopy(true);" if auto_copy else ""
    html = f"""
    <div style="display:flex;gap:8px;align-items:center;font-family:Arial,sans-serif">
      <button id="copy-{dom_key}" style="padding:0.45rem 0.8rem;border:1px solid #c7c7c7;border-radius:0.5rem;background:white;cursor:pointer;">复制 Prompt</button>
      <span id="status-{dom_key}" style="font-size:0.85rem;color:#666"></span>
    </div>
    <script>
      const button = document.getElementById('copy-{dom_key}');
      const status = document.getElementById('status-{dom_key}');
      const text = {text_js};
      async function attemptCopy(automatic=false) {{
        try {{
          if (navigator.clipboard && window.isSecureContext) {{
            await navigator.clipboard.writeText(text);
          }} else {{
            const area = document.createElement('textarea');
            area.value = text;
            area.style.position = 'fixed';
            area.style.opacity = '0';
            document.body.appendChild(area);
            area.focus();
            area.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(area);
            if (!ok) throw new Error('copy command failed');
          }}
          status.textContent = automatic ? '下一轮 Prompt 已复制' : '已复制';
        }} catch (err) {{
          status.textContent = automatic ? '自动复制被阻止，请点击“复制 Prompt”' : '复制被阻止，请使用代码框的复制按钮';
        }}
      }}
      button.addEventListener('click', () => attemptCopy(false));
      {auto_js}
    </script>
    """
    components.html(html, height=48)


def _scenario_label(criterion: dict[str, Any], scenario_id: str) -> str:
    return scenario_label(criterion, scenario_id)


def _custom_product_slug(name: str) -> str:
    return name.strip() or "Custom"


def _render_product_selector(config: dict[str, Any], *, prefix: str) -> tuple[str, str, str, dict[str, Any]]:
    products = config["products"]
    product_id = st.selectbox(
        "产品 / Product",
        [p["id"] for p in products],
        format_func=lambda pid: next(p["label"] for p in products if p["id"] == pid),
        key=f"{prefix}_product_id",
    )
    pconfig = product_config(config, product_id)
    product_name = pconfig["label"]
    product_slug = pconfig["slug"]
    if pconfig.get("custom_product"):
        product_name = st.text_input("自定义产品名称 / Custom Product Name", key=f"{prefix}_custom_product_name").strip()
        product_slug = _custom_product_slug(product_name)
    if pconfig.get("role"):
        st.caption(pconfig["role"])
    if pconfig.get("notice"):
        st.info(pconfig["notice"])
    return product_id, product_name, product_slug, pconfig


def _render_resume_panel() -> None:
    paths = active_paths()
    if not paths:
        return
    queues = sorted(in_progress_queues(paths.collection_queues), key=lambda x: x.get("updated_at", ""), reverse=True)
    sessions = sorted(in_progress_sessions(paths.collection_sessions), key=lambda x: x.get("updated_at", ""), reverse=True)
    if not queues and not sessions:
        return
    st.subheader("继续对话采集 / Resume Collection")
    if queues:
        qid = st.selectbox(
            "未完成队列 / In-progress Queue",
            [q["queue_id"] for q in queues],
            format_func=lambda q: next(
                f"{row.get('queue_name', q)} · {row.get('product')} · {phase_label(row.get('phase'))}"
                for row in queues if row["queue_id"] == q
            ),
            key="collector_resume_queue",
        )
        if st.button("继续队列 / Resume Queue", key="collector_resume_queue_btn"):
            st.session_state["collector_active_queue"] = qid
            st.session_state.pop("collector_active_session", None)
            st.rerun()
    if sessions:
        options = [s["session_id"] for s in sessions]
        selected = st.selectbox("未完成案例 / In-progress Case", options, key="collector_resume_session")
        row = next(s for s in sessions if s["session_id"] == selected)
        done = sum(bool((step.get("response") or "").strip()) for step in row.get("steps", []))
        st.caption(
            f"{row.get('product')} · {criterion_label(row.get('criterion_id'))} · {scenario_label(row, row.get('scenario_id'))} · "
            f"{condition_label(row.get('condition'), template=row.get('judge_template'))} · {phase_label(row.get('phase'))} · "
            f"{done}/{len(row.get('steps', []))} 轮已保存"
        )
        if st.button("继续案例 / Resume Case", key="collector_resume_case_btn"):
            st.session_state["collector_active_session"] = selected
            if row.get("queue_id"):
                st.session_state["collector_active_queue"] = row["queue_id"]
            st.rerun()
    st.divider()


def _render_single_setup(criteria: dict[str, dict[str, Any]], config: dict[str, Any]) -> None:
    paths = active_paths()
    if not paths:
        return
    st.subheader("独立测试案例 / Single Test Case")
    product_id, product_name, product_slug, pconfig = _render_product_selector(config, prefix="collector_single")
    available = allowed_criteria_for_product(criteria, config, product_id)
    criterion_items = sorted(available.items())
    selected = st.selectbox("测试项目 / Criterion", criterion_items, format_func=_criterion_label, key="collector_single_criterion")
    criterion_id, criterion = selected

    scenarios = scenario_ids(criterion)
    scenario_id = st.selectbox(
        "具体场景 / Scenario",
        scenarios,
        format_func=lambda sid: _scenario_label(criterion, sid),
        key=f"collector_single_scenario::{criterion_id}",
    )
    conditions = available_conditions(criterion)
    if conditions == [None]:
        condition = None
        st.caption(f"测试结构：{structure_label(criterion)}")
    else:
        condition = st.selectbox("实验条件 / Condition", conditions, format_func=condition_label, key=f"collector_single_condition::{criterion_id}")
        if "C1" not in conditions:
            st.caption("当前测试项目未配置冻结的 Pressure L5，因此不会显示 C1；系统不会自行编造压力 Prompt。")

    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.selectbox("阶段 / Phase", config["phases"], index=config["phases"].index("SMOKE"), format_func=phase_label, key="collector_single_phase")
    with c2:
        run_number = int(st.number_input("重复测试次数 / Run", min_value=1, max_value=99, value=1, step=1, key="collector_single_run"))
    with c3:
        collection_date = st.date_input("采集日期 / Collection Date", value=date.today(), key="collector_single_date").isoformat()
    notes = st.text_area("备注（可选） / Notes", height=80, key="collector_single_notes")

    preview_case_id = ""
    if product_name:
        preview_case_id = make_case_id(
            product_slug=product_slug,
            criterion_id=criterion_id,
            scenario_id=scenario_id,
            condition=condition,
            phase=phase,
            run_number=run_number,
        )
        st.caption("案例编号 / Case ID")
        st.code(preview_case_id, language=None)

    if st.button("开始 / 继续案例", type="primary", disabled=not bool(product_name), key="collector_single_start"):
        existing = get_collection_session(preview_case_id, paths.collection_sessions)
        if existing and existing.get("collection_status") == "IN_PROGRESS":
            st.session_state["collector_active_session"] = preview_case_id
            st.rerun()
        if preview_case_id in raw_case_ids(paths.raw_cases):
            st.error("该 case_id 已存在于 data/raw_cases.jsonl。请更改 run、phase 或测试选择，避免覆盖实验记录。")
            return
        session = create_collection_session(
            criterion=criterion,
            product_id=product_id,
            product_name=product_name,
            product_slug=product_slug,
            product_role=pconfig.get("role", ""),
            scenario_id=scenario_id,
            condition=condition,
            run_number=run_number,
            phase=phase,
            collection_date=collection_date,
            notes=notes,
        )
        session["project_id"] = active_project().get("project_id") if active_project() else None
        upsert_collection_session(session, paths.collection_sessions)
        st.session_state["collector_active_session"] = session["session_id"]
        st.rerun()


def _render_queue_builder(criteria: dict[str, dict[str, Any]], config: dict[str, Any]) -> None:
    paths = active_paths()
    if not paths:
        return
    st.subheader("测试方案与采集队列 / Test Plan & Collection Queue")
    st.caption("产品与测试覆盖彼此独立。先选择被测产品，再按模块组合具体测试项目、场景和实验条件。")
    product_id, product_name, product_slug, pconfig = _render_product_selector(config, prefix="collector_queue")

    preset_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "test_plan_presets.json"
    presets = json.loads(preset_path.read_text(encoding="utf-8"))["presets"]
    preset = st.selectbox("测试方案预设 / Test Plan preset", presets, format_func=lambda x: x["label"], key="collector_queue_preset")
    available = dict(criteria)
    criterion_ids = sorted(available)
    preset_ids = set(criterion_ids if preset.get("criterion_ids") == "*" else [cid for cid in preset.get("criterion_ids", []) if cid in available])
    preset_conditions = preset.get("conditions", ["C0", "C1", "C2"])

    st.markdown("### 选择测试项目 / Select Test Items")
    st.caption("Core/HR-02 可逐测试项目选择 C0/C1/C2；MR、MC、PC 等可逐场景选择。未选择的内容不会进入队列。")
    selections: dict[str, dict[str, Any]] = {}

    for module in OFFICIAL_MODULE_ORDER:
        module_criteria = [(cid, available[cid]) for cid in criterion_ids if available[cid].get("module") == module]
        if not module_criteria:
            continue
        with st.expander(module_label(module), expanded=module in {"relationship_safety", "minor_protection"}):
            for cid, criterion in module_criteria:
                default_enabled = cid in preset_ids
                enabled = st.checkbox(
                    criterion_label(cid, criterion),
                    value=default_enabled,
                    key=f"plan_enable::{preset['id']}::{cid}",
                )
                if not enabled:
                    continue
                template = criterion.get("judge_template")
                if template in ("core_l1_l5", "hr02_crisis"):
                    available_cond = [c for c in available_conditions(criterion) if c]
                    default_cond = [c for c in preset_conditions if c in available_cond]
                    chosen_cond = st.multiselect(
                        f"{cid} 实验条件 / Conditions",
                        available_cond,
                        default=default_cond or available_cond,
                        format_func=condition_label,
                        key=f"plan_conditions::{preset['id']}::{cid}",
                    )
                    if chosen_cond:
                        selections[cid] = {"scenarios": scenario_ids(criterion), "conditions": chosen_cond}
                else:
                    scenarios = scenario_ids(criterion)
                    chosen_scenarios = st.multiselect(
                        f"{cid} 具体场景 / Scenarios",
                        scenarios,
                        default=scenarios,
                        format_func=lambda sid, c=criterion: _scenario_label(c, sid),
                        key=f"plan_scenarios::{preset['id']}::{cid}",
                    )
                    if chosen_scenarios:
                        selections[cid] = {"scenarios": chosen_scenarios, "conditions": []}

    coverage_type = st.selectbox(
        "覆盖类型 / Coverage Type",
        ["FULL_BENCHMARK", "BENCHMARK_SUBSET", "CUSTOM"],
        index=["FULL_BENCHMARK", "BENCHMARK_SUBSET", "CUSTOM"].index(preset.get("coverage_type", "CUSTOM")),
        help="子集/自定义评测是有效的定向评测，但不能把聚合结果表述为与完整 benchmark 直接等价。",
        key=f"collector_queue_coverage::{preset['id']}",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.selectbox("阶段 / Phase", config["phases"], index=config["phases"].index("SMOKE"), format_func=phase_label, key="collector_queue_phase")
    with c2:
        start_run = int(st.number_input("起始重复次数 / First Run", min_value=1, max_value=99, value=1, step=1, key="collector_queue_start_run"))
    with c3:
        run_count = int(st.number_input("重复次数 / Number of Runs", min_value=1, max_value=10, value=1, step=1, key="collector_queue_run_count"))
    collection_date = st.date_input("采集日期 / Collection Date", value=date.today(), key="collector_queue_date").isoformat()
    queue_name = st.text_input("测试方案 / Queue 名称（可选）", key="collector_queue_name")
    notes = st.text_area("方案备注（可选） / Plan Notes", height=70, key="collector_queue_notes")

    run_numbers = list(range(start_run, start_run + run_count))
    preview_items: list[dict[str, Any]] = []
    if selections and product_name:
        preview_items = build_queue_items_from_selections(
            criteria=available, selections=selections, product_slug=product_slug, phase=phase, run_numbers=run_numbers
        )
        by_condition: dict[str, int] = {}
        for item in preview_items:
            item_criterion = available.get(item.get("criterion_id"), {})
            key = condition_label(item.get("condition"), template=item_criterion.get("judge_template"))
            by_condition[key] = by_condition.get(key, 0) + 1
        st.caption(f"方案预览 / Plan preview：{len(preview_items)} cases · " + " · ".join(f"{k}: {v}" for k, v in sorted(by_condition.items())))
        if coverage_type != "FULL_BENCHMARK":
            st.info("这是基准测试子集/自定义评测。其聚合结果不得表述为与完整 CompanionGuard Benchmark 直接等价。")
        with st.expander("查看全部 case / Preview plan cases"):
            st.dataframe(preview_items, use_container_width=True, hide_index=True)

    if st.button("保存测试方案并创建队列 / Save Test Plan & Create Queue", type="primary", disabled=not bool(preview_items), key="collector_queue_create"):
        queue_id = make_queue_id(product_slug=product_slug, phase=phase, collection_date=collection_date, path=paths.collection_queues)
        plan = {
            "plan_id": queue_id,
            "plan_name": queue_name or queue_id,
            "product_id": product_id,
            "product": product_name,
            "product_slug": product_slug,
            "preset_id": preset["id"],
            "coverage_type": coverage_type,
            "selections": selections,
            "criterion_ids": list(selections),
            "run_numbers": run_numbers,
            "phase": phase,
            "collection_date": collection_date,
            "notes": notes,
        }
        upsert_test_plan(paths.test_plans, plan)
        queue = create_collection_queue(
            queue_id=queue_id, queue_name=queue_name, product_id=product_id, product_name=product_name,
            product_slug=product_slug, product_role=pconfig.get("role", ""), phase=phase,
            collection_date=collection_date, items=preview_items, notes=notes,
        )
        queue["project_id"] = active_project().get("project_id") if active_project() else None
        queue["test_plan_id"] = queue_id
        queue["coverage_type"] = coverage_type
        queue["selections"] = selections
        upsert_collection_queue(queue, paths.collection_queues)
        queue = reconcile_collection_queue(queue, raw_path=paths.raw_cases, sessions_path=paths.collection_sessions)
        upsert_collection_queue(queue, paths.collection_queues)
        st.session_state["collector_active_queue"] = queue_id
        st.rerun()

def _start_queue_case(queue: dict[str, Any], item: dict[str, Any], criteria: dict[str, dict[str, Any]]) -> None:
    paths = active_paths()
    if not paths:
        return
    case_id = item["case_id"]
    if case_id in raw_case_ids(paths.raw_cases):
        update_queue_item_status(queue_id=queue["queue_id"], case_id=case_id, status="COMPLETE", session_id=case_id, path=paths.collection_queues)
        return
    existing = get_collection_session(case_id, paths.collection_sessions)
    if existing and existing.get("collection_status") == "IN_PROGRESS":
        if not existing.get("queue_id"):
            existing["queue_id"] = queue["queue_id"]
            upsert_collection_session(existing, paths.collection_sessions)
        update_queue_item_status(queue_id=queue["queue_id"], case_id=case_id, status="IN_PROGRESS", session_id=case_id, path=paths.collection_queues)
        st.session_state["collector_active_session"] = case_id
        st.session_state["collector_active_queue"] = queue["queue_id"]
        return
    criterion = criteria[item["criterion_id"]]
    session = create_collection_session(
        criterion=criterion,
        product_id=queue["product_id"],
        product_name=queue["product"],
        product_slug=queue["product_slug"],
        product_role=queue.get("product_role", ""),
        scenario_id=item["scenario_id"],
        condition=item.get("condition"),
        run_number=int(item["run_number"]),
        phase=queue["phase"],
        collection_date=queue["collection_date"],
        notes=queue.get("notes", ""),
        queue_id=queue["queue_id"],
    )
    session["project_id"] = queue.get("project_id")
    session["test_plan_id"] = queue.get("test_plan_id")
    session["coverage_type"] = queue.get("coverage_type", "CUSTOM")
    upsert_collection_session(session, paths.collection_sessions)
    update_queue_item_status(queue_id=queue["queue_id"], case_id=case_id, status="IN_PROGRESS", session_id=session["session_id"], path=paths.collection_queues)
    st.session_state["collector_active_session"] = session["session_id"]
    st.session_state["collector_active_queue"] = queue["queue_id"]


def _render_queue(criteria: dict[str, dict[str, Any]], queue_id: str) -> None:
    paths = active_paths()
    if not paths:
        return
    queue = get_collection_queue(queue_id, paths.collection_queues)
    if not queue:
        st.error("未找到已保存的采集队列。")
        st.session_state.pop("collector_active_queue", None)
        return
    queue = reconcile_collection_queue(queue, raw_path=paths.raw_cases, sessions_path=paths.collection_sessions)
    upsert_collection_queue(queue, paths.collection_queues)
    items = queue.get("items", [])
    complete = sum(i.get("status") == "COMPLETE" for i in items)
    st.markdown(f"## 对话采集队列 / Collection Queue · {queue.get('queue_name', queue_id)}")
    st.caption(f"产品：{queue.get('product')} · 阶段：{phase_label(queue.get('phase'))} · 日期：{queue.get('collection_date')} · 队列编号：{queue_id}")
    st.progress(complete / max(len(items), 1), text=f"已完成 {complete} / {len(items)} 个独立测试案例")

    current = next_queue_item(queue)
    if current:
        current_criterion = criteria.get(current["criterion_id"], {})
        st.info(
            f"下一独立测试案例：{current['position']} / {len(items)} · "
            f"{module_label(current_criterion.get('module'))} · {criterion_label(current['criterion_id'], current_criterion)} · "
            f"{scenario_label(current_criterion, current.get('scenario_id'))} · "
            f"{condition_label(current.get('condition'), template=current_criterion.get('judge_template'))} · "
            f"第 {current['run_number']} 次"
        )
        c1, c2 = st.columns([3, 1])
        with c1:
            st.warning("操作提示：请先在被测产品中新建对话或清空当前上下文，再开始这个独立测试案例。")
            if st.button("开始 / 继续当前案例", type="primary", use_container_width=True, key="queue_start_current"):
                _start_queue_case(queue, current, criteria)
                st.rerun()
        with c2:
            if st.button("退出队列 / Exit Queue", use_container_width=True, key="queue_exit"):
                st.session_state.pop("collector_active_queue", None)
                st.rerun()
    else:
        st.success("队列已完成。所有独立测试案例均已写入 raw_cases.jsonl。")
        if st.button("返回对话采集首页", key="queue_done_back"):
            st.session_state.pop("collector_active_queue", None)
            st.rerun()

    with st.expander("队列状态 / Queue Status", expanded=complete < len(items)):
        st.dataframe(
            [
                {
                    "序号": i.get("position"),
                    "案例编号": i.get("case_id"),
                    "测试项目": criterion_label(i.get("criterion_id"), criteria.get(i.get("criterion_id"), {})),
                    "场景": scenario_label(criteria.get(i.get("criterion_id"), {}), i.get("scenario_id")),
                    "条件": condition_label(i.get("condition"), template=criteria.get(i.get("criterion_id"), {}).get("judge_template")),
                    "重复次数": i.get("run_number"),
                    "状态": i.get("status"),
                }
                for i in items
            ],
            use_container_width=True,
            hide_index=True,
        )


def _persist_response_draft(session_id: str, step_index: int, response_key: str) -> None:
    paths = active_paths()
    if not paths:
        return
    try:
        session = get_collection_session(session_id, paths.collection_sessions)
        if not session or session.get("collection_status") != "IN_PROGRESS":
            return
        draft = st.session_state.get(response_key, "")
        updated = save_step_draft(session, step_index=step_index, draft_response=draft)
        upsert_collection_session(updated, paths.collection_sessions)
    except Exception:
        # Draft autosave must never block the primary Save & Next path.
        return


def _collector_judge_profile(case_id: str):
    return render_llm_profile_selector(
        "judge", key_prefix=f"collector_judge::{case_id}"
    )


def _render_judge_result(row: dict[str, Any]) -> None:
    render_judge_result(row, compact=True)


def _render_completed_session(criteria: dict[str, dict[str, Any]], session: dict[str, Any]) -> None:
    paths = active_paths()
    if not paths:
        return
    case_id = session["case_id"]
    criterion = criteria.get(session.get("criterion_id"), {})
    st.success(f"独立测试案例已完成 · {case_id}")
    st.caption(
        f"{module_label(criterion.get('module'))} · {criterion_label(session.get('criterion_id'), criterion)} · "
        f"{scenario_label(criterion, session.get('scenario_id'))} · {condition_label(session.get('condition'), template=criterion.get('judge_template'))}"
    )
    st.caption("已保存到项目 raw_cases.jsonl，并通过现有 Judge 输入契约校验。")

    evidence_rows = []
    for step in session.get("steps", []):
        for path in step.get("evidence_files") or []:
            evidence_rows.append({"response_turn": step.get("response_turn"), "file": path})
    if evidence_rows:
        with st.expander(f"截图证据 / Screenshot Evidence（{len(evidence_rows)}）"):
            st.dataframe(evidence_rows, use_container_width=True, hide_index=True)

    with st.expander("可选：直接运行 Judge", expanded=False):
        if case_id in completed_case_ids(paths.judge_results):
            st.info("该案例已经存在成功的 Judge 结果。")
        else:
            llm_profile = _collector_judge_profile(case_id)
            if st.button("将此案例送入 Judge", type="primary", key=f"collector_send_judge::{case_id}"):
                if not llm_profile:
                    st.error("请先配置 Judge 模型，也可以稍后从“LLM 判定”页面运行。")
                else:
                    raw_case = get_raw_case(case_id, paths.raw_cases)
                    if raw_case is None:
                        st.error("未找到原始案例记录。")
                    else:
                        try:
                            with st.spinner("正在运行冻结测试项目对应的 Judge..."):
                                row = run_single_case(case=raw_case, criteria=criteria, llm_profile=llm_profile, persist=True, judge_path=paths.judge_results, session_id=llm_session_id(), project_id=(active_project() or {}).get("project_id"))
                            _render_judge_result(row)
                        except Exception as exc:
                            st.error(str(exc))

    queue_id = session.get("queue_id") or st.session_state.get("collector_active_queue")
    if queue_id:
        queue = get_collection_queue(queue_id, paths.collection_queues)
        if queue:
            queue = reconcile_collection_queue(queue, raw_path=paths.raw_cases, sessions_path=paths.collection_sessions)
            upsert_collection_queue(queue, paths.collection_queues)
            current = next_queue_item(queue)
            if current:
                if st.button("下一个独立测试案例 →", type="primary", use_container_width=True, key=f"collector_next_case::{case_id}"):
                    st.session_state.pop("collector_active_session", None)
                    _start_queue_case(queue, current, criteria)
                    st.rerun()
            else:
                st.success("对话采集队列已完成。")
                if st.button("返回队列摘要", use_container_width=True, key=f"collector_queue_summary::{case_id}"):
                    st.session_state.pop("collector_active_session", None)
                    st.session_state["collector_active_queue"] = queue_id
                    st.rerun()
    else:
        if st.button("开始另一个独立测试案例", use_container_width=True):
            st.session_state.pop("collector_active_session", None)
            st.rerun()


def _render_active_session(criteria: dict[str, dict[str, Any]], session_id: str) -> None:
    paths = active_paths()
    if not paths:
        return
    session = get_collection_session(session_id, paths.collection_sessions)
    if not session:
        st.error("未找到已保存的采集案例。")
        st.session_state.pop("collector_active_session", None)
        return
    if session.get("collection_status") == "COMPLETE":
        _render_completed_session(criteria, session)
        return

    criterion = criteria.get(session["criterion_id"])
    if not criterion:
        st.error(f"测试项目已不存在：{session['criterion_id']}")
        return

    idx = min(int(session.get("current_step_index", 0)), len(session["steps"]) - 1)
    step = session["steps"][idx]
    total = len(session["steps"])

    st.markdown("### 当前测试 / Current Test")
    st.markdown(f"#### {module_label(criterion.get('module'))}")
    st.markdown(f"#### {criterion_label(session.get('criterion_id'), criterion)}")
    summary_cols = st.columns(4)
    summary_cols[0].metric("产品", session.get("product") or "—")
    summary_cols[1].metric("条件", condition_label(session.get("condition"), template=criterion.get("judge_template")))
    summary_cols[2].metric("阶段", phase_label(session.get("phase")))
    summary_cols[3].metric("重复测试", f"第 {session.get('run_number')} 次")
    st.progress((idx + 1) / total, text=f"进度：第 {idx + 1} / {total} 轮")
    with st.expander("技术信息 / Technical Information", expanded=False):
        st.caption(f"案例编号 / Case ID：{session['case_id']}")
        st.caption(f"场景 / Scenario：{scenario_label(criterion, session.get('scenario_id'))}")

    st.markdown("#### 当前发送内容 / Current Prompt")
    st.markdown(f"**{turn_label(step.get('prompt_turn'), condition=session.get('condition'), template=criterion.get('judge_template'))}** · 第 {idx + 1} / {total} 轮")
    render_condition_banner(
        session.get("condition"),
        template=criterion.get("judge_template"),
        first_turn=idx == 0,
    )
    st.code(step["prompt"], language=None)
    auto_target = st.session_state.get("collector_auto_copy_target")
    this_target = f"{session['case_id']}::{idx}"
    should_auto_copy = auto_target == this_target
    _copy_prompt_component(step["prompt"], key=f"{session['case_id']}-{idx}", auto_copy=should_auto_copy)
    if should_auto_copy:
        st.session_state.pop("collector_auto_copy_target", None)
        st.caption("浏览器可能阻止自动复制（Safari 尤其常见）。请以显式“复制 Prompt”按钮为准；这不影响保存与进入下一轮。")
    st.caption("Prompt 来自冻结配置。发送给真实产品前请勿修改。")

    response_key = f"collector_response::{session['case_id']}::{idx}"
    if response_key not in st.session_state:
        st.session_state[response_key] = step.get("response") or step.get("draft_response") or ""
    response = st.text_area(
        "粘贴模型原始回复 / Paste model response exactly as shown",
        key=response_key,
        height=240,
        help="逐字保存：不要润色、纠错、缩写或改写产品回复。",
    )
    # Persist the current widget value on every rerun. Avoiding an on_change callback
    # prevents the first click on Save from being consumed by a textarea blur rerun.
    if response != (step.get("draft_response") or step.get("response") or ""):
        try:
            draft_session = save_step_draft(session, step_index=idx, draft_response=response)
            upsert_collection_session(draft_session, paths.collection_sessions)
        except Exception:
            pass
    if step.get("draft_response") and not step.get("response"):
        st.caption("Draft autosaved. It will be restored if you leave and resume this case.")

    uploads = st.file_uploader(
        "本轮截图证据（可选） / Optional Screenshot Evidence",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"collector_evidence::{session['case_id']}::{idx}",
        help=(
            "截图仅作为辅助证据，不作为 OCR 输入；保存后会按案例编号归档，并关联到本轮产品回复。"
        ),
    )
    if uploads:
        st.caption(f"已选择 {len(uploads)} 张截图，将随 {step['response_turn']} 本轮回复保存。")
    if step.get("evidence_files"):
        with st.expander("已保存截图路径 / Saved Evidence Paths", expanded=False):
            st.code("\n".join(step["evidence_files"]), language=None)

    left, middle, right = st.columns([1, 2.4, 1])
    with left:
        if idx > 0 and st.button("← 上一轮 / Previous Turn", use_container_width=True, key=f"collector_previous_turn::{session['case_id']}::{idx}"):
            session = previous_step(session)
            upsert_collection_session(session, paths.collection_sessions)
            st.rerun()
    with middle:
        is_last = idx == total - 1
        label = "保存并完成案例" if is_last else "保存并进入下一轮"
        save_clicked = st.button(label, type="primary", use_container_width=True, key=f"collector_save_turn::{session['case_id']}::{idx}")
    with right:
        if st.button("退出本次案例", use_container_width=True, key=f"collector_exit_case::{session['case_id']}::{idx}"):
            st.session_state.pop("collector_active_session", None)
            st.rerun()

    if save_clicked:
        try:
            evidence_paths = step.get("evidence_files") or []
            if uploads:
                evidence_paths = save_evidence_files(
                    case_id=session["case_id"],
                    response_turn=step["response_turn"],
                    files=[(item.name, item.getvalue()) for item in uploads],
                    evidence_dir=paths.dialogue_evidence,
                )
            updated = save_step_response(
                session,
                step_index=idx,
                response=response,
                evidence_files=evidence_paths,
            )
            if updated["current_step_index"] >= len(updated["steps"]):
                raw_case = build_raw_case(updated, criterion)
                errors = dry_run([raw_case], criteria)
                if errors:
                    raise ValueError("Judge compatibility validation failed: " + "; ".join(errors))
                raw_case["project_id"] = session.get("project_id")
                raw_case.setdefault("metadata", {})["project_id"] = session.get("project_id")
                append_raw_case(raw_case, paths.raw_cases)
                updated = mark_session_complete(updated)
                upsert_collection_session(updated, paths.collection_sessions)
                if updated.get("queue_id"):
                    update_queue_item_status(
                        queue_id=updated["queue_id"],
                        case_id=updated["case_id"],
                        status="COMPLETE",
                        session_id=updated["session_id"],
                        path=paths.collection_queues,
                    )
                st.session_state["collector_active_session"] = updated["session_id"]
                st.rerun()
            else:
                upsert_collection_session(updated, paths.collection_sessions)
                st.session_state["collector_auto_copy_target"] = f"{updated['case_id']}::{updated['current_step_index']}"
                st.rerun()
        except Exception as exc:
            st.error(str(exc))


def data_collection_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    golden_page_head("对话数据采集 / Dialogue Data Collection", "显示信息可以更友好；复制和记录的 payload 始终指向冻结配置中的原始 Prompt。")
    with st.container(border=True):
        golden_card_head("Collection Workspace · 采集工作台", "当前 Project 的冻结 Prompt、Case Queue 与原始证据")
        st.info("在真实产品中执行固定 Prompt，并保存原始对话证据。")
        st.markdown(f"<div class='cg-golden-card-copy'><strong>Project：</strong>{project.get('project_name')}（{project.get('project_id')}）<br>系统自动管理固定 Prompt、案例编号、轮次对应、截图证据和原始数据；测试人员只需在真实产品中发送 Prompt，并原样粘贴模型回复。</div>", unsafe_allow_html=True)
    criteria = criteria_index()
    config = load_collector_config()
    config = dict(config)
    config["products"] = project.get("products", config.get("products", []))

    active_session = st.session_state.get("collector_active_session")
    if active_session:
        _render_active_session(criteria, active_session)
        return

    active_queue = st.session_state.get("collector_active_queue")
    if active_queue:
        _render_queue(criteria, active_queue)
        return

    _render_resume_panel()
    queue_tab, single_tab = st.tabs(["测试方案与队列", "独立测试案例"])
    with queue_tab:
        _render_queue_builder(criteria, config)
    with single_tab:
        _render_single_setup(criteria, config)
