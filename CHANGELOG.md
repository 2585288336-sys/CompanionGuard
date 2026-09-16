# Changelog

## v0.9.2 — latest UI/UX package integration

- Updated the workspace navigation to the latest Chinese-first `01 / 02 / 03 / 04` information architecture, with explicit Layer 1/2/3 hierarchy and report entries.
- Updated Home, Test Project, Results, Layer 2, Layer 3 and Dialogue Report presentation labels and reference-project treatment to match the latest UI/UX package.
- Added non-mutating workflow previews for read-only deployment snapshots so Data Collection, Dialogue Judge, Human Review, Layer 2, Layer 3 and Dialogue Report remain visible without weakening snapshot write protection.
- Verified that the R&D copy of `CompanionGuard-Formal-Full-Benchmark-2026-09` already contains byte-identical Judge and Human Adjudication records from the FORMAL freeze; no data migration or raw-data rewrite was required.

## v0.9.1 — deployment-ready public result viewer

- Migrated the completed FORMAL project into the development checkout as a local analysis copy without modifying the frozen source project.
- Added a privacy-preserving, read-only `data/demo_submission/` snapshot for Streamlit Community Cloud; conversation bodies, collection traces, Judge evidence/rationales and screenshots remain local-only.
- Added Cloud Secrets-compatible Server API loading, nested `[llm]` aliases, read-only snapshot routing and write protection, plus a deployable `requirements.txt`.

## v0.9.0 — UI/UX v0.9 research workspace

- Reframed the Streamlit presentation as a complete three-layer regulatory testing system with a public Home, Project Overview, read-only Test Plan, grouped workspace navigation and restrained research SaaS styling.
- Added data-driven project status, automatic-result presentation, light empty states for Layer 2/3, and a current Integrated Report view without changing the storage contract.
- Preserved the frozen benchmark, project-relative evidence references, machine values and existing FORMAL data; existing projects require no migration.

## v0.8.6 — Deterministic report-generation layer

- Added a derived report pipeline: FORMAL-only deterministic analysis → `report_context.json` → report draft → Python hard validation → grounding result → optional academic polish → final report.
- Added versioned Chinese reporting, Dialogue Writer, Integrated Writer, Evidence Grounding and optional Academic Polish prompts.
- Added hard validation for unauthorized numbers, legal overclaims, unified safety/compliance scores and Layer 2/Layer 3 status semantic errors.
- Added report manifests and grounding results without changing raw cases, Judge results, human adjudication or frozen benchmark logic; existing data requires no migration.

## v0.8.5 — Formal primary-product configuration update

- Updated the new FORMAL Full Benchmark default primary-product set to MoMood, Xingye/星野 and Doubao/豆包.
- Promoted Doubao to the same primary-product role as MoMood and Xingye; the generic `COMPARATOR_SUBSET_V1` preset remains reusable and is not bound to Doubao.
- Kept Replika as a legacy registry entry for historical project compatibility without exposing it as a new-project default.
- Synced Layer 2 and Layer 3 primary-product selection and replaced companion-only wording with a consumer-facing anthropomorphic conversational/companionship product scope.
- Preserved all criteria, prompts, experiment structures, Judge semantics, validity rules, check definitions, metric formulas and report-context metric definitions.
- Recorded that the product-set change occurred before FORMAL data collection; existing Replika project data is not migrated or renamed.

## v0.8.4 — Data portability safeguards

- Added independent `data_schema_version`, `app_version` and `code_commit` metadata to newly created project manifests while keeping legacy manifests readable.
- Added the read-only `scripts/verify_project_data.py` checker for project record counts, evidence-file counts, malformed JSONL/CSV records and missing/unsafe evidence references.
- Accepted both project-relative and repository-relative evidence references so a complete project directory can be copied to a new checkout without absolute-path coupling.
- Added regression tests for current and legacy project manifests, evidence resolution, missing evidence detection and loader compatibility.
- Documented the rule that future schema migrations must operate on a copied analysis project and preserve the formal frozen source data unchanged.

## v0.8.3 — Chinese-first workflow and review UI refinement

- Centralized Chinese-first labels for modules, official criterion names, C0/C1/C2 conditions, MR/MC/PC test structures, phases and L1–L5/R1–R2 turns without changing stored identifiers.
- Added inline screenshot previews in Data Explorer while retaining auditable stored evidence paths and missing-file warnings.
- Made collected COMPLETE raw cases the primary source for single-case and batch LLM Judge workflows; retained manual/ad-hoc input as an advanced secondary path.
- Added complete conversation and dynamic criterion context to Human Review, including target behaviors plus collapsed non-target and boundary rules.
- Fixed Human Review widget state isolation by including Case ID in form and field keys.
- Simplified human Case Validity to `VALID`/`INVALID`; normal automatic `VALID` cases no longer require a validity reason, while automatic `REVIEW` cases require explicit human confirmation and may receive an optional free-text invalidity note.
- Preserved frozen risk labels `FINDING`, `NO_FINDING`, `REVIEW`, all criteria/prompts, T/N rules, Judge schemas and metric definitions.
- Renamed global workflow navigation to “上一阶段 / 下一阶段” and multi-turn collection navigation to “上一轮”.
- Added regression coverage for centralized labels, non-`N/A` MR/MC/PC display structures and collected-case workflow helpers.

## v0.8.2 — Automatic validity screening and FORMAL adjudication policies

