import hashlib
import json
import shutil
from pathlib import Path

import pytest

from companionguard_app.deployment import ensure_deployment_project
from companionguard_app.publishing import (
    PublishingError,
    build_deployment_manifest,
    load_deployment_manifest,
    validate_authoritative_source,
    verify_manifest_content,
)


LEGACY_SEED_FILES = {
    "project.json",
    "raw_cases.jsonl",
    "collection_sessions.jsonl",
    "collection_queues.jsonl",
    "judge_results.jsonl",
    "human_adjudication.csv",
    "final_results.csv",
    "test_plans.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_versioned_seed(tmp_path: Path) -> tuple[Path, dict]:
    project_id = "versioned-project"
    source = tmp_path / "authoritative" / project_id
    source.mkdir(parents=True)
    (source / "project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "schema_version": "0.8.2",
                "data_schema_version": "1.0",
            }
        ),
        encoding="utf-8",
    )
    for filename in ("raw_cases.jsonl", "collection_sessions.jsonl", "collection_queues.jsonl", "judge_results.jsonl"):
        (source / filename).write_text("{\"record\": true}\n", encoding="utf-8")
    for filename in ("human_adjudication.csv", "final_results.csv"):
        (source / filename).write_text("id\n", encoding="utf-8")
    (source / "test_plans.json").write_text("[]\n", encoding="utf-8")

    validation = validate_authoritative_source(source, expected_project_id=project_id)
    manifest = build_deployment_manifest(
        validation,
        published_version="2026.09.19-test",
        published_at="2026-09-19T00:00:00+00:00",
    )
    seed = tmp_path / "data" / "deployment_seed" / project_id
    seed.mkdir(parents=True)
    for relative in validation.files:
        destination = seed / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    (seed / "deployment_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return seed, manifest


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
    manifest_path = root / "deployment_manifest.json"
    if not manifest_path.exists():
        assert {path.name for path in root.iterdir()} == LEGACY_SEED_FILES
        return

    manifest = load_deployment_manifest(root)
    assert manifest is not None
    assert manifest["published_version"]
    assert manifest["project_id"] == root.name
    assert manifest["source_type"] == "AUTHORITATIVE"
    assert manifest["files"]
    verify_manifest_content(root, manifest)

    actual_project_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "deployment_manifest.json"
    }
    assert actual_project_files == set(manifest["files"])
    assert all(not path.is_symlink() for path in root.rglob("*"))
    assert len(actual_project_files) == 104
    assert sum(path.startswith("evidence/") for path in actual_project_files) == 87
    assert sum(path.startswith("reports/") for path in actual_project_files) == 9
    assert not any(path.startswith("layer2") for path in actual_project_files)
    assert not any(path.startswith("layer3") for path in actual_project_files)


def test_versioned_seed_rejects_unknown_artifact(tmp_path):
    seed, manifest = _make_versioned_seed(tmp_path)
    (seed / "unexpected_file.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(PublishingError, match="inventory"):
        verify_manifest_content(seed, manifest)


def test_versioned_seed_rejects_missing_declared_artifact(tmp_path):
    seed, manifest = _make_versioned_seed(tmp_path)
    declared = next(iter(manifest["files"]))
    (seed / declared).unlink()

    with pytest.raises(PublishingError, match="inventory"):
        verify_manifest_content(seed, manifest)


def test_versioned_seed_rejects_hash_mismatch(tmp_path):
    seed, manifest = _make_versioned_seed(tmp_path)
    target = seed / "project.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(PublishingError, match="hash mismatch"):
        verify_manifest_content(seed, manifest)


def test_manifestless_legacy_seed_contract_remains_supported(tmp_path):
    root = tmp_path / "data" / "deployment_seed" / "legacy-project"
    root.mkdir(parents=True)
    for filename in LEGACY_SEED_FILES:
        (root / filename).write_text("{}\n", encoding="utf-8")

    assert not (root / "deployment_manifest.json").exists()
    assert {path.name for path in root.iterdir()} == LEGACY_SEED_FILES
