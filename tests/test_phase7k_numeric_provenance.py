from pathlib import Path

from companionguard_app.report_validation import validate_report_hard
from companionguard_app.reporting import build_writer_facing_context


ROOT = Path(__file__).resolve().parents[1]
VALID_NUMERIC_CORPUS = (
    ("本轮覆盖 22 个 criterion。", "22"),
    ("人工 NO_FINDING 的 175 例。", "175"),
    ("Cohen's κ 为 0.811。", "0.811"),
    ("criterion 发现率为 29.6%。", "29.6%"),
    ("criterion 发现率为 30.6%。", "30.6%"),
    ("criterion 发现率为 33.3%。", "33.3%"),
    ("压力差值为 +6.9 pp。", "+6.9 pp"),
    ("多轮差值为 -2.8 pp。", "-2.8 pp"),
    ("代表性 FINDING 共 10 例。", "10"),
)
UNSUPPORTED_NUMERIC_CORPUS = (
    ("本轮覆盖 21 个 criterion。", "21"),
    ("两个 criterion 的发现率均接近 30%。", "30%"),
    ("Cohen's κ 为 0.81。", "0.81"),
    ("人工 NO_FINDING 的 174 例。", "174"),
    ("criterion 发现率为 31%。", "31%"),
    ("推导比例为 62.9%。", "62.9%"),
)


def _context() -> dict:
    return {
        "meta": {"context_schema_version": "1.0", "report_type": "dialogue"},
        "coverage": {
            "total_formal_case_count": 210,
            "adjudicated_formal_case_count": 210,
            "valid_formal_case_count": 209,
            "invalid_formal_case_count": 1,
        },
        "overall": {"macro_finding_rate_display": "29.6%"},
        "overall_macro_finding_rate_display": "29.6%",
        "products": {"MoMood": {"formal_cases": 70, "finding_rate_display": "30.6%"}},
        "modules": {"module": 33.3},
        "module_finding_rates_display": {"module": "33.3%"},
        "criteria": {
            f"C-{index}": {
                "criterion_name": "Criterion",
                "formal_cases": 10,
                "finding_rate_display": "29.6%",
            }
            for index in range(1, 23)
        },
        "criterion_count": 22,
        "conditions": {"C0": {"finding_rate_display": "29.6%", "sample_size": 175}},
        "comparisons": {
            "pressure": {"display_value": "+6.9 pp"},
            "multi_turn": {"display_value": "-2.8 pp"},
        },
        "reliability": {"n": 210, "human_no_finding_count": 175},
        "reliability_display": {
            "human_no_finding_count_display": "175",
            "cohen_kappa_display": "0.811",
        },
        "cohen_kappa_display": "0.811",
        "representative_findings": [],
        "representative_finding_count": 10,
        "layer2": {},
        "layer3": {},
        "cross_layer": {},
        "limitations": [],
        "unresolved_questions": [],
        "verification_needed": [],
    }


def _check(text: str) -> dict:
    return validate_report_hard(report_text=text, context=_context(), report_type="dialogue")


def test_exact_numeric_provenance_corpus_passes():
    assert len(VALID_NUMERIC_CORPUS) == 9
    for text, literal in VALID_NUMERIC_CORPUS:
        result = _check(text)
        assert result["overall_status"] == "PASS", (text, result["issues"])
        assert literal not in {issue.get("value") for issue in result["issues"]}


def test_unsupported_numeric_provenance_corpus_fails_strictly():
    assert len(UNSUPPORTED_NUMERIC_CORPUS) == 6
    for text, literal in UNSUPPORTED_NUMERIC_CORPUS:
        result = _check(text)
        assert result["overall_status"] == "FAIL", (text, result)
        issues = [issue for issue in result["issues"] if issue["issue_type"] == "NUMBER_MISMATCH"]
        assert issues and issues[0]["value"] == literal
        assert issues[0]["sentence_excerpt"] == text


def test_numeric_contract_is_explicit_in_writer_context():
    writer = build_writer_facing_context(_context())
    contract = writer["report_contract"]["numeric_provenance"]
    assert contract == {
        "exact_context_values_only": True,
        "writer_may_recalculate": False,
        "writer_may_round": False,
        "writer_may_create_thresholds": False,
        "writer_may_create_approximate_numeric_literals": False,
        "preferred_display_fields": ["*_display", "sample_size"],
    }
    assert writer["representative_finding_count"] == 10


def test_dialogue_and_integrated_prompts_state_numeric_contract():
    required = (
        "不得重新计算",
        "四舍五入",
        "创建阈值",
        "约 X%",
        "29.6%",
        "cohen_kappa_display",
        "sample_size",
    )
    for name in ("dialogue_report_v1.1.md", "integrated_report_v1.1.md"):
        prompt = (ROOT / "prompts" / "reporting" / name).read_text(encoding="utf-8")
        for phrase in required:
            assert phrase in prompt, (name, phrase)


def test_three_production_30_percent_literals_are_three_strict_failures():
    draft = "\n".join([
        "两个 criterion 的发现率均接近或超过 30%。",
        "未成年人保护模块的两个 criterion 发现率均接近或超过 30%。",
        "MC 和 MR 发现率均接近或超过 30%。",
    ])
    result = _check(draft)
    mismatches = [issue for issue in result["issues"] if issue["issue_type"] == "NUMBER_MISMATCH"]
    assert result["overall_status"] == "FAIL"
    assert len(mismatches) == 3
    assert all(issue["value"] == "30%" and issue["sentence_excerpt"] for issue in mismatches)
