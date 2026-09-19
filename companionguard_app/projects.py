from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adjudication import FULL_ADJUDICATION, RANDOM_SAMPLE, SAMPLED_ADJUDICATION, STRATIFIED_SAMPLE
from .config import DATA_DIR, PROJECT_ROOT
from .runtime_scope import RuntimeScope, assert_writable_scope, assert_writable_target, resolve_project_root
from .versioning import APP_VERSION, DATA_SCHEMA_VERSION, current_code_commit

PROJECTS_DIR = DATA_DIR / "projects"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE).strip("-_.")
    return value or "project"


@dataclass(frozen=True)
class ProjectPaths:
    project_id: str
    root: Path
    manifest: Path
    raw_cases: Path
    collection_sessions: Path
    collection_queues: Path
    dialogue_evidence: Path
    judge_results: Path
    adjudication: Path
    final_results: Path
    adjudication_sampling: Path
    layer2_records: Path
    layer2_evidence: Path
    layer3_records: Path
    layer3_evidence: Path
    reports: Path
    test_plans: Path


def project_paths(project_id: str) -> ProjectPaths:
    root = PROJECTS_DIR / safe_slug(project_id)
    return ProjectPaths(
        project_id=project_id,
        root=root,
        manifest=root / "project.json",
        raw_cases=root / "raw_cases.jsonl",
        collection_sessions=root / "collection_sessions.jsonl",
        collection_queues=root / "collection_queues.jsonl",
        dialogue_evidence=root / "evidence" / "dialogue",
        judge_results=root / "judge_results.jsonl",
        adjudication=root / "human_adjudication.csv",
        final_results=root / "final_results.csv",
        adjudication_sampling=root / "adjudication_sampling.json",
        layer2_records=root / "layer2_product_safeguards.jsonl",
        layer2_evidence=root / "evidence" / "layer2",
        layer3_records=root / "layer3_public_evidence.jsonl",
        layer3_evidence=root / "evidence" / "layer3",
        reports=root / "reports",
        test_plans=root / "test_plans.json",
    )


def scoped_project_paths(
    project_id: str,
    *,
    scope: RuntimeScope | str = RuntimeScope.PUBLISHED,
    session_id: str | None = None,
    sandbox_id: str | None = None,
    data_root: Path | None = None,
) -> ProjectPaths:
    """Build project paths for an explicit published or workspace scope.

    The legacy ``project_paths(project_id)`` function above is intentionally
    unchanged.  This helper is the opt-in foundation for future scope-aware
    callers; it only resolves paths and never creates directories or files.
    """

    root = resolve_project_root(
        project_id,
        scope=scope,
        session_id=session_id,
        sandbox_id=sandbox_id,
        data_root=data_root,
    )
    return ProjectPaths(
        project_id=project_id,
        root=root,
        manifest=root / "project.json",
        raw_cases=root / "raw_cases.jsonl",
        collection_sessions=root / "collection_sessions.jsonl",
        collection_queues=root / "collection_queues.jsonl",
        dialogue_evidence=root / "evidence" / "dialogue",
        judge_results=root / "judge_results.jsonl",
        adjudication=root / "human_adjudication.csv",
        final_results=root / "final_results.csv",
        adjudication_sampling=root / "adjudication_sampling.json",
        layer2_records=root / "layer2_product_safeguards.jsonl",
        layer2_evidence=root / "evidence" / "layer2",
        layer3_records=root / "layer3_public_evidence.jsonl",
        layer3_evidence=root / "evidence" / "layer3",
        reports=root / "reports",
        test_plans=root / "test_plans.json",
    )


def _project_paths_at_root(project_id: str, root: Path) -> ProjectPaths:
    return ProjectPaths(
        project_id=project_id,
        root=root,
        manifest=root / "project.json",
        raw_cases=root / "raw_cases.jsonl",
        collection_sessions=root / "collection_sessions.jsonl",
        collection_queues=root / "collection_queues.jsonl",
        dialogue_evidence=root / "evidence" / "dialogue",
        judge_results=root / "judge_results.jsonl",
        adjudication=root / "human_adjudication.csv",
        final_results=root / "final_results.csv",
        adjudication_sampling=root / "adjudication_sampling.json",
        layer2_records=root / "layer2_product_safeguards.jsonl",
        layer2_evidence=root / "evidence" / "layer2",
        layer3_records=root / "layer3_public_evidence.jsonl",
        layer3_evidence=root / "evidence" / "layer3",
        reports=root / "reports",
        test_plans=root / "test_plans.json",
    )


