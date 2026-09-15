# Data Collection and Evidence Protocol

This document describes the generic Data Collector workflow. It is an engineering/data-handling guide; frozen CompanionGuard criteria, prompts, target/non-target rules and Judge logic remain in `criteria/*.json` and the project protocol.

## Human-in-the-loop boundary

The Collector deliberately does not automate account login, identity/age verification, CAPTCHA handling, or private product APIs. The researcher performs only the external-product interaction:

```text
CompanionGuard fixed prompt
        ↓ Copy Prompt
External product
        ↓ paste/send
Verbatim product response
        ↓ copy
CompanionGuard response box
        ↓ Save & Copy Next
```

CompanionGuard owns case selection, condition/run metadata, turn alignment, persistence, queue progress, raw-case construction, optional evidence linkage, and Judge preparation.

## Supported collection structures

The collection plan is derived from `judge_template` and criterion configuration rather than criterion-specific UI branches:

- Core / HR-02 C0: consolidated L1–L4 → A4, then canonical L5 → A5.
- Core / HR-02 C1: consolidated L1–L4 → A4, then configured `pressure_variant.L5` → A5.
- Core / HR-02 C2: L1 → A1 → L2 → A2 → L3 → A3 → L4 → A4 → L5 → A5.
- MR: R1 → A_R1, then R2 → A_R2.
- MC / PC / other single-turn regulatory-content criteria: Prompt → A1.

If a Core criterion has no configured `pressure_variant.L5`, C1 is not invented by the Collector.

## Collection Queue

A queue is a list of case specifications generated from configured criteria. The queue stores identifiers and status, not duplicated prompt text. Prompt text is loaded from the current criterion configuration when a case starts.

Runtime file:

```text
data/projects/<project_id>/collection_queues.jsonl
```

Queue items have `PENDING`, `IN_PROGRESS`, or `COMPLETE` status. `Next Case` starts/resumes the next unfinished item. Existing `raw_cases.jsonl` and collection sessions are reconciled when a queue is opened.

## Autosave and recovery

`Save & Copy Next` persists the completed response turn immediately to:

```text
data/projects/<project_id>/collection_sessions.jsonl
```

The response text is preserved verbatim. The text-area draft is also persisted without advancing the turn, so an in-progress paste can be restored after leaving and resuming the case.

After the final response turn, the Collector validates Judge compatibility and writes a complete raw case to:

```text
data/projects/<project_id>/raw_cases.jsonl
```

The Collector and Judge remain decoupled. A completed case may be judged later from `Run Test`, or optionally sent directly to Judge from the case-completion view.

## Screenshot evidence

Text copy is the primary source of model-output data. Screenshots are optional supporting evidence and are not OCR inputs.

Upload screenshots directly under the response turn they document. CompanionGuard saves them automatically as:

```text
data/projects/<project_id>/evidence/dialogue/<case_id>/<response_turn>_01.png
data/projects/<project_id>/evidence/dialogue/<case_id>/<response_turn>_02.png
...
```

Examples:

```text
data/evidence/MoMood_DS-01_C0_FORMAL_run01/A4_01.png
data/evidence/MoMood_DS-01_C0_FORMAL_run01/A5_01.png

data/evidence/Example_MR-02_NA_FORMAL_run01/A_R1_01.png
data/evidence/Example_MR-02_NA_FORMAL_run01/A_R2_01.png
```

The paths are written into the corresponding `collection_trace[].evidence_files` record in `raw_cases.jsonl`. Therefore no manually maintained screenshot-index document is required; the data structure itself is the index.

Data Explorer resolves these stored paths against the active project and renders the screenshots inline under the response turn they document. The original stored path remains visible and each available image can be downloaded. If a file was moved or removed, the case and path remain available for audit and the UI reports that the image is missing.

If multiple screenshots are needed for one response (for example a long reply requiring scrolling), upload them together in display order; the Collector assigns `_01`, `_02`, etc.

## Source repository vs experimental evidence

Runtime research data are intentionally ignored by Git:

```text
data/*.jsonl
data/*.csv
data/evidence/
```

Do not treat screenshots as source code or commit them to the public/source repository by default. For archival, supervisor review, or submission records, create a separate experiment bundle that includes `data/projects/<project_id>/raw_cases.jsonl` and `data/evidence/` together. Because the raw case records contain the screenshot paths, their correspondence remains machine-readable and auditable.

## Generic product support

The Collector workflow does not branch on concrete product names. Product profiles live in:

```text
config/collector.json
```

A profile may define a label, role, optional criterion allowlist, notice, or `custom_product` behavior. Users can add another product profile without changing Collector domain/UI code, or use `Custom Product` to collect against an unlisted product.
