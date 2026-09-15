from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .audits import load_json, load_jsonl, make_audit_row, save_audit_evidence, upsert_jsonl
from .collector import load_collector_config
from .projects import create_project, get_project, list_projects, project_paths, safe_slug
from .reliability import LABELS, reliability_metrics
from .reporting import build_dialogue_report, build_dialogue_report_context, build_integrated_report, build_integrated_report_context
from .service import run_documentary_assist, run_report_writer
from .llm_ui import llm_session_id, render_llm_profile_selector
from .storage import build_final_results, load_final_results


def active_project_id() -> str | None:
    return st.session_state.get("active_project_id")


def active_project() -> dict[str, Any] | None:
    pid = active_project_id()
    return get_project(pid) if pid else None


def active_paths():
    pid = active_project_id()
    return project_paths(pid) if pid else None


def _configured_products() -> list[dict[str, Any]]:
    config = load_collector_config()
    return [p for p in config.get("products", []) if not p.get("custom_product")]


def sidebar_project_selector() -> dict[str, Any] | None:
    projects = list_projects()
    if not projects:
        st.sidebar.info("先创建一个 Test Project。")
        return None
    ids = [p["project_id"] for p in projects]
    current = st.session_state.get("active_project_id")
    index = ids.index(current) if current in ids else 0
    chosen = st.sidebar.selectbox(
        "Active Test Project",
        ids,
        index=index,
        format_func=lambda pid: next((p.get("project_name", pid) for p in projects if p["project_id"] == pid), pid),
    )
    st.session_state["active_project_id"] = chosen
    project = get_project(chosen)
    if project:
        st.sidebar.caption(f"{project.get('mode')} · {len(project.get('products', []))} products")
    return project


def projects_page() -> None:
    st.header("Test Projects")
    st.caption("一个 Test Project / 测试项目包含本次测试的产品、三层证据数据、Judge结果、人工复核和最终报告。")
    existing = list_projects()
    if existing:
        st.subheader("Existing Projects")
        st.dataframe(pd.DataFrame([
            {
                "project_id": p.get("project_id"),
                "name": p.get("project_name"),
                "mode": p.get("mode"),
                "products": ", ".join(x.get("label") or x.get("name") or x.get("id", "") for x in p.get("products", [])),
                "created_at": p.get("created_at"),
            }
            for p in existing
        ]), use_container_width=True, hide_index=True)

    st.subheader("Create Project")
    name = st.text_input("Project name", placeholder="例如：2026年9月拟人化AI产品正式评测")
    default_id = safe_slug(name) if name else ""
    pid = st.text_input("Project ID", value=default_id, help="人类可读、用于数据目录；创建后不建议修改。")
    mode = st.selectbox("Mode", ["BENCHMARK", "CUSTOM"], help="BENCHMARK使用CompanionGuard冻结规则；CUSTOM为未来扩展模式。")

    configured = _configured_products()
    selected_ids = st.multiselect(
        "Configured products",
        [p["id"] for p in configured],
        format_func=lambda x: next(p.get("label", x) for p in configured if p["id"] == x),
    )
    custom_text = st.text_area("Additional custom products (one per line)", placeholder="Character.AI\nNomi")
    notes = st.text_area("Project notes (optional)")
    if st.button("Create Test Project", type="primary"):
        products = [dict(p) for p in configured if p["id"] in selected_ids]
        for line in custom_text.splitlines():
            value = line.strip()
            if value:
                products.append({"id": safe_slug(value), "label": value, "slug": safe_slug(value), "role": "User-defined product"})
        try:
            project = create_project(name=name, project_id=pid or default_id, products=products, mode=mode, notes=notes)
            st.session_state["active_project_id"] = project["project_id"]
            st.success(f"Created: {project['project_name']}")
            st.rerun()
        except Exception as e:
            st.error(str(e))


def _project_product_names(project: dict[str, Any]) -> list[str]:
    return [p.get("label") or p.get("name") or p.get("id") for p in project.get("products", []) if (p.get("label") or p.get("name") or p.get("id"))]


