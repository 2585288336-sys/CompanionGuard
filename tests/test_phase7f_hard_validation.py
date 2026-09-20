from __future__ import annotations

from pathlib import Path

from companionguard_app.report_pipeline import write_report_artifacts
from companionguard_app.report_validation import validate_report_hard
from companionguard_app.reporting import build_dialogue_report_context, build_writer_facing_context
from companionguard_app.runtime_scope import RuntimeScope


def _context() -> dict:
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue"},
        "coverage": {
            "total_formal_case_count": 210,
            "adjudicated_formal_case_count": 210,
            "valid_formal_case_count": 209,
            "invalid_formal_case_count": 1,
            "formal_case_count": 209,
        },
        "overall": {"macro_finding_rate": 0.666666, "macro_finding_rate_display": "66.7%"},
        "overall_macro_finding_rate": 0.666666,
        "overall_macro_finding_rate_display": "66.7%",
        "products": {"MoMood": {"formal_cases": 3, "finding_rate": 0.666666, "finding_rate_display": "66.7%"}},
        "modules": {},
        "criteria": {},
        "conditions": {"C0": {"finding_rate": 0.666666, "finding_rate_display": "66.7%"}},
        "comparisons": {},
        "reliability": {"n": 210, "cohen_kappa": 0.8105948261657602},
        "reliability_display": {
            "cohen_kappa": "0.811",
            "cohen_kappa_display": "0.811",
            "exact_agreement": "90.0%",
            "finding_precision": "90.0%",
            "finding_recall": "90.0%",
        },
        "cohen_kappa_display": "0.811",
        "representative_findings": [],
        "layer2": {},
        "layer3": {"records": [{"evidence_summary": "违规内容将在24小时内删除。"}]},
        "cross_layer": {},
        "limitations": [],
        "unresolved_questions": [],
        "verification_needed": [],
    }


def _check(text: str) -> dict:
    return validate_report_hard(report_text=text, context=_context(), report_type="dialogue")


def test_kappa_display_contract_is_strict():
    assert _check("Cohen's κ 为 0.811。")['overall_status'] == "PASS"
    assert _check("Cohen's κ 为 0.81。")['overall_status'] == "FAIL"
    assert _check("Cohen's κ 为 0.82。")['overall_status'] == "FAIL"
    assert any(issue["issue_type"] == "NUMBER_MISMATCH" for issue in _check("Cohen's κ 为 0.81。")['issues'])


def test_legal_assertions_fail_but_negated_boundaries_pass():
    assert _check("该企业违规。")['overall_status'] == "FAIL"
    assert _check("FINDING 不等于企业违法或不合规。")['overall_status'] == "PASS"
    assert _check("FINDING 不构成正式法律认定。")['overall_status'] == "PASS"
    assert _check("本报告不对企业是否违法作出判断。")['overall_status'] == "PASS"


def test_attributed_evidence_wording_is_not_a_report_legal_claim():
    assert _check("页面显示：输入内容包含违规信息，已被撤回。")['overall_status'] == "PASS"
    assert _check("材料写明：违规内容将在24小时内删除。")['overall_status'] == "PASS"
    result = _check("证据写有违规，因此企业违规。")
    assert result['overall_status'] == "FAIL"
    assert any(issue["issue_type"] == "LEGAL_OVERCLAIM" for issue in result['issues'])


def test_phase7g_real_integrated_legal_sentences_are_classified_by_context():
    assert _check('FINDING 不等于产品违法或不合规。')['overall_status'] == 'PASS'
    assert _check('FINDING 不构成正式法律认定。')['overall_status'] == 'PASS'
    assert _check('页面显示“输入内容包含违规信息，已被撤回”。')['overall_status'] == 'PASS'
    assert _check('页面显示“输入内容包含违规信息，已被撤回”，因此该产品违规。')['overall_status'] == 'FAIL'
    assert _check('举报分类包括“违法犯罪”。')['overall_status'] == 'PASS'
    assert _check('模型在特定叙事框架下为暴力或违法行为提供支持性回应。')['overall_status'] == 'PASS'
    assert _check('该产品违法。')['overall_status'] == 'FAIL'
    assert _check('该企业违规。')['overall_status'] == 'FAIL'
    assert _check('本次 Finding 证明企业不合规。')['overall_status'] == 'FAIL'


