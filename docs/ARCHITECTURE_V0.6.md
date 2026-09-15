# CompanionGuard v0.6 Architecture

## 1. Core deployment principle

CompanionGuard is currently a Streamlit web application backed by ordinary Python modules and file-based project storage. The browser is a UI client; semantic Judge calls execute on the server process.

The dialogue Judge is deliberately **not an agent**. No autonomous planning, tool selection loop, memory loop or self-directed task decomposition is needed. A deterministic pipeline is preferable because every judgment must be traceable to one frozen criterion and one known schema.

No external evaluation harness is required. CompanionGuard already provides the minimum harness-like responsibilities it needs: case loading, criterion routing, batch execution, schema validation, semantic validation, result persistence and human adjudication.

## 2. Server-side Judge call

```text
Browser
  ↓ Streamlit action
CompanionGuard Python service
  ↓
criterion JSON + case JSON
  ↓
Judge template router
  ↓
DeepSeek API
  ↓
validated structured result
  ↓
project-scoped judge_results.jsonl
```

Demo mode uses a server-side secret. BYOK remains session-only. v0.6 does not expose a public REST endpoint.

## 3. Test Project isolation

All runtime evidence is scoped by `project_id` under `data/projects/<project_id>/`. This prevents separate evaluation batches from sharing raw cases, Judge results or evidence attachments.

## 4. Three evidence layers

- Layer 1: Dialogue Evidence — real product replies to frozen tests.
- Layer 2: Product Evidence — externally observable product safeguards.
- Layer 3 Lite: Documentary Evidence — public formal materials supporting selected governance obligations.

The three status vocabularies remain separate and are never collapsed into one safety score.
