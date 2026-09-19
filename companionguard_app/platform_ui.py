from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .adjudication import FULL_ADJUDICATION, RANDOM_SAMPLE, SAMPLED_ADJUDICATION, STRATIFIED_SAMPLE, adjudication_policy
from .audits import load_json, load_jsonl, make_audit_row, save_audit_evidence, upsert_jsonl
from .collector import load_collector_config
from .projects import create_project, delete_project, get_project, list_projects, safe_slug
from .reliability import LABELS, reliability_metrics
from .reporting import build_dialogue_report, build_dialogue_report_context, build_integrated_report, build_integrated_report_context
from .report_pipeline import write_report_artifacts
from .service import criteria_index, run_documentary_assist, run_grounding_validator, run_report_writer
from .llm_ui import llm_session_id, render_llm_profile_selector
from .storage import build_final_results, load_adjudications, load_final_results, load_judge_results
from .runtime_scope import RuntimeScope
from .runtime_workspace import RuntimeContext, ensure_active_workspace, get_runtime_context
from .collector_storage import load_raw_cases
from .metrics import case_validity_counts, valid_case_rows
from .display_labels import criterion_label, module_label, scenario_label
from .ui_helpers import condition_label, phase_label, render_case_conversation, render_case_validity, render_judge_result


def active_project_id() -> str | None:
    value = st.session_state.get("active_project_id")
    return None if value in {None, "__NONE__"} else value


def active_project() -> dict[str, Any] | None:
    context = active_runtime_context()
    if context is None:
        return None
    try:
        value = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return get_project(context.published_project_id) if context.scope is RuntimeScope.PUBLISHED else None
    return value if isinstance(value, dict) else None


def active_paths():
    context = active_runtime_context()
    return context.paths if context else None


def active_runtime_context() -> RuntimeContext | None:
    pid = active_project_id()
    return get_runtime_context(pid) if pid else None


def active_scope() -> RuntimeScope | None:
    context = active_runtime_context()
    return context.scope if context else None


def ensure_active_workspace_for_write() -> RuntimeContext:
    context = active_runtime_context()
    if context is None:
        raise ValueError("请先选择测试项目，再开始评测操作。")
    return ensure_active_workspace(context.published_project_id)


def _configured_products() -> list[dict[str, Any]]:
    config = load_collector_config()
    return [
        p for p in config.get("products", [])
        if not p.get("custom_product") and not p.get("legacy_only")
    ]


def _default_benchmark_product_ids(products: list[dict[str, Any]]) -> list[str]:
    config = load_collector_config()
    configured_ids = {p.get("id") for p in products}
    return [
        product_id
        for product_id in config.get("formal_primary_product_ids", [])
        if product_id in configured_ids
    ]


def sidebar_project_selector() -> dict[str, Any] | None:
    projects = list_projects()
    if not projects:
        st.sidebar.info("先创建一个测试项目 / Create a Test Project first.")
        st.session_state["active_project_id"] = "__NONE__"
        return None
    ids = [p["project_id"] for p in projects]
    current = st.session_state.get("active_project_id")
    options = ["__NONE__"] + ids
    index = options.index(current) if current in options else (1 if ids else 0)
    chosen = st.sidebar.selectbox(
        "当前测试项目 / Active Test Project",
        options,
        index=index,
        format_func=lambda pid: "— 退出当前项目 / No active project —" if pid == "__NONE__" else next((p.get("project_name", pid) for p in projects if p["project_id"] == pid), pid),
    )
    if chosen == "__NONE__":
        st.session_state["active_project_id"] = "__NONE__"
        return None
    st.session_state["active_project_id"] = chosen
    project = get_project(chosen)
    if project:
        st.sidebar.caption(f"{project.get('mode')} · {len(project.get('products', []))} products")
    return project

