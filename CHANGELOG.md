# Changelog

## v0.6.0 — Project-scoped three-layer testing platform

- Added `Test Projects` as the top-level evaluation batch abstraction with multiple configured/custom products.
- Isolated runtime evidence under `data/projects/<project_id>/` instead of one global experiment dataset.
- Kept the frozen Layer 1 dialogue structures, criteria and four Judge templates unchanged.
- Added explicit Demo/server-key and BYOK Judge access behavior.
- Added a dedicated Judge–Human Reliability page with Exact Agreement, Cohen's κ, Finding Precision/Recall and a three-class confusion matrix.
- Preserved 100% Human Adjudication in Benchmark Mode; added optional full/random/criterion-stratified review views for Custom Mode.
- Added Layer 2 Product Safeguard Checks with 22 configured checks, four observation states, standardized nine-step inspection path and screenshot evidence.
- Added Layer 3 Lite Public Compliance Evidence Audit with six configured checks, four documentary states, source/evidence recording and optional DeepSeek evidence-extraction assist with human-final status.
- Added deterministic integrated Markdown reporting across Layer 1, Layer 2, Layer 3 and reliability without a 0–100 safety/compliance score.
- Added project/audit/reliability/report tests. Current suite: 31 tests + 20 subtests pass.

## v0.5.1 — Module A C1 pressure prompt freeze

- Added the seven previously missing fixed `pressure_variant.L5` prompts for UE-01, UE-02, DS-01, DS-02, FD-01, FD-02 and FD-03.
- These texts are newly frozen from this version under the already-frozen C1 method; they are not represented as recovered historical wording.
- Added `criteria/VERSION` = `0.3.1`.
- Added verbatim prompt-lock tests and C0/C1 structural freeze checks.
- Current unit-test suite: 26 tests pass.

## v0.5.0 — High-throughput collection workflow

- Added persistent `Collection Queue` generation from configured products, criteria, scenarios, conditions and runs.
- Added one-click `Next Case` queue progression and prominent current case/turn display.
- Replaced the main turn action with `Save & Copy Next`; next-prompt clipboard copy is best-effort with an explicit Copy Prompt fallback when browser security blocks automatic copying.
- Added turn-level response-draft autosave/recovery without prematurely advancing the collection plan.
- Added optional `Send This Case to Judge` from the completion screen while preserving Collector/Judge decoupling.
- Kept screenshot evidence as a turn-linked, non-OCR path under `data/evidence/<case_id>/`; documented the structured evidence convention.
- Added persistent `data/collection_queues.jsonl`.
- Removed concrete product-name branching from Collector UI; product roles, notices, allowlists and custom-product behavior are configuration-driven.
- Added queue/draft/MR second-round tests; 24 unit tests pass.

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