def layer2_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    config = load_json(Path(__file__).resolve().parents[1] / "config" / "layer2_checks.json")
    st.header("Layer 2 · Product Safeguard Checks")
    st.caption("产品机制观察，不评价模型回复。四种观察状态与 Dialogue FINDING 标签完全分离。")
    products = _project_product_names(project)
    if not products:
        st.error("当前项目没有产品。")
        return
    product = st.selectbox("Product", products)
    with st.expander("Standardized 9-step inspection path"):
        for item in config.get("standard_path", []):
            st.markdown(f"**Step {item['step']} · {item['name_zh']}** — " + "；".join(item.get("items", [])))
    app_version = st.text_input("App/Web version (optional)")
    operating_system = st.text_input("Operating system / platform (optional)")
    checks = config["checks"]
    check = st.selectbox("Check", checks, format_func=lambda x: f"{x['code']} · {x['name_zh']} · {x['regulation']}")
    existing = {(r.get("product"), r.get("check_code")): r for r in load_jsonl(paths.layer2_records)}
    prior = existing.get((product, check["code"]), {})

    status = st.selectbox("Observation status", config["statuses"], index=config["statuses"].index(prior.get("status")) if prior.get("status") in config["statuses"] else 0)
    st.caption("NOT_OBSERVED = 按预注册路径检查后未观察到；NOT_TRIGGERED = 需要触发但本次未成功触发；NOT_VERIFIABLE = 当前伦理/权限下无法外部验证。")
    evidence_summary = st.text_area("Observation / evidence summary", value=prior.get("evidence_summary", ""))
    notes = st.text_area("Notes / limitation", value=prior.get("notes", ""))
    files = st.file_uploader("Screenshot / screen-record evidence", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"l2::{product}::{check['code']}")
    if st.button("Save Layer 2 Check", type="primary"):
        saved = prior.get("evidence_files", [])
        if files:
            saved_abs = save_audit_evidence(evidence_root=paths.layer2_evidence, product=product, check_code=check["code"], files=[(f.name, f.getvalue()) for f in files])
            saved = [str(Path(x).relative_to(paths.root)) for x in saved_abs]
        row = make_audit_row(project_id=project["project_id"], product=product, check_code=check["code"], status=status, evidence_summary=evidence_summary, notes=notes, evidence_files=saved, metadata={"regulation": check.get("regulation"), "check_name_zh": check.get("name_zh"), "test_date": date.today().isoformat(), "app_version": app_version, "operating_system": operating_system})
        upsert_jsonl(paths.layer2_records, row, key_fields=("product", "check_code"))
        st.success("Layer 2 record saved.")
        st.rerun()

    records = load_jsonl(paths.layer2_records)
    if records:
        st.subheader("Product Safeguard Matrix")
        st.dataframe(pd.DataFrame(records)[["product", "check_code", "status", "evidence_summary", "notes", "updated_at"]], use_container_width=True, hide_index=True)


def layer3_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先在 Test Projects 创建并选择项目。")
        return
    config = load_json(Path(__file__).resolve().parents[1] / "config" / "layer3_checks.json")
    st.header("Layer 3 Lite · Public Compliance Evidence Audit")
    st.caption("只核查公开正式材料能否为关键后台治理义务提供证据；不做Layer 3合规率。LLM仅辅助提取/初判，人工状态为最终记录。")
    if project.get("mode") == "BENCHMARK":
        products = [p.get("label") or p.get("name") or p.get("id") for p in project.get("products", []) if str(p.get("role", "")).startswith("Primary anthropomorphic AI product")]
        if not products:
            products = _project_product_names(project)
        st.caption("Benchmark Mode: Layer 3 Lite is intended for the three primary products; comparator/expanded products are excluded when primary profiles are present.")
    else:
        products = _project_product_names(project)
    product = st.selectbox("Product", products)
    check = st.selectbox("Check", config["checks"], format_func=lambda x: f"{x['code']} · {x['name_zh']} · {x['regulation']}")
    existing = {(r.get("product"), r.get("check_code")): r for r in load_jsonl(paths.layer3_records)}
    prior = existing.get((product, check["code"]), {})

    source = st.text_input("Source / URL / document name", value=prior.get("source", ""))
    source_date = st.text_input("Source version/date (optional)", value=prior.get("source_date", ""))
    source_text = st.text_area("Relevant source text / excerpt", height=220, help="可粘贴公开政策相关段落；AI assist只基于这里的文本，不自动浏览网页。")
    llm_profile = render_llm_profile_selector("evidence", key_prefix=f"layer3_evidence::{product}::{check['code']}")
    assist_key = f"layer3_assist::{product}::{check['code']}"
    if st.button("AI Evidence Assist", disabled=not bool(source_text.strip())):
        if not llm_profile:
            st.error("请配置 Layer 3 Evidence Assistant LLM。")
        else:
            try:
                with st.spinner("Extracting public evidence..."):
                    st.session_state[assist_key] = run_documentary_assist(check=check, source_text=source_text, llm_profile=llm_profile, session_id=llm_session_id(), project_id=project.get("project_id"))
            except Exception as e:
                st.error(str(e))
    assist = st.session_state.get(assist_key)
    if assist:
        st.info(f"AI suggestion: {assist.get('suggested_status')}")
        if assist.get("evidence_quote"):
            st.code(assist["evidence_quote"], language=None)
        st.caption(assist.get("rationale", ""))

    suggested_default = assist.get("suggested_status") if assist else prior.get("status")
    index = config["statuses"].index(suggested_default) if suggested_default in config["statuses"] else 0
    status = st.selectbox("Human final documentary status", config["statuses"], index=index)
    summary_default = assist.get("evidence_summary") if assist else prior.get("evidence_summary", "")
    evidence_summary = st.text_area("Evidence summary", value=summary_default or "")
    notes = st.text_area("Limitation / human review note", value=prior.get("notes", ""))
    files = st.file_uploader("Supporting public document / screenshot (optional)", type=["png", "jpg", "jpeg", "webp", "pdf", "txt", "md"], accept_multiple_files=True, key=f"l3::{product}::{check['code']}")
    if st.button("Save Layer 3 Audit", type="primary"):
        saved = prior.get("evidence_files", [])
        if files:
            saved_abs = save_audit_evidence(evidence_root=paths.layer3_evidence, product=product, check_code=check["code"], files=[(f.name, f.getvalue()) for f in files])
            saved = [str(Path(x).relative_to(paths.root)) for x in saved_abs]
        row = make_audit_row(project_id=project["project_id"], product=product, check_code=check["code"], status=status, evidence_summary=evidence_summary, notes=notes, source=source, source_date=source_date, evidence_files=saved, metadata={"regulation": check.get("regulation"), "check_name_zh": check.get("name_zh"), "ai_assist": assist or None})
        upsert_jsonl(paths.layer3_records, row, key_fields=("product", "check_code"))
        st.success("Layer 3 record saved; human status is authoritative.")
        st.rerun()

    records = load_jsonl(paths.layer3_records)
    if records:
        st.subheader("Compliance Evidence Matrix")
        st.dataframe(pd.DataFrame(records)[["product", "check_code", "status", "evidence_summary", "source", "updated_at"]], use_container_width=True, hide_index=True)


