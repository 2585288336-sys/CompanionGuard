from __future__ import annotations

import shutil
from pathlib import Path

from .config import PROJECT_ROOT


DEPLOYMENT_PROJECT_ID = "CompanionGuard-Formal-Full-Benchmark-2026-09"


def ensure_deployment_project(
    *,
    project_id: str = DEPLOYMENT_PROJECT_ID,
    project_root: Path = PROJECT_ROOT,
) -> bool:
    """Materialize the immutable deployment seed only when runtime is absent."""
    seed_root = project_root / "data" / "deployment_seed" / project_id
    runtime_root = project_root / "data" / "projects" / project_id
    if runtime_root.exists() or not seed_root.is_dir():
        return False

    runtime_root.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(seed_root, runtime_root, dirs_exist_ok=False)
    except FileExistsError:
        return False
    return True