- Added conservative automatic Case Validity screening: normal complete responses default to `VALID`; only clearly empty/error/non-meaningful or explicitly unrelated responses enter `REVIEW`.
- Kept final `INVALID` as a human decision and kept Case Validity independent from frozen risk labels.
- Added project-level `FULL_ADJUDICATION` and `SAMPLED_ADJUDICATION` policies for FORMAL Benchmark projects.
- Added fixed-seed random/stratified sampling with a persisted `adjudication_sampling.json` plan and mandatory inclusion of risk `REVIEW`/auto-validity `REVIEW` cases.
- Added `analysis_label` and `adjudication_status` so unreviewed sampled cases use the LLM label without fabricating a human label.
- Restricted Judge–Human reliability to reviewed, valid cases and clarified report coverage for reviewed versus unreviewed analysis labels.
- Added regression coverage for automatic validity, sampled-plan determinism, forced review cases, and unreviewed final-result semantics.

## v0.8.1 — Post-smoke-test evidence, Judge and validity workflow

- Added inline screenshot previews and downloads to Data Explorer while preserving stored evidence paths and missing-file audit warnings.
- Made the single-case LLM Judge default to selecting completed cases from the active project's `raw_cases.jsonl`; retained manual / Ad-hoc input as a secondary mode.
- Added independent Case Validity values `VALID`, `INVALID`, and `REVIEW` without changing frozen risk labels `FINDING`, `NO_FINDING`, and `REVIEW`.
- Added validity reason/note fields to Human Adjudication and Final Results.
- Excluded INVALID and unresolved REVIEW cases from FORMAL dialogue metrics and Judge–Human reliability while preserving them for audit.
- Deleted the disposable `cg-v08-smoke-001` v0.8 smoke-test runtime data; source criteria and frozen experimental designs are unchanged.
- Added v0.8.1 regression coverage for evidence resolution, validity filtering and report exclusion counts.

## v0.8.0 — Smoke-test UX, granular Test Plans and execution safeguards

- Added Chinese-first bilingual navigation and key workflow labels.
- Added persistent workflow guidance with Previous/Next navigation and an explicit no-active-project exit state.
- Added project deletion for smoke-test cleanup with typed Project ID confirmation; deletion is confined to `data/projects/<project_id>/`.
- Reworked Test Plan composition so Core/HR-02 conditions are selected **per criterion** rather than through one global C0/C1/C2 filter.
- Added scenario-level selection for MR/MC/PC/single-turn tests, enabling targeted cases such as `MR-02` or `MC-01-A` without selecting the whole criterion family.
- Added Data Explorer for per-case transcript, raw JSON, evidence paths, Judge result and Human Adjudication inspection/download.
- Added explicit clean-context execution banners: every new case starts in a new/reset external-product conversation; turns inside one case remain continuous.
- Added prominent C0/C1/C2 Chinese/English condition banners, with C1 clearly marked as the Pressure condition.
- Replaced paragraph-style Judge presentation with structured summary label, checkpoints, target behaviors, evidence, rationale and raw JSON.
- Clarified `Override` in Human Review as a human label that supersedes a differing LLM auto-label while preserving an override reason.
- Fixed the first-click Save issue caused by textarea `on_change`/blur reruns; screenshot upload remains optional.
- Renamed the primary turn action from `Save & Copy Next` to `Save & Next`; browser auto-copy remains best-effort and the explicit Copy Prompt control is authoritative.
- Changed integrated-report Judge–Human Reliability to FORMAL cases only, preventing SMOKE κ/agreement from appearing beside zero FORMAL cases.
- Added role-specific LLM profile diagnostics without exposing API keys, making Judge/Evidence/Report profile separation visible in the UI.
- Added execution documentation and new regression tests for granular MR/MC selection, per-criterion conditions, formal reliability isolation and independent C0/C1/C2 case IDs.
- Current suite: 42 tests + 20 subtests pass.

## v0.7.0 — Provider-decoupled LLM roles and composable Test Plans

- Replaced DeepSeek-specific application coupling with a shared LLM Provider layer.
- Added OpenAI-style Chat Completions, OpenAI Responses-compatible and Anthropic Messages adapters with local JSON-schema validation where required.
- Defined four independent LLM roles: Dialogue Judge, Dialogue Report Writer, Layer 3 Evidence Assistant and Integrated Report Writer. Each role may use a different provider/model or share one.
- Kept BYOK keys session-only and added role-scoped server profiles; legacy DeepSeek environment variables remain a migration fallback for Judge/Evidence.
- Added lightweight server-funded LLM kill switch, per-day and per-session call ceilings, plus secret-free usage metadata logging.
- Removed product-level criterion allowlists. Product identity and test coverage are now independent.
- Added persistent Test Plans with `FULL_BENCHMARK`, `BENCHMARK_SUBSET` and `CUSTOM` coverage types.
- Moved the prior comparator subset into `config/test_plan_presets.json` as an editable/reusable preset rather than a Doubao-specific restriction.
- Propagated Test Plan coverage metadata into raw/final/report context so subset results cannot silently masquerade as full-benchmark results.
- Added deterministic Dialogue Report context/report and optional LLM Dialogue Report Writer.
- Added optional LLM Integrated Report Writer; Python remains authoritative for all metric calculations.
- Added `SearchProvider` extension interface for future Layer 3 retrieval while keeping autonomous web search disabled in the MVP.
- Added v0.7 architecture and decoupling tests. Current suite: 37 tests + 20 subtests pass.

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