def test_phase7g_human_no_finding_count_is_explicit_and_displayed():
    context = _context()
    context["reliability"]["human_no_finding_count"] = 175
    context["reliability_display"]["human_no_finding_count_display"] = "175"
    result = validate_report_hard(
        report_text="人工 NO_FINDING 的 175 例中，Judge 误判为 FINDING 的有 3 例。",
        context=context,
        report_type="dialogue",
    )
    assert result["overall_status"] == "PASS"
    writer = build_writer_facing_context(context)
    assert writer["dialogue_analysis"]["reliability"]["human_no_finding_count_display"] == "175"

    rows = [
        {"phase": "FORMAL", "auto_label": "NO_FINDING", "human_label": "NO_FINDING"},
        {"phase": "FORMAL", "auto_label": "FINDING", "human_label": "NO_FINDING"},
        {"phase": "FORMAL", "auto_label": "FINDING", "human_label": "FINDING"},
    ]
    generated = build_dialogue_report_context(project={"project_id": "p", "products": []}, final_rows=rows)
    assert generated["reliability"]["human_no_finding_count"] == 2
    assert generated["reliability_display"]["human_no_finding_count_display"] == "2"


def test_writer_facing_context_exposes_display_values_not_raw_kappa_or_rates():
    writer = build_writer_facing_context(_context())
    reliability = writer["dialogue_analysis"]["reliability"]
    assert reliability["cohen_kappa_display"] == "0.811"
    assert "cohen_kappa" not in reliability
    assert "finding_rate" not in writer["dialogue_analysis"]["products"]["MoMood"]
    assert writer["dialogue_analysis"]["products"]["MoMood"]["finding_rate_display"] == "66.7%"
    assert "finding_rate" not in writer["dialogue_analysis"]["conditions"]["C0"]
    assert writer["coverage"]["total_formal_case_count"] == 210
    assert writer["coverage"]["adjudicated_formal_case_count"] == 210
    assert writer["coverage"]["valid_formal_case_count"] == 209
    assert writer["coverage"]["invalid_formal_case_count"] == 1


def _integrated_text(suffix: str = "") -> str:
    return "\n".join([
        "## EXECUTIVE_SUMMARY", "摘要：本报告说明当前测试结果及其证据边界，并提出后续核查重点。",
        "## SCOPE", "评测范围：本次分析仅使用有效正式案例和已记录的产品与公开材料。",
        "## LAYER_1_ANALYSIS", "Layer 1：结果显示需要结合条件差异和具体能力表现进行分析。",
        "## LAYER_2_ANALYSIS", "Layer 2：产品机制证据需要与行为测试结果分开解释。",
        "## LAYER_3_ANALYSIS", "Layer 3：公开材料能够支持的结论受材料范围限制。",
        "## CROSS_LAYER_SYNTHESIS", "跨层分析：不同证据层之间的关系需要结合覆盖状态审慎判断。",
        "## REGULATORY_RECOMMENDATIONS", "监管建议：补充触发测试并要求提供可复核的公开材料。",
        "## LIMITATIONS", "局限性：后台机制、样本覆盖和代表案例证据完整度仍有限。",
        suffix,
    ])


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    workspace = data_root / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace.mkdir(parents=True)
    (workspace / "layer2_product_safeguards.jsonl").write_text("", encoding="utf-8")
    (workspace / "layer3_public_evidence.jsonl").write_text("", encoding="utf-8")
    return data_root, workspace


def _grounding_pass() -> dict:
    return {"overall_status": "PASS", "summary": {"sentences_checked": 1}, "evidence_integrity": {"status": "PASS"}, "report_quality": {"status": "PASS"}}


def test_hard_validation_fail_skips_grounding(tmp_path):
    data_root, workspace = _workspace(tmp_path)
    calls: list[bool] = []
    result = write_report_artifacts(
        report_type="integrated", project={"project_id": "fixture", "products": []}, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text=_integrated_text("该企业违规。"), minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: calls.append(True) or _grounding_pass(),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
    )
    assert result["hard_validation"]["overall_status"] == "FAIL"
    assert result["grounding"]["overall_status"] == "SKIPPED"
    assert calls == []


def test_hard_validation_pass_allows_grounding(tmp_path):
    data_root, workspace = _workspace(tmp_path)
    calls: list[bool] = []
    result = write_report_artifacts(
        report_type="integrated", project={"project_id": "fixture", "products": []}, final_rows=[],
        layer2_path=workspace / "layer2_product_safeguards.jsonl", layer3_path=workspace / "layer3_public_evidence.jsonl",
        reports_dir=workspace / "reports", draft_text=_integrated_text("FINDING 不构成正式法律认定。"), minimum_visible_chars=1,
        grounding_validator=lambda _draft, _context: calls.append(True) or _grounding_pass(),
        scope=RuntimeScope.WORKSPACE, workspace_root=workspace, data_root=data_root,
    )
    assert result["hard_validation"]["overall_status"] == "PASS"
    assert result["grounding"]["overall_status"] == "PASS"
    assert calls == [True]
