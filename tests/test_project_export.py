from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from companionguard_app.project_export import ProjectExportError, build_project_package
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_app.runtime_workspace import ensure_workspace, get_runtime_context


def _fixture_project(data_root, project_id: str, *, value: str = "official"):
    root = data_root / "projects" / project_id
    (root / "evidence" / "dialogue").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / "project.json").write_text(
        json.dumps({"project_id": project_id, "project_name": "Export Fixture", "schema_version": "1.0"}),
        encoding="utf-8",
    )
    (root / "raw_cases.jsonl").write_text(json.dumps({"case_id": "case-1", "value": value}) + "\n", encoding="utf-8")
    (root / "evidence" / "dialogue" / "screen.png").write_bytes(b"evidence bytes")
    (root / "reports" / "dialogue.md").write_text("report", encoding="utf-8")
    return root


def _archive_files(package_data: bytes):
    archive = zipfile.ZipFile(io.BytesIO(package_data))
    return archive, {name: archive.read(name) for name in archive.namelist()}


def test_published_export_is_read_only_and_contains_existing_project_files(tmp_path):
    source = _fixture_project(tmp_path, "published")
    before = {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
    state = {}
    context = get_runtime_context("published", state=state, data_root=tmp_path)

    package = build_project_package(context)
    archive, members = _archive_files(package.data)
    names = set(archive.namelist())
    prefix = "CompanionGuard-Project-published/"
    manifest = json.loads(members[prefix + "EXPORT_MANIFEST.json"])

    assert context.scope is RuntimeScope.PUBLISHED
    assert not (tmp_path / "runtime_sessions").exists()
    assert package.filename == "CompanionGuard-published-published.zip"
    assert prefix + "project.json" in names
    assert prefix + "evidence/dialogue/screen.png" in names
    assert prefix + "reports/dialogue.md" in names
    assert prefix + "EXPORT_MANIFEST.json" in names
    assert prefix + "SHA256SUMS.txt" in names
    assert prefix + "llm_usage.jsonl" not in names
    assert manifest["export_scope"] == "PUBLISHED"
    assert manifest["source_type"] == "official_published"
    assert manifest["privacy_behavior"].startswith("Project content is exported as-is;")
    assert manifest["file_count"] == len(before)
    assert all("session_id" not in line and "sandbox_id" not in line for line in members[prefix + "EXPORT_MANIFEST.json"].decode().splitlines())
    after = {path.relative_to(source): hashlib.sha256(path.read_bytes()).hexdigest() for path in source.rglob("*") if path.is_file()}
    assert after == before


def test_workspace_export_uses_only_current_workspace_and_excludes_runtime_manifest(tmp_path):
    source = _fixture_project(tmp_path, "published", value="official")
    state = {}
    context = ensure_workspace("published", state=state, data_root=tmp_path)
    context.paths.raw_cases.write_text(json.dumps({"case_id": "case-1", "value": "workspace"}) + "\n", encoding="utf-8")
    context.paths.root.joinpath("llm_usage.jsonl").write_text(
        json.dumps({"role": "integrated_report", "provider": "fake", "model": "fake-model"}) + "\n",
        encoding="utf-8",
    )
    context.paths.adjudication_sampling.write_text(
        json.dumps({"project_id": "published", "selected_case_ids": ["case-1"]}) + "\n",
        encoding="utf-8",
    )
    package = build_project_package(context)
    archive, members = _archive_files(package.data)
    prefix = "CompanionGuard-Project-published/"
    manifest_text = members[prefix + "EXPORT_MANIFEST.json"].decode()

    assert context.scope is RuntimeScope.WORKSPACE
    assert package.filename == "CompanionGuard-published-workspace.zip"
    assert prefix + ".workspace_manifest.json" not in archive.namelist()
    assert b"workspace" in members[prefix + "raw_cases.jsonl"]
    assert b"official" not in members[prefix + "raw_cases.jsonl"]
    assert prefix + "llm_usage.jsonl" in archive.namelist()
    assert prefix + "adjudication_sampling.json" in archive.namelist()
    assert b"fake-model" in members[prefix + "llm_usage.jsonl"]
    assert '"ephemeral_workspace": true' in manifest_text
    assert context.session_id not in manifest_text
    assert context.sandbox_id not in manifest_text
    assert str(tmp_path) not in manifest_text
    assert json.loads((source / "raw_cases.jsonl").read_text(encoding="utf-8"))["value"] == "official"


def test_sampling_plan_is_exported_with_manifest_and_checksum(tmp_path):
    root = _fixture_project(tmp_path, "published")
    sampling = b'{"project_id":"published","selected_case_ids":["case-1"]}\n'
    (root / "adjudication_sampling.json").write_bytes(sampling)

    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    archive, members = _archive_files(package.data)
    prefix = "CompanionGuard-Project-published/"
    relative = prefix + "adjudication_sampling.json"
    manifest = json.loads(members[prefix + "EXPORT_MANIFEST.json"])
    checksums = {
        path: digest
        for digest, path in (line.split("  ", 1) for line in members[prefix + "SHA256SUMS.txt"].decode().splitlines())
    }

    assert relative in archive.namelist()
    data_members = [name for name in archive.namelist() if name not in {prefix + "EXPORT_MANIFEST.json", prefix + "SHA256SUMS.txt"}]
    assert manifest["file_count"] == len(data_members)
    assert checksums[relative] == hashlib.sha256(sampling).hexdigest()


def test_export_succeeds_without_sampling_plan(tmp_path):
    _fixture_project(tmp_path, "published")
    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    archive, _ = _archive_files(package.data)
    assert "CompanionGuard-Project-published/adjudication_sampling.json" not in archive.namelist()


def test_another_session_exports_published_data_not_this_session_workspace(tmp_path):
    _fixture_project(tmp_path, "published", value="official")
    first_state = {}
    first_context = ensure_workspace("published", state=first_state, data_root=tmp_path)
    first_context.paths.raw_cases.write_text(json.dumps({"value": "first-session"}) + "\n", encoding="utf-8")

    second_context = get_runtime_context("published", state={}, data_root=tmp_path)
    package = build_project_package(second_context)
    _, members = _archive_files(package.data)

    assert second_context.scope is RuntimeScope.PUBLISHED
    assert b"official" in members["CompanionGuard-Project-published/raw_cases.jsonl"]
    assert b"first-session" not in members["CompanionGuard-Project-published/raw_cases.jsonl"]
    assert second_context.paths.root != first_context.paths.root


def test_export_checksums_cover_only_project_data(tmp_path):
    _fixture_project(tmp_path, "published")
    state = {}
    package = build_project_package(get_runtime_context("published", state=state, data_root=tmp_path))
    archive, members = _archive_files(package.data)
    prefix = "CompanionGuard-Project-published/"
    manifest = json.loads(members[prefix + "EXPORT_MANIFEST.json"])
    checksum_lines = members[prefix + "SHA256SUMS.txt"].decode().splitlines()
    checksums = {path: digest for digest, path in (line.split("  ", 1) for line in checksum_lines)}

    data_members = [name for name in archive.namelist() if name not in {prefix + "EXPORT_MANIFEST.json", prefix + "SHA256SUMS.txt"}]
    assert len(data_members) == manifest["file_count"] == len(checksums)
    for name in data_members:
        assert checksums[name] == hashlib.sha256(members[name]).hexdigest()
        assert not name.startswith("/")
        assert ".." not in name.split("/")


@pytest.mark.parametrize("filename", [".env", "client.env", "credentials.json", "api_key.txt", ".workspace_manifest.json"])
def test_export_excludes_infrastructure_and_secret_like_files(tmp_path, filename):
    root = _fixture_project(tmp_path, "published")
    (root / filename).write_text("do not export", encoding="utf-8")
    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    archive, _ = _archive_files(package.data)
    assert f"CompanionGuard-Project-published/{filename}" not in archive.namelist()


@pytest.mark.parametrize(
    "relative",
    [
        ".streamlit/secrets.toml",
        "reports/.env",
        "reports/.workspace_manifest.json",
        "temporary/promotion.json",
    ],
)
def test_export_excludes_nested_infrastructure_artifacts(tmp_path, relative):
    root = _fixture_project(tmp_path, "published")
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("infrastructure", encoding="utf-8")

    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    archive, _ = _archive_files(package.data)
    assert f"CompanionGuard-Project-published/{relative}" not in archive.namelist()


def test_unknown_project_artifact_fails_closed(tmp_path):
    root = _fixture_project(tmp_path, "published")
    (root / "unexpected_internal_state.json").write_text("internal", encoding="utf-8")

    with pytest.raises(ProjectExportError, match="Unclassified export artifact: unexpected_internal_state.json"):
        build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("reports/normal.md", "The system should never expose an API key."),
        ("reports/placeholder.md", "DEEPSEEK_API_KEY=<API_KEY>"),
    ],
)
def test_non_credential_text_and_placeholders_are_exportable(tmp_path, filename, content):
    root = _fixture_project(tmp_path, "published")
    (root / filename).write_text(content, encoding="utf-8")

    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    assert package.data


