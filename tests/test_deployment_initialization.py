from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import companionguard_app.deployment as deployment
from companionguard_app.deployment import ensure_deployment_project, verify_published_runtime_integrity
from companionguard_app.publishing import _inventory, _snapshot_hash, load_deployment_manifest


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = "CompanionGuard-Formal-Full-Benchmark-2026-09"
COMMITTED_SEED = ROOT / "data" / "deployment_seed" / PROJECT_ID
EXPECTED_VERSION = "2026.09.19-01"
EXPECTED_HASH = "94fd426bdfe6c0f6b3096d6eace5473c010b982f86391f177cd9ad2d4300435b"


def _tree_fingerprint(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _copy_project_artifacts(seed: Path, runtime: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    for source in sorted(seed.rglob("*")):
        relative = source.relative_to(seed)
        if relative.as_posix() == "deployment_manifest.json":
            continue
        destination = runtime / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


@pytest.fixture
def isolated_deployment(tmp_path: Path) -> dict[str, Path]:
    project_root = tmp_path / "project_root"
    seed = project_root / "data" / "deployment_seed" / PROJECT_ID
    shutil.copytree(COMMITTED_SEED, seed)
    runtime = project_root / "data" / "projects" / PROJECT_ID
    workspace = project_root / "data" / "runtime_sessions" / "session-A" / "projects" / "sandbox-A"
    workspace.mkdir(parents=True)
    (workspace / "marker.txt").write_text("workspace must survive", encoding="utf-8")
    return {"seed": seed, "runtime": runtime, "workspace": workspace}


def _manifest(fixture: dict[str, Path]) -> dict:
    manifest = load_deployment_manifest(fixture["seed"])
    assert manifest is not None
    return manifest


def _assert_healthy_runtime(fixture: dict[str, Path]) -> None:
    manifest = _manifest(fixture)
    runtime = fixture["runtime"]
    result = verify_published_runtime_integrity(runtime, manifest)
    assert result["valid"] is True
    assert len(_inventory(runtime, reject_forbidden=False)) == 104
    assert _snapshot_hash(_inventory(runtime, reject_forbidden=False)) == EXPECTED_HASH
    runtime_manifest = json.loads((runtime / ".published_runtime_manifest.json").read_text(encoding="utf-8"))
    assert runtime_manifest["project_id"] == PROJECT_ID
    assert runtime_manifest["published_version"] == EXPECTED_VERSION
    assert runtime_manifest["source_snapshot_hash"] == EXPECTED_HASH
    assert runtime_manifest["content_hash_algorithm"] == "SHA-256"


def _clear_verification_cache() -> None:
    deployment._VERIFIED_RUNTIME_KEYS.clear()


def test_legacy_published_runtime_migrates_to_versioned_runtime(isolated_deployment):
    fixture = isolated_deployment
    _copy_project_artifacts(fixture["seed"], fixture["runtime"])
    assert not (fixture["runtime"] / ".published_runtime_manifest.json").exists()

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=fixture["runtime"].parents[2]) is True

    _assert_healthy_runtime(fixture)
    assert (fixture["runtime"] / ".published_runtime_manifest.json").is_file()
    assert _tree_fingerprint(fixture["workspace"]) == {"marker.txt": hashlib.sha256(b"workspace must survive").hexdigest()}


def test_runtime_absent_is_created_from_versioned_seed(isolated_deployment):
    fixture = isolated_deployment
    assert not fixture["runtime"].exists()

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=fixture["runtime"].parents[2]) is True

    _assert_healthy_runtime(fixture)


def test_second_initialization_is_noop(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    before = _tree_fingerprint(fixture["runtime"])
    manifest_before = (fixture["runtime"] / ".published_runtime_manifest.json").read_bytes()

    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is False
    assert _tree_fingerprint(fixture["runtime"]) == before
    assert (fixture["runtime"] / ".published_runtime_manifest.json").read_bytes() == manifest_before


def test_fresh_process_equivalent_revalidates_healthy_runtime(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    before = _tree_fingerprint(fixture["runtime"])

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is False
    assert _tree_fingerprint(fixture["runtime"]) == before


def test_corrupted_runtime_is_repaired(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    (fixture["runtime"] / "project.json").write_text("corrupted\n", encoding="utf-8")

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    _assert_healthy_runtime(fixture)


def test_missing_runtime_artifact_is_repaired(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    (fixture["runtime"] / "raw_cases.jsonl").unlink()

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    _assert_healthy_runtime(fixture)


def test_unexpected_runtime_artifact_is_removed(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    unexpected = fixture["runtime"] / "unexpected_project_file"
    unexpected.write_text("unexpected", encoding="utf-8")

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    assert not unexpected.exists()
    _assert_healthy_runtime(fixture)


@pytest.mark.parametrize("mutation", ["malformed", "wrong_version"])
def test_malformed_or_wrong_version_runtime_metadata_refreshes(isolated_deployment, mutation):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    metadata = fixture["runtime"] / ".published_runtime_manifest.json"
    if mutation == "malformed":
        metadata.write_text("not json", encoding="utf-8")
    else:
        value = json.loads(metadata.read_text(encoding="utf-8"))
        value["published_version"] = "old-version"
        metadata.write_text(json.dumps(value), encoding="utf-8")

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    _assert_healthy_runtime(fixture)


def test_corrupted_seed_fails_closed_without_overwriting_runtime(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    before = _tree_fingerprint(fixture["runtime"])
    (fixture["seed"] / "project.json").write_text("corrupted seed\n", encoding="utf-8")

    _clear_verification_cache()
    with pytest.raises(RuntimeError, match="deployment seed"):
        ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root)
    assert _tree_fingerprint(fixture["runtime"]) == before
    assert _tree_fingerprint(fixture["workspace"]) == {"marker.txt": hashlib.sha256(b"workspace must survive").hexdigest()}


def test_workspace_is_preserved_during_runtime_repair(isolated_deployment):
    fixture = isolated_deployment
    project_root = fixture["runtime"].parents[2]
    workspace_before = _tree_fingerprint(fixture["workspace"])
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    (fixture["runtime"] / "project.json").write_text("corrupted\n", encoding="utf-8")

    _clear_verification_cache()
    assert ensure_deployment_project(project_id=PROJECT_ID, project_root=project_root) is True
    assert _tree_fingerprint(fixture["workspace"]) == workspace_before


def test_initializer_path_is_used_by_production_entrypoint():
    streamlit_entry = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    golden_ui = (ROOT / "companionguard_app" / "golden_ui.py").read_text(encoding="utf-8")
    assert "run_app()" in streamlit_entry
    assert "ensure_deployment_project()" in golden_ui
