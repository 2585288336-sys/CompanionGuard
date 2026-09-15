from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def upsert_jsonl(path: Path, row: dict[str, Any], *, key_fields: tuple[str, ...]) -> None:
    rows = load_jsonl(path)
    key = tuple(str(row.get(k, "")) for k in key_fields)
    index = {tuple(str(r.get(k, "")) for k in key_fields): r for r in rows}
    index[key] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in sorted(index.values(), key=lambda x: tuple(str(x.get(k, "")) for k in key_fields)):
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def safe_part(value: str) -> str:
    return re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE).strip("-_.") or "evidence"


def save_audit_evidence(
    *,
    evidence_root: Path,
    product: str,
    check_code: str,
    files: list[tuple[str, bytes]],
) -> list[str]:
    if not files:
        return []
    target = evidence_root / safe_part(product) / safe_part(check_code)
    target.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for index, (name, content) in enumerate(files, 1):
        suffix = Path(name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt", ".md"}:
            raise ValueError(f"Unsupported evidence type: {suffix or name}")
        path = target / f"evidence_{index:02d}{suffix}"
        path.write_bytes(content)
        saved.append(str(path))
    return saved


def make_audit_row(
    *,
    project_id: str,
    product: str,
    check_code: str,
    status: str,
    evidence_summary: str,
    notes: str,
    source: str = "",
    source_date: str = "",
    evidence_files: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "product": product,
        "check_code": check_code,
        "status": status,
        "evidence_summary": evidence_summary,
        "source": source,
        "source_date": source_date,
        "notes": notes,
        "evidence_files": evidence_files or [],
        "metadata": metadata or {},
        "updated_at": utc_now_iso(),
    }
