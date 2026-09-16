import hashlib
import json
from pathlib import Path

from companionguard_app.deployment import ensure_deployment_project


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_deployment_seed_is_copied_once_without_overwrite(tmp_path):
    project_id = "demo-project"
    seed = tmp_path / "data" / "deployment_seed" / project_id
    seed.mkdir(parents=True)
    (seed / "project.json").write_text(json.dumps({"project_id": project_id}), encoding="utf-8")
    (seed / "raw_cases.jsonl").write_text('{"case_id":"case-1"}\n', encoding="utf-8")
    seed_hashes = {path.name: _sha256(path) for path in seed.iterdir()}

    assert ensure_deployment_project(project_id=project_id, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / project_id
    assert sorted(path.name for path in runtime.iterdir()) == ["project.json", "raw_cases.jsonl"]
    assert {path.name: _sha256(path) for path in seed.iterdir()} == seed_hashes

    (runtime / "runtime-only.txt").write_text("keep", encoding="utf-8")
    assert not ensure_deployment_project(project_id=project_id, project_root=tmp_path)
    assert (runtime / "runtime-only.txt").read_text(encoding="utf-8") == "keep"
    assert {path.name: _sha256(path) for path in seed.iterdir()} == seed_hashes


def test_deployment_seed_contains_only_reviewed_seed_files():
    root = Path(__file__).resolve().parents[1] / "data" / "deployment_seed" / "CompanionGuard-Formal-Full-Benchmark-2026-09"
    expected = {
        "project.json",
        "raw_cases.jsonl",
        "collection_sessions.jsonl",
        "collection_queues.jsonl",
        "judge_results.jsonl",
        "human_adjudication.csv",
        "final_results.csv",
        "test_plans.json",
    }
    assert {path.name for path in root.iterdir()} == expected
    assert not (root / "evidence").exists()
    assert not (root / "reports").exists()
    assert not (root / "llm_usage.jsonl").exists()
    assert not (root / "snapshot_manifest.json").exists()
