# CompanionGuard v0.8 Architecture Notes

v0.8 is a smoke-test-driven UX refinement over v0.7. v0.8.1 adds evidence visibility and collected-case Judge access. v0.8.2 adds automatic case-validity screening and frozen FORMAL human-adjudication policies; it does not change the frozen dialogue criteria or Judge semantics.

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

## Main workflow

`Project → Test Plan → Data Collection → Data Explorer → LLM Judge → Human Review → Reliability/Results → Layer 2 → Layer 3 → Integrated Report`

The UI exposes Previous / Next navigation and project/session exits, but does not force a rigid wizard because Layer 2/3 may be executed independently when appropriate.
