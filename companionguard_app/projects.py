from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, PROJECT_ROOT

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
) -> dict[str, Any]:
    pid = safe_slug(project_id)
    if not name.strip():
        raise ValueError("Project name cannot be empty.")
    if not products:
        raise ValueError("At least one product is required.")
    paths = project_paths(pid)
    if paths.manifest.exists():
        raise ValueError(f"Project already exists: {pid}")
    paths.root.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    project = {
        "project_id": pid,
        "project_name": name.strip(),
        "mode": mode,
        "products": products,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
        "schema_version": "0.7.0",
    }
    paths.manifest.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.reports.mkdir(parents=True, exist_ok=True)
    return project


def update_project(project: dict[str, Any]) -> dict[str, Any]:
    pid = project.get("project_id")
    if not pid:
        raise ValueError("project_id is required")
    updated = dict(project)
    updated["updated_at"] = utc_now_iso()
    paths = project_paths(str(pid))
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.manifest.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    return updated


def relative_project_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
