# CompanionGuard v0.8.2

CompanionGuard is a configurable regulatory testing platform for anthropomorphic AI services. v0.8.2 is the post-smoke-test adjudication release. It preserves the frozen CompanionGuard v4 dialogue benchmark while adding conservative automatic case-validity screening and pre-registered FORMAL human-adjudication policies.

## Platform model

Each **Test Project / 测试项目** is an isolated evaluation batch:

```text
Test Project
├── Products
├── Layer 1 · Dialogue Behavioral Testing
│   ├── Test Plan / Collection Queue
│   ├── Data Collection
│   ├── LLM Judge
│   ├── Human Adjudication
│   ├── Judge–Human Reliability
│   ├── Dialogue Results
│   └── Dialogue Report
├── Layer 2 · Product Safeguard Checks
├── Layer 3 Lite · Public Compliance Evidence Audit
└── Integrated Report
```

Runtime data is isolated under `data/projects/<project_id>/`. SMOKE/CALIBRATION/FORMAL share a project file set but remain explicitly phase-tagged; official benchmark metrics use `phase == FORMAL`. For cleaner experiments, use a separate project for UI smoke tests and formal evaluation.

## v0.8 smoke-test fixes

- **Clean-context rule:** every new case starts in a new/reset external-product conversation. C0, C1, C2, different criteria and different runs are independent cases; turns inside one case stay in the same conversation.
- **Granular Test Plans:** Core/HR-02 conditions are selectable per criterion; MR/MC/PC scenarios are selectable individually (for example MR-02 or MC-01-A only).
- **Chinese-first bilingual UI:** main navigation, Test Plan modules, criteria, conditions and key workflow actions display Chinese first with English assistance.
- **Structured Judge output:** summary label, checkpoint labels, T-codes, evidence and rationale are rendered separately rather than as one paragraph.
- **Data Explorer:** inspect transcript, raw case JSON, screenshot links and Judge/Human Review state for each completed case; JSON can be downloaded without manual editing.
- **Project deletion:** smoke projects can be permanently removed from the Test Projects page with typed-ID confirmation.
- **Workflow navigation:** persistent Previous/Next controls and active-project exit make the next step explicit without forcing a rigid wizard.
- **Save-first-click fix:** response draft persistence no longer uses a textarea blur callback that could consume the first Save click; screenshot evidence remains optional.
- **Formal-report isolation:** integrated report reliability now uses FORMAL adjudicated cases only, so SMOKE agreement/κ cannot appear beside zero FORMAL cases.

## v0.8.1 post-smoke-test fixes

- **Screenshot previews:** Data Explorer renders linked dialogue screenshots inline, with download controls and a clear missing-file warning; stored evidence paths remain auditable.
- **Collected-case Judge:** the single-case Judge now defaults to selecting a completed case from the active project's `raw_cases.jsonl`. Manual / Ad-hoc input remains available as a secondary mode.
- **Separate Case Validity:** Human Review records `VALID`, `INVALID`, or `REVIEW` independently from the frozen `FINDING`, `NO_FINDING`, and `REVIEW` risk labels.
- **Metric exclusion:** only `FORMAL` + `VALID` cases enter dialogue risk metrics and Judge–Human reliability. INVALID/REVIEW cases remain in final results and audit views.
- **Smoke data cleanup:** the v0.8 smoke-test project data is disposable runtime data and is not part of the v0.8.1 code release.

## v0.8.2 adjudication fixes

- **Automatic case-validity screening:** normal, complete, meaningful model responses receive `auto_case_validity=VALID`. Empty responses, placeholders, obvious system errors, non-meaningful output, and explicit Judge notes that a response is unrelated receive `REVIEW` for human validity confirmation. The screen never assigns final `INVALID`.
- **Validity is not risk review:** an ordinary case can show `Auto Case Validity = VALID` while still requiring the frozen risk-label Human Adjudication in `FULL_ADJUDICATION` mode. Risk `REVIEW` is not automatically treated as invalidity.
- **FORMAL adjudication policies:** Benchmark projects choose `FULL_ADJUDICATION` or `SAMPLED_ADJUDICATION` at creation. Sampled projects freeze a fixed-seed `RANDOM_SAMPLE` or `STRATIFIED_SAMPLE` plan before reviewing; all FORMAL risk-label `REVIEW` and auto-validity `REVIEW` cases are forced into the human set.
- **Clean analysis semantics:** reviewed cases carry `human_label`, `final_label`, and `adjudication_status=REVIEWED`; sampled but unreviewed cases carry no human label and use `analysis_label=auto_label`. Reliability uses reviewed cases only.

## Layer 1 · frozen dialogue structures

The benchmark is driven by `criteria/*.json`; application code does not hard-code criterion-specific decisions.

- **C0｜集中式基线**: consolidated L1–L4 → A4, then canonical L5 → A5.
- **C1｜集中式压力**: identical L1–L4 → A4, then frozen `pressure_variant.L5` → A5.
- **C2｜顺序多轮**: L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5.
- **MR**: R1 → A_R1 → R2 → A_R2.
- **MC / PC**: single-turn prompt → A1.

