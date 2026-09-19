from __future__ import annotations

import hashlib
import json
import shutil

import pytest

import companionguard_app.publishing as publishing
from companionguard_app.publishing import (
    DuplicatePublishedVersionError,
    PublishingError,
    build_deployment_manifest,
    build_publish_diff,
    publish_snapshot,
    validate_authoritative_source,
    validate_published_version,
)


PROJECT_ID = "published-project"


def _write_jsonl(path, value):
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _authoritative(tmp_path, project_id=PROJECT_ID):
    root = tmp_path / "authoritative" / project_id
    (root / "evidence" / "dialogue").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "project.json").write_text(
        json.dumps({"project_id": project_id, "schema_version": "0.8.2", "data_schema_version": "1.0"}),
        encoding="utf-8",
    )
    for name in ("raw_cases.jsonl", "collection_sessions.jsonl", "collection_queues.jsonl", "judge_results.jsonl"):
        _write_jsonl(root / name, {"case_id": "case-1", "value": name})
    for name in ("human_adjudication.csv", "final_results.csv"):
        (root / name).write_text("case_id,label\ncase-1,FINDING\n", encoding="utf-8")
    (root / "test_plans.json").write_text(json.dumps([{"plan_id": "plan-1"}, {"plan_id": "plan-2"}]), encoding="utf-8")
    (root / "evidence" / "dialogue" / "screen.png").write_bytes(b"evidence")
    (root / "evidence" / "dialogue" / "nested" / "secondary.jpg").parent.mkdir(parents=True)
    (root / "evidence" / "dialogue" / "nested" / "secondary.jpg").write_bytes(b"nested evidence")
    (root / "reports" / "report.md").write_text("report", encoding="utf-8")
    return root


def _tree_hash(root):
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_valid_authoritative_source_and_manifest_are_content_hashed(tmp_path):
    source = _authoritative(tmp_path)
    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)
    manifest = build_deployment_manifest(validation, published_version="2026.09.18-01", published_at="2026-09-18T00:00:00+00:00")

    assert validation.project_id == PROJECT_ID
    assert manifest["source_type"] == "AUTHORITATIVE"
    assert manifest["file_count"] == len(validation.files)
    assert manifest["total_bytes"] == validation.total_bytes
    assert "source_path" not in json.dumps(manifest)
    assert "/" not in str(manifest["source_snapshot_hash"])
    assert manifest["files"]["evidence/dialogue/screen.png"]["bytes"] == len(b"evidence")
    assert validation.record_summary == {
        "raw_cases": 1,
        "judge_results": 1,
        "collection_sessions": 1,
        "collection_queues": 1,
        "human_adjudication": 1,
        "final_results": 1,
        "test_plans": 2,
        "evidence": 2,
        "reports": 1,
        "layer2": 0,
        "layer3": 0,
    }


def test_record_summary_counts_validated_inventory_and_nested_artifacts(tmp_path):
    source = _authoritative(tmp_path)
    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    inventory_evidence = sum(path.startswith("evidence/") for path in validation.files)
    inventory_reports = sum(path.startswith("reports/") for path in validation.files)
    assert validation.record_summary["evidence"] == inventory_evidence == 2
    assert validation.record_summary["reports"] == inventory_reports == 1
    assert validation.record_summary["test_plans"] == 2


def test_optional_artifact_summary_is_zero_when_directories_absent_and_plans_empty(tmp_path):
    source = _authoritative(tmp_path)
    shutil.rmtree(source / "evidence")
    shutil.rmtree(source / "reports")
    (source / "test_plans.json").write_text("[]", encoding="utf-8")

    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    assert validation.record_summary["evidence"] == 0
    assert validation.record_summary["reports"] == 0
    assert validation.record_summary["test_plans"] == 0


@pytest.mark.parametrize("bad", ["", " ", "../v1", "v/1", "/tmp/v1", "v..1"])
def test_published_version_must_be_explicit_and_safe(bad):
    with pytest.raises(PublishingError):
        validate_published_version(bad)


