#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from companionguard_app.data_integrity import format_verification_report, verify_project_data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only integrity and evidence portability check for a CompanionGuard project."
    )
    parser.add_argument(
        "project_dir",
        type=Path,
        help="Path to data/projects/<project_id>",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=None,
        help="Optional repository root when checking a project copied outside data/projects.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print machine-readable JSON instead of the human-readable report.",
    )
    args = parser.parse_args()
    report = verify_project_data(args.project_dir, repository_root=args.repository_root)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_verification_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
