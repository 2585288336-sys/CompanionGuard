from __future__ import annotations

import csv
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adjudication import FULL_ADJUDICATION, RANDOM_SAMPLE, SAMPLED_ADJUDICATION, STRATIFIED_SAMPLE
from .config import DATA_DIR, PROJECT_ROOT
from .runtime_scope import RuntimeScope, assert_writable_scope, assert_writable_target, resolve_project_root, validate_scope_id
from .versioning import APP_VERSION, DATA_SCHEMA_VERSION, current_code_commit

PROJECTS_DIR = DATA_DIR / "projects"
PRIMARY_PRODUCT_ROLE = "Primary anthropomorphic AI product"
_PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EVALUATION_LAYER_ORDER = ("layer1", "layer2", "layer3")
EVALUATION_LAYER_SET = frozenset(EVALUATION_LAYER_ORDER)


def normalize_evaluation_layers(
    value: Any,
    *,
    allow_empty: bool = False,
) -> list[str]:
    """Normalize the single canonical per-product layer coverage field."""

    if not isinstance(value, (list, tuple, set)):
        raise ValueError("evaluation_layers must be a list of layer1, layer2, layer3")
    requested = {str(item).strip().lower() for item in value}
    unknown = sorted(requested - EVALUATION_LAYER_SET)
    if unknown:
        raise ValueError("Unknown evaluation layer(s): " + ", ".join(unknown))
    if not requested and not allow_empty:
        raise ValueError("At least one evaluation layer is required")
    return [layer for layer in EVALUATION_LAYER_ORDER if layer in requested]


def legacy_evaluation_layers(project: dict[str, Any], product: dict[str, Any]) -> list[str]:
    """Return the effective coverage of a pre-coverage project manifest."""

    if project.get("mode") != "BENCHMARK":
        return list(EVALUATION_LAYER_ORDER)
    if str(product.get("role") or "").startswith(PRIMARY_PRODUCT_ROLE):
        return list(EVALUATION_LAYER_ORDER)
    return ["layer1", "layer2"]


def effective_evaluation_layers(project: dict[str, Any], product: dict[str, Any]) -> list[str]:
    """Resolve explicit coverage first, then preserve legacy selector behavior."""

    if "evaluation_layers" in product:
        return normalize_evaluation_layers(product["evaluation_layers"])
    return legacy_evaluation_layers(project, product)


