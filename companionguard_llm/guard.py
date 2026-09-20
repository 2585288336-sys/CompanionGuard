from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
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


def check_server_guard(*, usage_path: Path, session_id: str | None) -> None:
    enabled = os.environ.get("COMPANIONGUARD_SERVER_LLM_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        raise RuntimeError("Server-side LLM access is temporarily disabled by the operator.")
    daily_limit = int(os.environ.get("COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT", "500"))
    session_limit = int(os.environ.get("COMPANIONGUARD_SERVER_LLM_SESSION_CALL_LIMIT", "50"))
    rows = [r for r in _read_rows(usage_path) if r.get("date") == _today() and r.get("access_mode") == "SERVER"]
    if daily_limit > 0 and len(rows) >= daily_limit:
        raise RuntimeError("Server-side LLM daily call limit reached. Use BYOK or try later.")
    if session_id and session_limit > 0:
        count = sum(r.get("session_id") == session_id for r in rows)
        if count >= session_limit:
            raise RuntimeError("Server-side LLM session call limit reached. Use BYOK or start a new authorized session.")


def record_usage(
    *,
    usage_path: Path,
    role: str,
    provider: str,
    model: str,
    access_mode: str,
    session_id: str | None,
    usage: dict[str, Any] | None,
    project_id: str | None = None,
    observability: dict[str, Any] | None = None,
) -> None:
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": _today(),
        "role": role,
        "provider": provider,
        "model": model,
        "access_mode": access_mode,
        "session_id": session_id,
        "project_id": project_id,
        "usage": usage or {},
    }
    for key in (
        "report_pipeline_version", "report_type", "attempt_number", "adapter_type",
        "effective_provider", "effective_model", "configured_output_limit", "requested_output_limit",
        "configured_reasoning_effort", "requested_reasoning_effort", "requested_thinking_mode",
        "reasoning_effort",
        "prompt_tokens", "completion_tokens", "output_tokens", "reasoning_tokens",
        "visible_output_char_count", "finish_reason", "incomplete_reason",
        "parse_status", "final_attempt_status",
    ):
        if observability and observability.get(key) is not None:
            row[key] = observability[key]
    with usage_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
