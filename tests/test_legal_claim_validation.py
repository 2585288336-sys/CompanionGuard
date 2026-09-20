from companionguard_app.report_validation import validate_report_hard


HISTORICAL_FALSE_POSITIVE_CORPUS = (
    "FINDING 不等于产品违法或不合规。",
    "本报告不构成正式法律结论。",
    "输入内容包含违规信息，已被撤回。",
    "页面显示‘输入内容包含违规信息，已被撤回’。",
    "举报分类包括‘违法犯罪’。",
    "用户服务协议中的投诉举报制度主要针对内容违规和侵权情形。",
    "模型在特定叙事框架下为暴力或违法行为提供支持性回应。",
    "不构成统一安全或合规评分。",
    "产品把该输入作为违规内容拦下。",
    "公开材料记录显示该产品曾因内容问题被媒体曝光，本报告照录该表述，不作法律定性。",
    "页面显示“输入内容包含违规信息，已被撤回”，但本报告不作法律判断。",
)

TRUE_POSITIVE_CORPUS = (
    "MoMood 违法。",
    "MoMood 存在违规行为。",
    "该企业违反相关规定。",
    "星野属于违法违规产品。",
    "本次评测证明豆包不合规。",
    "该企业未履行法定义务。",
    "该产品被认定为不合规。",
    "本次评测证明企业违反相关规定。",
)


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
        "overall": {"macro_finding_rate": 0.5, "macro_finding_rate_display": "50.0%"},
        "overall_macro_finding_rate": 0.5,
        "overall_macro_finding_rate_display": "50.0%",
        "products": {name: {"formal_cases": 70} for name in ("MoMood", "星野", "豆包")},
        "product_layer_coverage": [
            {"product_id": name, "display_name": name, "layers": {}}
            for name in ("MoMood", "星野", "豆包")
        ],
        "modules": {},
        "criteria": {},
        "conditions": {},
        "comparisons": {},
        "reliability": {"n": 210},
        "reliability_display": {},
        "representative_findings": [],
        "layer2": {},
        "layer3": {"records": []},
        "cross_layer": {},
        "limitations": [],
        "unresolved_questions": [],
        "verification_needed": [],
    }


def _check(text: str) -> dict:
    return validate_report_hard(report_text=text, context=_context(), report_type="dialogue")


def test_historical_legal_false_positive_corpus_passes():
    assert len(HISTORICAL_FALSE_POSITIVE_CORPUS) == 11
    for text in HISTORICAL_FALSE_POSITIVE_CORPUS:
        result = _check(text)
        assert result["overall_status"] == "PASS", (text, result["issues"])


def test_historical_true_positive_corpus_still_fails_with_structural_diagnostics():
    assert len(TRUE_POSITIVE_CORPUS) == 8
    for text in TRUE_POSITIVE_CORPUS:
        result = _check(text)
        assert result["overall_status"] == "FAIL", (text, result)
        legal_issues = [issue for issue in result["issues"] if issue["issue_type"] == "LEGAL_OVERCLAIM"]
        assert legal_issues, (text, result["issues"])
        for issue in legal_issues:
            assert issue["sentence_excerpt"] == text
            assert issue["detected_subject"]
            assert issue["detected_predicate"]
            assert issue["reason"]


def test_score_boundary_stays_separate_from_legal_claim_detection():
    assert _check("不构成统一安全或合规评分。")["overall_status"] == "PASS"
    result = _check("该产品合规评分为 85。")
    assert result["overall_status"] == "FAIL"
    assert any(issue["issue_type"] == "UNAUTHORIZED_SCORE" for issue in result["issues"])


def test_mixed_attribution_and_direct_claim_only_flags_direct_claim():
    result = _check("页面显示‘输入内容包含违规信息，已被撤回’，因此该产品违规。")
    legal_issues = [issue for issue in result["issues"] if issue["issue_type"] == "LEGAL_OVERCLAIM"]
    assert len(legal_issues) == 1
    assert legal_issues[0]["detected_subject"] == "该产品"
    assert legal_issues[0]["detected_predicate"] == "违规"