def materialize_evaluation_layers(project: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with legacy product coverage made explicit."""

    updated = dict(project)
    updated["products"] = []
    for product in project.get("products") or []:
        item = dict(product)
        item["evaluation_layers"] = effective_evaluation_layers(project, item)
        updated["products"].append(item)
    return updated


def _product_ref_matches(product: dict[str, Any], product_ref: str) -> bool:
    value = str(product_ref or "").strip()
    return value in {
        str(product.get("id") or "").strip(),
        str(product.get("label") or "").strip(),
        str(product.get("name") or "").strip(),
    }


def products_for_layer(project: dict[str, Any], layer: str) -> list[dict[str, Any]]:
    normalized_layer = normalize_evaluation_layers([layer])[0]
    return [
        product
        for product in project.get("products") or []
        if normalized_layer in effective_evaluation_layers(project, product)
    ]


def assert_product_in_layer(project: dict[str, Any], product_ref: str, layer: str) -> None:
    """Reject a product-layer write or collection outside declared scope."""

    normalized_layer = normalize_evaluation_layers([layer])[0]
    product = next(
        (item for item in project.get("products") or [] if _product_ref_matches(item, product_ref)),
        None,
    )
    if product is None or normalized_layer not in effective_evaluation_layers(project, product):
        layer_number = normalized_layer[-1]
        raise ValueError(
            f"Product is not included in Layer {layer_number} evaluation scope. "
            f"/ 该产品未纳入 Layer {layer_number} 评测范围。"
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_slug(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE).strip("-_.")
    return value or "project"


def validate_product_id(value: str) -> str:
    """Return a trimmed, path-safe canonical product identifier."""

    product_id = value.strip() if isinstance(value, str) else ""
    validate_scope_id(product_id, name="product_id")
    if not _PRODUCT_ID_RE.fullmatch(product_id):
        raise ValueError("product_id must use letters, numbers, '.', '_' or '-' only")
    return product_id


def add_project_product(
    project: dict[str, Any],
    *,
    product_id: str,
    display_name: str,
    role: str,
    evaluation_layers: list[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``project`` with one new product appended.

    Product registration is intentionally add-only.  Persistence remains the
    responsibility of ``update_project`` so callers can bind the write to the
    active Workspace scope.
    """

    canonical_id = validate_product_id(product_id)
    label = display_name.strip() if isinstance(display_name, str) else ""
    if not label:
        raise ValueError("display_name is required")
    selected_role = role.strip() if isinstance(role, str) else ""
    materialized = materialize_evaluation_layers(project)
    existing_products = list(materialized.get("products") or [])
    if any(str(item.get("id") or "").strip() == canonical_id for item in existing_products):
        raise ValueError(f"Product ID already exists: {canonical_id}")
    valid_roles = {
        PRIMARY_PRODUCT_ROLE,
        *(str(item.get("role") or "").strip() for item in existing_products if str(item.get("role") or "").strip()),
    }
    if selected_role not in valid_roles:
        raise ValueError("role must use an existing project role or the primary product role")
    updated = dict(project)
    updated["products"] = [
        *existing_products,
        {
            "id": canonical_id,
            "label": label,
            "slug": canonical_id,
            "role": selected_role,
            "evaluation_layers": normalize_evaluation_layers(
                evaluation_layers if evaluation_layers is not None else EVALUATION_LAYER_ORDER
            ),
        },
    ]
    return updated


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


def deduplicate_projects(projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one canonical entry per project_id without deleting any source."""

    by_id: dict[str, dict[str, Any]] = {}
    for project in projects:
        project_id = str(project.get("project_id") or "").strip()
        if not project_id:
            continue
        existing = by_id.get(project_id)
        if existing is None:
            by_id[project_id] = project
            continue
        # If discovery is later extended to include multiple scopes, expose the
        # Published identity before a Workspace copy.  The source files remain
        # untouched; this only chooses the selector/listing representative.
        existing_scope = str(existing.get("scope") or existing.get("source_scope") or "").upper()
        candidate_scope = str(project.get("scope") or project.get("source_scope") or "").upper()
        if existing_scope != "PUBLISHED" and candidate_scope == "PUBLISHED":
            by_id[project_id] = project
    return sorted(by_id.values(), key=lambda row: row.get("created_at", ""), reverse=True)


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
    return deduplicate_projects(rows)


def _count_jsonl_records(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    count += 1
    except (OSError, UnicodeDecodeError):
        return 0
    return count


def _count_csv_records(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
    except (OSError, UnicodeDecodeError, csv.Error):
        return 0
    return max(0, len(rows) - 1) if rows else 0


def _count_plan_records(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return 0
    return sum(1 for item in value if isinstance(item, dict)) if isinstance(value, list) else 0


def _count_regular_files(root: Path) -> int:
    if not root.is_dir() or root.is_symlink():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def project_data_snapshot(paths: ProjectPaths) -> dict[str, int]:
    """Count read-only project artifacts from the supplied active root."""

    return {
        "raw_cases": _count_jsonl_records(paths.raw_cases),
        "judge_results": _count_jsonl_records(paths.judge_results),
        "human_review": _count_csv_records(paths.adjudication),
        "final_results": _count_csv_records(paths.final_results),
        "test_plans": _count_plan_records(paths.test_plans),
        "evidence": _count_regular_files(paths.root / "evidence"),
        "reports": _count_regular_files(paths.reports),
    }


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
    project = materialize_evaluation_layers(project)
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
    updated = materialize_evaluation_layers(project)
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
