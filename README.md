# CompanionGuard v4 — DeepSeek Judge Runner

This folder is the runnable Judge layer for the frozen CompanionGuard v4 criteria.

## 1. What it does

`judge_runner.py`:

1. reads one case per line from JSONL;
2. loads the frozen `criteria/*.json`;
3. routes by `judge_template`:
   - `core_l1_l5`
   - `hr02_crisis`
   - `mr_minor_relationship`
   - `single_turn_regulatory_content`
4. calls DeepSeek Chat Completions in JSON Output mode;
5. validates the returned JSON against a local schema;
6. performs semantic consistency checks;
7. verifies that every evidence quote is an exact substring of an actual assistant/model response;
8. automatically retries invalid Judge output;
9. writes one auditable result wrapper per case to JSONL.

The script deliberately does **not** save DeepSeek `reasoning_content`.

## 2. Environment

Python 3.10+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your API key:

macOS / Linux:

```bash
export DEEPSEEK_API_KEY="YOUR_KEY"
```

PowerShell:

```powershell
$env:DEEPSEEK_API_KEY="YOUR_KEY"
```

Optional custom endpoint:

```bash
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

## 3. First run: local dry-run

Run from this project folder:

```bash
python judge_runner.py \
  --input examples/sample_cases.jsonl \
  --criteria-dir criteria \
  --output outputs/sample_results.jsonl \
  --dry-run
```

No API credits are used. This validates case routing and checkpoints.

## 4. Small API smoke test

```bash
python judge_runner.py \
  --input examples/sample_cases.jsonl \
  --criteria-dir criteria \
  --output outputs/sample_results.jsonl \
  --model deepseek-v4-pro \
  --thinking disabled \
  --temperature 0 \
  --limit 4
```

Recommended MVP default:
- model: `deepseek-v4-pro`
- thinking: `disabled`
- temperature: `0`
- workers: `1` for the first smoke test
- validation retries: `2`

Reason: the Judge is a bounded classifier and consistency matters. You can separately calibrate
`--thinking enabled --reasoning-effort high` against your human labels before freezing the final Judge configuration.

## 5. Batch run

```bash
python judge_runner.py \
  --input YOUR_CASES.jsonl \
  --criteria-dir criteria \
  --output outputs/judge_results.jsonl \
  --model deepseek-v4-pro \
  --thinking disabled \
  --temperature 0 \
  --workers 1
```

If the first batch is stable and your API rate limit permits it, increase `--workers` cautiously.

The runner resumes automatically: already-written rows with `status="ok"` are skipped.
Use `--overwrite` only when you intentionally want to rerun everything.

## 6. Batch input format

Each JSONL line is one case:

```json
{
  "case_id": "UE-01_C0_MoMood_run1",
  "criterion_id": "UE-01",
  "condition": "C0",
  "product": "MoMood",
  "conversation": [
    {"role": "user", "turn": "L1", "content": "..."},
    {"role": "assistant", "turn": "A4", "content": "..."},
    {"role": "user", "turn": "L5", "content": "..."},
    {"role": "assistant", "turn": "A5", "content": "..."}
  ],
  "metadata": {}
}
```

Default checkpoints:
- Core / HR-02: `A4` and `A5`
- MR: `A_R1` and `A_R2`
- Single-turn: `A1`

If your exported data uses different turn labels, override them:

```json
"checkpoints": {
  "pre_trigger": "model_before_trigger",
  "post_trigger": "model_after_trigger"
}
```

For MR:

```json
"checkpoints": {
  "r1": "model_r1",
  "r2": "model_r2"
}
```

For single-turn:

```json
"checkpoints": {
  "single_turn_response": "model_response"
}
```

For MC, set `category` to the subcategory such as `MC-01`, `MC-02`, or `MC-03`.
For PC files, `criterion_id` such as `PC-01` is used as category by default.

See:
- `batch_input_schema.json`
- `examples/sample_cases.jsonl`

## 7. Output format

Every output line contains:
- case provenance;
- criterion/template;
- DeepSeek configuration;
- prompt version;
- criterion SHA-256;
- validated Judge result;
- raw final JSON content;
- token usage if returned by API;
- retry log;
- errors if unresolved.

Example wrapper:

```json
{
  "case_id": "UE-01_C0_MoMood_run1",
  "criterion_id": "UE-01",
  "judge_template": "core_l1_l5",
  "status": "ok",
  "judge": {
    "provider": "DeepSeek",
    "model": "deepseek-v4-pro",
    "thinking": "disabled",
    "temperature": 0.0,
    "prompt_version": "companionguard-v4-judge-prompts-2026-09-14"
  },
  "result": {
    "...": "template-specific validated JSON"
  },
  "error": null
}
```

See `batch_output_schema.json`.

## 8. Human adjudication

Do not treat `result` as the final gold label.

For the v4 MVP retain:
- `auto_label`
- `human_label`
- `final_label`
- `override_reason`

Formal analysis should use `final_label`.

Recommended override codes:
- `MISSED_TARGET_BEHAVIOR`
- `FALSE_POSITIVE_TARGET_BEHAVIOR`
- `MISREAD_CONTEXT`
- `BOUNDARY_RULE_MISAPPLIED`
- `EVIDENCE_NOT_SUPPORTED`
- `REVIEW_REQUIRED`
- `OTHER`

## 9. Freeze rule

After the calibration set is complete, freeze:
- DeepSeek model name;
- thinking mode;
- reasoning effort / temperature;
- all four system prompts;
- criterion JSON files;
- output schemas;
- runner version.

Do not silently change any of these halfway through the formal batch.

## 10. Important implementation note

DeepSeek JSON Output guarantees valid JSON formatting, but it does not replace your local
CompanionGuard schema/semantic checks. The runner therefore validates output locally and retries
when the Judge:
- invents a T-code;
- produces an inconsistent `final_label`;
- uses an invalid transition;
- hallucinates an evidence quote;
- uses the wrong case/category identifier.
