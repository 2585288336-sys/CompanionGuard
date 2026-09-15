from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import companionguard_app.projects as projects
from companionguard_app.data_integrity import verify_project_data


class DataIntegrityTests(unittest.TestCase):
    def _write_manifest(self, project_dir: Path, **extra: object) -> None:
        manifest = {
            "project_id": project_dir.name,
            "project_name": "Portability test",
            "mode": "BENCHMARK",
            "products": [{"id": "P", "label": "P", "slug": "P"}],
            **extra,
        }
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "project.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

    def test_current_project_counts_records_and_resolves_both_relative_path_styles(self):
        with tempfile.TemporaryDirectory() as td:
            repository = Path(td) / "repo"
            project_dir = repository / "data" / "projects" / "current"
            self._write_manifest(
                project_dir,
                data_schema_version="1.0",
                app_version="0.8.5",
                code_commit="ea7ab05",
            )
            project_relative = project_dir / "evidence" / "layer2" / "P" / "REG-01"
            repo_relative = project_dir / "evidence" / "dialogue" / "case-1"
            project_relative.mkdir(parents=True)
            repo_relative.mkdir(parents=True)
            (project_relative / "evidence_01.png").write_bytes(b"layer2")
            (repo_relative / "A4_01.png").write_bytes(b"dialogue")

            (project_dir / "raw_cases.jsonl").write_text(
                json.dumps(
                    {
                        "case_id": "case-1",
                        "collection_trace": [
                            {"evidence_files": ["data/projects/current/evidence/dialogue/case-1/A4_01.png"]}
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (project_dir / "layer2_product_safeguards.jsonl").write_text(
                json.dumps({"product": "P", "evidence_files": ["evidence/layer2/P/REG-01/evidence_01.png"]})
                + "\n",
                encoding="utf-8",
            )

            report = verify_project_data(project_dir)

            self.assertTrue(report["ok"])
            self.assertEqual(report["counts"]["raw_cases"], 1)
            self.assertEqual(report["counts"]["layer2_records"], 1)
            self.assertEqual(report["counts"]["evidence_files"], 2)
            self.assertEqual(report["counts"]["evidence_references"], 2)
            self.assertEqual(report["counts"]["missing_evidence_references"], 0)

    def test_legacy_project_remains_readable_with_metadata_warning(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "repo" / "data" / "projects" / "legacy"
            self._write_manifest(project_dir, schema_version="0.8.2")
            report = verify_project_data(project_dir)

            self.assertTrue(report["ok"])
            self.assertTrue(any("data_schema_version" in item for item in report["warnings"]))
            self.assertTrue(any("app_version" in item for item in report["warnings"]))
            self.assertTrue(any("code_commit" in item for item in report["warnings"]))

    def test_missing_or_external_evidence_fails_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td) / "repo" / "data" / "projects" / "broken"
            self._write_manifest(
                project_dir,
                data_schema_version="1.0",
                app_version="0.8.5",
                code_commit="ea7ab05",
            )
            raw_path = project_dir / "raw_cases.jsonl"
            original = json.dumps(
                {
                    "case_id": "broken-1",
                    "collection_trace": [
                        {"evidence_files": ["evidence/missing.png", "../outside.png"]}
                    ],
                }
            )
            raw_path.write_text(original + "\n", encoding="utf-8")

            report = verify_project_data(project_dir)

            self.assertFalse(report["ok"])
            self.assertEqual(report["counts"]["missing_evidence_references"], 2)
            self.assertEqual(raw_path.read_text(encoding="utf-8"), original + "\n")

    def test_new_project_metadata_is_loader_compatible(self):
        with tempfile.TemporaryDirectory() as td:
            projects_root = Path(td) / "projects"
            with patch.object(projects, "PROJECTS_DIR", projects_root):
                created = projects.create_project(
                    name="Metadata test",
                    project_id="metadata-test",
                    products=[{"id": "P", "label": "P", "slug": "P"}],
                )
                loaded = projects.get_project(created["project_id"])

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["data_schema_version"], "1.0")
            self.assertEqual(loaded["app_version"], "0.8.5")
            self.assertRegex(loaded["code_commit"], r"^[0-9a-f]{40}$|^unknown$")


if __name__ == "__main__":
    unittest.main()
