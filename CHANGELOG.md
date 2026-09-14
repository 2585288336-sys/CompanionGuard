# Changelog

## v0.4.0 — Real-product Data Collector

- Added the fourth Streamlit view: `Data Collection`.
- Added human-in-the-loop fixed-prompt acquisition without requiring the Judge API.
- Added dynamic collection planning from existing `judge_template` and frozen criterion JSON.
- Added Core C0/C1/C2, HR-02, MR, MC and PC collection structures without criterion-specific application branches.
- Added resumable `IN_PROGRESS` sessions in `data/collection_sessions.jsonl`.
- Added automatic completion into Judge-ready `data/raw_cases.jsonl`.
- Added stable phase-aware human-readable case IDs.
- Added `SMOKE`, `CALIBRATION`, and `FORMAL` phases; official Results metrics now use only `FORMAL` records.
- Added optional screenshot evidence under `data/evidence/<case_id>/` without making OCR part of the MVP path.
- Added direct `Run Test` batch loading from collected `raw_cases.jsonl`.
- Added configurable product definitions and the frozen 豆包 comparator allowlist in `config/collector.json`.
- Added Collector unit tests for structures, restrictions, verbatim text preservation, persistence, duplicate protection and Judge compatibility.
- Preserved the existing four Judge templates, T/N rules, human adjudication flow and criterion-driven architecture.

## v0.3.0 — Streamlit MVP

- Added three-view Streamlit frontend: Run Test, Human Review, Results.
- Kept `criteria/*.json` as the independent, dynamically loaded rule layer.
- Added application service, case-builder, storage and metric modules without changing Judge core responsibilities.
- Added JSONL batch upload and single-case benchmark execution.
- Added persistent human adjudication and merged `final_results.csv`.
- Added dashboard metrics and Finding Matrix export.
- Kept the 24-hour MVP file-based; no database, auth system, async queue or frontend framework added.

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
