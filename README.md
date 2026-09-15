# CompanionGuard v0.6.0

CompanionGuard is a configurable regulatory testing platform for anthropomorphic AI services. v0.6.0 upgrades the earlier single-workspace MVP into a project-scoped three-layer testing system while preserving the frozen CompanionGuard v4 dialogue benchmark and Judge logic.

## Platform model

Each **Test Project / 测试项目** is an isolated evaluation batch with its own products, dialogue cases, screenshots, Judge results, human adjudication, Layer 2 observations, Layer 3 documentary evidence, reliability analysis and reports.

```text
Test Project
├── Products
├── Layer 1 · Dialogue Behavioral Testing
│   ├── Data Collection
│   ├── LLM Judge
│   ├── Human Adjudication
│   ├── Judge–Human Reliability
│   └── Dialogue Results
├── Layer 2 · Product Safeguard Checks
├── Layer 3 Lite · Public Compliance Evidence Audit
└── Integrated Report
```

Runtime records are isolated under:

```text
data/projects/<project_id>/
├── project.json
├── raw_cases.jsonl
├── collection_sessions.jsonl
├── collection_queues.jsonl
├── judge_results.jsonl
├── human_adjudication.csv
├── final_results.csv
├── layer2_product_safeguards.jsonl
├── layer3_public_evidence.jsonl
├── evidence/
│   ├── dialogue/
│   ├── layer2/
│   └── layer3/
└── reports/
```

`data/projects/` is runtime experimental data and is ignored by Git.

## Layer 1 · Dialogue Behavioral Testing

The frozen dialogue benchmark remains configuration-driven through `criteria/*.json`. The application does not hard-code criterion-specific decisions.

Four Judge templates remain unchanged:

- `core_l1_l5`
- `hr02_crisis`
- `mr_minor_relationship`
- `single_turn_regulatory_content`

Collection structures remain frozen:

- **C0｜集中式基线**: consolidated L1–L4 → A4, then canonical L5 → A5.
- **C1｜集中式压力**: same L1–L4 → A4, then frozen `pressure_variant.L5` → A5.
- **C2｜顺序多轮**: L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5.
- **MR**: R1 → A_R1 → R2 → A_R2.
- **MC / PC**: single-turn prompt → A1.

Criteria prompt-set version remains `criteria/VERSION = 0.3.1`.

### Data Collector

The researcher never edits JSON manually. The Collector:

1. knows the active Test Project and product;
2. loads the fixed prompt from criterion configuration;
3. shows the current case / condition / run / turn prominently;
4. lets the researcher copy the prompt to a real external product;
5. accepts the verbatim model response;
6. optionally accepts turn-level screenshot evidence;
7. stores and resumes in-progress drafts;
8. advances with `Save & Copy Next`;
9. supports a persistent Collection Queue and one-click `Next Case`;
10. automatically builds a Judge-compatible raw case when complete.

Text copy is the primary evidence path. OCR is intentionally not part of the MVP.

### LLM Judge: what the Python Judge Engine actually is

The Judge Engine is **not an agent** and does **not require an evaluation harness**. It is a deterministic Python orchestration pipeline:

```text
raw case
  ↓
load criterion JSON
  ↓
read judge_template
  ↓
select one of 4 fixed Judge system prompts + JSON schemas
  ↓
construct criterion-bound payload
  ↓
DeepSeek API call
  ↓
JSON-schema validation
  ↓
business / semantic validation
  ↓
judge_results.jsonl
```

The large model performs the semantic classification. Python controls routing, rule loading, validation, retries and persistence. This is intentionally simpler and more auditable than an agent architecture.

A harness such as Inspect/EvalScope could later be used as an external execution framework, but it is unnecessary for the current CompanionGuard workflow because the project already has its own case format, criterion router, Judge schemas, validation and batch runner.

### Demo and BYOK access

When deployed as a Streamlit web service:

- **Demo / server Judge**: `DEEPSEEK_API_KEY` is stored server-side in environment variables or Streamlit secrets. A web user clicks Judge, but never receives the key.
- **BYOK**: the user enters their own key for the current Streamlit session. It is not written to JSONL, CSV, logs or Git.

The current v0.6 interface is a web UI, not a public REST API. No FastAPI/auth service has been added. If programmatic third-party API access becomes necessary later, it should be a separate deployment step rather than changing the frozen Judge semantics.

### Human Adjudication

Benchmark Mode preserves the frozen v4 requirement of **100% human adjudication**. Custom Mode may expose full review, random sampling or criterion-stratified sampling views.

Human review records:

- auto label;
- human label;
- final label;
- override reason;
- review note.

Official benchmark analysis uses `final_label`.

### Reliability

The dedicated Reliability page computes:

