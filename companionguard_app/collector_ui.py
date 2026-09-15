from __future__ import annotations

import json
import os
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
from .platform_ui import active_project, active_paths
from .storage import completed_case_ids


def _criterion_label(item: tuple[str, dict[str, Any]]) -> str:
    cid, obj = item
    return f"{cid} · {obj.get('criterion_name_zh', '')}"


def _dom_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value)


def _copy_prompt_component(text: str, key: str, *, auto_copy: bool = False) -> None:
    dom_key = _dom_key(key)
    text_js = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
    auto_js = "attemptCopy(true);" if auto_copy else ""
    html = f"""
    <div style="display:flex;gap:8px;align-items:center;font-family:Arial,sans-serif">
      <button id="copy-{dom_key}" style="padding:0.45rem 0.8rem;border:1px solid #c7c7c7;border-radius:0.5rem;background:white;cursor:pointer;">Copy Prompt</button>
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
          status.textContent = automatic ? 'Next prompt copied' : 'Copied';
        }} catch (err) {{
          status.textContent = automatic ? 'Auto-copy blocked — click Copy Prompt' : 'Clipboard blocked — use the code box copy icon';
        }}
      }}
      button.addEventListener('click', () => attemptCopy(false));
      {auto_js}
    </script>
    """
    components.html(html, height=48)


def _scenario_label(criterion: dict[str, Any], scenario_id: str) -> str:
    if criterion["judge_template"] == "mr_minor_relationship":
        item = (criterion.get("canonical_scenario") or {}).get(scenario_id, {})
        age = item.get("declared_age")
        return f"{scenario_id} · age {age}" if age is not None else scenario_id
    return scenario_id


def _custom_product_slug(name: str) -> str:
    return name.strip() or "Custom"


def _render_product_selector(config: dict[str, Any], *, prefix: str) -> tuple[str, str, str, dict[str, Any]]:
    products = config["products"]
    product_id = st.selectbox(
        "Product",
        [p["id"] for p in products],
        format_func=lambda pid: next(p["label"] for p in products if p["id"] == pid),
        key=f"{prefix}_product_id",
    )
    pconfig = product_config(config, product_id)
    product_name = pconfig["label"]
    product_slug = pconfig["slug"]
    if pconfig.get("custom_product"):
        product_name = st.text_input("Custom Product name", key=f"{prefix}_custom_product_name").strip()
        product_slug = _custom_product_slug(product_name)
    if pconfig.get("role"):
        st.caption(pconfig["role"])
    if pconfig.get("notice"):
        st.info(pconfig["notice"])
    if pconfig.get("criterion_allowlist"):
        st.caption(
            f"This product profile restricts collection to {len(pconfig['criterion_allowlist'])} configured criteria. "
            "The restriction comes from config/collector.json, not UI code."
        )
    return product_id, product_name, product_slug, pconfig


def _render_resume_panel() -> None:
    paths = active_paths()
    if not paths:
        return
    queues = sorted(in_progress_queues(paths.collection_queues), key=lambda x: x.get("updated_at", ""), reverse=True)
    sessions = sorted(in_progress_sessions(paths.collection_sessions), key=lambda x: x.get("updated_at", ""), reverse=True)
    if not queues and not sessions:
        return
    st.subheader("Resume Collection")
    if queues:
        qid = st.selectbox(
            "In-progress queue",
            [q["queue_id"] for q in queues],
            format_func=lambda q: next(
                f"{row.get('queue_name', q)} · {row.get('product')} · {row.get('phase')}"
                for row in queues if row["queue_id"] == q
            ),
            key="collector_resume_queue",
        )
        if st.button("Resume Queue", key="collector_resume_queue_btn"):
            st.session_state["collector_active_queue"] = qid
            st.session_state.pop("collector_active_session", None)
            st.rerun()
    if sessions:
        options = [s["session_id"] for s in sessions]
        selected = st.selectbox("In-progress case", options, key="collector_resume_session")
        row = next(s for s in sessions if s["session_id"] == selected)
        done = sum(bool((step.get("response") or "").strip()) for step in row.get("steps", []))
        st.caption(
            f"{row.get('product')} · {row.get('criterion_id')} · {row.get('scenario_id')} · "
            f"{row.get('condition') or 'N/A'} · {row.get('phase')} · {done}/{len(row.get('steps', []))} responses saved"
        )
        if st.button("Resume Case", key="collector_resume_case_btn"):
            st.session_state["collector_active_session"] = selected
            if row.get("queue_id"):
                st.session_state["collector_active_queue"] = row["queue_id"]
            st.rerun()
    st.divider()


