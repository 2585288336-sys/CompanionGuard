from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_scope import RuntimeScope, assert_writable_scope


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_test_plans(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    try: obj=json.loads(path.read_text(encoding='utf-8'))
    except Exception: return []
    return obj if isinstance(obj,list) else []


def save_test_plans(
    path: Path,
    plans: list[dict[str, Any]],
    *,
    scope: RuntimeScope | str | None = None,
) -> None:
    assert_writable_scope(scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding='utf-8')


def upsert_test_plan(
    path: Path,
    plan: dict[str, Any],
    *,
    scope: RuntimeScope | str | None = None,
) -> dict[str, Any]:
    assert_writable_scope(scope)
    plans=load_test_plans(path); now=_now(); row=dict(plan); row.setdefault('created_at',now); row['updated_at']=now
    replaced=False
    for i,p in enumerate(plans):
        if p.get('plan_id')==row.get('plan_id'): plans[i]=row; replaced=True; break
    if not replaced: plans.append(row)
    save_test_plans(path,plans,scope=scope); return row
