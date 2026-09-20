from __future__ import annotations

import json

import pytest

from companionguard_app.grounding_validator import validate_grounding
from companionguard_app.platform_ui import layer3_product_names
from companionguard_app.projects import (
    PRIMARY_PRODUCT_ROLE,
    add_project_product,
    assert_product_in_layer,
    effective_evaluation_layers,
    materialize_evaluation_layers,
    products_for_layer,
)
from companionguard_app.reporting import (
    COVERAGE_STATUS_IN_SCOPE_NO_DATA,
    COVERAGE_STATUS_IN_SCOPE_WITH_DATA,
    COVERAGE_STATUS_NOT_IN_SCOPE,
    build_dialogue_report,
    build_dialogue_report_context,
    build_integrated_report,
    build_integrated_report_context,
    build_product_layer_coverage,
    build_writer_facing_context,
)


def _project(products: list[dict]) -> dict:
    return {
        "project_id": "coverage-fixture",
        "project_name": "Coverage Fixture",
        "mode": "CUSTOM",
        "products": products,
    }


def _row(product: str, *, final_label: str = "NO_FINDING") -> dict:
    return {
        "case_id": f"{product}-case-1",
        "phase": "FORMAL",
        "final_case_validity": "VALID",
        "adjudication_status": "REVIEWED",
        "product": product,
        "criterion_id": "HR-02",
        "module": "extreme_behavior_and_crisis_response",
        "condition": "C0",
        "final_label": final_label,
        "analysis_label": final_label,
        "human_label": final_label,
        "auto_label": final_label,
    }


def _coverage_project() -> dict:
    return _project([
        {"id": "A", "label": "Product A", "role": PRIMARY_PRODUCT_ROLE, "evaluation_layers": ["layer1", "layer2", "layer3"]},
        {"id": "B", "label": "Product B", "role": "Comparison product", "evaluation_layers": ["layer2", "layer3"]},
        {"id": "C", "label": "Product C", "role": "Comparison product", "evaluation_layers": ["layer2"]},
        {"id": "D", "label": "Product D", "role": PRIMARY_PRODUCT_ROLE, "evaluation_layers": ["layer1"]},
        {"id": "E", "label": "Product E", "role": "Comparison product", "evaluation_layers": ["layer1", "layer2", "layer3"]},
    ])


def _by_id(matrix: list[dict]) -> dict:
    return {item["product_id"]: item for item in matrix}


def test_explicit_coverage_normalizes_order_deduplicates_and_rejects_empty_or_unknown():
    project = _project([{"id": "A", "label": "A", "evaluation_layers": ["layer3", "layer1", "layer1"]}])
    assert effective_evaluation_layers(project, project["products"][0]) == ["layer1", "layer3"]
    with pytest.raises(ValueError, match="At least one"):
        add_project_product(project, product_id="B", display_name="B", role=PRIMARY_PRODUCT_ROLE, evaluation_layers=[])
    with pytest.raises(ValueError, match="Unknown"):
        add_project_product(project, product_id="C", display_name="C", role=PRIMARY_PRODUCT_ROLE, evaluation_layers=["layer4"])


def test_legacy_coverage_preserves_benchmark_and_custom_behavior():
    benchmark = _project([
        {"id": "primary", "label": "Primary", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "comparison", "label": "Comparison", "role": "Comparison product"},
    ])
    benchmark["mode"] = "BENCHMARK"
    assert effective_evaluation_layers(benchmark, benchmark["products"][0]) == ["layer1", "layer2", "layer3"]
    assert effective_evaluation_layers(benchmark, benchmark["products"][1]) == ["layer1", "layer2"]
    custom = _project([{ "id": "comparison", "label": "Comparison", "role": "Comparison product"}])
    assert effective_evaluation_layers(custom, custom["products"][0]) == ["layer1", "layer2", "layer3"]


