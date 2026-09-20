from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

import companionguard_app.platform_ui as platform_ui
from companionguard_app.projects import PRIMARY_PRODUCT_ROLE, update_project as persist_project
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.runtime_workspace import ensure_workspace


PROJECT_ID = "coverage-rerun-fixture"


class FakeStreamlit:
    def __init__(
        self,
        *,
        submitted: bool = False,
        add_layers: list[str] | None = None,
        save_coverage: bool = False,
        coverage_layers: list[str] | None = None,
        text_values: dict[str, str] | None = None,
    ) -> None:
        self.submitted = submitted
        self.add_layers = add_layers if add_layers is not None else ["layer1", "layer2", "layer3"]
        self.save_coverage = save_coverage
        self.coverage_layers = coverage_layers if coverage_layers is not None else ["layer1", "layer2", "layer3"]
        self.text_values = text_values or {}
        self.multiselect_calls = 0
        self.dataframes: list[Any] = []
        self.errors: list[str] = []
        self.successes: list[str] = []
        self.rerun_calls = 0

    def subheader(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def dataframe(self, data, **_kwargs):
        self.dataframes.append(data)

    def form(self, *_args, **_kwargs):
        return nullcontext()

    def text_input(self, label, **_kwargs):
        return self.text_values.get(label, "")

    def selectbox(self, _label, options, **_kwargs):
        return options[0]

    def multiselect(self, _label, _options, default=None, **_kwargs):
        self.multiselect_calls += 1
        if self.submitted:
            return list(self.add_layers)
        if self.save_coverage and self.multiselect_calls == 2:
            return list(self.coverage_layers)
        return list(default or [])

    def form_submit_button(self, *_args, **_kwargs):
        return self.submitted

    def button(self, label, **_kwargs):
        return self.save_coverage and "保存测试范围" in label

    def markdown(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None

    def error(self, message, **_kwargs):
        self.errors.append(str(message))

    def success(self, message, **_kwargs):
        self.successes.append(str(message))

    def rerun(self):
        self.rerun_calls += 1


def _project(products: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project_id": PROJECT_ID,
        "project_name": "Coverage Rerun Fixture",
        "mode": "BENCHMARK",
        "schema_version": "0.8.2",
        "data_schema_version": "1.0",
        "products": products or [
            {"id": "MoMood", "label": "MoMood", "role": PRIMARY_PRODUCT_ROLE},
            {"id": "Xingye", "label": "星野", "role": PRIMARY_PRODUCT_ROLE},
            {"id": "Doubao", "label": "豆包", "role": PRIMARY_PRODUCT_ROLE},
        ],
    }


def _write_project(tmp_path: Path, project: dict[str, Any]) -> Path:
    root = tmp_path / "projects" / project["project_id"]
    root.mkdir(parents=True)
    (root / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    return root


def _patch_scope(monkeypatch, scope: RuntimeScope):
    monkeypatch.setattr(platform_ui, "active_scope", lambda: scope)


def test_published_browsing_renders_coverage_without_rerun_or_workspace(monkeypatch):
    project = _project()
    fake = FakeStreamlit()
    _patch_scope(monkeypatch, RuntimeScope.PUBLISHED)
    monkeypatch.setattr(platform_ui, "st", fake)
    monkeypatch.setattr(platform_ui, "ensure_active_workspace_for_write", lambda: pytest.fail("Published browsing must not create a Workspace"))

    platform_ui._render_evaluated_products(project)

    assert fake.rerun_calls == 0
    assert fake.errors == []
    assert fake.dataframes
    rows = fake.dataframes[0]
    assert all("Layer 1" in row["测试范围 / Evaluation Layers"] for row in rows)
    assert all("Layer 2" in row["测试范围 / Evaluation Layers"] for row in rows)
    assert all("Layer 3" in row["测试范围 / Evaluation Layers"] for row in rows)
    assert fake.multiselect_calls == 2


def test_published_add_product_creates_workspace_and_reruns_only_after_save(tmp_path, monkeypatch):
    project = _project(products=[{"id": "A", "label": "A", "slug": "a", "role": PRIMARY_PRODUCT_ROLE}])
    published = _write_project(tmp_path, project)
    before = (published / "project.json").read_bytes()
    state: dict[str, Any] = {"active_project_id": PROJECT_ID}
    fake = FakeStreamlit(
        submitted=True,
        add_layers=["layer2", "layer3"],
        text_values={"产品 ID / Product ID": "D", "显示名称 / Display name": "Product D"},
    )
    context_holder: dict[str, Any] = {}
    _patch_scope(monkeypatch, RuntimeScope.PUBLISHED)
    monkeypatch.setattr(platform_ui, "st", fake)
    monkeypatch.setattr(
        platform_ui,
        "ensure_active_workspace_for_write",
        lambda: context_holder.setdefault("context", ensure_workspace(PROJECT_ID, state=state, data_root=tmp_path)),
    )
    monkeypatch.setattr(
        platform_ui,
        "update_project",
        lambda project, **kwargs: persist_project(project, data_root=tmp_path, **kwargs),
    )

    platform_ui._render_evaluated_products(project)

    context = context_holder["context"]
    saved = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    product_d = next(item for item in saved["products"] if item["id"] == "D")
    assert context.scope is RuntimeScope.WORKSPACE
    assert product_d["evaluation_layers"] == ["layer2", "layer3"]
    assert (published / "project.json").read_bytes() == before
    assert fake.rerun_calls == 1


def test_workspace_coverage_update_preserves_identity_and_reruns_after_save(tmp_path, monkeypatch):
    project = _project(products=[{
        "id": "A", "label": "Product A", "slug": "product-a", "role": PRIMARY_PRODUCT_ROLE,
        "evaluation_layers": ["layer1", "layer2", "layer3"],
    }])
    _write_project(tmp_path, project)
    state: dict[str, Any] = {}
    context = ensure_workspace(PROJECT_ID, state=state, data_root=tmp_path)
    workspace_project = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    fake = FakeStreamlit(submitted=False, save_coverage=True, coverage_layers=["layer2", "layer3"])
    _patch_scope(monkeypatch, RuntimeScope.WORKSPACE)
    monkeypatch.setattr(platform_ui, "st", fake)
    monkeypatch.setattr(platform_ui, "ensure_active_workspace_for_write", lambda: context)
    monkeypatch.setattr(
        platform_ui,
        "update_project",
        lambda project, **kwargs: persist_project(project, data_root=tmp_path, **kwargs),
    )

    platform_ui._render_evaluated_products(workspace_project)

    saved = json.loads(context.paths.manifest.read_text(encoding="utf-8"))
    assert saved["products"] == [{
        "id": "A", "label": "Product A", "slug": "product-a", "role": PRIMARY_PRODUCT_ROLE,
        "evaluation_layers": ["layer2", "layer3"],
    }]
    assert fake.rerun_calls == 1


@pytest.mark.parametrize(
    ("text_values", "add_layers"),
    [
        ({"产品 ID / Product ID": "D", "显示名称 / Display name": "Product D"}, []),
        ({"产品 ID / Product ID": "Bad/ID", "显示名称 / Display name": "Bad"}, ["layer1"]),
    ],
)
def test_add_product_validation_failure_does_not_write_or_rerun(monkeypatch, text_values, add_layers):
    project = _project()
    fake = FakeStreamlit(submitted=True, add_layers=add_layers, text_values=text_values)
    _patch_scope(monkeypatch, RuntimeScope.PUBLISHED)
    monkeypatch.setattr(platform_ui, "st", fake)
    monkeypatch.setattr(platform_ui, "ensure_active_workspace_for_write", lambda: pytest.fail("validation failure must not create a Workspace"))

    platform_ui._render_evaluated_products(project)

    assert fake.errors
    assert fake.rerun_calls == 0


def test_add_product_exception_does_not_rerun(monkeypatch):
    project = _project()
    fake = FakeStreamlit(
        submitted=True,
        text_values={"产品 ID / Product ID": "D", "显示名称 / Display name": "Product D"},
    )
    _patch_scope(monkeypatch, RuntimeScope.PUBLISHED)
    monkeypatch.setattr(platform_ui, "st", fake)
    monkeypatch.setattr(platform_ui, "add_project_product", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("expected save error")))
    monkeypatch.setattr(platform_ui, "ensure_active_workspace_for_write", lambda: pytest.fail("save exception must not create a Workspace"))

    platform_ui._render_evaluated_products(project)

    assert fake.errors == ["expected save error"]
    assert fake.rerun_calls == 0
