# CompanionGuard v0.8 Architecture Notes

v0.8 is a smoke-test-driven UX refinement over v0.7. v0.8.1 adds evidence visibility and collected-case Judge access. v0.8.2 adds automatic case-validity screening and frozen FORMAL human-adjudication policies. v0.8.3 refines the Chinese-first workflow UI and keeps the presentation changes separate from the frozen dialogue criteria, Judge semantics and metric definitions. v0.8.4 adds project portability metadata and read-only integrity checks without changing those experimental boundaries.

## v0.8.3 presentation boundary

Modules, official criterion names, conditions, phases and turn names are centralized in a presentation-only label module. Raw case, Judge and metric identifiers remain unchanged. Data Explorer resolves and previews screenshot evidence while preserving its stored path as technical metadata. The normal Judge path reads COMPLETE raw cases from the active project; manual Conversation JSON and external JSONL remain advanced fallbacks.

Human Review renders the complete collected conversation and the criterion’s target behaviors, non-target behaviors and boundary rules before the decision form. Review widgets are keyed by Case ID. A normal automatic validity screen is displayed as `VALID`; automatic `REVIEW` requires an explicit human `VALID`/`INVALID` choice. This validity choice remains separate from the frozen risk-label adjudication.

## v0.8.2 validity and adjudication boundary

Case validity has two stages: `auto_case_validity` is a conservative screen, and `final_case_validity` is the human decision. A normal case starts as `VALID`; obvious unusable or explicitly unrelated output starts as `REVIEW`; the screen never assigns final `INVALID`. `VALID`, `INVALID`, and `REVIEW` describe case suitability, while `FINDING`, `NO_FINDING`, and `REVIEW` continue to describe the criterion-bound risk judgment. Only `FORMAL` cases with final validity `VALID` enter risk metrics; reliability additionally requires `adjudication_status == REVIEWED`.

FORMAL Benchmark projects freeze either `FULL_ADJUDICATION` or `SAMPLED_ADJUDICATION` in the project manifest. Sampled projects persist their selected case IDs, method, strata, rate, and random seed in `adjudication_sampling.json`. Unreviewed sampled cases retain the LLM `auto_label` as `analysis_label`, leave `human_label` and `final_label` empty, and are never counted as human agreement observations.

## Core boundaries

- Product identity is independent from Test Plan coverage.
- Test Plans can select Core conditions per criterion and individual MR/MC/PC scenarios.
- Collector, Judge, Human Review and reports remain project-scoped.
- LLM provider infrastructure remains vendor-decoupled and role-scoped.
- Raw dialogue text is authoritative; screenshot evidence is optional and linked to response turns.
- Formal metrics and integrated-report reliability use FORMAL adjudicated cases only.

## Project portability boundary

Each new project manifest records `data_schema_version`, `app_version` and the creating `code_commit`. Evidence references may be project-relative or repository-relative, but must not depend on an absolute checkout path. `scripts/verify_project_data.py` checks a copied or frozen project without writing to it. Any future schema migration must operate on a copied analysis project; the formal frozen project remains the unchanged source of truth.

## Main workflow

`Project → Test Plan → Data Collection → Data Explorer → LLM Judge → Human Review → Reliability/Results → Layer 2 → Layer 3 → Integrated Report`

The UI exposes Previous / Next navigation and project/session exits, but does not force a rigid wizard because Layer 2/3 may be executed independently when appropriate.
