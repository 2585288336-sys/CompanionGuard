# CompanionGuard v0.5.0

CompanionGuard is a configurable regulatory evaluation MVP for anthropomorphic AI services. v0.5.0 extends the human-in-the-loop Data Collector with reusable collection queues, turn-level draft recovery, evidence linkage, one-click queue progression, and optional direct Judge handoff while preserving the frozen evaluation protocol.

The current end-to-end flow is:

```text
Data Collection (real product, human-in-the-loop)
        ↓
data/raw_cases.jsonl
        ↓
Run Test / Python Judge Engine
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
Results Dashboard (FORMAL phase only)
```

The Collector and Judge are deliberately decoupled. Data collection does not require a Judge API key and can continue when DeepSeek is unavailable.

## Frozen evaluation structures

Regulatory criteria remain configuration, not application code. The app dynamically loads `criteria/*.json` and routes by each criterion's `judge_template` field. The four existing Judge templates are unchanged:

- `core_l1_l5`
- `hr02_crisis`
- `mr_minor_relationship`
- `single_turn_regulatory_content`

The Data Collector mirrors those structures without criterion-specific Python branches:

- Core / HR-02 `C0`: one consolidated L1–L4 prompt → A4, then L5 → A5.
- Core / HR-02 `C1`: same consolidated L1–L4 prompt, then the frozen `pressure_variant.L5` → A5.
- Core / HR-02 `C2`: L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5.
- MR: R1 → A_R1 → R2 → A_R2.
- MC / PC / other single-turn regulatory probes: prompt → A1.

If a core criterion does not contain a frozen `pressure_variant.L5` in its current criteria JSON, CompanionGuard does not invent a C1 prompt and does not expose C1 for that criterion. This preserves the frozen-config boundary.

## Project layout

```text
CompanionGuard/
├── companionguard_judge/          # reusable Judge engine
│   ├── client.py
│   ├── prompts.py
│   ├── schemas.py
│   ├── validation.py
│   ├── pipeline.py
│   └── cli.py
├── companionguard_app/
│   ├── cases.py                   # existing Judge case templates
│   ├── collector.py               # collection plans, case IDs, raw-case construction
│   ├── collector_storage.py       # session/raw/evidence persistence
│   ├── collector_ui.py            # Data Collection Streamlit view
│   ├── config.py
│   ├── metrics.py
│   ├── service.py                 # app ↔ Judge orchestration
│   ├── storage.py                 # Judge/adjudication/final-result persistence
│   └── ui.py                      # Run Test / Human Review / Results
├── config/
│   └── collector.json             # products, phases, product test restrictions
├── criteria/                      # independent frozen rule configuration
├── data/                          # runtime data; ignored by Git
├── examples/
├── tests/
├── streamlit_app.py
├── judge_runner.py
└── pyproject.toml
```

`criteria/` remains the rules layer. `config/collector.json` contains collection logistics such as product definitions and the frozen 豆包 comparator allowlist. Runtime experiment records are stored only under `data/`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For Judge execution, set a DeepSeek key through an environment variable:

```bash
export DEEPSEEK_API_KEY="YOUR_KEY"
```

Or copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` for local deployment. Never commit the real key. BYOK keys supplied in the UI remain session-only and are not written to JSONL, CSV, logs, or Git.

## Run the web MVP

```bash
streamlit run streamlit_app.py
```

The MVP now has four views.

### 1. Run Test

Run an individual case or a batch through the existing DeepSeek Judge. Batch mode can now read `data/raw_cases.jsonl` directly, so completed Collector cases do not need to be re-uploaded or manually converted.

### 2. Data Collection

The Collector is the primary real-product acquisition workflow:

1. Select Product.
2. Select Criterion / Scenario.
3. Select Condition when applicable.
4. Select Phase and Run.
5. Start the session.
6. Copy the fixed prompt shown by CompanionGuard.
7. Send it in the real product.
8. Paste the model response exactly as shown.
9. Click `Save & Copy Next` (best-effort clipboard copy; browsers may require the visible Copy Prompt button).
10. Repeat until the case is complete, then optionally choose `Send This Case to Judge`.

Each saved response is persisted immediately to `data/collection_sessions.jsonl`. Exiting the page leaves the session `IN_PROGRESS`; it can be resumed after refresh or restart. The final turn triggers Judge-compatibility validation and writes one complete case to `data/raw_cases.jsonl`.

The Collector never rewrites model text. It only checks whether the pasted response is empty; the original string is preserved verbatim.

Screenshots are optional supporting evidence. Uploaded images are saved under:

```text
data/evidence/<case_id>/
```

They are associated with the relevant response turn and their paths are written into `collection_trace[].evidence_files`. Multiple screenshots for one turn are numbered `_01`, `_02`, etc. Screenshot OCR / vision extraction is intentionally not part of the MVP; text copy remains the primary data path. See `docs/DATA_COLLECTION.md` for the evidence/archive convention.

### Collection Queue and high-throughput collection

The Data Collection page supports both **Collection Queue** and **Single Case** modes. A queue dynamically expands selected configured criteria into their frozen structures and chosen runs. It does not duplicate prompt text into queue configuration.

Queue workflow:

```text
Create Queue
  → Start / Resume Current Case
  → Copy Prompt
  → paste/send in external product
  → paste verbatim response
  → Save & Copy Next
  → ...
  → case COMPLETE
  → Next Case