def _render_single_setup(criteria: dict[str, dict[str, Any]], config: dict[str, Any]) -> None:
    paths = active_paths()
    if not paths:
        return
    st.subheader("Single Case")
    product_id, product_name, product_slug, pconfig = _render_product_selector(config, prefix="collector_single")
    available = allowed_criteria_for_product(criteria, config, product_id)
    criterion_items = sorted(available.items())
    selected = st.selectbox("Criterion", criterion_items, format_func=_criterion_label, key="collector_single_criterion")
    criterion_id, criterion = selected

    scenarios = scenario_ids(criterion)
    scenario_id = st.selectbox(
        "Scenario",
        scenarios,
        format_func=lambda sid: _scenario_label(criterion, sid),
        key=f"collector_single_scenario::{criterion_id}",
    )
    conditions = available_conditions(criterion)
    if conditions == [None]:
        condition = None
        st.text_input("Condition", value="N/A (not applicable for this test structure)", disabled=True, key="collector_single_na")
    else:
        condition = st.selectbox("Condition", conditions, key=f"collector_single_condition::{criterion_id}")
        if "C1" not in conditions:
            st.caption("当前 criterion JSON 未配置 pressure_variant.L5，因此不会暴露 C1；Collector 不自行编造 pressure prompt。")

    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.selectbox("Phase", config["phases"], index=config["phases"].index("SMOKE"), key="collector_single_phase")
    with c2:
        run_number = int(st.number_input("Run", min_value=1, max_value=99, value=1, step=1, key="collector_single_run"))
    with c3:
        collection_date = st.date_input("Collection date", value=date.today(), key="collector_single_date").isoformat()
    notes = st.text_area("Optional notes", height=80, key="collector_single_notes")

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
        st.code(preview_case_id, language=None)

    if st.button("Start / Resume Case", type="primary", disabled=not bool(product_name), key="collector_single_start"):
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
    st.subheader("Collection Queue")
    st.caption("Build a reusable queue from configured products/criteria. Queue logic does not hard-code model names or criterion IDs.")
    product_id, product_name, product_slug, pconfig = _render_product_selector(config, prefix="collector_queue")
    available = allowed_criteria_for_product(criteria, config, product_id)
    criterion_ids = sorted(available)
    selected_ids = st.multiselect(
        "Criteria to collect",
        criterion_ids,
        format_func=lambda cid: f"{cid} · {available[cid].get('criterion_name_zh', '')}",
        key="collector_queue_criteria",
    )
    condition_filter = st.multiselect(
        "Core conditions to include",
        ["C0", "C1", "C2"],
        default=["C0", "C1", "C2"],
        help="Only applies to Core/HR-02. MR/MC/PC keep their frozen structures. Missing C1 prompts are skipped rather than invented.",
        key="collector_queue_conditions",
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.selectbox("Phase", config["phases"], index=config["phases"].index("SMOKE"), key="collector_queue_phase")
    with c2:
        start_run = int(st.number_input("First run", min_value=1, max_value=99, value=1, step=1, key="collector_queue_start_run"))
    with c3:
        run_count = int(st.number_input("Number of runs", min_value=1, max_value=10, value=1, step=1, key="collector_queue_run_count"))
    collection_date = st.date_input("Collection date", value=date.today(), key="collector_queue_date").isoformat()
    queue_name = st.text_input("Queue name (optional)", key="collector_queue_name")
    notes = st.text_area("Queue notes (optional)", height=70, key="collector_queue_notes")

    run_numbers = list(range(start_run, start_run + run_count))
    preview_items: list[dict[str, Any]] = []
    if selected_ids and product_name:
        preview_items = build_queue_items(
            criteria=available,
            criterion_ids=selected_ids,
            product_slug=product_slug,
            phase=phase,
            run_numbers=run_numbers,
            condition_filter=condition_filter,
        )
        by_condition: dict[str, int] = {}
        for item in preview_items:
            key = item.get("condition") or "N/A"
            by_condition[key] = by_condition.get(key, 0) + 1
        st.caption(f"Queue preview: {len(preview_items)} cases · " + " · ".join(f"{k}: {v}" for k, v in sorted(by_condition.items())))
        with st.expander("Preview queue cases"):
            st.dataframe(preview_items, use_container_width=True, hide_index=True)

    if st.button("Create Queue", type="primary", disabled=not bool(preview_items), key="collector_queue_create"):
        queue_id = make_queue_id(product_slug=product_slug, phase=phase, collection_date=collection_date, path=paths.collection_queues)
        queue = create_collection_queue(
            queue_id=queue_id,
            queue_name=queue_name,
            product_id=product_id,
            product_name=product_name,
            product_slug=product_slug,
            product_role=pconfig.get("role", ""),
            phase=phase,
            collection_date=collection_date,
            items=preview_items,
            notes=notes,
        )
        queue["project_id"] = active_project().get("project_id") if active_project() else None
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
        st.error("Saved collection queue was not found.")
        st.session_state.pop("collector_active_queue", None)
        return
    queue = reconcile_collection_queue(queue, raw_path=paths.raw_cases, sessions_path=paths.collection_sessions)
    upsert_collection_queue(queue, paths.collection_queues)
    items = queue.get("items", [])
    complete = sum(i.get("status") == "COMPLETE" for i in items)
    st.markdown(f"## Queue · {queue.get('queue_name', queue_id)}")
    st.caption(f"{queue.get('product')} · {queue.get('phase')} · {queue.get('collection_date')} · {queue_id}")
    st.progress(complete / max(len(items), 1), text=f"{complete} / {len(items)} cases complete")

    current = next_queue_item(queue)
    if current:
        st.info(
            f"NEXT CASE  {current['position']}/{len(items)}  ·  {current['case_id']}  ·  "
            f"{current['criterion_id']} / {current['scenario_id']} / {current.get('condition') or 'N/A'} / Run {current['run_number']}"
        )
        c1, c2 = st.columns([3, 1])
        with c1:
            if st.button("Start / Resume Current Case", type="primary", use_container_width=True, key="queue_start_current"):
                _start_queue_case(queue, current, criteria)
                st.rerun()
        with c2:
            if st.button("Exit Queue", use_container_width=True, key="queue_exit"):
                st.session_state.pop("collector_active_queue", None)
                st.rerun()
    else:
        st.success("Queue complete. All cases are present in raw_cases.jsonl.")
        if st.button("Back to Collection Home", key="queue_done_back"):
            st.session_state.pop("collector_active_queue", None)
            st.rerun()

    with st.expander("Queue status", expanded=complete < len(items)):
        st.dataframe(
            [
                {
                    "#": i.get("position"),
                    "case_id": i.get("case_id"),
                    "criterion": i.get("criterion_id"),
                    "scenario": i.get("scenario_id"),
                    "condition": i.get("condition") or "N/A",
                    "run": i.get("run_number"),
                    "status": i.get("status"),
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


def _collector_api_key_input(case_id: str) -> str:
    server_key = os.environ.get("DEEPSEEK_API_KEY", "")
    try:
        secret_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        secret_key = ""
    server_key = server_key or secret_key
    options = ["Demo / server Judge", "BYOK"] if server_key else ["BYOK"]
    mode = st.radio("Judge access", options, horizontal=True, key=f"collector_judge_mode::{case_id}")
    if mode == "Demo / server Judge":
        return server_key
    return st.text_input(
        "DeepSeek API Key (session-only)",
        type="password",
        key=f"collector_judge_key::{case_id}",
        help="Only needed for Send This Case to Judge. The key is not written to JSONL/CSV/logs.",
    )


def _render_judge_result(row: dict[str, Any]) -> None:
    if row.get("status") != "ok":
        st.error(row.get("error") or "Judge failed")
        return
    result = row.get("result") or {}
    st.success(f"Judge complete · Auto label: {row.get('auto_label')}")
    if result.get("matched_target_behaviors"):
        st.write("Matched T-code:", ", ".join(result["matched_target_behaviors"]))
    if result.get("evidence"):
        for evidence in result["evidence"]:
            if isinstance(evidence, dict) and evidence.get("quote"):
                st.code(evidence["quote"], language=None)
    if result.get("rationale"):
        st.write(result["rationale"])


def _render_completed_session(criteria: dict[str, dict[str, Any]], session: dict[str, Any]) -> None:
    paths = active_paths()
    if not paths:
        return
    case_id = session["case_id"]
    st.success(f"Case complete · {case_id}")
    st.caption("Saved to data/raw_cases.jsonl and validated against the existing Judge input contract.")

    evidence_rows = []
    for step in session.get("steps", []):
        for path in step.get("evidence_files") or []:
            evidence_rows.append({"response_turn": step.get("response_turn"), "file": path})
    if evidence_rows:
        with st.expander(f"Screenshot evidence ({len(evidence_rows)})"):
            st.dataframe(evidence_rows, use_container_width=True, hide_index=True)

    with st.expander("Optional: Send This Case to Judge", expanded=False):
        if case_id in completed_case_ids(paths.judge_results):
            st.info("This case already has a successful Judge result in data/judge_results.jsonl.")
        else:
            api_key = _collector_api_key_input(case_id)
            if st.button("Send This Case to Judge", type="primary", key=f"collector_send_judge::{case_id}"):
                if not api_key:
                    st.error("Provide a DeepSeek API Key first, or judge later from Run Test.")
                else:
                    raw_case = get_raw_case(case_id, paths.raw_cases)
                    if raw_case is None:
                        st.error("Raw case not found.")
                    else:
                        try:
                            with st.spinner("Running criterion-bound Judge..."):
                                row = run_single_case(case=raw_case, criteria=criteria, api_key=api_key, persist=True, judge_path=paths.judge_results)
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
                if st.button("Next Case →", type="primary", use_container_width=True, key=f"collector_next_case::{case_id}"):
                    st.session_state.pop("collector_active_session", None)
                    _start_queue_case(queue, current, criteria)
                    st.rerun()
            else:
                st.success("Collection Queue complete.")
                if st.button("Return to Queue Summary", use_container_width=True, key=f"collector_queue_summary::{case_id}"):
                    st.session_state.pop("collector_active_session", None)
                    st.session_state["collector_active_queue"] = queue_id
                    st.rerun()
    else:
        if st.button("Start another case", use_container_width=True):
            st.session_state.pop("collector_active_session", None)
            st.rerun()


def _render_active_session(criteria: dict[str, dict[str, Any]], session_id: str) -> None:
    paths = active_paths()
    if not paths:
        return
    session = get_collection_session(session_id, paths.collection_sessions)
    if not session:
        st.error("Saved collection session was not found.")
        st.session_state.pop("collector_active_session", None)
        return
    if session.get("collection_status") == "COMPLETE":
        _render_completed_session(criteria, session)
        return

    criterion = criteria.get(session["criterion_id"])
    if not criterion:
        st.error(f"Criterion no longer exists: {session['criterion_id']}")
        return

    idx = min(int(session.get("current_step_index", 0)), len(session["steps"]) - 1)
    step = session["steps"][idx]
    total = len(session["steps"])

    st.markdown(
        f"## {session['product']} · {session['criterion_id']} · {session.get('condition') or 'N/A'} · Run {session['run_number']}"
    )
    st.info(
        f"CURRENT TURN  {idx + 1} / {total}   ·   {step['prompt_turn']} → {step['response_turn']}   ·   "
        f"Scenario {session['scenario_id']}   ·   {session['phase']}"
    )
    st.caption(f"Case ID: {session['case_id']}")
    st.progress((idx + 1) / total, text=f"Turn {idx + 1} of {total}")

    st.markdown("#### Fixed Prompt")
    st.code(step["prompt"], language=None)
    auto_target = st.session_state.get("collector_auto_copy_target")
    this_target = f"{session['case_id']}::{idx}"
    should_auto_copy = auto_target == this_target
    _copy_prompt_component(step["prompt"], key=f"{session['case_id']}-{idx}", auto_copy=should_auto_copy)
    if should_auto_copy:
        st.session_state.pop("collector_auto_copy_target", None)
        st.caption("Save & Copy Next attempted to place this prompt on the clipboard. If the browser blocked it, click Copy Prompt.")
    st.caption("Prompt is loaded from configuration. Do not edit it before sending to the external product.")

    response_key = f"collector_response::{session['case_id']}::{idx}"
    if response_key not in st.session_state:
        st.session_state[response_key] = step.get("response") or step.get("draft_response") or ""
    response = st.text_area(
        "Paste model response exactly as shown",
        key=response_key,
        height=240,
        help="Verbatim storage: do not polish, correct, shorten or rewrite the product response.",
        on_change=_persist_response_draft,
        args=(session["session_id"], idx, response_key),
    )
    if step.get("draft_response") and not step.get("response"):
        st.caption("Draft autosaved. It will be restored if you leave and resume this case.")

    uploads = st.file_uploader(
        "Optional screenshot evidence for this response turn",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"collector_evidence::{session['case_id']}::{idx}",
        help=(
            "Screenshots are supporting evidence, not OCR input. On save they are stored under "
            "data/evidence/<case_id>/ and linked to this response_turn in collection_trace.evidence_files."
        ),
    )
    if uploads:
        st.caption(f"{len(uploads)} screenshot(s) selected for {step['response_turn']}; they will be saved with this turn.")
    if step.get("evidence_files"):
        st.caption("Saved evidence: " + ", ".join(step["evidence_files"]))

    left, middle, right = st.columns([1, 2.4, 1])
    with left:
        if idx > 0 and st.button("← Previous", use_container_width=True):
            session = previous_step(session)
            upsert_collection_session(session, paths.collection_sessions)
            st.rerun()
    with middle:
        is_last = idx == total - 1
        label = "Save & Complete Case" if is_last else "Save & Copy Next"
        save_clicked = st.button(label, type="primary", use_container_width=True)
    with right:
        if st.button("Exit session", use_container_width=True):
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
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    st.header("Data Collection")
    st.caption(f"Active Project: {project.get('project_name')}")
    st.caption(
        "Human-in-the-loop real-product collection. CompanionGuard controls prompts, case/turn alignment, queue state, "
        "evidence linkage and raw JSONL; the researcher only sends prompts in the external product and pastes verbatim replies."
    )
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
    queue_tab, single_tab = st.tabs(["Collection Queue", "Single Case"])
    with queue_tab:
        _render_queue_builder(criteria, config)
    with single_tab:
        _render_single_setup(criteria, config)
