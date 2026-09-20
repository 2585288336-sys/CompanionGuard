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
from .projects import (
    EVALUATION_LAYER_ORDER,
    PRIMARY_PRODUCT_ROLE,
    add_project_product,
    assert_product_in_layer,
    create_project,
    delete_project,
    get_project,
    list_projects,
    materialize_evaluation_layers,
    products_for_layer,
    safe_slug,
    update_project,
)
from .reliability import LABELS, reliability_metrics
from .reporting import build_dialogue_report, build_dialogue_report_context, build_integrated_report, build_integrated_report_context
from .report_pipeline import report_artifact_dir, write_report_artifacts
from .service import criteria_index, run_documentary_assist, run_grounding_validator, run_report_writer
from .llm_ui import llm_session_id, render_llm_profile_selector
from .storage import build_final_results, load_adjudications, load_final_results, load_judge_results
from .runtime_scope import RuntimeScope
from .runtime_workspace import (
    RuntimeContext,
    WorkspaceRecoveryError,
    ensure_active_workspace,
    get_runtime_context,
    workspace_recovery_failed,
)
from .collector_storage import load_raw_cases
from .metrics import case_validity_counts, valid_case_rows
from .display_labels import criterion_label, module_label, scenario_label
from .ui_helpers import condition_label, phase_label, render_case_conversation, render_case_validity, render_judge_result


def active_project_id() -> str | None:
    value = st.session_state.get("active_project_id")
    return None if value in {None, "__NONE__"} else value


def active_project() -> dict[str, Any] | None:
    if workspace_recovery_failed():
        return None
    context = active_runtime_context()
    if context is None:
        return None
    try:
        value = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return get_project(context.published_project_id) if context.scope is RuntimeScope.PUBLISHED else None
    return value if isinstance(value, dict) else None


def active_paths():
    if workspace_recovery_failed():
        return None
    context = active_runtime_context()
    return context.paths if context else None


def active_runtime_context() -> RuntimeContext | None:
    if workspace_recovery_failed():
        return None
    pid = active_project_id()
    return get_runtime_context(pid) if pid else None


def active_scope() -> RuntimeScope | None:
    context = active_runtime_context()
    return context.scope if context else None


def ensure_active_workspace_for_write() -> RuntimeContext:
    if workspace_recovery_failed():
        raise WorkspaceRecoveryError(
            "当前临时工作区无法恢复；请先返回官方发布版，再开始新的临时评测工作区。"
        )
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


def _new_project_default_product_ids() -> list[str]:
    """New projects require an explicit product choice; none are preselected."""

    return []


def _build_new_project_products(
    configured: list[dict[str, Any]],
    selected_ids: list[str],
    custom_text: str,
) -> list[dict[str, Any]]:
    products = [dict(product) for product in configured if product["id"] in selected_ids]
    for line in custom_text.splitlines():
        value = line.strip()
        if value:
            products.append({
                "id": safe_slug(value),
                "label": value,
                "slug": safe_slug(value),
                "role": "User-defined product",
                "evaluation_layers": list(EVALUATION_LAYER_ORDER),
            })
    for product in products:
        product.setdefault("evaluation_layers", list(EVALUATION_LAYER_ORDER))
    return products


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
    selected_ids = st.multiselect(
        "选择评测产品 / Select evaluated products",
        [p["id"] for p in configured],
        default=_new_project_default_product_ids(),
        format_func=lambda x: next(p.get("label", x) for p in configured if p["id"] == x),
    )
    if mode == "BENCHMARK":
        st.caption(
            "MoMood、星野、豆包为当前 FORMAL Full Benchmark 已注册的主产品。创建新项目时，可根据需要自由选择或添加评测产品。 "
            "MoMood, Xingye, and Doubao are registered primary products in the current FORMAL Full Benchmark. New projects can freely choose or add products according to their evaluation scope."
        )
    st.caption(
        "新建项目中的产品初始纳入全部三层；创建后可在‘当前项目评测产品’中调整各产品测试范围。 "
        "New project products initially include all three layers; adjust each product's evaluation scope after creation in ‘Evaluated products in this project’."
    )
    custom_text = st.text_area("添加其他评测产品（每行一个） / Add other evaluated products", placeholder="Character.AI\nNomi", help="用于添加上述列表中没有的产品。 / Use this field for products not listed above.")
    notes = st.text_area("项目备注（可选） / Project notes")
    if st.button("创建测试项目 / Create Test Project", type="primary"):
        products = _build_new_project_products(configured, selected_ids, custom_text)
        if not products:
            st.error("请至少选择或添加一个评测产品。 / Please select or add at least one evaluated product.")
            return
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

    project = active_project()
    if project:
        st.divider()
        st.caption("以下设置作用于当前已打开项目。 / The settings below apply to the currently opened project.")
        _render_evaluated_products(project)


