from __future__ import annotations

import json
import shutil

import pytest

import companionguard_app.deployment as deployment
from companionguard_app.deployment import ensure_deployment_project, verify_published_runtime_integrity
from companionguard_app.publishing import build_deployment_manifest, validate_authoritative_source

from test_publishing import PROJECT_ID, _authoritative, _tree_hash


def _seed_from_source(tmp_path, source, version):
    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)
    manifest = build_deployment_manifest(validation, published_version=version, published_at="2026-09-18T00:00:00+00:00")
    seed = tmp_path / "data" / "deployment_seed" / PROJECT_ID
    seed.mkdir(parents=True, exist_ok=True)
    for relative in validation.files:
        destination = seed / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    (seed / "deployment_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return seed, manifest


def test_versioned_seed_initializes_runtime_with_runtime_only_metadata(tmp_path):
    source = _authoritative(tmp_path)
    seed, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)

    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    assert json.loads((runtime / ".published_runtime_manifest.json").read_text())[
        "published_version"
    ] == manifest["published_version"]
    assert not (runtime / "deployment_manifest.json").exists()
    assert _tree_hash(seed) != _tree_hash(runtime)
    assert (runtime / "project.json").read_bytes() == (seed / "project.json").read_bytes()
    assert verify_published_runtime_integrity(runtime, manifest)["valid"] is True


def test_same_version_is_noop_and_changed_version_refreshes_only_published_runtime(tmp_path):
    source_v1 = _authoritative(tmp_path / "v1")
    seed, _ = _seed_from_source(tmp_path, source_v1, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    assert not ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert not (runtime / "runtime-note.txt").exists()

    (runtime / "runtime-note.txt").write_text("unexpected project artifact", encoding="utf-8")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert not (runtime / "runtime-note.txt").exists()

    workspace = tmp_path / "data" / "runtime_sessions" / "session-1" / "projects" / "sandbox-1"
    workspace.mkdir(parents=True)
    (workspace / "workspace.txt").write_text("do not touch", encoding="utf-8")
    workspace_hash = _tree_hash(workspace)

    source_v2 = _authoritative(tmp_path / "v2")
    (source_v2 / "raw_cases.jsonl").write_text('{"case_id":"case-2"}\n', encoding="utf-8")
    seed_v2, _ = _seed_from_source(tmp_path / "next", source_v2, "2026.09.18-02")
    for child in seed_v2.iterdir():
        target = seed / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert b"case-2" in (runtime / "raw_cases.jsonl").read_bytes()
    assert _tree_hash(workspace) == workspace_hash


def test_same_version_modified_file_is_detected_and_repaired(tmp_path):
    source = _authoritative(tmp_path)
    seed, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    (runtime / "raw_cases.jsonl").write_text('{"case_id":"corrupted"}\n', encoding="utf-8")

    result = verify_published_runtime_integrity(runtime, manifest)
    assert result["valid"] is False
    assert result["modified_files"] == ["raw_cases.jsonl"]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert (runtime / "raw_cases.jsonl").read_bytes() == (seed / "raw_cases.jsonl").read_bytes()


def test_same_version_missing_and_truncated_evidence_are_repaired(tmp_path):
    source = _authoritative(tmp_path)
    seed, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    evidence = runtime / "evidence" / "dialogue" / "screen.png"
    evidence.write_bytes(b"truncated")

    result = verify_published_runtime_integrity(runtime, manifest)
    assert result["valid"] is False
    assert result["modified_files"] == ["evidence/dialogue/screen.png"]
    evidence.unlink()
    result = verify_published_runtime_integrity(runtime, manifest)
    assert result["valid"] is False
    assert result["missing_files"] == ["evidence/dialogue/screen.png"]

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert evidence.read_bytes() == (seed / "evidence" / "dialogue" / "screen.png").read_bytes()


@pytest.mark.parametrize("metadata_mutation", ["missing", "malformed", "wrong_version", "wrong_hash"])
def test_bad_runtime_metadata_refreshes_from_healthy_seed(tmp_path, metadata_mutation):
    source = _authoritative(tmp_path)
    seed, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    metadata = runtime / ".published_runtime_manifest.json"
    if metadata_mutation == "missing":
        metadata.unlink()
    elif metadata_mutation == "malformed":
        metadata.write_text("not json", encoding="utf-8")
    else:
        value = json.loads(metadata.read_text(encoding="utf-8"))
        value["published_version"] = "wrong" if metadata_mutation == "wrong_version" else value["published_version"]
        value["source_snapshot_hash"] = "wrong" if metadata_mutation == "wrong_hash" else value["source_snapshot_hash"]
        metadata.write_text(json.dumps(value), encoding="utf-8")

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert json.loads(metadata.read_text(encoding="utf-8"))["published_version"] == manifest["published_version"]
    assert verify_published_runtime_integrity(runtime, manifest)["valid"] is True


def test_runtime_metadata_is_allowed_but_unknown_project_files_trigger_refresh(tmp_path):
    source = _authoritative(tmp_path)
    _, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    (runtime / ".published_runtime_manifest.json").write_text(
        (runtime / ".published_runtime_manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (runtime / "unknown-artifact.txt").write_text("unexpected", encoding="utf-8")

    result = verify_published_runtime_integrity(runtime, manifest)
    assert result["valid"] is False
    assert result["unexpected_files"] == ["unknown-artifact.txt"]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert not (runtime / "unknown-artifact.txt").exists()


@pytest.mark.parametrize("corruption", ["missing", "hash", "malformed"])
def test_corrupted_seed_never_overwrites_healthy_runtime(tmp_path, corruption):
    source = _authoritative(tmp_path)
    seed, _ = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    before = _tree_hash(runtime)

    if corruption == "missing":
        (seed / "raw_cases.jsonl").unlink()
    elif corruption == "hash":
        (seed / "raw_cases.jsonl").write_text('{"case_id":"bad-seed"}\n', encoding="utf-8")
    else:
        (seed / "deployment_manifest.json").write_text("not json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="deployment seed"):
        ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert _tree_hash(runtime) == before


def test_workspace_is_untouched_by_published_integrity_refresh(tmp_path):
    source = _authoritative(tmp_path)
    seed, manifest = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    workspace = tmp_path / "data" / "runtime_sessions" / "session-a" / "projects" / "sandbox-a"
    workspace.mkdir(parents=True)
    (workspace / "workspace.txt").write_text("keep", encoding="utf-8")
    before = _tree_hash(workspace)
    (runtime / "raw_cases.jsonl").write_text("corrupted\n", encoding="utf-8")

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert _tree_hash(workspace) == before
    assert (runtime / "raw_cases.jsonl").read_bytes() == (seed / "raw_cases.jsonl").read_bytes()


def test_failed_versioned_refresh_leaves_previous_runtime_intact(tmp_path, monkeypatch):
    source = _authoritative(tmp_path)
    seed, _ = _seed_from_source(tmp_path, source, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    before = _tree_hash(runtime)

    source_v2 = _authoritative(tmp_path / "v2")
    (source_v2 / "raw_cases.jsonl").write_text('{"case_id":"changed"}\n', encoding="utf-8")
    seed_v2, _ = _seed_from_source(tmp_path / "next", source_v2, "2026.09.18-02")
    for child in seed_v2.iterdir():
        target = seed / child.name
        if child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)

    def fail_copy(*args, **kwargs):
        raise OSError("simulated refresh failure")

    monkeypatch.setattr(deployment, "_copy_file_stream", fail_copy)
    with pytest.raises(RuntimeError, match="refresh"):
        ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert _tree_hash(runtime) == before