def list_projects() -> list[dict[str, Any]]:
    if not PROJECTS_DIR.exists():
        return []
    rows: list[dict[str, Any]] = []
    for manifest in sorted(PROJECTS_DIR.glob("*/project.json")):
        try:
            obj = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)


def get_project(project_id: str) -> dict[str, Any] | None:
    path = project_paths(project_id).manifest
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return obj if isinstance(obj, dict) else None


def create_project(
    *,
    name: str,
    project_id: str,
    products: list[dict[str, Any]],
    mode: str = "BENCHMARK",
    notes: str = "",
    human_adjudication_policy: str = "FULL_ADJUDICATION",
    human_adjudication_sampling_method: str = "STRATIFIED_SAMPLE",
    human_adjudication_sample_rate: float = 0.25,
    human_adjudication_random_seed: int = 20260915,
    human_adjudication_strata: list[str] | None = None,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    assert_writable_scope(scope)
    pid = safe_slug(project_id)
    if not name.strip():
        raise ValueError("Project name cannot be empty.")
    if not products:
        raise ValueError("At least one product is required.")
    if human_adjudication_policy not in {FULL_ADJUDICATION, SAMPLED_ADJUDICATION}:
        raise ValueError(f"Unsupported human adjudication policy: {human_adjudication_policy}")
    if human_adjudication_sampling_method not in {RANDOM_SAMPLE, STRATIFIED_SAMPLE}:
        raise ValueError(f"Unsupported sampling method: {human_adjudication_sampling_method}")
    if not 0 <= float(human_adjudication_sample_rate) <= 1:
        raise ValueError("Human adjudication sample rate must be between 0 and 1.")
    if workspace_root is None:
        raise ValueError("create_project requires an explicit Workspace root.")
    paths = _project_paths_at_root(pid, Path(workspace_root))
    target_manifest = assert_writable_target(scope, paths.manifest, workspace_root=paths.root, data_root=data_root)
    if target_manifest.exists():
        raise ValueError(f"Project already exists: {pid}")
    target_root = target_manifest.parent
    target_root.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    project = {
        "project_id": pid,
        "project_name": name.strip(),
        "mode": mode,
        "products": products,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
        # Keep the legacy field for readers from v0.8.2 and earlier. The
        # explicit portability metadata below is independent of app version.
        "schema_version": "0.8.2",
        "data_schema_version": DATA_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "code_commit": current_code_commit(PROJECT_ROOT),
        "human_adjudication_policy": human_adjudication_policy,
        "human_adjudication_sampling_method": human_adjudication_sampling_method,
        "human_adjudication_sample_rate": human_adjudication_sample_rate,
        "human_adjudication_random_seed": human_adjudication_random_seed,
        "human_adjudication_strata": human_adjudication_strata or ["product", "criterion_id", "condition"],
    }
    target_manifest.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    assert_writable_target(scope, target_root / "reports", workspace_root=paths.root, data_root=data_root).mkdir(parents=True, exist_ok=True)
    return project


def update_project(
    project: dict[str, Any],
    *,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    assert_writable_scope(scope)
    pid = project.get("project_id")
    if not pid:
        raise ValueError("project_id is required")
    updated = dict(project)
    updated["updated_at"] = utc_now_iso()
    if workspace_root is None:
        raise ValueError("update_project requires an explicit Workspace root.")
    paths = _project_paths_at_root(str(pid), Path(workspace_root))
    target_manifest = assert_writable_target(scope, paths.manifest, workspace_root=paths.root, data_root=data_root)
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    target_manifest.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated



def delete_project(
    project_id: str,
    *,
    scope: RuntimeScope | str | None = None,
    workspace_root: Path | None = None,
    data_root: Path | None = None,
) -> None:
    """Delete only the explicitly supplied current Workspace root."""
    assert_writable_scope(scope)
    if workspace_root is None:
        raise ValueError("delete_project requires an explicit Workspace root.")
    paths = _project_paths_at_root(project_id, Path(workspace_root))
    target_root = assert_writable_target(scope, paths.root, workspace_root=paths.root, data_root=data_root)
    if not target_root.exists():
        raise FileNotFoundError(f"Project does not exist: {project_id}")
    shutil.rmtree(target_root)


def relative_project_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
