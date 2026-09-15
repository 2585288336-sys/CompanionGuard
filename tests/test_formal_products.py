from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from companionguard_app.collector import (
    available_conditions,
    build_queue_items_from_selections,
    load_collector_config,
    scenario_ids,
)
from companionguard_app.platform_ui import layer3_product_names
from companionguard_app.projects import get_project
from companionguard_app.reporting import build_integrated_report
from companionguard_judge.pipeline import load_criteria


class FormalProductConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.config = load_collector_config()

    def test_formal_primary_defaults_promote_doubao_and_hide_replika_from_new_defaults(self):
        self.assertEqual(
            self.config["formal_primary_product_ids"], ["MoMood", "Xingye", "Doubao"]
        )
        products = {p["id"]: p for p in self.config["products"]}
        self.assertEqual(
            [products[x]["role"] for x in self.config["formal_primary_product_ids"]],
            ["Primary anthropomorphic AI product"] * 3,
        )
        self.assertTrue(products["Replika"]["legacy_only"])

    def test_full_benchmark_queue_has_equal_coverage_for_all_primary_products(self):
        criteria = load_criteria(self.root / "criteria")
        selections = {
            criterion_id: {
                "scenarios": scenario_ids(criterion),
                "conditions": [c for c in available_conditions(criterion) if c],
            }
            for criterion_id, criterion in criteria.items()
        }
        sizes = {
            product_id: len(
                build_queue_items_from_selections(
                    criteria=criteria,
                    selections=selections,
                    product_slug=product_id,
                    phase="FORMAL",
                    run_numbers=[1],
                )
            )
            for product_id in self.config["formal_primary_product_ids"]
        }
        self.assertEqual(len(set(sizes.values())), 1, sizes)
        self.assertGreater(next(iter(sizes.values())), 0)

    def test_comparator_subset_is_not_bound_to_doubao(self):
        presets = json.loads(
            (self.root / "config" / "test_plan_presets.json").read_text(encoding="utf-8")
        )["presets"]
        subset = next(p for p in presets if p["id"] == "COMPARATOR_SUBSET_V1")
        self.assertNotIn("product", subset)
        self.assertNotIn("product_ids", subset)
        self.assertEqual(subset["coverage_type"], "BENCHMARK_SUBSET")

    def test_layer2_and_layer3_project_scope_include_doubao(self):
        project = {
            "mode": "BENCHMARK",
            "products": [
                {"id": "MoMood", "label": "MoMood", "role": "Primary anthropomorphic AI product"},
                {"id": "Xingye", "label": "星野", "role": "Primary anthropomorphic AI product"},
                {"id": "Doubao", "label": "豆包", "role": "Primary anthropomorphic AI product"},
            ],
        }
        self.assertEqual(layer3_product_names(project), ["MoMood", "星野", "豆包"])
        self.assertEqual(
            [p["label"] for p in project["products"]], ["MoMood", "星野", "豆包"]
        )

    def test_legacy_replika_project_and_report_remain_metadata_driven(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "projects" / "legacy-replika"
            project_dir.mkdir(parents=True)
            manifest = {
                "project_id": "legacy-replika",
                "project_name": "Legacy Replika",
                "mode": "BENCHMARK",
                "products": [{"id": "Replika", "label": "Replika", "slug": "Replika", "role": "Primary anthropomorphic AI product"}],
            }
            (project_dir / "project.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            import companionguard_app.projects as projects

            original = projects.PROJECTS_DIR
            projects.PROJECTS_DIR = Path(td) / "projects"
            try:
                loaded = get_project("legacy-replika")
            finally:
                projects.PROJECTS_DIR = original
            self.assertEqual(loaded["products"][0]["id"], "Replika")
            report = build_integrated_report(
                project=loaded,
                final_rows=[],
                layer2_path=project_dir / "layer2.jsonl",
                layer3_path=project_dir / "layer3.jsonl",
            )
            self.assertIn("Products: Replika", report)
            self.assertNotIn("Products: MoMood, 星野, 豆包", report)


if __name__ == "__main__":
    unittest.main()