def reliability_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择项目。")
        return
    st.header("Judge–Human Reliability")
    build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results)
    rows = load_final_results(paths.final_results)
    if not rows:
        st.info("还没有同时完成 LLM Judge 与人工复核的结果。")
        return
    phases = sorted({r.get("phase", "") for r in rows if r.get("phase")})
    phase = st.multiselect("Phase", phases, default=phases)
    filtered = [r for r in rows if not phase or r.get("phase") in phase]
    result = reliability_metrics(filtered)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cases compared", result["n"])
    c2.metric("Exact Agreement", "—" if result["exact_agreement"] is None else f"{result['exact_agreement']*100:.1f}%")
    c3.metric("Cohen's κ", "—" if result["cohen_kappa"] is None else f"{result['cohen_kappa']:.3f}")
    c4.metric("Finding Recall", "—" if result["finding_recall"] is None else f"{result['finding_recall']*100:.1f}%")
    matrix = pd.DataFrame(result["matrix"]).T
    matrix.index.name = "LLM Judge"
    matrix.columns.name = "Human"
    st.subheader("Confusion Matrix")
    st.dataframe(matrix, use_container_width=True)
    st.caption("Benchmark FORMAL 模式按冻结协议采用100%人工复核。抽样复核仅作为Custom Eval未来能力，不改变Benchmark协议。")


def dialogue_report_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择项目。")
        return
    st.header("Layer 1 · Dialogue Report")
    build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results)
    rows = load_final_results(paths.final_results)
    deterministic = build_dialogue_report(project, rows)
    st.markdown(deterministic)
    paths.reports.mkdir(parents=True, exist_ok=True)
    deterministic_path = paths.reports / "dialogue_report_deterministic.md"
    deterministic_path.write_text(deterministic, encoding="utf-8")
    st.download_button("Download deterministic dialogue report", data=deterministic.encode("utf-8"), file_name=f"{project['project_id']}_dialogue_report.md", mime="text/markdown")
    with st.expander("Optional LLM-written dialogue report", expanded=False):
        st.caption("Python computes the metrics; the report model only writes from the frozen structured context. External writing skills/prompts are intentionally not bundled yet.")
        profile = render_llm_profile_selector("dialogue_report", key_prefix="dialogue_report_writer")
        if st.button("Generate LLM Dialogue Report", disabled=profile is None):
            try:
                context = build_dialogue_report_context(project=project, final_rows=rows)
                text = run_report_writer(role="dialogue_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"))
                (paths.reports / "dialogue_report_llm.md").write_text(text, encoding="utf-8")
                st.session_state["dialogue_report_llm_text"] = text
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("dialogue_report_llm_text"):
            st.markdown(st.session_state["dialogue_report_llm_text"])


def report_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择项目。")
        return
    st.header("Integrated Product Report")
    build_final_results(criteria, judge_path=paths.judge_results, adjudication_path=paths.adjudication, output_path=paths.final_results)
    rows = load_final_results(paths.final_results)
    report = build_integrated_report(project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records)
    st.markdown(report)
    paths.reports.mkdir(parents=True, exist_ok=True)
    output = paths.reports / "integrated_report.md"
    output.write_text(report, encoding="utf-8")
    st.download_button("Download integrated report (.md)", data=report.encode("utf-8"), file_name=f"{project['project_id']}_integrated_report.md", mime="text/markdown")
    with st.expander("Optional LLM-written integrated report", expanded=False):
        st.caption("The deterministic context is authoritative. This writer can later receive your separately researched report-writing prompt/skill without changing other LLM roles.")
        profile = render_llm_profile_selector("integrated_report", key_prefix="integrated_report_writer")
        if st.button("Generate LLM Integrated Report", disabled=profile is None):
            try:
                context = build_integrated_report_context(project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records)
                text = run_report_writer(role="integrated_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"))
                (paths.reports / "integrated_report_llm.md").write_text(text, encoding="utf-8")
                st.session_state["integrated_report_llm_text"] = text
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("integrated_report_llm_text"):
            st.markdown(st.session_state["integrated_report_llm_text"])
