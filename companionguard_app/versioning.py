from __future__ import annotations

import subprocess
from pathlib import Path

from . import __version__


APP_VERSION = __version__
DATA_SCHEMA_VERSION = "1.0"
UNKNOWN_CODE_COMMIT = "unknown"


def current_code_commit(project_root: Path) -> str:
    """Return the checked-out commit without making Git a runtime dependency."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_CODE_COMMIT
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else UNKNOWN_CODE_COMMIT
