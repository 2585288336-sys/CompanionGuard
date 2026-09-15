from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


JSONL_ARTIFACTS = {
    "raw_cases": "raw_cases.jsonl",
    "collection_sessions": "collection_sessions.jsonl",
    "collection_queues": "collection_queues.jsonl",
    "judge_results": "judge_results.jsonl",
    "layer2_records": "layer2_product_safeguards.jsonl",
    "layer3_records": "layer3_public_evidence.jsonl",
}

CSV_ARTIFACTS = {
    "human_adjudication": "human_adjudication.csv",
    "final_results": "final_results.csv",
}

EVIDENCE_KEYS = frozenset(
    {
        "evidence_files",
        "evidence_file",
        "evidence_path",
        "screenshot_path",
        "screenshot_paths",
    }
)


def _evidence_values(value: Any, location: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        if value.strip():
            yield value.strip(), location
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _evidence_values(item, f"{location}[{index}]")
        return
    if isinstance(value, dict):
        for key in ("path", "file", "stored_path", "relative_path"):
            if key in value:
                yield from _evidence_values(value[key], f"{location}.{key}")


def _evidence_references(value: Any, location: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key in EVIDENCE_KEYS:
                yield from _evidence_values(child, child_location)
            else:
                yield from _evidence_references(child, child_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _evidence_references(child, f"{location}[{index}]")


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str], list[tuple[str, str]]]:
    if not path.exists():
        return [], [], []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    references: list[tuple[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"{path.name}: cannot read file: {exc}"], []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name}:{line_number}: record is not a JSON object")
            continue
        rows.append(value)
        references.extend(_evidence_references(value, f"{path.name}:{line_number}"))
    return rows, errors, references


def _read_csv(path: Path) -> tuple[list[dict[str, Any]], list[str], list[tuple[str, str]]]:
    if not path.exists():
        return [], [], []
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    references: list[tuple[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, 2):
                if row is None:
                    errors.append(f"{path.name}:{row_number}: empty CSV record")
                    continue
                value = dict(row)
                rows.append(value)
                references.extend(_evidence_references(value, f"{path.name}:{row_number}"))
    except (OSError, csv.Error) as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
    return rows, errors, references


def _repository_root(project_dir: Path) -> Path | None:
    if project_dir.parent.name == "projects" and project_dir.parent.parent.name == "data":
        return project_dir.parent.parent.parent
    return None


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_project_evidence(
    project_dir: Path,
    stored_path: str,
    *,
    repository_root: Path | None = None,
) -> tuple[Path | None, str]:
    """Resolve project-relative or repository-relative evidence safely.

    The returned kind is one of ``project-relative``, ``repository-relative``,
    ``absolute``, ``missing`` or ``outside-project``.
    """
    raw = Path(stored_path)
    project_root = project_dir.resolve()
    if raw.is_absolute():
        try:
            resolved = raw.resolve()
        except OSError:
            return None, "missing"
        if not _inside(resolved, project_root):
            return None, "outside-project"
        return (resolved, "absolute") if resolved.is_file() else (None, "missing")

    candidates: list[tuple[Path, str]] = [(project_root / raw, "project-relative")]
    repo_root = (repository_root or _repository_root(project_root))
    if repo_root is not None:
        candidates.append((repo_root.resolve() / raw, "repository-relative"))

    for candidate, kind in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not _inside(resolved, project_root):
            if candidate.exists():
                return None, "outside-project"
            continue
        if resolved.is_file():
            return resolved, kind
    return None, "missing"


def verify_project_data(
    project_dir: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Read-only integrity and portability check for one project directory."""
    root = Path(project_dir).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    references: list[tuple[str, str]] = []
    counts: dict[str, int] = {"project_manifest": 0}
    manifest: dict[str, Any] = {}
    manifest_path = root / "project.json"

    if not root.is_dir():
        errors.append(f"Project directory does not exist: {root}")
    elif not manifest_path.exists():
        errors.append(f"Missing project manifest: {manifest_path.name}")
    else:
        counts["project_manifest"] = 1
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"project.json: cannot read valid JSON: {exc}")
        else:
            if not isinstance(value, dict):
                errors.append("project.json: manifest is not a JSON object")
            else:
                manifest = value

    if manifest:
        if not manifest.get("project_id"):
            warnings.append("project.json has no project_id")
        elif str(manifest["project_id"]) != root.name:
            warnings.append(
                f"project_id {manifest['project_id']!r} does not match directory {root.name!r}"
            )
        for field in ("data_schema_version", "app_version", "code_commit"):
            if not manifest.get(field):
                warnings.append(f"project.json lacks portability metadata: {field}")

    for label, filename in JSONL_ARTIFACTS.items():
        rows, file_errors, file_references = _read_jsonl(root / filename)
        counts[label] = len(rows)
        errors.extend(file_errors)
        references.extend(file_references)

    for label, filename in CSV_ARTIFACTS.items():
        rows, file_errors, file_references = _read_csv(root / filename)
        counts[label] = len(rows)
        errors.extend(file_errors)
        references.extend(file_references)

    evidence_root = root / "evidence"
    evidence_files = (
        [path for path in evidence_root.rglob("*") if path.is_file()]
        if evidence_root.exists()
        else []
    )
    counts["evidence_files"] = len(evidence_files)
    counts["evidence_references"] = len(references)

    missing: list[dict[str, str]] = []
    absolute_reference_count = 0
    for stored_path, location in references:
        resolved, kind = resolve_project_evidence(
            root,
            stored_path,
            repository_root=repository_root,
        )
        if kind == "absolute":
            absolute_reference_count += 1
            warnings.append(f"{location}: evidence path is absolute: {stored_path}")
        elif resolved is None:
            missing.append({"path": stored_path, "source": location, "reason": kind})
            errors.append(f"{location}: evidence file not found or unsafe: {stored_path}")

    counts["missing_evidence_references"] = len(missing)
    return {
        "ok": not errors,
        "project_path": str(root),
        "project_id": manifest.get("project_id"),
        "metadata": {
            "data_schema_version": manifest.get("data_schema_version"),
            "app_version": manifest.get("app_version"),
            "code_commit": manifest.get("code_commit"),
        },
        "counts": counts,
        "absolute_evidence_references": absolute_reference_count,
        "missing_evidence_references": missing,
        "warnings": warnings,
        "errors": errors,
    }


def format_verification_report(report: dict[str, Any]) -> str:
    status = "PASS" if report.get("ok") else "FAIL"
    lines = [
        f"Status: {status}",
        f"Project: {report.get('project_id') or 'unknown'}",
        f"Path: {report.get('project_path')}",
        "Metadata: "
        + ", ".join(
            f"{key}={value or 'missing'}" for key, value in (report.get("metadata") or {}).items()
        ),
        "Counts:",
    ]
    for key, value in (report.get("counts") or {}).items():
        lines.append(f"  - {key}: {value}")
    for label, items in (("Warnings", report.get("warnings")), ("Errors", report.get("errors"))):
        if items:
            lines.append(f"{label}:")
            lines.extend(f"  - {item}" for item in items)
    return "\n".join(lines)
