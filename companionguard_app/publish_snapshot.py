"""Owner-controlled CLI for versioned benchmark publication and dry-runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PROJECT_ROOT
from .publishing import PublishingError, load_deployment_manifest, publish_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate or publish a CompanionGuard benchmark snapshot.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--version", required=True, dest="published_version")
    parser.add_argument("--destination", type=Path, default=PROJECT_ROOT / "data" / "deployment_seed")
    parser.add_argument("--publish", action="store_true", help="Explicitly promote the validated snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and diff without writing (the default).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.publish and args.dry_run:
        parser.error("--publish and --dry-run are mutually exclusive")
    try:
        plan = publish_snapshot(
            args.source,
            project_id=args.project_id,
            published_version=args.published_version,
            destination_root=args.destination,
            confirm_publish=args.publish,
        )
    except PublishingError as exc:
        parser.error(str(exc))
    current_manifest = load_deployment_manifest(plan.destination) if plan.destination and plan.destination.is_dir() else None
    summary = {
        "project_id": plan.project_id,
        "source_type": "AUTHORITATIVE",
        "source_validation": "passed",
        "published_version": plan.published_version,
        "current_published_version": current_manifest.get("published_version") if current_manifest else None,
        "proposed_version": plan.published_version,
        "manifest": plan.manifest,
        "diff": plan.diff.as_dict(),
        "published": plan.published,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