def test_materialization_and_layer_selectors_use_effective_coverage():
    project = _project([
        {"id": "primary", "label": "Primary", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "comparison", "label": "Comparison", "role": "Comparison product", "evaluation_layers": ["layer2", "layer3"]},
    ])
    materialized = materialize_evaluation_layers(project)
    assert materialized["products"][0]["evaluation_layers"] == ["layer1", "layer2", "layer3"]
    assert [item["id"] for item in products_for_layer(materialized, "layer1")] == ["primary"]
    assert [item["id"] for item in products_for_layer(materialized, "layer3")] == ["primary", "comparison"]
    assert layer3_product_names(materialized) == ["Primary", "Comparison"]
    assert_product_in_layer(materialized, "primary", "layer1")
    with pytest.raises(ValueError, match="Layer 1"):
        assert_product_in_layer(materialized, "comparison", "layer1")


def test_product_layer_matrix_distinguishes_not_in_scope_and_in_scope_without_data():
    project = _coverage_project()
    matrix = build_product_layer_coverage(
        project=project,
        final_rows=[_row("A")],
        layer2_records=[{"product": "B", "check_code": "CRI-01", "status": "OBSERVED"}],
        layer3_records=[],
    )
    by_id = _by_id(matrix)
    assert by_id["A"]["layers"]["layer1"]["status"] == COVERAGE_STATUS_IN_SCOPE_WITH_DATA
    assert by_id["B"]["layers"]["layer1"]["status"] == COVERAGE_STATUS_NOT_IN_SCOPE
    assert by_id["B"]["layers"]["layer3"]["status"] == COVERAGE_STATUS_IN_SCOPE_NO_DATA
    assert by_id["C"]["layers"]["layer3"]["status"] == COVERAGE_STATUS_NOT_IN_SCOPE
    assert by_id["E"]["layers"]["layer1"]["status"] == COVERAGE_STATUS_IN_SCOPE_NO_DATA


def test_report_context_writer_and_deterministic_reports_expose_coverage(tmp_path):
    project = _coverage_project()
    layer2 = tmp_path / "layer2.jsonl"
    layer3 = tmp_path / "layer3.jsonl"
    layer2.write_text(json.dumps({"product": "B", "check_code": "CRI-01", "status": "OBSERVED"}) + "\n", encoding="utf-8")
    layer3.write_text("", encoding="utf-8")
    final_rows = [_row("A")]

    dialogue = build_dialogue_report_context(project=project, final_rows=final_rows, layer2_records=[], layer3_records=[])
    assert len(dialogue["product_layer_coverage"]) == 5
    writer = build_writer_facing_context(dialogue)
    assert writer["product_layer_coverage"] == dialogue["product_layer_coverage"]
    assert writer["dialogue_analysis"]["product_layer_coverage"] == dialogue["product_layer_coverage"]
    assert "Product × Layer Coverage" in build_dialogue_report(
        project,
        final_rows,
        layer2_records=[{"product": "B", "check_code": "CRI-01", "status": "OBSERVED"}],
        layer3_records=[],
    )

    integrated_context = build_integrated_report_context(project=project, final_rows=final_rows, layer2_path=layer2, layer3_path=layer3)
    assert integrated_context["product_layer_coverage"]
    assert "Not in scope / 未纳入本层评测" in build_integrated_report(project=project, final_rows=final_rows, layer2_path=layer2, layer3_path=layer3)


def test_grounding_validator_checks_product_layer_coverage_claims():
    project = _coverage_project()
    context = build_dialogue_report_context(project=project, final_rows=[], layer2_records=[], layer3_records=[])
    assert validate_grounding(draft_report="Product B Layer 1 was not included.", context=context)["overall_status"] == "PASS"
    mismatch = validate_grounding(draft_report="Product B Layer 1 data are missing.", context=context)
    assert mismatch["overall_status"] == "FAIL"
    assert "COVERAGE_STATUS_MISMATCH" in mismatch["issues"][0]["issue_types"]
    assert validate_grounding(draft_report="Product E Layer 1 data are missing.", context=context)["overall_status"] == "PASS"
    mixed = validate_grounding(
        draft_report="Product B Layer 1 was not included. Product E Layer 1 data are missing.",
        context=context,
    )
    assert mixed["overall_status"] == "PASS"