@pytest.mark.parametrize(
    ("filename", "content", "rule"),
    [
        ("reports/secret.md", "DEEPSEEK_API_KEY=<synthetic-non-placeholder-value>", "credential_assignment"),
        ("reports/bearer.md", "Authorization: Bearer synthetic-token-value", "authorization_bearer"),
        ("reports/key.txt", "-----BEGIN PRIVATE KEY-----", "private_key_header"),
        ("adjudication_sampling.json", "DEEPSEEK_API_KEY=synthetic-token-value", "credential_assignment"),
    ],
)
def test_high_confidence_credentials_block_export_without_echoing_value(tmp_path, filename, content, rule):
    root = _fixture_project(tmp_path, "published")
    (root / filename).write_text(content, encoding="utf-8")

    with pytest.raises(ProjectExportError) as error:
        build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))

    message = str(error.value)
    assert rule in message
    assert "synthetic-non-placeholder-value" not in message
    assert "synthetic-token-value" not in message


def test_binary_evidence_is_exported_without_text_scanning(tmp_path):
    root = _fixture_project(tmp_path, "published")
    (root / "evidence" / "dialogue" / "screen.jpg").write_bytes(b"not text")

    package = build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))
    archive, _ = _archive_files(package.data)
    assert "CompanionGuard-Project-published/evidence/dialogue/screen.jpg" in archive.namelist()


def test_export_rejects_symlink_instead_of_building_partial_package(tmp_path):
    root = _fixture_project(tmp_path, "published")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "evidence" / "dialogue" / "outside-link.txt").symlink_to(outside)

    with pytest.raises(ProjectExportError, match="Symlink is not allowed in export") as error:
        build_project_package(get_runtime_context("published", state={}, data_root=tmp_path))

    assert str(tmp_path) not in str(error.value)
