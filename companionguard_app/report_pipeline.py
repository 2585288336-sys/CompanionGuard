from __future__ import annotations

import json
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Callable

from .grounding_validator import normalize_grounding_result, validate_grounding
from .audits import load_jsonl
from .report_schema import report_manifest, validate_context_shape
from .report_validation import validate_report_hard
from .reporting import build_dialogue_report_context, build_integrated_report_context, build_writer_facing_context
from .runtime_scope import RuntimeScope, assert_writable_target


WRITER_MIN_VISIBLE_CHARS = 500
REPAIRABLE_HARD_ISSUES = frozenset({"NUMBER_MISMATCH", "LEGAL_OVERCLAIM", "UNAUTHORIZED_SCORE"})


def report_artifact_dir(reports_dir: Path, report_type: str) -> Path:
    if report_type not in {"dialogue", "integrated"}:
        raise ValueError(f"Unsupported report type: {report_type}")
    return reports_dir / report_type


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _writer_status(text: str | None, metadata: dict[str, Any] | None, *, minimum_visible_chars: int = WRITER_MIN_VISIBLE_CHARS, requested_output_limit: int | None = None) -> str:
    value = (text or "").strip()
    metadata = metadata or {}
    finish_reason = str(metadata.get("finish_reason") or "").lower()
    incomplete_reason = str(metadata.get("incomplete_reason") or "").lower()
    if finish_reason in {"length", "max_tokens", "max_output_tokens"} or incomplete_reason in {"length", "max_tokens", "max_output_tokens"}:
        return "WRITER_TRUNCATED"
    if finish_reason in {"content_filter", "insufficient_system_resource", "aborted", "unknown"} or incomplete_reason in {"content_filter", "insufficient_system_resource", "aborted", "unknown"}:
        return "WRITER_INCOMPLETE"
    token_count = metadata.get("completion_tokens") or metadata.get("output_tokens")
    if not finish_reason and requested_output_limit and isinstance(token_count, (int, float)) and token_count >= requested_output_limit:
        return "WRITER_TRUNCATED_SUSPECTED"
    if not value or len(value) < minimum_visible_chars:
        return "WRITER_EMPTY_OUTPUT"
    return "PASS"


def _skipped_validation(failure_type: str) -> dict[str, Any]:
    return {
        "validator_version": "Python Hard Validation v1.1",
        "overall_status": "SKIPPED",
        "failure_type": failure_type,
        "checks_run": [],
        "failures": [],
        "issues": [],
        "summary": {"issue_count": 0, "numbers_checked": 0},
    }


def _skipped_grounding(failure_type: str) -> dict[str, Any]:
    return {
        "validator_version": "Evidence Grounding Validator",
        "overall_status": "SKIPPED",
        "failure_type": failure_type,
        "summary": {"sentences_checked": 0, "supported": 0, "partially_supported": 0, "unsupported": 0, "not_applicable": 0, "critical_errors": 0},
        "issues": [],
    }


def _persistable_hard_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(result)
    status = normalized.get("overall_status")
    normalized.setdefault("checks_run", ["context_shape", "required_sections", "numeric_literals", "boundary_claims"])
    normalized.setdefault("failures", list(normalized.get("issues") or []))
    normalized.setdefault("failure_type", None if status in {"PASS", "SKIPPED"} else "HARD_VALIDATION_FAILED")
    normalized.setdefault("expected", {"overall_status": "PASS"})
    normalized.setdefault("actual", {"overall_status": status})
    return normalized


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _validator_passes(result: dict[str, Any]) -> bool:
    """Require both v1.1 evidence and report-quality gates when present."""
    if result.get("overall_status") != "PASS":
        return False
    evidence = result.get("evidence_integrity")
    quality = result.get("report_quality")
    return (not evidence or evidence.get("status") == "PASS") and (not quality or quality.get("status") == "PASS")


def _hard_repair_eligible(*, result: dict[str, Any], writer_status: str, context: dict[str, Any]) -> bool:
    if writer_status != "PASS" or result.get("overall_status") != "FAIL":
        return False
    if validate_context_shape(context):
        return False
    issue_types = {str(issue.get("issue_type")) for issue in (result.get("issues") or [])}
    return bool(issue_types) and issue_types.issubset(REPAIRABLE_HARD_ISSUES)


