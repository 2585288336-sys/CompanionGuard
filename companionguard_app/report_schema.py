from __future__ import annotations

from typing import Any

CONTEXT_SCHEMA_VERSION = "1.0"
WRITER_PROMPT_VERSION = "1.0"
GROUNDING_PROMPT_VERSION = "1.0"
POLISH_PROMPT_VERSION = "1.0"
SMALL_SAMPLE_THRESHOLD = 5
REPORT_TYPES = {"dialogue", "integrated"}


def validate_context_shape(context: dict[str, Any]) -> list[str]:
    """Validate the derived report context without touching source records."""
    errors: list[str] = []
    if context.get("meta", {}).get("context_schema_version") != CONTEXT_SCHEMA_VERSION:
        errors.append("context_schema_version must be 1.0")
    required = {"meta", "coverage", "overall", "products", "modules", "criteria", "conditions", "comparisons", "reliability", "representative_findings", "layer2", "layer3", "cross_layer", "limitations", "unresolved_questions", "verification_needed"}
    errors.extend(f"missing context field: {key}" for key in sorted(required - set(context)))
    if context.get("meta", {}).get("report_type") not in REPORT_TYPES:
        errors.append("meta.report_type must be dialogue or integrated")
    return errors


def report_manifest(*, report_type: str, project: dict[str, Any], validation_status: str, grounding_status: str = "NOT_RUN", polish_enabled: bool = False) -> dict[str, Any]:
    return {
        "report_type": report_type,
        "project_id": project.get("project_id"),
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "writer_prompt_version": WRITER_PROMPT_VERSION,
        "grounding_prompt_version": GROUNDING_PROMPT_VERSION,
        "polish_prompt_version": POLISH_PROMPT_VERSION,
        "validation_status": validation_status,
        "grounding_status": grounding_status,
        "academic_polish_enabled": bool(polish_enabled),
        "source_policy": "FORMAL-only metrics; raw source records are read-only",
    }
