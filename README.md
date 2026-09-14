# CompanionGuard v0.3.0

CompanionGuard is a configurable regulatory evaluation MVP for anthropomorphic AI services.

Its frozen MVP flow is:

```text
Streamlit Frontend
        ↓
Python Judge Engine
        ↓
criteria/*.json
        ↓
DeepSeek API
        ↓
data/judge_results.jsonl
        ↓
Human Adjudication
        ↓
data/final_results.csv
        ↓
Dashboard
```

## What is configurable

Regulatory criteria are configuration, not application code. The app dynamically loads `criteria/*.json` and routes each criterion using its `judge_template` field. Adding a compatible criterion JSON does not require adding a new `if criterion == ...` branch.

Four Judge **templates** are currently supported; the Judge **model** is DeepSeek:

- `core_l1_l5`
- `hr02_crisis`
- `mr_minor_relationship`
- `single_turn_regulatory_content`

## Project layout

```text
companionguard_v4_judge/
├── companionguard_judge/     # reusable Judge engine
│   ├── client.py
│   ├── prompts.py
│   ├── schemas.py
│   ├── validation.py
│   ├── pipeline.py
│   └── cli.py
├── companionguard_app/       # application layer for the Streamlit MVP
│   ├── cases.py              # build cases from criterion configuration
│   ├── config.py
│   ├── metrics.py
│   ├── service.py            # app ↔ Judge orchestration
│   ├── storage.py            # JSONL / CSV persistence
│   └── ui.py                 # three MVP views
├── criteria/                 # independent frozen rule configuration
├── data/                     # generated outputs; ignored by Git
├── examples/
├── tests/
├── streamlit_app.py          # web entry point
├── judge_runner.py           # CLI entry point
└── pyproject.toml
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Set the DeepSeek key through an environment variable:

```bash
export DEEPSEEK_API_KEY="YOUR_KEY"
```

Or copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill the key for a local Streamlit deployment. Never commit the real secrets file.

## Run the web MVP

```bash
streamlit run streamlit_app.py
```

The MVP has three views:

### 1. Run Test

- dynamically select a frozen criterion;
- choose benchmark scenario/condition;
- paste actual model output into a generated conversation template;
- run one case through DeepSeek Judge;
- or upload a JSONL batch.

For `C2` multi-turn cases, keep the full `A1–A5` history in the conversation JSON.

### 2. Human Review

Review each successful auto-judgment and save:

- `auto_label`
- `human_label`
- `final_label`
- `override_reason`
- free-text review note

Formal analysis uses `final_label`.

### 3. Results

The dashboard reads `data/final_results.csv` and shows:

- adjudicated case count;
- Finding / Review counts;
- Overall Macro Finding Rate when all five frozen modules have data;
- Pressure Robustness Gap (`C1 - C0`);
- Multi-turn Robustness Gap (`C2 - C0`);
- module Finding Rates;
- Finding Matrix;
- downloadable filtered CSV.

## Output files

Generated runtime data are intentionally simple and inspectable:

```text
data/judge_results.jsonl       # raw structured Judge results
data/human_adjudication.csv    # human decisions / overrides
data/final_results.csv         # merged formal-analysis table
```

No database is required for the 24-hour MVP.

## Why criteria are separate

The application does not encode `DS-01`, `HR-02`, etc. as product logic. Those live in JSON configuration. This keeps the same engine reusable for a future Custom Eval Mode: a user can define a new compatible criterion and run the same Judge → human review → dashboard workflow.

The current UI exposes Benchmark Mode only. Custom Eval authoring is intentionally deferred until after the competition MVP.

## Validation philosophy

DeepSeek Responses API structured output handles JSON shape. Local validation only enforces CompanionGuard semantics that JSON Schema cannot know, such as valid T-codes, label/transition consistency, and verbatim evidence grounding. There is no duplicate generic `jsonschema` layer.

## Tests

```bash
python -m unittest discover -s tests -v
python judge_runner.py --input examples/sample_cases.jsonl --criteria-dir criteria --dry-run
```

## Git versioning

- `v0.1.0`: original Judge runner snapshot
- `v0.2.0`: simplified structured Judge engine
- `v0.3.0`: Streamlit MVP, human adjudication and results dashboard

After Judge calibration, create a dedicated calibration tag and keep model, prompts, criteria and Judge settings frozen during the formal batch.
