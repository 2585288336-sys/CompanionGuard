# CompanionGuard v4 DeepSeek Judge

A minimal, reproducible Judge pipeline for the frozen CompanionGuard v4 criteria.

## Design principles

- DeepSeek **Responses API + JSON Schema structured output** handles structural output constraints.
- Local code does **not** duplicate JSON Schema validation.
- Local validation is limited to project-specific semantics that JSON Schema cannot know:
  - T-code must exist in the selected criterion;
  - `final_label` and transition must agree with checkpoint labels;
  - evidence quote must occur verbatim in the actual assistant/model response;
  - single-turn `test_id/category` must match the current case.
- Human adjudication remains the final label source for formal analysis.
- Frozen criteria live in `criteria/*.json`; model/prompt settings should be frozen after calibration.

## Project layout

```text
companionguard_v4_judge/
├── companionguard_judge/
│   ├── client.py        # DeepSeek Responses API only
│   ├── prompts.py       # four frozen Judge system prompts
│   ├── schemas.py       # four provider-side output schemas
│   ├── validation.py    # semantic/evidence checks only
│   ├── pipeline.py      # batch orchestration
│   └── cli.py           # CLI arguments
├── criteria/            # frozen criterion JSON files
├── examples/            # JSONL examples
├── tests/               # standard-library unit tests
├── judge_runner.py      # thin entry point
├── pyproject.toml       # single dependency source
└── .env.example
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Set the key without committing it:

```bash
export DEEPSEEK_API_KEY="YOUR_KEY"
```

## Dry run first

```bash
python judge_runner.py \
  --input examples/sample_cases.jsonl \
  --criteria-dir criteria \
  --dry-run
```

Dry-run performs no API calls.

## Judge a small calibration batch

```bash
python judge_runner.py \
  --input examples/sample_cases.jsonl \
  --criteria-dir criteria \
  --output outputs/sample_results.jsonl \
  --model deepseek-v4-pro \
  --reasoning-effort none \
  --temperature 0
```

`reasoning-effort none` is the current deterministic calibration default. Compare it against a small human-labelled set before freezing the final configuration.

## Input JSONL

One case per line. Core example:

```json
{
  "case_id": "UE-01_C0_MoMood_run1",
  "criterion_id": "UE-01",
  "condition": "C0",
  "product": "MoMood",
  "conversation": [
    {"role": "user", "turn": "L4", "content": "..."},
    {"role": "assistant", "turn": "A4", "content": "..."},
    {"role": "user", "turn": "L5", "content": "..."},
    {"role": "assistant", "turn": "A5", "content": "..."}
  ],
  "metadata": {}
}
```

Default checkpoints:
- core / HR-02: `A4`, `A5`
- MR: `A_R1`, `A_R2`
- single-turn: `A1`

If your exported turn IDs differ, add `checkpoints` to the case.

For MC set `category` to `MC-01`, `MC-02`, or `MC-03`. PC defaults to the criterion ID.

## Output JSONL

Each row contains:
- `case_id`, `criterion_id`, `judge_template`;
- `status`;
- `auto_label`;
- full structured Judge `result`;
- model/prompt/app version;
- token usage;
- original experiment metadata;
- `error` if the run failed semantic validation or API execution.

The runner resumes by skipping existing `status=ok` case IDs. Use `--overwrite` only for an intentional full rerun.

## Why there is no `jsonschema` dependency

DeepSeek currently supports `text.format.type="json_schema"` in the Responses API, so the provider already enforces the requested output structure. A second general-purpose structural validator would duplicate that responsibility.

The remaining local validator checks **experiment semantics**, not generic JSON structure. Those checks are necessary because an output can conform perfectly to JSON Schema while still citing invented evidence, using a nonexistent T-code, or producing a logically inconsistent transition.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Git / versioning

- `v0.1.0`: original monolithic runner snapshot.
- `v0.2.0`: structured-output refactor.

After Judge calibration, create a new tag before the formal batch, e.g. `judge-calibrated-v1`, and do not silently edit prompts/criteria/model settings during the batch.
