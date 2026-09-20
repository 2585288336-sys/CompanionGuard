from __future__ import annotations

import json
from pathlib import Path

import pytest

import companionguard_app.platform_ui as platform_ui
from companionguard_app.projects import PRIMARY_PRODUCT_ROLE, add_project_product, update_project
from companionguard_app.reporting import build_integrated_report_context
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.runtime_workspace import ensure_workspace, get_runtime_context


def _project(project_id: str = "product-fixture", *, products: list[dict] | None = None) -> dict:
    return {
        "project_id": project_id,
        "project_name": "Product Registration Fixture",
        "mode": "BENCHMARK",
        "schema_version": "0.8.2",
        "data_schema_version": "1.0",
        "products": products or [
            {"id": "A", "label": "Product A", "slug": "A", "role": PRIMARY_PRODUCT_ROLE},
            {"id": "B", "label": "Product B", "slug": "B", "role": PRIMARY_PRODUCT_ROLE},
            {"id": "C", "label": "Product C", "slug": "C", "role": PRIMARY_PRODUCT_ROLE},
        ],
    }


def _write_project(tmp_path, project: dict) -> None:
    root = tmp_path / "projects" / project["project_id"]
    root.mkdir(parents=True)
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")


def test_add_project_product_is_add_only_and_rejects_invalid_identity():
    project = _project()
    updated = add_project_product(project, product_id=" D ", display_name="Product Delta", role=PRIMARY_PRODUCT_ROLE)

    assert [item["id"] for item in project["products"]] == ["A", "B", "C"]
    assert updated["products"][-1] == {
        "id": "D", "label": "Product Delta", "slug": "D", "role": PRIMARY_PRODUCT_ROLE,
    }

    with pytest.raises(ValueError, match="already exists"):
        add_project_product(project, product_id="A", display_name="Another A", role=PRIMARY_PRODUCT_ROLE)
    with pytest.raises(ValueError, match="path component"):
        add_project_product(project, product_id="Product D/escape", display_name="D", role=PRIMARY_PRODUCT_ROLE)
    with pytest.raises(ValueError, match="display_name"):
        add_project_product(project, product_id="D", display_name=" ", role=PRIMARY_PRODUCT_ROLE)


def test_new_project_defaults_are_empty_and_product_combinations_are_explicit():
    configured = [
        {"id": "MoMood", "label": "MoMood", "slug": "MoMood", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "Xingye", "label": "星野", "slug": "Xingye", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "Doubao", "label": "豆包", "slug": "Doubao", "role": PRIMARY_PRODUCT_ROLE},
    ]

    assert platform_ui._new_project_default_product_ids() == []
    assert [item["id"] for item in platform_ui._build_new_project_products(configured, ["MoMood"], "")] == ["MoMood"]
    assert [item["id"] for item in platform_ui._build_new_project_products(configured, ["Xingye", "Doubao"], "")] == ["Xingye", "Doubao"]
    assert [item["id"] for item in platform_ui._build_new_project_products(configured, [], "Character.AI")] == ["Character.AI"]
    assert [item["id"] for item in platform_ui._build_new_project_products(configured, ["MoMood"], "Character.AI")] == ["MoMood", "Character.AI"]


def test_project_design_copy_distinguishes_create_and_current_project_sections():
    source = Path(platform_ui.__file__).read_text(encoding="utf-8")
    for expected in (
        "选择评测产品 / Select evaluated products",
        "添加其他评测产品（每行一个） / Add other evaluated products",
        "当前项目评测产品 / Evaluated products in this project",
        "添加评测产品到当前项目 / Add evaluated product to this project",
    ):
        assert expected in source
    assert "预配置产品 / Configured products" not in source
    assert "默认评测产品" not in source


def test_product_registration_lazy_creates_workspace_and_preserves_published(tmp_path):
    project = _project()
    _write_project(tmp_path, project)
    state = {}

    updated = add_project_product(project, product_id="D", display_name="Product Delta", role=PRIMARY_PRODUCT_ROLE)
    context = ensure_workspace(project["project_id"], state=state, data_root=tmp_path)
    saved = update_project(updated, scope=RuntimeScope.WORKSPACE, workspace_root=context.paths.root, data_root=tmp_path)

    published = json.loads((tmp_path / "projects" / project["project_id"] / "project.json").read_text(encoding="utf-8"))
    workspace = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    assert context.scope is RuntimeScope.WORKSPACE
    assert [item["id"] for item in published["products"]] == ["A", "B", "C"]
    assert [item["id"] for item in workspace["products"]] == ["A", "B", "C", "D"]
    assert saved["products"][-1]["label"] == "Product Delta"
    assert get_runtime_context(project["project_id"], state=state, data_root=tmp_path).scope is RuntimeScope.WORKSPACE
    assert platform_ui._project_product_names(workspace) == ["Product A", "Product B", "Product C", "Product Delta"]
    assert "Product Delta" in platform_ui.layer3_product_names(workspace)


def test_product_registration_preserves_different_layer_coverage(tmp_path):
    products = [
        {"id": "A", "label": "A", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "B", "label": "B", "role": "Comparison product"},
        {"id": "C", "label": "C", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "D", "label": "D", "role": PRIMARY_PRODUCT_ROLE},
        {"id": "E", "label": "E", "role": "Comparison product"},
    ]
    project = _project(products=products)
    l2 = tmp_path / "layer2.jsonl"
    l3 = tmp_path / "layer3.jsonl"
    l2.write_text(json.dumps({"product": "D", "check_code": "L2-01", "status": "OBSERVED"}) + "\n", encoding="utf-8")
    l3.write_text(json.dumps({"product": "D", "check_code": "L3-01", "status": "DOCUMENTED"}) + "\n", encoding="utf-8")
    final_rows = [
        {
            "case_id": f"case-{product}", "phase": "FORMAL", "final_case_validity": "VALID",
            "adjudication_status": "REVIEWED", "product": product, "criterion_id": "C1",
            "module": "fixture", "condition": "C0", "final_label": "NO_FINDING",
            "analysis_label": "NO_FINDING", "human_label": "NO_FINDING", "auto_label": "NO_FINDING",
        }
        for product in ("A", "B", "C")
    ]

    context = build_integrated_report_context(project=project, final_rows=final_rows, layer2_path=l2, layer3_path=l3)

    assert len(platform_ui._project_product_names(project)) == 5
    assert platform_ui.layer3_product_names(project) == ["A", "C", "D"]
    assert set(context["dialogue"]["products"]) == {"A", "B", "C", "D", "E"}
    assert context["dialogue"]["products"]["D"]["formal_cases"] == 0
    assert context["layer2_product_safeguards"][0]["product"] == "D"
