# CompanionGuard v0.8 Architecture Notes

v0.8 is a smoke-test-driven UX refinement over v0.7. v0.8.1 adds evidence visibility, collected-case Judge access and an independent case-validity layer; it does not change the frozen dialogue criteria or Judge semantics.

## v0.8.1 validity boundary

Case validity is stored separately from the frozen dialogue risk labels. `VALID`, `INVALID`, and `REVIEW` describe whether a collected case is suitable for risk analysis; `FINDING`, `NO_FINDING`, and `REVIEW` continue to describe the criterion-bound risk judgment. Only `FORMAL` cases with `case_validity == VALID` enter dialogue metrics and Judge–Human reliability. INVALID and unresolved REVIEW cases remain in project final results and audit views.

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
