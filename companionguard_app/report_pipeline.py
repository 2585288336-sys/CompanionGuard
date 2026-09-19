from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .grounding_validator import validate_grounding
from .report_schema import report_manifest
from .report_validation import validate_report_hard
from .reporting import build_dialogue_report_context, build_integrated_report_context, build_writer_facing_context
from .runtime_scope import RuntimeScope, assert_writable_target


def _validator_passes(result: dict[str, Any]) -> bool:
    """Require both v1.1 evidence and report-quality gates when present."""
    if result.get("overall_status") != "PASS":
        return False
    evidence = result.get("evidence_integrity")
    quality = result.get("report_quality")
    return (not evidence or evidence.get("status") == "PASS") and (not quality or quality.get("status") == "PASS")


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


def write_report_artifacts(*, report_type: str, project: dict[str, Any], final_rows: list[dict[str, Any]], layer2_path: Path, layer3_path: Path, reports_dir: Path, draft_text: str | None = None, writer: Callable[[dict[str, Any]], str] | None = None, grounding_validator: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None, polish: Callable[[str], str] | None = None, writer_prompt_version: str = "1.1", scope: RuntimeScope | str | None = None, workspace_root: Path | None = None, data_root: Path | None = None) -> dict[str, Any]:
    target_reports_dir = assert_writable_target(scope, reports_dir, workspace_root=workspace_root, data_root=data_root)
    target_layer2_path = assert_writable_target(scope, layer2_path, workspace_root=workspace_root, data_root=data_root)
    target_layer3_path = assert_writable_target(scope, layer3_path, workspace_root=workspace_root, data_root=data_root)
    target_reports_dir.mkdir(parents=True, exist_ok=True)
    context = build_report_context(report_type=report_type, project=project, final_rows=final_rows, layer2_path=target_layer2_path, layer3_path=target_layer3_path)
    context_path = target_reports_dir / "report_context.json"
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    writer_context_path = target_reports_dir / "writer_context.json"
    writer_context_path.write_text(json.dumps(build_writer_facing_context(context), ensure_ascii=False, indent=2), encoding="utf-8")
    draft = draft_text if draft_text is not None else (writer(context) if writer else "")
    draft_path = target_reports_dir / "draft_report.md"
    draft_path.write_text(draft, encoding="utf-8")
    hard = validate_report_hard(report_text=draft, context=context, report_type=report_type, quality_version=writer_prompt_version)
    grounding = grounding_validator(draft, context) if grounding_validator else validate_grounding(draft_report=draft, context=context)
    grounding_path = target_reports_dir / "grounding_result.json"
    grounding_path.write_text(json.dumps(grounding, ensure_ascii=False, indent=2), encoding="utf-8")
    targeted_repair_record = {
        "attempted": False,
        "status": "NOT_TRIGGERED",
        "reason": "No targeted repair was requested in this run.",
        "source_grounding_status": grounding.get("overall_status", "UNKNOWN"),
        "issue_count": len(grounding.get("issues") or []),
    }
    targeted_repair_path = target_reports_dir / "targeted_repair.json"
    targeted_repair_path.write_text(json.dumps(targeted_repair_record, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = draft
    if hard["overall_status"] == "PASS" and _validator_passes(grounding) and polish:
        final_text = polish(draft)
        final_hard = validate_report_hard(report_text=final_text, context=context, report_type=report_type, quality_version=writer_prompt_version)
        if final_hard["overall_status"] != "PASS":
            final_text = ""
            hard = final_hard
    final_path = target_reports_dir / "final_report.md"
    if final_text and hard["overall_status"] == "PASS" and _validator_passes(grounding):
        final_path.write_text(final_text, encoding="utf-8")
        validation_status = "PASS"
    else:
        final_path.unlink(missing_ok=True)
        validation_status = "FAIL"
    manifest = report_manifest(report_type=report_type, project=project, validation_status=validation_status, grounding_status=grounding["overall_status"], polish_enabled=bool(polish), writer_prompt_version=writer_prompt_version)
    (target_reports_dir / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"context": context, "writer_context": build_writer_facing_context(context), "hard_validation": hard, "grounding": grounding, "targeted_repair": targeted_repair_record, "manifest": manifest, "paths": {"context": context_path, "writer_context": writer_context_path, "draft": draft_path, "grounding": grounding_path, "targeted_repair": targeted_repair_path, "final": final_path}}
