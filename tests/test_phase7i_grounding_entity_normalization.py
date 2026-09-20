from companionguard_app.grounding_validator import normalize_grounding_result


KNOWN_PRODUCTS = {"MoMood", "星野", "豆包"}


def _context() -> dict:
    return {
        "products": {name: {} for name in KNOWN_PRODUCTS},
        "product_layer_coverage": [
            {"product_id": name, "display_name": name, "layers": {}}
            for name in KNOWN_PRODUCTS
        ],
    }


def _entity_failure(candidate: str) -> dict:
    return {
        "validator_version": "Evidence Grounding Prompt v1.0",
        "overall_status": "FAIL",
        "summary": {
            "sentences_checked": 0,
            "supported": 0,
            "partially_supported": 0,
            "unsupported": 1,
            "critical_errors": 1,
        },
        "issues": [{
            "sentence_id": "unknown",
            "support_status": "UNSUPPORTED",
            "issue_types": ["ENTITY_MISMATCH"],
            "reason": f"product not in context: {candidate}",
        }],
        "unsupported_numbers": [],
        "cross_layer_errors": [],
        "legal_overclaim_errors": [],
        "final_decision": "需要修订后重新验证",
    }


def test_known_product_entity_lists_are_normalized():
    for candidate in (
        "MoMood、星野、豆包",
        "MoMood、星野和豆包",
        "MoMood，星野，豆包",
        "MoMood / 星野 / 豆包",
        "MoMood、星野以及豆包",
        "MoMood",
    ):
        result = normalize_grounding_result(_entity_failure(candidate), _context())
        assert result["overall_status"] == "PASS"
        assert result["issues"] == []
        assert result["summary"]["sentences_checked"] == 1
        assert result["summary"]["unsupported"] == 0
        assert result["summary"]["critical_errors"] == 0


def test_unknown_or_mixed_product_entity_lists_still_fail():
    for candidate in ("MoMood、星野、Replika", "Replika", "ChatGPT", "第四款产品 Claude"):
        result = normalize_grounding_result(_entity_failure(candidate), _context())
        assert result["overall_status"] == "FAIL"
        assert len(result["issues"]) == 1
        assert result["issues"][0]["issue_types"] == ["ENTITY_MISMATCH"]


def test_non_entity_issue_is_not_removed():
    result = _entity_failure("MoMood、星野、豆包")
    result["issues"][0]["issue_types"] = ["UNSUPPORTED_CLAIM"]
    normalized = normalize_grounding_result(result, _context())
    assert normalized["overall_status"] == "FAIL"
    assert normalized["issues"][0]["issue_types"] == ["UNSUPPORTED_CLAIM"]
