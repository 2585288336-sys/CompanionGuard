from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from companionguard_judge.pipeline import dry_run

from .collector import (
    allowed_criteria_for_product,
    available_conditions,
    build_raw_case,
    create_collection_session,
    load_collector_config,
    make_case_id,
    mark_session_complete,
    previous_step,
    product_config,
    save_step_response,
    scenario_ids,
)
from .collector_storage import (
    append_raw_case,
    get_collection_session,
    in_progress_sessions,
    raw_case_ids,
    save_evidence_files,
    upsert_collection_session,
)
from .service import criteria_index


def _criterion_label(item: tuple[str, dict[str, Any]]) -> str:
    cid, obj = item
    return f"{cid} · {obj.get('criterion_name_zh', '')}"


def _copy_prompt_component(text: str, key: str) -> None:
    escaped = (
        text.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("${", "\\${")
        .replace("</", "<\\/")
    )
    html = f"""
    <div style="display:flex;gap:8px;align-items:center;font-family:Arial,sans-serif">
      <button id="copy-{key}" style="padding:0.45rem 0.8rem;border:1px solid #c7c7c7;border-radius:0.5rem;background:white;cursor:pointer;">Copy Prompt</button>
      <span id="status-{key}" style="font-size:0.85rem;color:#666"></span>
    </div>
    <script>
      const button = document.getElementById('copy-{key}');
      const status = document.getElementById('status-{key}');
      const text = `{escaped}`;
      button.addEventListener('click', async () => {{
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
          status.textContent = 'Copied';
        }} catch (err) {{
          status.textContent = 'Clipboard blocked — use the code box copy icon';
        }}
      }});
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


def _render_resume_panel() -> None:
    sessions = sorted(in_progress_sessions(), key=lambda x: x.get("updated_at", ""), reverse=True)
    if not sessions:
        return
    st.subheader("Resume In-Progress Session")
    options = [s["session_id"] for s in sessions]
    selected = st.selectbox("Saved session", options, key="collector_resume_session")
    row = next(s for s in sessions if s["session_id"] == selected)
    done = sum(bool((step.get("response") or "").strip()) for step in row.get("steps", []))
    st.caption(
        f"{row.get('product')} · {row.get('criterion_id')} · {row.get('scenario_id')} · "
        f"{row.get('condition') or 'N/A'} · {row.get('phase')} · {done}/{len(row.get('steps', []))} responses saved"
    )
    if st.button("Resume Selected", key="collector_resume_btn"):
        st.session_state["collector_active_session"] = selected
        st.rerun()
    st.divider()


def _render_setup(criteria: dict[str, dict[str, Any]], config: dict[str, Any]) -> None:
    st.subheader("Session Setup")
    products = config["products"]
    product_id = st.selectbox(
        "Product",
        [p["id"] for p in products],
        format_func=lambda pid: next(p["label"] for p in products if p["id"] == pid),
        key="collector_product_id",
    )
    pconfig = product_config(config, product_id)
    product_name = pconfig["label"]
    product_slug = pconfig["slug"]
    if product_id == "CUSTOM":
        product_name = st.text_input("Custom Product name", key="collector_custom_product_name").strip()
        product_slug = _custom_product_slug(product_name)
    if pconfig.get("role"):
        st.caption(pconfig["role"])

    available = allowed_criteria_for_product(criteria, config, product_id)
    if product_id == "Doubao":
        st.info(
            "豆包为 General-purpose Anthropomorphic Comparator，仅允许缩减对照集："
            "DS-01、DS-02、FD-01、FD-03、HR-02、MR。"
        )
    criterion_items = sorted(available.items())
    selected = st.selectbox("Criterion", criterion_items, format_func=_criterion_label, key="collector_criterion")
    criterion_id, criterion = selected

    scenarios = scenario_ids(criterion)
    scenario_id = st.selectbox(
        "Scenario",
        scenarios,
        format_func=lambda sid: _scenario_label(criterion, sid),
        key=f"collector_scenario::{criterion_id}",
    )

    conditions = available_conditions(criterion)
    if conditions == [None]:
        condition = None
        st.text_input("Condition", value="N/A (not applicable for this test structure)", disabled=True)
    else:
        condition = st.selectbox("Condition", conditions, key=f"collector_condition::{criterion_id}")
        if "C1" not in conditions:
            st.caption(
                "该 criterion 的当前冻结 criteria JSON 未配置 pressure_variant.L5；Collector 不会自行编造 C1 prompt。"
            )

    c1, c2, c3 = st.columns(3)
    with c1:
        phase = st.selectbox("Phase", config["phases"], index=config["phases"].index("SMOKE"))
    with c2:
        run_number = int(st.number_input("Run", min_value=1, max_value=99, value=1, step=1))
    with c3:
        collection_date = st.date_input("Collection date", value=date.today()).isoformat()
    notes = st.text_area("Optional notes", height=80)

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

    if st.button("Start / Resume Session", type="primary", disabled=not bool(product_name)):
        existing = get_collection_session(preview_case_id)
        if existing and existing.get("collection_status") == "IN_PROGRESS":
            st.session_state["collector_active_session"] = preview_case_id
            st.rerun()
        if preview_case_id in raw_case_ids():
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
        upsert_collection_session(session)
        st.session_state["collector_active_session"] = session["session_id"]
        st.rerun()


def _render_active_session(criteria: dict[str, dict[str, Any]], session_id: str) -> None:
    session = get_collection_session(session_id)
    if not session:
        st.error("Saved collection session was not found.")
        st.session_state.pop("collector_active_session", None)
        return
    if session.get("collection_status") == "COMPLETE":
        st.success(f"{session['case_id']} is complete and saved to data/raw_cases.jsonl.")
        if st.button("Start another case"):
            st.session_state.pop("collector_active_session", None)
            st.rerun()
        return

    criterion = criteria.get(session["criterion_id"])
    if not criterion:
        st.error(f"Criterion no longer exists: {session['criterion_id']}")
        return

    st.subheader("Collection Session")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Product", session["product"])
    h2.metric("Criterion", session["criterion_id"])
    h3.metric("Condition", session.get("condition") or "N/A")
    h4.metric("Phase", session["phase"])
    st.caption(f"Case ID: {session['case_id']} · Scenario: {session['scenario_id']} · Run {session['run_number']}")

    idx = min(int(session.get("current_step_index", 0)), len(session["steps"]) - 1)
    step = session["steps"][idx]
    total = len(session["steps"])
    st.progress((idx + 1) / total, text=f"Turn {idx + 1} of {total} · {step['prompt_turn']} → {step['response_turn']}")

    st.markdown("Prompt")
    st.code(step["prompt"], language=None)
    _copy_prompt_component(step["prompt"], key=f"{session['case_id']}-{idx}")
    st.caption("Prompt is loaded from the frozen criterion configuration. Do not edit it before sending to the product.")

    response_key = f"collector_response::{session['case_id']}::{idx}"
    if response_key not in st.session_state:
        st.session_state[response_key] = step.get("response") or ""
    response = st.text_area(
        "Paste model response exactly as shown",
        key=response_key,
        height=240,
        help="原样保存产品回复；不要润色、纠错、删减或改写。",
    )
    uploads = st.file_uploader(
        "Optional evidence screenshots",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"collector_evidence::{session['case_id']}::{idx}",
        help="截图是辅助证据，不替代文本采集。文件会按 case_id 关联保存。",
    )
    if step.get("evidence_files"):
        st.caption("Saved evidence: " + ", ".join(step["evidence_files"]))

    left, middle, right = st.columns([1, 2, 1])
    with left:
        if idx > 0 and st.button("← Previous", use_container_width=True):
            session = previous_step(session)
            upsert_collection_session(session)
            st.rerun()
    with middle:
        save_clicked = st.button("Save & Next", type="primary", use_container_width=True)
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
                append_raw_case(raw_case)
                updated = mark_session_complete(updated)
                upsert_collection_session(updated)
                st.session_state["collector_active_session"] = updated["session_id"]
                st.success("Case complete. Raw case saved and validated for the existing Judge pipeline.")
                st.rerun()
            else:
                upsert_collection_session(updated)
                st.rerun()
        except Exception as exc:
            st.error(str(exc))


def data_collection_page() -> None:
    st.header("Data Collection")
    st.caption(
        "Human-in-the-loop real-product collection: CompanionGuard controls fixed prompts and metadata; "
        "the researcher sends prompts in the external product and pastes verbatim responses here. No Judge API is required."
    )
    criteria = criteria_index()
    config = load_collector_config()

    active = st.session_state.get("collector_active_session")
    if active:
        _render_active_session(criteria, active)
        return

    _render_resume_panel()
    _render_setup(criteria, config)