def _grounding_issue_is_localized(issue: dict[str, Any], *, deterministic_confirmed: bool = False) -> bool:
    if deterministic_confirmed or issue.get("deterministic_confirmed") is True:
        return True
    sentence_id = str(issue.get("sentence_id") or "").strip().lower()
    return bool(issue.get("sentence_excerpt")) or sentence_id not in {"", "unknown", "none"}


def _grounding_repair_eligible(result: dict[str, Any]) -> bool:
    if result.get("overall_status") != "FAIL":
        return False
    issues = list(result.get("issues") or [])
    if not issues:
        return False
    deterministic_confirmed = result.get("deterministic_confirmed") is True
    return all(_grounding_issue_is_localized(issue, deterministic_confirmed=deterministic_confirmed) for issue in issues)


def _repair_payload(*, repair_kind: str, draft: str, issues: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "repair_kind": repair_kind,
        "draft": draft,
        "issues": issues,
        "deterministic_context": build_writer_facing_context(context),
        "repair_contract": {
            "max_attempts": 1,
            "edit_scope": "reported sentences only",
            "must_preserve_all_unreported_text": True,
            "must_use_exact_numeric_facts": True,
        },
    }


def _invoke_repair(repair: Callable[[dict[str, Any]], str], payload: dict[str, Any]) -> str:
    repaired = repair(payload)
    return repaired if isinstance(repaired, str) else ""


def build_report_context(*, report_type: str, project: dict[str, Any], final_rows: list[dict[str, Any]], layer2_path: Path, layer3_path: Path) -> dict[str, Any]:
    if report_type == "dialogue":
        context = build_dialogue_report_context(
            project=project,
            final_rows=final_rows,
            layer2_records=load_jsonl(layer2_path),
            layer3_records=load_jsonl(layer3_path),
        )
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


