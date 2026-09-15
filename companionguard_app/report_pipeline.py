from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .grounding_validator import validate_grounding
from .report_schema import report_manifest
from .report_validation import validate_report_hard
from .reporting import build_dialogue_report_context, build_integrated_report_context


def build_report_context(*, report_type: str, project: dict[str, Any], final_rows: list[dict[str, Any]], layer2_path: Path, layer3_path: Path) -> dict[str, Any]:
    if report_type == "dialogue":
        context = build_dialogue_report_context(project=project, final_rows=final_rows)
    elif report_type == "integrated":
        context = build_integrated_report_context(project=project, final_rows=final_rows, layer2_path=layer2_path, layer3_path=layer3_path)
    else:
        raise ValueError(f"Unsupported report type: {report_type}")
    return context


def targeted_repair(*, draft_text: str, grounding_result: dict[str, Any], repair: Callable[[str, list[dict[str, Any]]], str] | None = None) -> str:
    """Repair only reported sentences; returns the original draft when no issue exists."""
    issues = list(grounding_result.get("issues") or [])
    if not issues or repair is None:
        return draft_text
    return repair(draft_text, issues)


def write_report_artifacts(*, report_type: str, project: dict[str, Any], final_rows: list[dict[str, Any]], layer2_path: Path, layer3_path: Path, reports_dir: Path, draft_text: str | None = None, writer: Callable[[dict[str, Any]], str] | None = None, polish: Callable[[str], str] | None = None) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    context = build_report_context(report_type=report_type, project=project, final_rows=final_rows, layer2_path=layer2_path, layer3_path=layer3_path)
    context_path = reports_dir / "report_context.json"
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    draft = draft_text if draft_text is not None else (writer(context) if writer else "")
    draft_path = reports_dir / "draft_report.md"
    draft_path.write_text(draft, encoding="utf-8")
    hard = validate_report_hard(report_text=draft, context=context, report_type=report_type)
    grounding = validate_grounding(draft_report=draft, context=context)
    grounding_path = reports_dir / "grounding_result.json"
    grounding_path.write_text(json.dumps(grounding, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = draft
    if hard["overall_status"] == "PASS" and grounding["overall_status"] == "PASS" and polish:
        final_text = polish(draft)
        final_hard = validate_report_hard(report_text=final_text, context=context, report_type=report_type)
        if final_hard["overall_status"] != "PASS":
            final_text = ""
            hard = final_hard
    final_path = reports_dir / "final_report.md"
    if final_text and hard["overall_status"] == "PASS" and grounding["overall_status"] == "PASS":
        final_path.write_text(final_text, encoding="utf-8")
        validation_status = "PASS"
    else:
        final_path.unlink(missing_ok=True)
        validation_status = "FAIL"
    manifest = report_manifest(report_type=report_type, project=project, validation_status=validation_status, grounding_status=grounding["overall_status"], polish_enabled=bool(polish))
    (reports_dir / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"context": context, "hard_validation": hard, "grounding": grounding, "manifest": manifest, "paths": {"context": context_path, "draft": draft_path, "grounding": grounding_path, "final": final_path}}