Four dialogue Judge templates remain unchanged: `core_l1_l5`, `hr02_crisis`, `mr_minor_relationship`, `single_turn_regulatory_content`.

### Product selection and Test Plans

A **Product** is only the object being tested. It no longer determines which criteria may run.

A **Test Plan** independently specifies:

- product;
- criteria;
- **per-criterion C0/C1/C2 selection** where applicable;
- **scenario-level selection** for MR/MC/PC/single-turn tests;
- run numbers;
- phase;
- coverage type.

Coverage types:

- `FULL_BENCHMARK`
- `BENCHMARK_SUBSET`
- `CUSTOM`

A benchmark subset is a valid targeted evaluation, but its aggregate result must not be presented as directly equivalent to a full CompanionGuard benchmark run.

`config/test_plan_presets.json` includes:

- `COMPANIONGUARD_FULL`;
- `COMPARATOR_SUBSET_V1` (the earlier comparator subset, now reusable for any product);
- `CUSTOM`.

Presets are starting points, not product restrictions.

### Data Collector

The researcher never edits JSON manually. The Collector controls case/turn alignment, fixed prompts, queue state, draft recovery, screenshot linkage and Judge-ready raw case creation. The researcher only sends prompts in the real external product and pastes verbatim replies back into CompanionGuard. **Start every new case in a new/reset product conversation; keep all turns of that case in the same conversation.**

Text copy is the primary response source. Screenshot evidence is optional and linked to the exact response turn. OCR is intentionally excluded from the MVP.

## Four LLM roles, one provider infrastructure

CompanionGuard now has **four independent LLM roles**:

1. **Dialogue Judge** — criterion-bound classification of product dialogue.
2. **Dialogue Report Writer** — prose report from deterministic Layer 1 report context.
3. **Layer 3 Evidence Assistant** — extracts/suggests public documentary evidence status from supplied source text.
4. **Integrated Report Writer** — prose report from deterministic cross-layer report context.

They share one LLM provider abstraction, but they do **not** have to use the same provider or model. For example:

```text
Judge                  → DeepSeek
Dialogue Report Writer → Claude
Evidence Assistant     → Qwen
Integrated Report      → another configured model
```

or all four may use one model.

Supported adapter types in v0.8:

- OpenAI-style Chat Completions (broad compatibility);
- OpenAI Responses-compatible APIs;
- Anthropic Messages API.

Adding another vendor should require only a new adapter implementing the common JSON/text generation interface. Judge, Evidence and Report business logic must not branch on vendor names.

### Judge is not an Agent and does not require a harness

```text
raw case
→ criterion JSON
→ fixed Judge template/schema
→ configured Judge LLM
→ JSON-schema validation
→ CompanionGuard semantic validation
→ judge_results.jsonl
```

Python owns routing, rules, schema/semantic validation, retry boundaries and persistence. The LLM performs semantic classification. No autonomous planning/tool-selection loop is used.

Inspect/EvalScope/lm-evaluation-harness are therefore optional future integrations, not dependencies of the current Judge.

### Server model and BYOK

Every LLM role can use:

- **CompanionGuard Server Model** — server-side role profile; the browser never receives the API key.
- **BYOK** — user selects a supported provider adapter, base URL/model and provides a session-only key.

BYOK keys are never written to project JSONL/CSV, `project.json`, usage logs or Git.

Server-funded LLM calls have a lightweight operator guard:

```text
COMPANIONGUARD_SERVER_LLM_ENABLED
COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT
COMPANIONGUARD_SERVER_LLM_SESSION_CALL_LIMIT
```

Usage logs contain role/provider/model/token metadata only, never secrets. Full user accounts/RBAC/billing remain intentionally deferred until a true multi-user public deployment.

## Human adjudication and reliability

Benchmark FORMAL mode supports two project-frozen policies: `FULL_ADJUDICATION` and `SAMPLED_ADJUDICATION`. The former gives every FORMAL case a human risk-label decision; the latter uses a pre-registered sample plus mandatory review of risk/validity `REVIEW` cases. A project must not change its policy or sampling rule after formal evaluation begins.

Reliability reports:

- Judge–Human Exact Agreement;
- Cohen's κ over `FINDING / NO_FINDING / REVIEW`;
- Finding Precision;
- Finding Recall;
- 3×3 confusion matrix.

Case validity has an automatic screen and a human final decision. Normal cases start at `auto_case_validity=VALID`; clearly unusable or explicitly unrelated cases start at `REVIEW`; only a human decision can set `final_case_validity=INVALID`. Validity never changes the frozen risk label and only `FORMAL` + `final_case_validity=VALID` records enter official risk metrics. INVALID and unresolved REVIEW records remain available for audit.

FORMAL Benchmark projects support two frozen adjudication protocols:

- `FULL_ADJUDICATION`: every FORMAL case receives human risk-label adjudication; this remains the default for research-scale runs.
- `SAMPLED_ADJUDICATION`: all FORMAL cases receive the LLM Judge label, while a pre-registered fixed-seed random or stratified sample receives human adjudication. All FORMAL risk-label REVIEW and auto-validity REVIEW cases are mandatory human cases. Unreviewed cases are never given a fabricated `human_label`.

## Dialogue reporting

Python computes all metrics and builds an authoritative structured report context. The optional Dialogue Report Writer only turns that context into prose.

v0.7 intentionally ships only a minimal grounded reporting prompt. External high-quality writing/report skills are **not** bundled yet; they can later replace `prompts/reporting/dialogue_report.md` without modifying the Judge.

## Layer 2 · Product Safeguard Checks

Layer 2 evaluates observable product mechanisms, not dialogue. It uses the frozen 22 checks in `config/layer2_checks.json` and four product-evidence states:

- `OBSERVED`
- `NOT_OBSERVED`
- `NOT_TRIGGERED`
- `NOT_VERIFIABLE`

The standardized nine-step product inspection path and screenshot evidence remain supported. Layer 2 does not output a compliance score.

## Layer 3 Lite · Public Compliance Evidence Audit

Layer 3 Lite uses six checks (`L3-01`–`L3-06`) and four documentary states:

- `DOCUMENTED`
- `PARTIALLY_DOCUMENTED`
- `NOT_FOUND`
- `NOT_PUBLICLY_VERIFIABLE`

Current MVP flow:

```text
human-supplied official source text
→ Evidence Assistant LLM
→ evidence/status suggestion
→ human final documentary status
```

The Evidence Assistant is not a dialogue Judge and human review remains authoritative.

v0.7 adds a `SearchProvider` extension interface for future official-source retrieval, but the default search provider is explicitly disabled. Layer 3 therefore does **not** silently become a free-form web agent. A future search adapter should retrieve candidate official sources, then pass the retrieved source text through the existing Evidence Assistant + human review pipeline.

## Integrated reporting

The deterministic integrated report combines Layer 1 FORMAL results, reliability, Layer 2 observations and Layer 3 documentary evidence. The optional Integrated Report Writer receives only this structured context and writes prose.

It must not:

- recalculate metrics;
- invent evidence;
- collapse the three evidence layers;
- create a 0–100 safety/compliance score;
- make a formal legal compliance determination.

The external writing skill/template research requested by the project owner is intentionally deferred; `prompts/reporting/integrated_report.md` is a minimal safe placeholder that can later be replaced independently.

## Data layout

```text
data/projects/<project_id>/
├── project.json
├── test_plans.json
├── raw_cases.jsonl
├── collection_sessions.jsonl
├── collection_queues.jsonl
├── judge_results.jsonl
├── human_adjudication.csv
├── adjudication_sampling.json
├── final_results.csv
├── layer2_product_safeguards.jsonl
├── layer3_public_evidence.jsonl
├── evidence/
└── reports/
```

`human_adjudication.csv` and `final_results.csv` carry automatic/final validity, adjudication status, and analysis-label fields. `adjudication_sampling.json` records the frozen sampled case IDs, method, rate, strata, and random seed.

Global server LLM usage metadata is stored under ignored runtime `data/` and contains no API keys.

## Project layout

```text
CompanionGuard_v0.7.0/
├── companionguard_llm/            # provider profiles/adapters/guard/search extension
├── companionguard_judge/          # criterion-bound dialogue Judge
├── companionguard_app/            # Streamlit/domain/application services
├── config/
│   ├── collector.json
│   ├── test_plan_presets.json
│   ├── layer2_checks.json
│   └── layer3_checks.json
├── criteria/
├── prompts/reporting/             # replaceable report-writer prompts
├── data/                           # runtime only; Git-ignored
├── docs/
├── tests/
├── streamlit_app.py
└── pyproject.toml
```

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
streamlit run streamlit_app.py
```

A server Judge profile may be configured with role-specific environment variables, e.g.:

```bash
export COMPANIONGUARD_JUDGE_PROVIDER_TYPE="openai_responses"
export COMPANIONGUARD_JUDGE_PROVIDER_NAME="DeepSeek"
export COMPANIONGUARD_JUDGE_BASE_URL="https://api.deepseek.com"
export COMPANIONGUARD_JUDGE_MODEL="deepseek-v4-pro"
export COMPANIONGUARD_JUDGE_API_KEY="..."
```

The Evidence and two Report Writer roles use the same naming pattern with `EVIDENCE`, `DIALOGUE_REPORT` and `INTEGRATED_REPORT`.

## Validation

```bash
python -m pytest -q
python judge_runner.py --input examples/sample_cases.jsonl --criteria-dir criteria --dry-run
```

v0.7.0 build validation:

```text
37 tests passed, 20 subtests passed
Judge dry-run OK: 4 cases, 22 criteria loaded
```

The build container still does not provide a browser-level Streamlit environment, so final UI interaction smoke testing should be performed locally after `pip install -e .`.
