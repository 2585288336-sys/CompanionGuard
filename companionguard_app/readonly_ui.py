"""Presentation-only pages for deployment snapshots.

Read-only snapshots should expose the same workflow concepts as a working
project, while never calling a writer, Judge, collector, or report generator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from .audits import load_jsonl
from .collector_storage import load_raw_cases
from .display_labels import condition_label, criterion_label, module_label, phase_label
from .platform_ui import active_paths, active_project
from .storage import load_adjudications, load_judge_results
from .ui_theme import empty_state


def _banner() -> None:
    st.info("当前为公开演示快照：本页展示已保存的项目数据和完整工作流 UI，不会向快照写入采集、Judge、人工复核或报告数据。")


def _context() -> tuple[dict[str, Any] | None, Any]:
    return active_project(), active_paths()


def _basic_rows(project: dict[str, Any], paths: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    cases = load_raw_cases(paths.raw_cases)
    judges = [r for r in load_judge_results(paths.judge_results) if r.get("status") == "ok"]
    adjudications = load_adjudications(paths.adjudication)
    return cases, judges, adjudications


def _collection_preview(project: dict[str, Any], paths: Any) -> None:
    st.header("对话数据采集 / Dialogue Data Collection")
    st.caption("展示正式数据采集工作流、案例队列和已保存记录；原始对话与截图是否公开由部署快照的数据范围决定。")
    _banner()
    cases, _, _ = _basic_rows(project, paths)
    queues = load_jsonl(paths.collection_queues)
    c1, c2, c3 = st.columns(3)
    c1.metric("已保存案例", len(cases))
    c2.metric("采集队列", len(queues))
    c3.metric("当前阶段", project.get("phase") or "FORMAL")
    if not cases:
        empty_state("当前项目暂无采集记录", "研发版中可通过 Case Queue 按照冻结 Test Plan 采集并保存原始案例。")
        return
    rows = []
    for case in cases:
        rows.append({
            "案例编号": case.get("case_id"),
            "产品": case.get("product"),
            "条件": case.get("condition"),
            "阶段": case.get("phase") or (case.get("metadata") or {}).get("phase"),
            "采集状态": case.get("collection_status"),
            "证据轮次": len(case.get("collection_trace") or []),
        })
    st.subheader("Case Queue / 案例队列")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _judge_preview(project: dict[str, Any], paths: Any) -> None:
    st.header("自动判定 / Dialogue Judge")
    st.caption("以已保存的 criterion-bound Judge 结果展示 Finding Matrix；研发版中可对已采集案例运行 Judge。")
    _banner()
    cases, judges, _ = _basic_rows(project, paths)
    case_map = {c.get("case_id"): c for c in cases}
    ok = [r for r in judges if r.get("status") == "ok"]
    c1, c2, c3 = st.columns(3)
    c1.metric("已采集案例", len(cases))
    c2.metric("自动判定", len(ok))
    c3.metric("待人工复核", len(ok))
    if not ok:
        empty_state("当前项目暂无成功的自动判定记录", "研发版中可选择已采集案例或批量队列运行 Dialogue Judge。")
        return
    rows = []
    for result in ok:
        case = case_map.get(result.get("case_id"), {})
        metadata = case.get("metadata") or result.get("metadata") or {}
        rows.append({
            "案例编号": result.get("case_id"),
            "产品": result.get("product") or case.get("product"),
            "测试项目": criterion_label(result.get("criterion_id")),
            "模块": module_label(result.get("module")),
            "条件": result.get("condition") or case.get("condition"),
            "阶段": metadata.get("phase") or case.get("phase"),
            "自动风险标签": result.get("auto_label"),
            "案例有效性": result.get("auto_case_validity") or "VALID",
            "人工复核状态": "未复核",
        })
    st.subheader("Finding Matrix / 判定矩阵")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _human_review_preview(project: dict[str, Any], paths: Any) -> None:
    st.header("人工复核 / Human Review")
    st.caption("展示 Auto Judgment、人工复核和案例有效性字段；公开快照不提供写入控件。")
    _banner()
    _, judges, adjudications = _basic_rows(project, paths)
    adj_map = {r.get("case_id"): r for r in adjudications}
    rows = []
    for result in judges:
        if result.get("status") != "ok":
            continue
        case_id = result.get("case_id")
        adj = adj_map.get(case_id)
        rows.append({
            "案例编号": case_id,
            "自动风险标签": result.get("auto_label"),
            "人工风险标签": (adj or {}).get("human_label") or "—",
            "最终标签": (adj or {}).get("final_label") or "—",
            "案例有效性": (adj or {}).get("final_case_validity") or result.get("auto_case_validity") or "VALID",
            "复核状态": "已复核" if adj else "待复核",
        })
    c1, c2 = st.columns(2)
    c1.metric("自动判定案例", len(rows))
    c2.metric("已保存人工复核", len(adjudications))
    if rows:
        st.subheader("Review Queue / 复核队列")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        empty_state("当前项目暂无人工复核队列", "完成自动判定后，案例会进入 Human Review，并区分风险标签与案例有效性。")


def _audit_preview(page_title: str, subtitle: str, path: Path, columns: list[str], empty_title: str, empty_message: str) -> None:
    st.header(page_title)
    st.caption(subtitle)
    _banner()
    rows = load_jsonl(path)
    if not rows:
        empty_state(empty_title, empty_message)
        return
    st.dataframe(pd.DataFrame([{key: row.get(key) for key in columns} for row in rows]), use_container_width=True, hide_index=True)


def _dialogue_report_preview(project: dict[str, Any], paths: Any) -> None:
    st.header("对话评测报告 / Dialogue Report")
    st.caption("Dialogue Report 仅汇总 Layer 1；Integrated Report 另行整合三层证据。")
    _banner()
    report_files = sorted(paths.reports.glob("*.md")) if paths.reports.exists() else []
    if not report_files:
        empty_state("当前项目暂无已保存的对话报告", "研发版中可在已有 deterministic analysis 基础上生成报告；不会修改冻结 Prompt 或原始数据。")
        return
    selected = st.selectbox("已保存报告 / Saved report", report_files, format_func=lambda p: p.name)
    st.markdown(selected.read_text(encoding="utf-8"))


def readonly_page(page: str) -> None:
    """Render a non-mutating equivalent of a write-oriented workflow page."""
    project, paths = _context()
    if not project or not paths:
        st.warning("请先选择测试项目。")
        return
    if page == "data_collection":
        _collection_preview(project, paths)
    elif page == "judge":
        _judge_preview(project, paths)
    elif page == "human_review":
        _human_review_preview(project, paths)
    elif page == "layer2":
        _audit_preview("产品安全机制检查 / Product Safeguards", "展示当前 Project 已保存的 Layer 2 产品机制记录。", paths.layer2_records, ["product", "check_code", "status", "notes"], "当前项目暂无正式检查记录", "空数据不代表功能未完成；研发版可按正式 22 项框架录入检查结果。")
    elif page == "layer3":
        _audit_preview("公开制度材料核查 / Public Evidence", "展示当前 Project 已保存的 Layer 3 公开材料核查记录。", paths.layer3_records, ["product", "check_code", "status", "notes"], "当前项目暂无正式核查记录", "空数据不代表功能未完成；研发版可按正式六项检查录入公开证据。")
    elif page == "dialogue_report":
        _dialogue_report_preview(project, paths)
    else:
        st.info("当前页面为公开快照的只读展示。")
