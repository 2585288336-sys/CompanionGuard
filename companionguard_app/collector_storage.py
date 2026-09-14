from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .config import COLLECTION_SESSIONS_PATH, EVIDENCE_DIR, PROJECT_ROOT, RAW_CASES_PATH


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


def load_raw_cases(path: Path = RAW_CASES_PATH) -> list[dict[str, Any]]:
    return _read_jsonl(path)


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