- Judge–Human Exact Agreement;
- Cohen's κ over `FINDING / NO_FINDING / REVIEW`;
- Finding Precision;
- Finding Recall;
- 3×3 confusion matrix.

## Layer 2 · Product Safeguard Checks

Layer 2 evaluates **observable product mechanisms**, not model dialogue. It uses 22 frozen checks in `config/layer2_checks.json` and the four evidence states:

- `OBSERVED`
- `NOT_OBSERVED`
- `NOT_TRIGGERED`
- `NOT_VERIFIABLE`

The page includes the standardized nine-step product inspection path and records product/version/platform metadata, status, evidence summary, notes and screenshot evidence.

The 22 checks are:

`REG-01`, `REG-02`, `MIN-01`–`MIN-06`, `ELD-01`–`ELD-03`, `CRI-01`, `CRI-02`, `AID-01`, `DEP-01`, `TIME-01`, `EXIT-01`, `EXIT-02`, `DATA-01`, `DATA-02`, `REDRESS-01`, `REDRESS-02`.

Layer 2 does not generate a 0–100 compliance score.

## Layer 3 Lite · Public Compliance Evidence Audit

Layer 3 Lite evaluates **public documentary evidence** for six representative requirements in `config/layer3_checks.json`:

- `L3-01` third-party provision of interaction data and conditions;
- `L3-02` sensitive interaction data used for model training and separate consent;
- `L3-03` under-14 personal information / guardian consent rules;
- `L3-04` public crisis / self-harm response policy;
- `L3-05` appeal / complaint / reporting process and feedback explanation;
- `L3-06` public algorithm filing status.

Documentary states are:

- `DOCUMENTED`
- `PARTIALLY_DOCUMENTED`
- `NOT_FOUND`
- `NOT_PUBLICLY_VERIFIABLE`

The page supports manual evidence entry plus optional DeepSeek **evidence extraction assist**. That assist is not one of the four dialogue Judge templates and does not make the final determination. Human documentary status is authoritative.

Benchmark Mode intends Layer 3 Lite for the three primary products rather than the broader Layer 2 sample.

Layer 3 does not calculate a compliance rate.

## Integrated Report

The report module deterministically combines:

- Layer 1 FORMAL dialogue results;
- pressure and multi-turn gaps;
- per-module and per-product dialogue summaries;
- Judge–Human reliability;
- Layer 2 Product Safeguard Matrix records;
- Layer 3 Compliance Evidence Matrix records.

It deliberately does **not** create a single 0–100 safety/compliance score or claim a formal legal compliance determination.

## Project layout

```text
CompanionGuard_v0.6.0/
├── companionguard_judge/          # criterion-bound LLM Judge engine
├── companionguard_app/
│   ├── collector.py               # frozen collection-plan expansion
│   ├── collector_storage.py       # queue/session/raw/evidence persistence
│   ├── collector_ui.py
│   ├── projects.py                # project-scoped data paths and manifests
│   ├── audits.py                  # Layer 2/3 structured evidence persistence
│   ├── reliability.py             # agreement/kappa/precision/recall
│   ├── reporting.py               # deterministic integrated Markdown report
│   ├── platform_ui.py             # project/layer/reliability/report pages
│   ├── service.py                 # UI ↔ Judge orchestration
│   ├── storage.py                 # Judge/adjudication/final result persistence
│   └── ui.py                      # Layer 1 Judge/Review/Results
├── config/
│   ├── collector.json
│   ├── layer2_checks.json
│   └── layer3_checks.json
├── criteria/                      # frozen Dialogue rules and prompts
├── data/                          # runtime data only
├── docs/
├── tests/
├── streamlit_app.py
├── judge_runner.py
└── pyproject.toml
```

## Install and run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
streamlit run streamlit_app.py
```

For server-side Demo Judge:

```bash
export DEEPSEEK_API_KEY="YOUR_SERVER_KEY"
```

Never commit real API keys.

## First use

1. Open `Test Projects`.
2. Create a project name / project ID.
3. Select configured products and/or add custom products.
4. Open `Layer 1 · Data Collection`.
5. Build one or more product Collection Queues.
6. Collect real replies and screenshots.
7. Run Judge immediately per completed case or later from `Layer 1 · LLM Judge`.
8. Complete `Layer 1 · Human Review`.
9. Inspect `Layer 1 · Reliability` and `Dialogue Results`.
10. Enter Layer 2 product observations.
11. Enter Layer 3 public evidence.
12. Download the `Integrated Report`.

## Validation

```bash
python -m pytest -q
python judge_runner.py --input examples/sample_cases.jsonl --dry-run
```

v0.6.0 validation in the build environment:

```text
31 tests passed, 20 subtests passed
Judge dry-run OK: 4 cases, 22 criteria loaded
```

The build container does not include Streamlit, so browser-level UI smoke testing must be performed in a local/deployed environment after `pip install -e .`.
