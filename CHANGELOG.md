
## v0.3.0 — Streamlit MVP

- Added three-view Streamlit frontend: Run Test, Human Review, Results.
- Kept `criteria/*.json` as the independent, dynamically loaded rule layer.
- Added application service, case-builder, storage and metric modules without changing Judge core responsibilities.
- Added JSONL batch upload and single-case benchmark execution.
- Added persistent human adjudication and merged `final_results.csv`.
- Added dashboard metrics and Finding Matrix export.
- Kept the 24-hour MVP file-based; no database, auth system, async queue or frontend framework added.

# Changelog

## v0.2.0
- Switched from Chat Completions `json_object` + local `jsonschema` to DeepSeek Responses API `json_schema`.
- Removed duplicated structural validation and `jsonschema` dependency.
- Split the 1412-line monolith into small modules with single responsibilities.
- Retained only criterion-specific semantic validation and exact evidence verification.
- Replaced custom nested API retry loops with the SDK's built-in retry mechanism.
- Removed concurrency from the MVP runner.
- Added unit tests and Git versioning.

## v0.1.0
- Initial monolithic DeepSeek Judge runner.