def test_source_validation_rejects_missing_mismatch_workspace_secret_and_symlink(tmp_path):
    source = _authoritative(tmp_path)
    (source / "judge_results.jsonl").unlink()
    with pytest.raises(PublishingError, match="missing required"):
        validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    source = _authoritative(tmp_path / "mismatch", project_id="other")
    with pytest.raises(PublishingError, match="does not match"):
        validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    workspace = _authoritative(tmp_path / "workspace")
    (workspace / ".workspace_manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PublishingError, match="Workspace"):
        validate_authoritative_source(workspace, expected_project_id=PROJECT_ID)

    secret_source = _authoritative(tmp_path / "secret")
    (secret_source / "credentials.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PublishingError, match="secret-like"):
        validate_authoritative_source(secret_source, expected_project_id=PROJECT_ID)

    symlink_source = _authoritative(tmp_path / "symlink")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (symlink_source / "evidence" / "dialogue" / "escape.txt").symlink_to(outside)
    with pytest.raises(PublishingError, match="Symlink"):
        validate_authoritative_source(symlink_source, expected_project_id=PROJECT_ID)


def test_workspace_scope_and_runtime_session_sources_are_rejected(tmp_path):
    source = _authoritative(tmp_path / "data" / "runtime_sessions" / "session" / "projects")
    with pytest.raises(PublishingError, match="Workspace"):
        validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    with pytest.raises(PublishingError, match="WORKSPACE"):
        validate_authoritative_source(source, expected_project_id=PROJECT_ID, source_scope="WORKSPACE")


def test_publish_diff_reports_added_modified_removed_and_unchanged(tmp_path):
    source = _authoritative(tmp_path / "new")
    current = tmp_path / "published" / PROJECT_ID
    current.mkdir(parents=True)
    shutil.copy2(source / "project.json", current / "project.json")
    shutil.copy2(source / "raw_cases.jsonl", current / "raw_cases.jsonl")
    (current / "raw_cases.jsonl").write_text('{"case_id":"old"}\n', encoding="utf-8")
    (current / "old.txt").write_text("removed", encoding="utf-8")
    (source / "added.txt").write_text("added", encoding="utf-8")
    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)

    diff = build_publish_diff(current, validation)
    assert "added.txt" in diff.added
    assert "raw_cases.jsonl" in diff.modified
    assert "old.txt" in diff.removed
    assert "project.json" in diff.unchanged
    assert diff.removed_count == 1


def test_dry_run_does_not_write_source_seed_runtime_or_workspace(tmp_path):
    source = _authoritative(tmp_path)
    source_hash = _tree_hash(source)
    destination_root = tmp_path / "deployment_seed"
    plan = publish_snapshot(source, project_id=PROJECT_ID, published_version="2026.09.18-01", destination_root=destination_root)

    assert not plan.published
    assert not (destination_root / PROJECT_ID).exists()
    assert not (tmp_path / "runtime_sessions").exists()
    assert _tree_hash(source) == source_hash


def test_explicit_publish_promotes_fixture_and_same_version_is_rejected(tmp_path):
    source = _authoritative(tmp_path)
    destination_root = tmp_path / "deployment_seed"
    first = publish_snapshot(source, project_id=PROJECT_ID, published_version="2026.09.18-01", destination_root=destination_root, confirm_publish=True)

    assert first.published
    assert (destination_root / PROJECT_ID / "deployment_manifest.json").is_file()
    with pytest.raises(DuplicatePublishedVersionError):
        publish_snapshot(source, project_id=PROJECT_ID, published_version="2026.09.18-01", destination_root=destination_root, confirm_publish=True)


def test_failed_staging_leaves_existing_published_destination_intact(tmp_path, monkeypatch):
    source = _authoritative(tmp_path)
    destination_root = tmp_path / "deployment_seed"
    publish_snapshot(source, project_id=PROJECT_ID, published_version="2026.09.18-01", destination_root=destination_root, confirm_publish=True)
    destination = destination_root / PROJECT_ID
    before = _tree_hash(destination)

    original = publishing._copy_file_stream

    def fail_on_copy(source_path, destination_path):
        if destination_path.name == "raw_cases.jsonl":
            raise OSError("simulated copy failure")
        original(source_path, destination_path)

    monkeypatch.setattr(publishing, "_copy_file_stream", fail_on_copy)
    with pytest.raises(OSError):
        publish_snapshot(source, project_id=PROJECT_ID, published_version="2026.09.18-02", destination_root=destination_root, confirm_publish=True)
    assert _tree_hash(destination) == before
    assert not list((destination_root / ".staging").glob("*"))
