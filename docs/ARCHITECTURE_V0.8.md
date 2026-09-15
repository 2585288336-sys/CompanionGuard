# CompanionGuard v0.8 Architecture Notes

v0.8 is a smoke-test-driven UX refinement over v0.7. It does not change the frozen dialogue criteria or Judge semantics.

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
