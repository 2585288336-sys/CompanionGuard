from __future__ import annotations

import json
import shutil

import pytest

import companionguard_app.deployment as deployment
from companionguard_app.deployment import ensure_deployment_project
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


def test_same_version_is_noop_and_changed_version_refreshes_only_published_runtime(tmp_path):
    source_v1 = _authoritative(tmp_path / "v1")
    seed, _ = _seed_from_source(tmp_path, source_v1, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID
    (runtime / "runtime-note.txt").write_text("keep on no-op", encoding="utf-8")
    assert not ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert (runtime / "runtime-note.txt").read_text() == "keep on no-op"

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
