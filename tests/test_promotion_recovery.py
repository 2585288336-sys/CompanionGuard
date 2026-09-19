from __future__ import annotations

import json
import shutil

import pytest

import companionguard_app.publishing as publishing
from companionguard_app.deployment import ensure_deployment_project
from companionguard_app.publishing import (
    PublishingError,
    atomic_promote,
    build_deployment_manifest,
    promotion_marker_path,
    recover_interrupted_promotion,
    stage_snapshot,
    validate_authoritative_source,
)

from test_publishing import PROJECT_ID, _authoritative, _tree_hash
from test_versioned_deployment import _seed_from_source


def _prepared_promotion(tmp_path, version="2026.09.18-01", *, destination_root=None):
    source = _authoritative(tmp_path / "source")
    validation = validate_authoritative_source(source, expected_project_id=PROJECT_ID)
    manifest = build_deployment_manifest(validation, published_version=version, published_at="2026-09-18T00:00:00+00:00")
    destination_root = destination_root or (tmp_path / "published")
    destination = destination_root / PROJECT_ID
    staged = stage_snapshot(validation, manifest, staging_root=destination_root / ".staging")
    return validation, manifest, destination, staged


def _fail_after_phase(monkeypatch, phase):
    original = publishing._atomic_write_json

    def fail(path, value):
        if value.get("phase") == phase:
            raise RuntimeError(f"simulated interruption at {phase}")
        original(path, value)

    monkeypatch.setattr(publishing, "_atomic_write_json", fail)


def test_normal_promotion_cleans_marker_and_backup(tmp_path):
    _, manifest, destination, staged = _prepared_promotion(tmp_path)

    atomic_promote(staged, destination, intended_manifest=manifest)

    assert publishing.verify_manifest_content(destination, manifest) is None
    assert not promotion_marker_path(destination).exists()
    assert not list(destination.parent.glob(f".{destination.name}.backup-*"))
    assert not staged.exists()


def test_recovery_restores_last_snapshot_after_old_moved(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )

    before = _tree_hash(destination)
    _fail_after_phase(monkeypatch, "OLD_MOVED")
    with pytest.raises(RuntimeError, match="OLD_MOVED"):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)

    assert not destination.exists()
    assert promotion_marker_path(destination).exists()
    assert recover_interrupted_promotion(destination, intended_manifest=manifest_v2)
    assert _tree_hash(destination) == before
    assert not promotion_marker_path(destination).exists()
    assert not staged_v2.exists()
    assert not list(destination.parent.glob(f".{destination.name}.backup-*"))


def test_recovery_keeps_new_snapshot_after_new_installed(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )
    expected_new = _tree_hash(staged_v2)

    _fail_after_phase(monkeypatch, "NEW_INSTALLED")
    with pytest.raises(RuntimeError, match="NEW_INSTALLED"):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)

    assert recover_interrupted_promotion(destination, intended_manifest=manifest_v2)
    assert _tree_hash(destination) == expected_new
    assert not promotion_marker_path(destination).exists()
    assert not list(destination.parent.glob(f".{destination.name}.backup-*"))


def test_recovery_restores_backup_when_new_destination_is_corrupted(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )
    before = _tree_hash(destination)

    _fail_after_phase(monkeypatch, "OLD_MOVED")
    with pytest.raises(RuntimeError):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)
    backup = next(destination.parent.glob(f".{destination.name}.backup-*"))
    staged_v2.replace(destination)
    (destination / "raw_cases.jsonl").write_text("corrupted\n", encoding="utf-8")

    assert recover_interrupted_promotion(destination, intended_manifest=manifest_v2)
    assert _tree_hash(destination) == before
    assert not promotion_marker_path(destination).exists()


def test_corrupted_backup_fails_closed_and_preserves_transaction(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )

    _fail_after_phase(monkeypatch, "OLD_MOVED")
    with pytest.raises(RuntimeError):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)
    backup = next(destination.parent.glob(f".{destination.name}.backup-*"))
    (backup / "raw_cases.jsonl").write_text("corrupted backup\n", encoding="utf-8")

    with pytest.raises(PublishingError, match="backup snapshot"):
        recover_interrupted_promotion(destination, intended_manifest=manifest_v2)
    assert not destination.exists()
    assert promotion_marker_path(destination).exists()
    assert backup.exists()
    assert staged_v2.exists()


def test_unresolved_transaction_blocks_a_second_promotion(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )

    _fail_after_phase(monkeypatch, "OLD_MOVED")
    with pytest.raises(RuntimeError):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)
    backup = next(destination.parent.glob(f".{destination.name}.backup-*"))
    (backup / "raw_cases.jsonl").write_text("corrupted backup\n", encoding="utf-8")

    _, manifest_v3, _, staged_v3 = _prepared_promotion(
        tmp_path / "v3", "2026.09.18-03", destination_root=destination.parent
    )
    with pytest.raises(PublishingError, match="backup snapshot"):
        atomic_promote(staged_v3, destination, intended_manifest=manifest_v3)
    assert staged_v3.exists()
    assert promotion_marker_path(destination).exists()


def test_stale_phase_marker_is_recovered_from_filesystem_state(tmp_path, monkeypatch):
    _, manifest_v1, destination, staged_v1 = _prepared_promotion(tmp_path / "v1", "2026.09.18-01")
    atomic_promote(staged_v1, destination, intended_manifest=manifest_v1)
    _, manifest_v2, _, staged_v2 = _prepared_promotion(
        tmp_path / "v2", "2026.09.18-02", destination_root=destination.parent
    )

    _fail_after_phase(monkeypatch, "NEW_INSTALLED")
    with pytest.raises(RuntimeError):
        atomic_promote(staged_v2, destination, intended_manifest=manifest_v2)
    backup = next(destination.parent.glob(f".{destination.name}.backup-*"))
    shutil.rmtree(backup)
    marker = json.loads(promotion_marker_path(destination).read_text(encoding="utf-8"))
    marker["phase"] = "PREPARED"
    promotion_marker_path(destination).write_text(json.dumps(marker), encoding="utf-8")

    assert recover_interrupted_promotion(destination, intended_manifest=manifest_v2)
    assert not promotion_marker_path(destination).exists()
    assert not staged_v2.exists()


def test_deployment_initializer_recovers_before_refreshing_runtime(tmp_path, monkeypatch):
    source_v1 = _authoritative(tmp_path / "v1")
    seed, _ = _seed_from_source(tmp_path, source_v1, "2026.09.18-01")
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    runtime = tmp_path / "data" / "projects" / PROJECT_ID

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

    _fail_after_phase(monkeypatch, "OLD_MOVED")
    with pytest.raises(RuntimeError, match="simulated interruption"):
        ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert not runtime.exists()
    assert promotion_marker_path(runtime).exists()

    # The next initializer invocation first restores v1, then performs the
    # normal validated v2 refresh instead of promoting over an unresolved txn.
    monkeypatch.undo()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=tmp_path)
    assert b'"case_id":"case-2"' in (runtime / "raw_cases.jsonl").read_bytes()
    assert not promotion_marker_path(runtime).exists()