def format_evaluation_layers_compact(evaluation_layers: list[str] | tuple[str, ...]) -> str:
    """Return a compact, display-only layer summary in canonical order."""

    compact_labels = {"layer1": "L1", "layer2": "L2", "layer3": "L3"}
    selected = set(evaluation_layers)
    return " · ".join(
        compact_labels[layer]
        for layer in EVALUATION_LAYER_ORDER
        if layer in selected
    )


def _render_evaluated_products(project: dict[str, Any]) -> None:
    """Render the add-only product registration section for the active project."""

    st.subheader("当前项目评测产品 / Evaluated products in this project")
    st.caption("这里维护当前项目的评测产品及其测试范围。每个产品可分别纳入 Layer 1 对话行为测试、Layer 2 产品安全机制检查和 Layer 3 公开制度材料核查。\n\nThis section maintains the evaluated products and their evaluation scope. Each product can be included separately in Layer 1 Dialogue Behavioral Testing, Layer 2 Product Safeguard Checks, and Layer 3 Public Compliance Evidence Audit.")
    scope = active_scope()
    if scope is RuntimeScope.PUBLISHED:
        st.caption("当前正在查看官方发布版。若在此处新增产品，系统会先创建本次会话的临时工作区；修改只保存在该工作区中，不会改动官方发布版。\n\nYou are viewing the published version. Adding a product will create a temporary workspace for this session; changes will stay in that workspace and will not modify the published version.")
    elif scope is RuntimeScope.WORKSPACE:
        st.caption("当前修改保存在本次会话的临时工作区中。 / Current changes are saved in this session's temporary workspace.")
    products = project.get("products") or []
    layer_labels = {
        "layer1": "Layer 1｜对话行为测试 / Dialogue Behavioral Testing",
        "layer2": "Layer 2｜产品安全机制检查 / Product Safeguard Checks",
        "layer3": "Layer 3｜公开制度材料核查 / Public Compliance Evidence Audit",
    }
    st.dataframe(
        [
            {
                "产品 ID / Product ID": item.get("id", ""),
                "显示名称 / Display name": item.get("label") or item.get("name") or item.get("id", ""),
                "角色 / Role": item.get("role", ""),
                "测试范围 / Evaluation Layers": format_evaluation_layers_compact(
                    item.get("evaluation_layers", EVALUATION_LAYER_ORDER)
                ),
            }
            for item in products
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "L1 对话行为测试 · L2 产品安全机制检查 · L3 公开制度材料核查\n\n"
        "L1 Dialogue Behavioral Testing · L2 Product Safeguard Checks · L3 Public Compliance Evidence Audit"
    )
    roles = sorted({PRIMARY_PRODUCT_ROLE, *(str(item.get("role") or "").strip() for item in products if str(item.get("role") or "").strip())})
    with st.form(f"add_evaluated_product::{project.get('project_id')}"):
        product_id = st.text_input("产品 ID / Product ID", help="用于系统内部识别，需保持唯一。 / Used for internal identification and must remain unique.")
        display_name = st.text_input("显示名称 / Display name", help="用于页面展示。 / Used for display in the interface.")
        role = st.selectbox("角色 / Role", roles)
        evaluation_layers = st.multiselect(
            "测试范围 / Evaluation layers",
            list(EVALUATION_LAYER_ORDER),
            default=list(EVALUATION_LAYER_ORDER),
            format_func=lambda layer: layer_labels[layer],
            help="至少选择一个评测层。 / Select at least one evaluation layer.",
        )
        submitted = st.form_submit_button("添加评测产品到当前项目 / Add evaluated product to this project", type="primary")
    if submitted:
        try:
            if not evaluation_layers:
                raise ValueError("请至少选择一个评测层。 / Select at least one evaluation layer.")
            updated = add_project_product(
                project,
                product_id=product_id,
                display_name=display_name,
                role=role,
                evaluation_layers=evaluation_layers,
            )
            context = ensure_active_workspace_for_write()
            update_project(updated, scope=RuntimeScope.WORKSPACE, workspace_root=context.paths.root)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(f"已追加产品 / Added: {display_name.strip()}")
            st.rerun()
    if not products:
        st.info("当前项目尚未注册评测产品；先添加至少一个产品后再设置测试范围。 / Add at least one evaluated product before editing layer coverage.")
        return

    st.markdown("#### 调整当前产品测试范围 / Edit product evaluation scope")
    product_options = [item.get("id") for item in products if item.get("id")]
    selected_product_id = st.selectbox(
        "选择产品 / Select product",
        product_options,
        format_func=lambda pid: next((item.get("label") or pid for item in products if item.get("id") == pid), pid),
        key=f"coverage_product::{project.get('project_id')}",
    )
    selected_product = next(item for item in products if item.get("id") == selected_product_id)
    selected_layers = st.multiselect(
        "测试范围 / Evaluation layers",
        list(EVALUATION_LAYER_ORDER),
        default=list(selected_product.get("evaluation_layers", EVALUATION_LAYER_ORDER)),
        format_func=lambda layer: layer_labels[layer],
        key=f"coverage_layers::{project.get('project_id')}::{selected_product_id}",
    )
    if st.button("保存测试范围 / Save evaluation scope", type="primary", key=f"save_coverage::{project.get('project_id')}"):
        try:
            if not selected_layers:
                raise ValueError("请至少选择一个评测层。 / Select at least one evaluation layer.")
            updated = materialize_evaluation_layers(project)
            for item in updated["products"]:
                if item.get("id") == selected_product_id:
                    item["evaluation_layers"] = list(selected_layers)
                    break
            context = ensure_active_workspace_for_write()
            update_project(updated, scope=RuntimeScope.WORKSPACE, workspace_root=context.paths.root)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("测试范围已保存到当前 Workspace。 / Evaluation scope saved to the current Workspace.")
            st.rerun()


def _project_product_names(project: dict[str, Any]) -> list[str]:
    return [p.get("label") or p.get("name") or p.get("id") for p in project.get("products", []) if (p.get("label") or p.get("name") or p.get("id"))]


def layer3_product_names(project: dict[str, Any]) -> list[str]:
    """Return products in effective Layer 3 scope."""
    return [
        p.get("label") or p.get("name") or p.get("id")
        for p in products_for_layer(project, "layer3")
        if p.get("label") or p.get("name") or p.get("id")
    ]


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
    products = [
        p.get("label") or p.get("name") or p.get("id")
        for p in products_for_layer(project, "layer2")
        if p.get("label") or p.get("name") or p.get("id")
    ]
    if not products:
        st.error("当前项目没有纳入 Layer 2 的产品。 / No products are included in Layer 2 for this project.")
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
            assert_product_in_layer(project, product, "layer2")
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
    if not products:
        st.error("当前项目没有纳入 Layer 3 的产品。 / No products are included in Layer 3 for this project.")
        return
    if project.get("mode") == "BENCHMARK":
        st.caption("BENCHMARK 模式：Layer 3 Lite 按产品测试范围显示；旧项目继续兼容正式主产品角色筛选。")
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
                    st.session_state[assist_key] = run_documentary_assist(check=check, source_text=source_text, llm_profile=llm_profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=context.scope, workspace_root=context.paths.root)
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
            assert_product_in_layer(project, product, "layer3")
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
    rows = load_final_results(paths.final_results)
    dialogue_artifacts = report_artifact_dir(paths.reports, "dialogue")
    dialogue_final = dialogue_artifacts / "final_report.md"
    dialogue_manifest_path = dialogue_artifacts / "report_manifest.json"
    dialogue_manifest = {}
    if dialogue_manifest_path.exists():
        try:
            dialogue_manifest = json.loads(dialogue_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            dialogue_manifest = {}
    if dialogue_manifest.get("latest_attempt_status") not in {None, "PASS"}:
        if dialogue_final.exists():
            st.warning(f"最新一次报告生成失败（{dialogue_manifest['latest_attempt_status']}）。以下展示的是上一份成功报告；成功时间：{dialogue_manifest.get('last_successful_at') or '未知'}。")
        else:
            st.info("尚无通过验证的最终报告。")
    elif not dialogue_final.exists():
        st.info("尚无通过验证的最终报告。")
    if dialogue_final.exists():
        with st.container():
            st.markdown('<span class="report-document-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
            st.markdown(dialogue_final.read_text(encoding="utf-8"))
        st.download_button("下载 LLM 对话测试报告", data=dialogue_final.read_bytes(), file_name=f"{project['project_id']}_dialogue_llm_report.md", mime="text/markdown")
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
                context = build_dialogue_report_context(
                    project=project,
                    final_rows=rows,
                    layer2_records=load_jsonl(paths.layer2_records),
                    layer3_records=load_jsonl(paths.layer3_records),
                )
                writer_result = run_report_writer(role="dialogue_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope, workspace_root=runtime_context.paths.root, return_metadata=True)
                result = write_report_artifacts(
                    report_type="dialogue", project=project, final_rows=rows,
                    layer2_path=paths.layer2_records, layer3_path=paths.layer3_records,
                    reports_dir=paths.reports, draft_text=writer_result["text"],
                    writer_status=writer_result["status"], writer_metadata=writer_result.get("attempts", [{}])[-1] if writer_result.get("attempts") else {}, scope=runtime_context.scope,
                    workspace_root=paths.root,
                )
                if result["manifest"]["validation_status"] != "PASS":
                    st.error(f"报告生成失败：{result['manifest'].get('latest_attempt_status')}。未覆盖上一份成功报告。")
            except Exception as e:
                st.error(str(e))
def report_page(criteria: dict[str, dict[str, Any]]) -> None:
    project = active_project()
    paths = active_paths()
    if not project or not paths:
        st.warning("请先选择测试项目。")
        return
    integrated_artifacts = report_artifact_dir(paths.reports, "integrated")
    output = integrated_artifacts / "final_report.md"
    manifest_path = integrated_artifacts / "report_manifest.json"
    report = output.read_text(encoding="utf-8") if output.exists() else None
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    if manifest.get("latest_attempt_status") not in {None, "PASS"}:
        if report is not None:
            st.warning(f"最新一次报告生成失败（{manifest['latest_attempt_status']}）。以下展示的是上一份成功报告；成功时间：{manifest.get('last_successful_at') or '未知'}。")
        else:
            st.info("尚无通过验证的最终报告。")
    elif report is None:
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
                writer_result = run_report_writer(role="integrated_report", report_context=context, llm_profile=profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope, workspace_root=runtime_context.paths.root, return_metadata=True)
                result = write_report_artifacts(
                    report_type="integrated", project=project, final_rows=rows,
                    layer2_path=paths.layer2_records, layer3_path=paths.layer3_records,
                    reports_dir=paths.reports, draft_text=writer_result["text"],
                    writer_status=writer_result["status"], writer_metadata=writer_result.get("attempts", [{}])[-1] if writer_result.get("attempts") else {},
                    grounding_validator=lambda draft, report_context: run_grounding_validator(draft_report=draft, report_context=report_context, llm_profile=grounding_profile, session_id=llm_session_id(), project_id=project.get("project_id"), scope=runtime_context.scope, workspace_root=runtime_context.paths.root), scope=runtime_context.scope,
                    workspace_root=paths.root,
                )
                if result["manifest"]["validation_status"] != "PASS":
                    st.error(f"报告生成失败：{result['manifest'].get('latest_attempt_status')}。未覆盖上一份成功报告。")
            except Exception as e:
                st.error(str(e))
