# CompanionGuard v0.7 Architecture

## 1. Platform boundary

CompanionGuard remains a Streamlit + Python testing platform. It does not use an agent framework, FastAPI, database, Celery, Redis or a third-party evaluation harness for the MVP.

The core separation is now:

```text
UI
↓
Project / Test Plan / Collection services
↓
Domain-specific workflows
├── Dialogue Judge
├── Layer 3 Evidence Assistant
├── Dialogue Report Writer
└── Integrated Report Writer
↓
Shared LLM Provider layer
├── OpenAI-style Chat Completions adapter
├── OpenAI Responses-compatible adapter
└── Anthropic Messages adapter
```

Business logic never branches on a concrete vendor name. Adding another vendor means adding an adapter implementing the same JSON/text generation interface.

## 2. Four LLM roles, one infrastructure

CompanionGuard has four independent LLM roles:

1. `judge` — criterion-bound dialogue classification.
2. `dialogue_report` — writes the Layer 1 report from deterministic report context.
3. `evidence` — extracts/suggests evidence status for Layer 3 supplied source text.
4. `integrated_report` — writes the final cross-layer report from deterministic report context.

These roles may use the same model/provider, but they are not required to. Each role has an independent server profile or BYOK profile. API keys are session/server secrets and are never serialized into project data.

## 3. Judge remains non-agentic

```text
raw case
→ frozen criterion JSON
→ fixed Judge template/schema
→ configured Judge LLM
→ JSON schema validation
→ CompanionGuard semantic validation
→ judge_results.jsonl
```

The LLM supplies semantic classification. Python owns routing, validation, retry boundaries, persistence and reproducibility. No autonomous tool selection or web search occurs inside the Judge.

## 4. Product and Test Plan are independent

A product no longer has a criterion allowlist. Test coverage belongs to a `Test Plan`:

```text
Test Project
├── Product A
│   ├── Full Benchmark plan
│   └── Targeted subset plan
└── Product B
    └── Custom plan
```

Coverage types are:

- `FULL_BENCHMARK`
- `BENCHMARK_SUBSET`
- `CUSTOM`

`BENCHMARK_SUBSET` and `CUSTOM` are valid targeted evaluations but must not be reported as directly equivalent to a full-benchmark aggregate.

A legacy comparator subset is retained only as a reusable preset. It can be applied to any product and edited.

## 5. Layer 3 retrieval boundary

v0.7 keeps the MVP source path conservative:

```text
human-supplied official source
→ Evidence Assistant
→ evidence extraction/status suggestion
→ human final status
```

A `SearchProvider` protocol is reserved for future retrieval. The default implementation is explicitly disabled, so v0.7 never silently turns Layer 3 into a free-form web agent. A future search adapter should retrieve official-source candidates, then pass source content into the existing Evidence Assistant + human-review workflow.

## 6. Reporting boundary

Python computes metrics and builds authoritative structured report context. LLM report writers only transform that context into prose:

```text
final structured data
→ deterministic Python metrics/context
→ role-specific report prompt
→ configurable Report Writer LLM
→ draft report
```

External writing skills/prompts are intentionally not bundled in v0.7. They can later replace the two files under `prompts/reporting/` without modifying Judge or Evidence logic.

## 7. Server-funded LLM guard

Server-side model access supports a lightweight kill switch and call ceilings via environment variables:

- `COMPANIONGUARD_SERVER_LLM_ENABLED`
- `COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT`
- `COMPANIONGUARD_SERVER_LLM_SESSION_CALL_LIMIT`

Usage records contain role/provider/model/usage metadata, never API keys. Full user accounts, project ownership/RBAC and billing are intentionally deferred until CompanionGuard becomes a true multi-user public service.
