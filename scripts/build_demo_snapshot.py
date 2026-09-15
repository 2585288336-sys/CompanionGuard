"""Build a privacy-preserving, read-only deployment snapshot.

The frozen project remains the source of truth. This utility copies only the
metadata and result fields needed by the public viewer; it deliberately omits
conversation bodies, collection traces, Judge evidence/rationales and image
files.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any


RAW_METADATA_FIELDS = [
    "case_id", "project_id", "product", "criterion_id", "scenario_id",
    "condition", "phase", "run_number", "collection_date", "category",
    "expected_category", "collection_status",
]
JUDGE_METADATA_FIELDS = [
    "case_id", "criterion_id", "product", "condition", "module", "status",
    "auto_label", "auto_case_validity", "auto_validity_reason",
]
FINAL_RESULT_FIELDS = [
    "case_id", "criterion_id", "criterion_name", "module", "product",
    "scenario_id", "condition", "phase", "run_number", "collection_date",
    "coverage_type", "auto_label", "human_label", "final_label",
    "analysis_label", "adjudication_status", "adjudication_policy",
    "case_validity", "auto_case_validity", "final_case_validity",
    "judge_provider", "judge_model", "judge_template", "reviewed_at",
]
HUMAN_RESULT_FIELDS = [
    "case_id", "auto_label", "human_label", "final_label", "reviewed_at",
    "case_validity", "auto_case_validity", "final_case_validity",
    "validity_reviewed_at",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv_subset(source: Path, target: Path, fields: list[str]) -> int:
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    return len(rows)


def build_snapshot(source: Path, target: Path) -> dict[str, Any]:
    if not (source / "project.json").is_file():
        raise FileNotFoundError(f"Frozen project manifest not found: {source / 'project.json'}")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing snapshot: {target}")

    target.mkdir(parents=True)
    manifest = json.loads((source / "project.json").read_text(encoding="utf-8"))
    manifest.update({
        "read_only": True,
        "deployment_snapshot": True,
        "snapshot_note": "Public structured snapshot; original conversations and screenshots remain in the local frozen archive.",
    })
    (target / "project.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    raw_rows = read_jsonl(source / "raw_cases.jsonl")
    write_jsonl(target / "raw_cases.jsonl", [
        {field: row.get(field, "") for field in RAW_METADATA_FIELDS}
        for row in raw_rows
    ])

    judge_rows = read_jsonl(source / "judge_results.jsonl")
    write_jsonl(target / "judge_results.jsonl", [
        {field: row.get(field, "") for field in JUDGE_METADATA_FIELDS}
        for row in judge_rows
    ])

    for filename in ("test_plans.json",):
        shutil.copy2(source / filename, target / filename)

    final_count = write_csv_subset(source / "final_results.csv", target / "final_results.csv", FINAL_RESULT_FIELDS)
    human_count = write_csv_subset(source / "human_adjudication.csv", target / "human_adjudication.csv", HUMAN_RESULT_FIELDS)

    summary = {
        "snapshot_version": "1.0",
        "source_project_id": manifest.get("project_id"),
        "data_cutoff": max((str(row.get("collection_date", "")) for row in raw_rows), default=""),
        "raw_case_count": len(raw_rows),
        "judge_record_count": len(judge_rows),
        "final_result_count": final_count,
        "human_adjudication_count": human_count,
        "conversation_bodies_included": False,
        "collection_traces_included": False,
        "judge_evidence_or_rationales_included": False,
        "screenshots_included": False,
    }
    (target / "snapshot_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    summary = build_snapshot(args.source, args.target)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