def projects_page() -> None:
    st.caption("一个 Test Project / 测试项目包含本次测试的产品、三层证据数据、Judge结果、人工复核和最终报告。")
    if st.session_state.pop("project_just_created", False):
        st.success("项目创建完成。下一阶段建议进入『Layer 1 · 对话采集』，为每个产品建立测试方案；也可以先从 Layer 2/3 开始。")
        if st.button("下一阶段：进入对话采集 / Go to Data Collection", type="primary", key="project_next_collection"):
            st.session_state["requested_nav"] = "data_collection"
            st.rerun()
    existing = list_projects()
    if existing:
        st.subheader("已有项目 / Existing Projects")
        st.dataframe(pd.DataFrame([
            {
                "project_id": p.get("project_id"),
                "name": p.get("project_name"),
                "mode": p.get("mode"),
                "human_adjudication_policy": p.get("human_adjudication_policy", FULL_ADJUDICATION),
                "products": ", ".join(x.get("label") or x.get("name") or x.get("id", "") for x in p.get("products", [])),
                "created_at": p.get("created_at"),
            }
            for p in existing
        ]), use_container_width=True, hide_index=True)

    if existing:
        with st.expander("删除测试项目 / Delete Project", expanded=False):
            st.warning("删除会永久移除该项目目录下的 raw cases、截图、Judge结果、人工复核、Layer 2/3 与报告；不会修改源码或 criteria。建议只用于删除 smoke test。")
            delete_id = st.selectbox("选择项目 / Project", [p["project_id"] for p in existing], key="delete_project_select")
            confirm = st.text_input("输入 Project ID 以确认 / Type Project ID to confirm", key="delete_project_confirm")
            if st.button("永久删除项目 / Permanently delete", disabled=confirm != delete_id, key="delete_project_btn"):
                try:
                    delete_project(delete_id, scope=RuntimeScope.PUBLISHED)
                    if st.session_state.get("active_project_id") == delete_id:
                        st.session_state.pop("active_project_id", None)
                    st.success(f"已删除 / Deleted: {delete_id}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.subheader("创建项目 / Create Project")
    name = st.text_input("项目名称 / Project name", placeholder="例如：2026年9月拟人化AI产品正式评测")
    default_id = safe_slug(name) if name else ""
    pid = st.text_input("项目 ID / Project ID", value=default_id, help="人类可读、用于数据目录；创建后不建议修改。")
    mode = st.selectbox("模式 / Mode", ["BENCHMARK", "CUSTOM"], help="BENCHMARK使用CompanionGuard冻结规则；CUSTOM为未来扩展模式。")

    adjudication_policy = FULL_ADJUDICATION
    sampling_method = STRATIFIED_SAMPLE
    sample_rate = 0.25
    random_seed = 20260915
    strata = ["product", "criterion_id", "condition"]
    if mode == "BENCHMARK":
        adjudication_policy = st.radio(
            "FORMAL 人工复核策略 / FORMAL Human Adjudication Policy",
            [FULL_ADJUDICATION, SAMPLED_ADJUDICATION],
            format_func=lambda value: {
                FULL_ADJUDICATION: "全量人工复核 / Full adjudication",
                SAMPLED_ADJUDICATION: "预注册抽样人工复核 / Pre-registered sampled adjudication",
            }[value],
            help="项目创建后策略写入 manifest；正式评测开始后不应临时改变。",
        )
        if adjudication_policy == SAMPLED_ADJUDICATION:
            sampling_method = st.selectbox(
                "抽样方法 / Sampling method",
                [STRATIFIED_SAMPLE, RANDOM_SAMPLE],
                format_func=lambda value: {
                    STRATIFIED_SAMPLE: "分层抽样 / Stratified sample",
                    RANDOM_SAMPLE: "随机抽样 / Random sample",
                }[value],
            )
            sample_rate = float(st.number_input("最低抽样比例 / Minimum sampling rate", min_value=0.01, max_value=1.0, value=0.25, step=0.05))
            random_seed = int(st.number_input("随机种子 / Random seed", min_value=0, max_value=2147483647, value=20260915, step=1))
            strata = st.multiselect(
                "分层维度 / Stratification fields",
                ["product", "module", "criterion_id", "condition"],
                default=["product", "criterion_id", "condition"],
                help="分层抽样至少建议保留 Product、Criterion、Condition；配置写入项目 manifest。",
            ) or ["product", "criterion_id", "condition"]

    configured = _configured_products()
    default_product_ids = _default_benchmark_product_ids(configured) if mode == "BENCHMARK" else []
    selected_ids = st.multiselect(
        "预配置产品 / Configured products",
        [p["id"] for p in configured],
        default=default_product_ids,
        format_func=lambda x: next(p.get("label", x) for p in configured if p["id"] == x),
    )
    if mode == "BENCHMARK":
        default_labels = [
            p.get("label") or p.get("id", "")
            for p in configured
            if p.get("id") in default_product_ids
        ]
        st.caption(
            "FORMAL Full Benchmark 默认主产品："
            + "、".join(default_labels)
            + "。产品身份与 Test Plan 覆盖范围保持解耦。"
        )
    custom_text = st.text_area("自定义产品（每行一个） / Additional custom products", placeholder="Character.AI\nNomi")
    notes = st.text_area("项目备注（可选） / Project notes")
    if st.button("创建测试项目 / Create Test Project", type="primary"):
        products = [dict(p) for p in configured if p["id"] in selected_ids]
        for line in custom_text.splitlines():
            value = line.strip()
            if value:
                products.append({"id": safe_slug(value), "label": value, "slug": safe_slug(value), "role": "User-defined product"})
        try:
            project = create_project(
                name=name, project_id=pid or default_id, products=products, mode=mode, notes=notes,
                human_adjudication_policy=adjudication_policy,
                human_adjudication_sampling_method=sampling_method,
                human_adjudication_sample_rate=sample_rate,
                human_adjudication_random_seed=random_seed,
                human_adjudication_strata=strata,
                scope=RuntimeScope.PUBLISHED,
            )
            st.session_state["active_project_id"] = project["project_id"]
            st.session_state["project_just_created"] = True
            st.success(f"已创建 / Created: {project['project_name']}")
            st.rerun()
        except Exception as e:
            st.error(str(e))


def _project_product_names(project: dict[str, Any]) -> list[str]:
    return [p.get("label") or p.get("name") or p.get("id") for p in project.get("products", []) if (p.get("label") or p.get("name") or p.get("id"))]


def layer3_product_names(project: dict[str, Any]) -> list[str]:
    """Return the product scope shown by the current Layer 3 policy."""
    products = _project_product_names(project)
    if project.get("mode") != "BENCHMARK":
        return products
    primary = [
        p.get("label") or p.get("name") or p.get("id")
        for p in project.get("products", [])
        if str(p.get("role", "")).startswith("Primary anthropomorphic AI product")
        and (p.get("label") or p.get("name") or p.get("id"))
    ]
    return primary or products


def data_explorer_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    st.caption("查看已生成的标准案例、逐轮原始回复、截图预览，以及对应的 Judge / 人工复核结果。这里用于检查与导出，不建议手工编辑 JSON。")
    criteria = criteria_index()
    cases = load_raw_cases(paths.raw_cases)
    if not cases:
        st.info("当前项目还没有 COMPLETE raw case。")
        return

    adjudications = {r.get("case_id"): r for r in load_adjudications(paths.adjudication)}
    judge_results = load_judge_results(paths.judge_results)
    latest_judges = {}
    for result in judge_results:
        if result.get("status") == "ok" and result.get("case_id"):
            latest_judges[result["case_id"]] = result
    table = []
    for case in cases:
        case_id = case.get("case_id")
        criterion = criteria.get(case.get("criterion_id"), {})
        evidence_count = sum(len(step.get("evidence_files") or []) for step in (case.get("collection_trace") or []))
        judge_status = "完成" if case_id in latest_judges else "未完成"
        table.append({
            "案例编号": case_id,
            "产品": case.get("product"),
            "模块": module_label(criterion.get("module")),
            "测试项目": criterion_label(case.get("criterion_id"), criterion),
            "场景": scenario_label(criterion, (case.get("metadata") or {}).get("scenario_id") or case.get("scenario_id")),
            "条件": condition_label(case.get("condition"), template=criterion.get("judge_template")),
            "阶段": phase_label(case.get("phase") or (case.get("metadata") or {}).get("phase")),
            "重复次数": (case.get("metadata") or {}).get("run_number") or case.get("run_number"),
            "截图数量": evidence_count,
            "Judge": judge_status,
            "自动有效性": latest_judges.get(case_id, {}).get("auto_case_validity", "—"),
            "最终有效性": adjudications.get(case_id, {}).get("final_case_validity") or adjudications.get(case_id, {}).get("case_validity", "—"),
        })
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    case_id = st.selectbox("选择案例 / Select case", [c.get("case_id") for c in cases], key="data_explorer_case_selector")
    case = next(c for c in cases if c.get("case_id") == case_id)
    criterion = criteria.get(case.get("criterion_id"), {})

    transcript_tab, json_tab, judge_tab = st.tabs(["完整对话与截图", "标准 JSON / Raw Case", "Judge 与人工复核"])
    with transcript_tab:
        st.subheader(f"{module_label(criterion.get('module'))} · {criterion_label(case.get('criterion_id'), criterion)}")
        st.caption(
            f"场景：{scenario_label(criterion, (case.get('metadata') or {}).get('scenario_id') or case.get('scenario_id'))} · "
            f"条件：{condition_label(case.get('condition'), template=criterion.get('judge_template'))} · "
            f"阶段：{phase_label(case.get('phase') or (case.get('metadata') or {}).get('phase'))}"
        )
        render_case_conversation(
            {**case, "judge_template": case.get("judge_template") or criterion.get("judge_template")},
            project_root=paths.root,
            key_prefix=f"data-explorer::{case_id}",
            expanded=True,
        )
    with json_tab:
        st.json(case)
        st.download_button("下载当前案例 JSON", data=json.dumps(case, ensure_ascii=False, indent=2).encode("utf-8"), file_name=f"{case_id}.json", mime="application/json")
        if paths.raw_cases.exists():
            st.download_button("下载全部原始案例 JSONL", data=paths.raw_cases.read_bytes(), file_name=f"{project['project_id']}_raw_cases.jsonl", mime="application/json")
    with judge_tab:
        judge_rows = [r for r in load_judge_results(paths.judge_results) if r.get("case_id") == case_id and r.get("status") == "ok"]
        if judge_rows:
            render_judge_result(judge_rows[-1], compact=True)
            render_case_validity(judge_rows[-1].get("auto_case_validity"), title="自动有效性筛查 / Auto Validity Screening")
        else:
            st.info("该 case 尚未完成 LLM Judge。")
        if case_id in adjudications:
            st.markdown("#### 人工复核 / Human Adjudication")
            render_case_validity(adjudications[case_id].get("final_case_validity") or adjudications[case_id].get("case_validity"), title="最终案例有效性 / Final Case Validity")
            st.json(adjudications[case_id])


def layer2_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    config = load_json(Path(__file__).resolve().parents[1] / "config" / "layer2_checks.json")
    st.caption("产品机制观察，不评价模型回复。四种观察状态与 Dialogue FINDING 标签完全分离。")
    products = _project_product_names(project)
    if not products:
        st.error("当前项目没有产品。")
        return
    product = st.selectbox("产品 / Product", products)
    with st.expander("标准化九步检查路径 / Standardized 9-step inspection path"):
        for item in config.get("standard_path", []):
            st.markdown(f"**Step {item['step']} · {item['name_zh']}** — " + "；".join(item.get("items", [])))
    app_version = st.text_input("App/Web 版本（可选） / Version")
    operating_system = st.text_input("操作系统/平台（可选） / OS or platform")
    checks = config["checks"]
    check = st.selectbox("检查项 / Check", checks, format_func=lambda x: f"{x['code']} · {x['name_zh']} · {x['regulation']}")
    existing = {(r.get("product"), r.get("check_code")): r for r in load_jsonl(paths.layer2_records)}
    prior = existing.get((product, check["code"]), {})

    status = st.selectbox("观察状态 / Observation status", config["statuses"], index=config["statuses"].index(prior.get("status")) if prior.get("status") in config["statuses"] else 0)
    st.caption("NOT_OBSERVED = 按预注册路径检查后未观察到；NOT_TRIGGERED = 需要触发但本次未成功触发；NOT_VERIFIABLE = 当前伦理/权限下无法外部验证。")
    evidence_summary = st.text_area("观察/证据摘要 / Evidence summary", value=prior.get("evidence_summary", ""))
    notes = st.text_area("备注/局限 / Notes or limitation", value=prior.get("notes", ""))
    files = st.file_uploader("截图/录屏证据 / Screenshot or screen-record evidence", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key=f"l2::{product}::{check['code']}")
    if st.button("保存 Layer 2 检查 / Save Layer 2 Check", type="primary"):
        try:
            context = ensure_active_workspace_for_write()
            project = active_project()
            paths = context.paths
            if not project:
                raise ValueError("Workspace project manifest is unavailable.")
            saved = prior.get("evidence_files", [])
            if files:
                saved_abs = save_audit_evidence(evidence_root=paths.layer2_evidence, product=product, check_code=check["code"], files=[(f.name, f.getvalue()) for f in files], scope=context.scope, workspace_root=paths.root)
                saved = [str(Path(x).relative_to(paths.root)) for x in saved_abs]
            row = make_audit_row(project_id=project["project_id"], product=product, check_code=check["code"], status=status, evidence_summary=evidence_summary, notes=notes, evidence_files=saved, metadata={"regulation": check.get("regulation"), "check_name_zh": check.get("name_zh"), "test_date": date.today().isoformat(), "app_version": app_version, "operating_system": operating_system})
            upsert_jsonl(paths.layer2_records, row, key_fields=("product", "check_code"), scope=context.scope, workspace_root=paths.root)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Layer 2 检查已保存。")
            st.rerun()

    records = load_jsonl(paths.layer2_records)
    if records:
        st.subheader("产品安全机制检查矩阵 / Product Safeguard Matrix")
        st.dataframe(
            pd.DataFrame(records)[["product", "check_code", "status", "evidence_summary", "notes", "updated_at"]].rename(columns={
                "product": "产品", "check_code": "检查项", "status": "观察状态", "evidence_summary": "证据摘要", "notes": "备注", "updated_at": "更新时间",
            }),
            use_container_width=True,
            hide_index=True,
        )


def layer3_page() -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先创建并选择测试项目。")
        return
    config = load_json(Path(__file__).resolve().parents[1] / "config" / "layer3_checks.json")
    st.caption("只核查公开正式材料能否为关键后台治理义务提供证据；不做Layer 3合规率。LLM仅辅助提取/初判，人工状态为最终记录。")
    products = layer3_product_names(project)
    if project.get("mode") == "BENCHMARK":
        st.caption("BENCHMARK 模式：Layer 3 Lite 默认显示项目中标记为正式主产品的产品；比较产品和扩展产品不自动纳入。")
    product = st.selectbox("产品 / Product", products)
    check = st.selectbox("核查项 / Check", config["checks"], format_func=lambda x: f"{x['code']} · {x['name_zh']} · {x['regulation']}")
    existing = {(r.get("product"), r.get("check_code")): r for r in load_jsonl(paths.layer3_records)}
    prior = existing.get((product, check["code"]), {})

    source = st.text_input("来源/URL/文档名 / Source", value=prior.get("source", ""))
    source_date = st.text_input("来源版本/日期（可选） / Source version/date", value=prior.get("source_date", ""))
    source_text = st.text_area("相关来源文本/摘录 / Relevant source text", height=220, help="可粘贴公开政策相关段落；AI assist只基于这里的文本，不自动浏览网页。")
    llm_profile = render_llm_profile_selector("evidence", key_prefix=f"layer3_evidence::{product}::{check['code']}")
    assist_key = f"layer3_assist::{product}::{check['code']}"
    if st.button("AI 证据辅助 / AI Evidence Assist", disabled=not bool(source_text.strip())):
        if not llm_profile:
            st.error("请配置 Layer 3 Evidence Assistant LLM。")
        else:
            try:
                context = ensure_active_workspace_for_write()
                with st.spinner("Extracting public evidence..."):
                    st.session_state[assist_key] = run_documentary_assist(check=check, source_text=source_text, llm_profile=llm_profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=context.scope)
            except Exception as e:
                st.error(str(e))
    assist = st.session_state.get(assist_key)
    if assist:
        st.info(f"AI 初步建议 / AI suggestion：{assist.get('suggested_status')}")
        if assist.get("evidence_quote"):
            st.code(assist["evidence_quote"], language=None)
        st.caption(assist.get("rationale", ""))

    suggested_default = assist.get("suggested_status") if assist else prior.get("status")
    index = config["statuses"].index(suggested_default) if suggested_default in config["statuses"] else 0
    status = st.selectbox("人工最终证据状态 / Human final status", config["statuses"], index=index)
    summary_default = assist.get("evidence_summary") if assist else prior.get("evidence_summary", "")
    evidence_summary = st.text_area("证据摘要 / Evidence summary", value=summary_default or "")
    notes = st.text_area("局限/人工复核备注 / Limitation or review note", value=prior.get("notes", ""))
    files = st.file_uploader("公开材料/截图（可选） / Supporting document", type=["png", "jpg", "jpeg", "webp", "pdf", "txt", "md"], accept_multiple_files=True, key=f"l3::{product}::{check['code']}")
    if st.button("保存 Layer 3 核查 / Save Layer 3 Audit", type="primary"):
        try:
            context = ensure_active_workspace_for_write()
            project = active_project()
            paths = context.paths
            if not project:
                raise ValueError("Workspace project manifest is unavailable.")
            saved = prior.get("evidence_files", [])
            if files:
                saved_abs = save_audit_evidence(evidence_root=paths.layer3_evidence, product=product, check_code=check["code"], files=[(f.name, f.getvalue()) for f in files], scope=context.scope, workspace_root=paths.root)
                saved = [str(Path(x).relative_to(paths.root)) for x in saved_abs]
            row = make_audit_row(project_id=project["project_id"], product=product, check_code=check["code"], status=status, evidence_summary=evidence_summary, notes=notes, source=source, source_date=source_date, evidence_files=saved, metadata={"regulation": check.get("regulation"), "check_name_zh": check.get("name_zh"), "ai_assist": assist or None})
            upsert_jsonl(paths.layer3_records, row, key_fields=("product", "check_code"), scope=context.scope, workspace_root=paths.root)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Layer 3 核查已保存；人工最终状态为权威记录。")
            st.rerun()

    records = load_jsonl(paths.layer3_records)
    if records:
        st.subheader("公开合规证据矩阵 / Compliance Evidence Matrix")
        st.dataframe(
            pd.DataFrame(records)[["product", "check_code", "status", "evidence_summary", "source", "updated_at"]].rename(columns={
                "product": "产品", "check_code": "核查项", "status": "证据状态", "evidence_summary": "证据摘要", "source": "来源", "updated_at": "更新时间",
            }),
            use_container_width=True,
            hide_index=True,
        )


def reliability_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择测试项目。")
        return
    rows = load_final_results(paths.final_results)
    if not rows:
        st.info("还没有同时完成 LLM Judge 与人工复核的结果。")
        return
    if project.get("mode") == "BENCHMARK":
        filtered_all = [r for r in rows if r.get("phase") == "FORMAL"]
        st.caption("Benchmark Reliability 仅统计 phase == FORMAL；SMOKE/CALIBRATION 结果保留在项目数据中，但不进入正式一致性指标。")
    else:
        phases = sorted({r.get("phase", "") for r in rows if r.get("phase")})
        phase = st.multiselect("阶段 / Phase", phases, default=phases, format_func=phase_label)
        filtered_all = [r for r in rows if not phase or r.get("phase") in phase]
    filtered = valid_case_rows(filtered_all)
    validity = case_validity_counts(filtered_all)
    if validity["INVALID"] or validity["REVIEW"]:
        st.info(f"案例有效性筛选：VALID {validity['VALID']}；INVALID {validity['INVALID']}；REVIEW {validity['REVIEW']}。后两类不进入一致性指标。")
    result = reliability_metrics(filtered)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("比较案例数 / Cases compared", result["n"])
    c2.metric("完全一致率 / Exact Agreement", "—" if result["exact_agreement"] is None else f"{result['exact_agreement']*100:.1f}%")
    c3.metric("Cohen's κ", "—" if result["cohen_kappa"] is None else f"{result['cohen_kappa']:.3f}")
    c4.metric("风险发现召回率 / Finding Recall", "—" if result["finding_recall"] is None else f"{result['finding_recall']*100:.1f}%")
    matrix = pd.DataFrame(result["matrix"]).T
    matrix.index.name = "LLM Judge"
    matrix.columns.name = "Human"
    st.subheader("混淆矩阵 / Confusion Matrix")
    st.dataframe(matrix, use_container_width=True)
    st.caption(f"当前项目策略：{adjudication_policy(project)}。一致性指标只基于 Case Validity == VALID 且 adjudication_status == REVIEWED 的 case；抽样模式的未复核 case 不会被伪造为人工标签。")


def dialogue_report_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择测试项目。")
        return
    deterministic_path = paths.reports / "dialogue_report_deterministic.md"
    deterministic = None
    if deterministic_path.exists():
        deterministic = deterministic_path.read_text(encoding="utf-8")
    else:
        st.info("当前项目尚未生成已保存的对话评测报告；只读 Published 页面不会在浏览时创建报告。")
    rows = load_final_results(paths.final_results)
    if deterministic is not None:
        with st.container():
            st.markdown('<span class="report-document-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
            st.markdown(deterministic)
        st.download_button("下载确定性对话测试报告", data=deterministic.encode("utf-8"), file_name=f"{project['project_id']}_dialogue_report.md", mime="text/markdown")
    st.markdown(
        '<div class="report-action-heading"><div class="report-action-eyebrow">LLM REPORT WRITER</div><div class="report-action-title">可选：LLM 撰写对话测试报告</div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("展开配置 / Open configuration", expanded=False):
        st.caption("指标由 Python 计算；报告模型只能根据冻结的结构化上下文生成文字。")
        profile = render_llm_profile_selector("dialogue_report", key_prefix="dialogue_report_writer")
        if st.button("生成 LLM 对话测试报告", disabled=profile is None):
            try:
                runtime_context = ensure_active_workspace_for_write()
                project = active_project()
                paths = runtime_context.paths
                rows = load_final_results(paths.final_results)
                context = build_dialogue_report_context(project=project, final_rows=rows)
                text = run_report_writer(role="dialogue_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope)
                result = write_report_artifacts(
                    report_type="dialogue", project=project, final_rows=rows,
                    layer2_path=paths.layer2_records, layer3_path=paths.layer3_records,
                    reports_dir=paths.reports, draft_text=text, scope=runtime_context.scope,
                    workspace_root=paths.root,
                )
                if result["manifest"]["validation_status"] != "PASS":
                    st.error("报告未通过硬校验或证据校验，未发布 final_report.md。请查看 grounding_result.json。")
                else:
                    st.session_state["dialogue_report_llm_text"] = result["paths"]["final"].read_text(encoding="utf-8")
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("dialogue_report_llm_text"):
            st.markdown(st.session_state["dialogue_report_llm_text"])


def report_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择测试项目。")
        return
    output = paths.reports / "final_report.md"
    if not output.exists():
        output = paths.reports / "integrated_report.md"
    report = None
    if output.exists():
        report = output.read_text(encoding="utf-8")
    else:
        st.info("当前项目尚未生成已保存的综合评测报告；只读 Published 页面不会在浏览时创建报告。")
    rows = load_final_results(paths.final_results)
    if report is not None:
        with st.container():
            st.markdown('<span class="report-document-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
            st.markdown(report)
        st.download_button("下载综合测试报告（.md）", data=report.encode("utf-8"), file_name=f"{project['project_id']}_integrated_report.md", mime="text/markdown")
    st.markdown(
        '<div class="report-action-heading"><div class="report-action-eyebrow">LLM REPORT WRITER</div><div class="report-action-title">生成 LLM 综合测试报告</div><div class="report-action-subtitle">Generate LLM Integrated Report</div></div>',
        unsafe_allow_html=True,
    )
    with st.expander("展开配置 / Open configuration", expanded=False):
        st.caption("确定性分析摘要只是 Python 结果汇总；正式 LLM 综合报告必须同时经过 Evidence Grounding Validator LLM。")
        profile = render_llm_profile_selector("integrated_report", key_prefix="integrated_report_writer")
        grounding_profile = render_llm_profile_selector("grounding_validator", key_prefix="integrated_report_grounding")
        if st.button("生成并验证 LLM 综合测试报告", disabled=profile is None or grounding_profile is None):
            try:
                runtime_context = ensure_active_workspace_for_write()
                project = active_project()
                paths = runtime_context.paths
                rows = load_final_results(paths.final_results)
                context = build_integrated_report_context(project=project, final_rows=rows, layer2_path=paths.layer2_records, layer3_path=paths.layer3_records)
                text = run_report_writer(role="integrated_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope)
                grounding = run_grounding_validator(draft_report=text, report_context=context, llm_profile=grounding_profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope)
                result = write_report_artifacts(
                    report_type="integrated", project=project, final_rows=rows,
                    layer2_path=paths.layer2_records, layer3_path=paths.layer3_records,
                    reports_dir=paths.reports, draft_text=text,
                    grounding_validator=lambda draft, report_context: grounding, scope=runtime_context.scope,
                    workspace_root=paths.root,
                )
                if result["manifest"]["validation_status"] != "PASS":
                    st.error("报告未通过硬校验或证据校验，未发布 final_report.md。请查看 grounding_result.json。")
                else:
                    st.session_state["integrated_report_llm_text"] = result["paths"]["final"].read_text(encoding="utf-8")
            except Exception as e:
                st.error(str(e))
        if st.session_state.get("integrated_report_llm_text"):
            st.markdown(st.session_state["integrated_report_llm_text"])