def write_report_artifacts(*, report_type: str, project: dict[str, Any], final_rows: list[dict[str, Any]], layer2_path: Path, layer3_path: Path, reports_dir: Path, draft_text: str | None = None, writer: Callable[[dict[str, Any]], str] | None = None, grounding_validator: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None, hard_repair: Callable[[dict[str, Any]], str] | None = None, grounding_repair: Callable[[dict[str, Any]], str] | None = None, polish: Callable[[str], str] | None = None, writer_prompt_version: str = "1.1", scope: RuntimeScope | str | None = None, workspace_root: Path | None = None, data_root: Path | None = None, writer_status: str | None = None, writer_metadata: dict[str, Any] | None = None, minimum_visible_chars: int = WRITER_MIN_VISIBLE_CHARS) -> dict[str, Any]:
    target_reports_dir = assert_writable_target(scope, reports_dir, workspace_root=workspace_root, data_root=data_root)
    target_layer2_path = assert_writable_target(scope, layer2_path, workspace_root=workspace_root, data_root=data_root)
    target_layer3_path = assert_writable_target(scope, layer3_path, workspace_root=workspace_root, data_root=data_root)
    target_reports_dir = report_artifact_dir(target_reports_dir, report_type)
    target_reports_dir.mkdir(parents=True, exist_ok=True)
    context = build_report_context(report_type=report_type, project=project, final_rows=final_rows, layer2_path=target_layer2_path, layer3_path=target_layer3_path)
    context_path = target_reports_dir / "report_context.json"
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    writer_context_path = target_reports_dir / "writer_context.json"
    writer_context_path.write_text(json.dumps(build_writer_facing_context(context), ensure_ascii=False, indent=2), encoding="utf-8")
    draft = draft_text if draft_text is not None else (writer(context) if writer else "")
    requested_limit = (writer_metadata or {}).get("requested_output_limit") or (writer_metadata or {}).get("configured_output_limit")
    writer_status = writer_status or _writer_status(draft, writer_metadata, minimum_visible_chars=minimum_visible_chars, requested_output_limit=requested_limit)
    metadata_attempts = (writer_metadata or {}).get("attempt_number")
    writer_attempts = max(1, int(metadata_attempts)) if isinstance(metadata_attempts, (int, float)) and metadata_attempts > 0 else (1 if draft_text is not None or writer else 0)
    hard_validation_attempts = 0
    grounding_attempts = 0
    hard_repair_attempted = False
    grounding_repair_attempted = False
    repair_status = "NOT_TRIGGERED"
    repair_kind = None
    repair_reason = "No targeted repair was requested in this run."
    draft_path = target_reports_dir / "draft_report.md"
    draft_path.write_text(draft, encoding="utf-8")

    def run_hard(text: str) -> dict[str, Any]:
        nonlocal hard_validation_attempts
        hard_validation_attempts += 1
        return validate_report_hard(report_text=text, context=context, report_type=report_type, quality_version=writer_prompt_version)

    def run_grounding(text: str, hard_result: dict[str, Any]) -> dict[str, Any]:
        nonlocal grounding_attempts
        if hard_result.get("overall_status") != "PASS":
            return _skipped_grounding("HARD_VALIDATION_FAILED")
        grounding_attempts += 1
        raw_grounding = grounding_validator(text, context) if grounding_validator else validate_grounding(draft_report=text, context=context)
        normalized = normalize_grounding_result(raw_grounding, context)
        deterministic_confirmation = validate_grounding(draft_report=text, context=context)
        deterministic_types = {
            issue_type
            for issue in (deterministic_confirmation.get("issues") or [])
            for issue_type in (issue.get("issue_types") or [])
        }
        if normalized.get("issues") and deterministic_types:
            normalized = dict(normalized)
            confirmed_issues = []
            for issue in normalized.get("issues") or []:
                issue = dict(issue)
                if deterministic_types.intersection(issue.get("issue_types") or []):
                    issue["deterministic_confirmed"] = True
                confirmed_issues.append(issue)
            normalized["issues"] = confirmed_issues
        unlocalized = [
            issue for issue in (normalized.get("issues") or [])
            if not _grounding_issue_is_localized(issue, deterministic_confirmed=normalized.get("deterministic_confirmed") is True)
        ]
        if unlocalized:
            normalized = dict(normalized)
            summary = dict(normalized.get("summary") or {})
            blocking_count = sum(
                1 for issue in (normalized.get("issues") or [])
                if _grounding_issue_is_localized(issue, deterministic_confirmed=normalized.get("deterministic_confirmed") is True)
            )
            summary["critical_errors"] = blocking_count
            summary["unlocalized_issues"] = len(unlocalized)
            normalized["summary"] = summary
            normalized["blocking_issue_count"] = blocking_count
            normalized["unlocalized_issue_count"] = len(unlocalized)
        if grounding_validator and normalized.get("overall_status") == "PASS":
            summary = normalized.get("summary") or {}
            if summary.get("sentences_checked") == 0:
                normalized = dict(normalized)
                normalized["overall_status"] = "FAIL"
                normalized["failure_type"] = "GROUNDING_ZERO_SENTENCES"
                normalized["issues"] = list(normalized.get("issues") or []) + [{
                    "issue_type": "GROUNDING_ZERO_SENTENCES",
                    "message": "Grounding returned PASS without checking any sentences.",
                }]
        return normalized

    if writer_status != "PASS":
        hard = _skipped_validation(writer_status)
        grounding = _skipped_grounding(writer_status)
    else:
        hard = run_hard(draft)
        if _hard_repair_eligible(result=hard, writer_status=writer_status, context=context) and hard_repair:
            hard_repair_attempted = True
            repair_kind = "HARD_VALIDATION"
            repair_reason = "A single bounded hard-validation repair was attempted."
            repair_status = "FAILED"
            payload = _repair_payload(repair_kind="HARD_VALIDATION", draft=draft, issues=list(hard.get("issues") or []), context=context)
            try:
                repaired = _invoke_repair(hard_repair, payload)
            except Exception as exc:
                repaired = ""
                repair_reason = f"Hard repair callback failed: {type(exc).__name__}"
            if repaired.strip():
                draft = repaired
                draft_path.write_text(draft, encoding="utf-8")
                hard = run_hard(draft)
                if hard.get("overall_status") == "PASS":
                    repair_status = "PASS"
            else:
                repair_reason = repair_reason if repair_reason != "A single bounded hard-validation repair was attempted." else "Hard repair returned empty output."
        grounding = run_grounding(draft, hard)
        if hard.get("overall_status") == "PASS" and _grounding_repair_eligible(grounding) and grounding_repair:
            grounding_repair_attempted = True
            repair_kind = "GROUNDING"
            repair_reason = "A single bounded grounding repair was attempted after hard validation passed."
            repair_status = "FAILED"
            payload = _repair_payload(repair_kind="GROUNDING", draft=draft, issues=list(grounding.get("issues") or []), context=context)
            try:
                repaired = _invoke_repair(grounding_repair, payload)
            except Exception as exc:
                repaired = ""
                repair_reason = f"Grounding repair callback failed: {type(exc).__name__}"
            if repaired.strip():
                draft = repaired
                draft_path.write_text(draft, encoding="utf-8")
                hard = run_hard(draft)
                grounding = run_grounding(draft, hard)
                if hard.get("overall_status") == "PASS" and _validator_passes(grounding):
                    repair_status = "PASS"
    hard = _persistable_hard_result(hard)
    hard_validation_path = target_reports_dir / "hard_validation_result.json"
    hard_validation_path.write_text(json.dumps(hard, ensure_ascii=False, indent=2), encoding="utf-8")
    grounding_path = target_reports_dir / "grounding_result.json"
    grounding_path.write_text(json.dumps(grounding, ensure_ascii=False, indent=2), encoding="utf-8")
    targeted_repair_record = {
        "attempted": hard_repair_attempted or grounding_repair_attempted,
        "status": repair_status,
        "repair_kind": repair_kind,
        "reason": repair_reason,
        "source_grounding_status": grounding.get("overall_status", "UNKNOWN"),
        "issue_count": len(grounding.get("issues") or []),
        "hard_repair_attempted": hard_repair_attempted,
        "grounding_repair_attempted": grounding_repair_attempted,
    }
    targeted_repair_path = target_reports_dir / "targeted_repair.json"
    targeted_repair_path.write_text(json.dumps(targeted_repair_record, ensure_ascii=False, indent=2), encoding="utf-8")
    final_text = draft
    final_hard = hard
    if hard["overall_status"] == "PASS" and _validator_passes(grounding) and polish:
        final_text = polish(draft)
        final_hard = run_hard(final_text)
        final_hard = _persistable_hard_result(final_hard)
        if final_hard["overall_status"] != "PASS":
            final_text = ""
        hard = final_hard
        hard_validation_path.write_text(json.dumps(hard, ensure_ascii=False, indent=2), encoding="utf-8")
    final_path = target_reports_dir / "final_report.md"
    previous_manifest_path = target_reports_dir / "report_manifest.json"
    previous_manifest = {}
    if previous_manifest_path.exists():
        try:
            previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_manifest = {}
    if final_text and hard["overall_status"] == "PASS" and _validator_passes(grounding):
        _atomic_write(final_path, final_text)
        validation_status = "PASS"
        last_successful_at = _now()
    else:
        validation_status = "FAIL"
        last_successful_at = previous_manifest.get("last_successful_at")
        if not last_successful_at and final_path.exists():
            last_successful_at = datetime.fromtimestamp(final_path.stat().st_mtime, tz=timezone.utc).isoformat()
    latest_attempt_status = writer_status if writer_status != "PASS" else (
        "HARD_VALIDATION_FAILED" if hard["overall_status"] != "PASS" else
        "GROUNDING_VALIDATION_FAILED" if not _validator_passes(grounding) else "PASS"
    )
    manifest = report_manifest(
        report_type=report_type, project=project, validation_status=validation_status,
        grounding_status=grounding["overall_status"], polish_enabled=bool(polish),
        writer_prompt_version=writer_prompt_version,
        latest_attempt_status=latest_attempt_status,
        last_successful_at=last_successful_at,
        writer_attempts=writer_attempts,
        hard_validation_attempts=hard_validation_attempts,
        targeted_repair_attempted=hard_repair_attempted or grounding_repair_attempted,
        grounding_attempts=grounding_attempts,
        final_status=validation_status,
    )
    (target_reports_dir / "report_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"context": context, "writer_context": build_writer_facing_context(context), "hard_validation": hard, "grounding": grounding, "targeted_repair": targeted_repair_record, "manifest": manifest, "paths": {"context": context_path, "writer_context": writer_context_path, "draft": draft_path, "hard_validation": hard_validation_path, "grounding": grounding_path, "targeted_repair": targeted_repair_path, "final": final_path}}
