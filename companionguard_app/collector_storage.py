from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .config import COLLECTION_QUEUES_PATH, COLLECTION_SESSIONS_PATH, EVIDENCE_DIR, PROJECT_ROOT, RAW_CASES_PATH


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_collection_sessions(path: Path = COLLECTION_SESSIONS_PATH) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def collection_session_index(path: Path = COLLECTION_SESSIONS_PATH) -> dict[str, dict[str, Any]]:
    return {row["session_id"]: row for row in load_collection_sessions(path) if row.get("session_id")}


def upsert_collection_session(session: dict[str, Any], path: Path = COLLECTION_SESSIONS_PATH) -> None:
    sessions = collection_session_index(path)
    sessions[session["session_id"]] = session
    ordered = sorted(sessions.values(), key=lambda x: (x.get("created_at", ""), x.get("session_id", "")))
    _write_jsonl(path, ordered)


def get_collection_session(session_id: str, path: Path = COLLECTION_SESSIONS_PATH) -> dict[str, Any] | None:
    return collection_session_index(path).get(session_id)


def in_progress_sessions(path: Path = COLLECTION_SESSIONS_PATH) -> list[dict[str, Any]]:
    return [row for row in load_collection_sessions(path) if row.get("collection_status") == "IN_PROGRESS"]


def load_collection_queues(path: Path = COLLECTION_QUEUES_PATH) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def collection_queue_index(path: Path = COLLECTION_QUEUES_PATH) -> dict[str, dict[str, Any]]:
    return {row["queue_id"]: row for row in load_collection_queues(path) if row.get("queue_id")}


def upsert_collection_queue(queue: dict[str, Any], path: Path = COLLECTION_QUEUES_PATH) -> None:
    queues = collection_queue_index(path)
    queues[queue["queue_id"]] = queue
    ordered = sorted(queues.values(), key=lambda x: (x.get("created_at", ""), x.get("queue_id", "")))
    _write_jsonl(path, ordered)


def get_collection_queue(queue_id: str, path: Path = COLLECTION_QUEUES_PATH) -> dict[str, Any] | None:
    return collection_queue_index(path).get(queue_id)


def in_progress_queues(path: Path = COLLECTION_QUEUES_PATH) -> list[dict[str, Any]]:
    return [row for row in load_collection_queues(path) if row.get("queue_status") == "IN_PROGRESS"]


def make_queue_id(*, product_slug: str, phase: str, collection_date: str, path: Path = COLLECTION_QUEUES_PATH) -> str:
    base = f"{_safe_file_part(product_slug)}_{_safe_file_part(phase)}_{collection_date.replace('-', '')}"
    existing = set(collection_queue_index(path))
    index = 1
    while f"{base}_q{index:02d}" in existing:
        index += 1
    return f"{base}_q{index:02d}"


def update_queue_item_status(
    *,
    queue_id: str,
    case_id: str,
    status: str,
    session_id: str | None = None,
    path: Path = COLLECTION_QUEUES_PATH,
) -> dict[str, Any]:
    queues = collection_queue_index(path)
    queue = queues.get(queue_id)
    if queue is None:
        raise KeyError(f"Unknown queue_id: {queue_id}")
    allowed = {"PENDING", "IN_PROGRESS", "COMPLETE"}
    if status not in allowed:
        raise ValueError(f"Unsupported queue item status: {status}")
    matched = False
    for item in queue.get("items", []):
        if item.get("case_id") == case_id:
            item["status"] = status
            if session_id is not None:
                item["session_id"] = session_id
            matched = True
            break
    if not matched:
        raise KeyError(f"case_id is not in queue {queue_id}: {case_id}")
    from .collector import utc_now_iso
    queue["updated_at"] = utc_now_iso()
    if queue.get("items") and all(i.get("status") == "COMPLETE" for i in queue["items"]):
        queue["queue_status"] = "COMPLETE"
        queue["completed_at"] = queue["updated_at"]
    upsert_collection_queue(queue, path=path)
    return queue


def reconcile_collection_queue(
    queue: dict[str, Any],
    *,
    sessions_path: Path = COLLECTION_SESSIONS_PATH,
    raw_path: Path = RAW_CASES_PATH,
) -> dict[str, Any]:
    """Reconcile persisted queue items with the authoritative raw/session stores."""
    import copy
    from .collector import utc_now_iso
    updated = copy.deepcopy(queue)
    complete = raw_case_ids(raw_path)
    sessions = collection_session_index(sessions_path)
    for item in updated.get("items", []):
        case_id = item.get("case_id")
        if case_id in complete:
            item["status"] = "COMPLETE"
            item["session_id"] = case_id
        elif case_id in sessions and sessions[case_id].get("collection_status") == "IN_PROGRESS":
            item["status"] = "IN_PROGRESS"
            item["session_id"] = case_id
        else:
            item["status"] = "PENDING"
            item["session_id"] = None
    if updated.get("items") and all(i.get("status") == "COMPLETE" for i in updated["items"]):
        updated["queue_status"] = "COMPLETE"
        updated["completed_at"] = updated.get("completed_at") or utc_now_iso()
    else:
        updated["queue_status"] = "IN_PROGRESS"
    updated["updated_at"] = utc_now_iso()
    return updated


def get_raw_case(case_id: str, path: Path = RAW_CASES_PATH) -> dict[str, Any] | None:
    return next((row for row in load_raw_cases(path) if row.get("case_id") == case_id), None)


def load_raw_cases(path: Path = RAW_CASES_PATH) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def resolve_evidence_path(path: str | Path, project_root: Path) -> Path | None:
    """Resolve a stored evidence path without leaving the project/source roots."""
    if not path:
        return None
    raw = Path(str(path))
    candidates = [raw] if raw.is_absolute() else [project_root / raw, PROJECT_ROOT / raw]
    allowed_roots = [project_root.resolve(), PROJECT_ROOT.resolve()]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_file():
            continue
        if any(resolved == root or root in resolved.parents for root in allowed_roots):
            return resolved
    return None


def raw_case_ids(path: Path = RAW_CASES_PATH) -> set[str]:
    return {row["case_id"] for row in load_raw_cases(path) if row.get("case_id")}


def append_raw_case(case: dict[str, Any], path: Path = RAW_CASES_PATH) -> None:
    if case.get("collection_status") != "COMPLETE":
        raise ValueError("Only COMPLETE cases may be written to raw_cases.jsonl.")
    if case.get("case_id") in raw_case_ids(path):
        raise ValueError(f"case_id already exists in raw_cases.jsonl: {case.get('case_id')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(case, ensure_ascii=False) + "\n")


def _safe_file_part(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-_.")
    return value or "evidence"


def save_evidence_files(
    *,
    case_id: str,
    response_turn: str,
    files: list[tuple[str, bytes]],
    evidence_dir: Path = EVIDENCE_DIR,
) -> list[str]:
    if not files:
        return []
    case_dir = evidence_dir / _safe_file_part(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    prefix = _safe_file_part(response_turn)
    for old in case_dir.glob(f"{prefix}_*"):
        if old.is_file():
            old.unlink()

    saved: list[str] = []
    for i, (original_name, content) in enumerate(files, 1):
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError(f"Unsupported evidence image type: {suffix or original_name}")
        path = case_dir / f"{prefix}_{i:02d}{suffix}"
        path.write_bytes(content)
        try:
            saved.append(str(path.relative_to(PROJECT_ROOT)))
        except ValueError:
            saved.append(str(path))
    return saved