```

The current case and turn are displayed prominently to reduce case/condition/turn mistakes. Queue state is persisted in `data/collection_queues.jsonl`. In-progress response drafts are persisted in `data/collection_sessions.jsonl` without advancing the turn.

`Save & Copy Next` uses a best-effort browser clipboard attempt after advancing. Browser security policy can block programmatic clipboard access; the next prompt always remains visible with an explicit `Copy Prompt` button as the reliable fallback.

After case completion, the user can either continue collecting or optionally `Send This Case to Judge`. Direct Judge handoff is never required for collection and uses the same session-only BYOK/environment key behavior as Run Test.

### 3. Human Review

Review successful auto-judgments and save:

- `auto_label`
- `human_label`
- `final_label`
- `override_reason`
- free-text review note

Formal analysis uses `final_label`.

### 4. Results

Official dashboard metrics and the Finding Matrix include only:

```text
phase == FORMAL
```

`SMOKE`, `CALIBRATION`, and legacy records without a phase remain inspectable but are excluded from official metrics.

## Products and phases

Collector phases are:

- `SMOKE`
- `CALIBRATION`
- `FORMAL`

The default is `SMOKE` to reduce accidental contamination of formal results.

Configured products are:

- MoMood
- 星野
- Replika
- 豆包
- Custom Product

豆包 is frozen as `General-purpose Anthropomorphic Comparator`. The Collector limits it to:

```text
DS-01
DS-02
FD-01
FD-03
HR-02
MR
```

This restriction is defined in `config/collector.json`, not in criterion-specific Python branches.

## Case IDs

Collector case IDs are stable and human-readable:

```text
MoMood_DS-01_C1_FORMAL_run01
MoMood_MR-02_NA_FORMAL_run01
Xingye_PC-01-A_NA_SMOKE_run01
```

The phase is included so a `SMOKE` run and a `FORMAL` run cannot silently collide. No hash or UUID is used.

## `raw_cases.jsonl` structure

A completed Collector case has this shape:

```json
{
  "case_id": "MoMood_DS-01_C0_FORMAL_run01",
  "criterion_id": "DS-01",
  "scenario_id": "DS-01",
  "condition": "C0",
  "product": "MoMood",
  "phase": "FORMAL",
  "run_number": 1,
  "collection_date": "2026-09-14",
  "collection_status": "COMPLETE",
  "conversation": [
    {"role": "user", "turn": "L1", "content": "..."},
    {"role": "user", "turn": "L2", "content": "..."},
    {"role": "user", "turn": "L3", "content": "..."},
    {"role": "user", "turn": "L4", "content": "..."},
    {"role": "assistant", "turn": "A4", "content": "...verbatim response..."},
    {"role": "user", "turn": "L5", "content": "..."},
    {"role": "assistant", "turn": "A5", "content": "...verbatim response..."}
  ],
  "collection_trace": [
    {
      "sequence": 1,
      "prompt_turn": "L1-L4",
      "response_turn": "A4",
      "prompt": "...exact consolidated prompt actually sent...",
      "response": "...verbatim response...",
      "saved_at": "...",
      "evidence_files": []
    }
  ],
  "metadata": {
    "source": "data_collector",
    "scenario_id": "DS-01",
    "phase": "FORMAL",
    "run_number": 1,
    "collection_date": "2026-09-14",
    "notes": "",
    "collection_status": "COMPLETE"
  }
}
```

`conversation` remains compatible with the existing Judge checkpoint logic. `collection_trace` preserves the exact real-product send/response sequence, including the consolidated L1–L4 message used in C0/C1.

## Runtime data files

```text
data/raw_cases.jsonl             # complete real-product raw cases
data/collection_sessions.jsonl   # resumable IN_PROGRESS/COMPLETE collection sessions
data/collection_queues.jsonl     # reusable collection queues and case status
data/evidence/                   # optional screenshots keyed by case_id
data/judge_results.jsonl         # structured Judge results
data/human_adjudication.csv      # human decisions / overrides
data/final_results.csv           # merged adjudicated records
```

No database is required for the current MVP.

## First real case walkthrough

Example: collect `MoMood / DS-01 / C0 / FORMAL / Run 1`.

1. Start the app with `streamlit run streamlit_app.py`.
2. Open `Data Collection`.
3. Choose `MoMood`.
4. Choose `DS-01`.
5. Scenario remains `DS-01`.
6. Choose `C0`.
7. Set Phase to `FORMAL` and Run to `1`.
8. Click `Start / Resume Session`.
9. CompanionGuard shows Turn 1 of 2, `L1-L4 → A4`, and the exact consolidated prompt.
10. Click `Copy Prompt`, send it in MoMood, copy the complete product response, paste it into `Paste model response exactly as shown`, and click `Save & Next`.
11. CompanionGuard shows `L5 → A5`. Repeat the send/copy/paste step.
12. After the second save, the case is marked `COMPLETE`, validated against the existing Judge input contract, and appended to `data/raw_cases.jsonl`.
13. Open `Run Test` → `批量JSONL` → `Collected raw_cases.jsonl` to Judge collected cases later.

No JSON editing is required at any point.

## Validation and tests

```bash
python -m unittest discover -s tests -v
python judge_runner.py --input examples/sample_cases.jsonl --criteria-dir criteria --dry-run
```

Collector tests cover:

- C0 consolidated acquisition;
- C1 frozen pressure prompt use;
- C2 five-turn acquisition;
- HR-02 structure;
- MR two-turn structure;
- MC/PC single-turn structure;
- 豆包 allowlist enforcement;
- readable phase-aware case IDs;
- verbatim response preservation;
- session persistence/resume;
- duplicate raw-case prevention;
- evidence association by case ID;
- Judge dry-run compatibility of Collector output.

## Git versioning

- `v0.1.0`: initial Judge runner snapshot
- `v0.2.0`: simplified structured Judge engine
- `v0.3.0`: Streamlit MVP, human adjudication and results dashboard
- `v0.4.0`: real-product Data Collector, resumable sessions, raw-case pipeline and FORMAL phase separation
