# CompanionGuard Production Golden Recovery Guide

本文档记录 CompanionGuard“满意版本 1”（Production Golden Recovery
Point）的恢复信息。它用于在后续开发破坏当前实现时，恢复代码、Golden UI
和已纳入 Git 的官方 deployment seed。

> 重要：满意版本 1 可以从 Git 精确恢复 code、UI 和 tracked deployment
> seed，但不能仅凭 Git 精确恢复 runtime evidence、runtime reports、Secrets、
> Streamlit Cloud 控制台状态或尚未发布进 deployment seed 的后续数据。

## 1. Golden Recovery Point

| Item | Value |
|---|---|
| Golden Recovery Commit | `2df5d7b51c78b2bd2d51f01d83e45b81a9166bf5` |
| Tree SHA | `18cc816cd53c2061f71bd16bde75eb46167e9092` |
| Commit message | `fix(ui): remove obsolete workspace footer` |
| Recovery tag | `competition-production-stable-20260917` |
| Archive branch | `archive/competition-production-stable-20260917` |
| Production branch | `main` |

The recovery tag and archive branch both target the Golden Recovery Commit.
The tag is a lightweight tag. The recovery commit is also the production
`main` target recorded during this audit.

## 1.1 Current stable production recovery point (2026-09-19)

The currently verified production application is protected separately from
the previous Golden Recovery Point:

| Item | Value |
|---|---|
| Stable production commit | `23c6e135625d4e63b4e4bebaa1725f9a9db2fb46` |
| Stable tag | `production-stable-20260919` |
| Archive branch | `archive/production-stable-20260919` |
| Deployment snapshot | `2026.09.19-01` |
| Deployment snapshot hash | `94fd426bdfe6c0f6b3096d6eace5473c010b982f86391f177cd9ad2d4300435b` |

The previous protected recovery point remains available at
`competition-production-stable-20260917` and
`archive/competition-production-stable-20260917`, both targeting
`2df5d7b51c78b2bd2d51f01d83e45b81a9166bf5`.

## 2. Production deployment identity

| Item | Value |
|---|---|
| Production URL | `https://companionguard-safety-test.streamlit.app` |
| Repository | `2585288336-sys/CompanionGuard` |
| Branch | `main` |
| Entrypoint | `streamlit_app.py` |

`.streamlit/config.toml` is tracked in the repository. Streamlit Cloud app
binding, repository mapping, branch mapping, production URL, and Secrets are
external platform state; Git alone cannot recreate those console settings.

## 3. Golden UI and application recovery scope

The Golden Recovery Commit contains the production application and its
presentation layer, including:

- Home
- sidebar and navigation
- project design
- test plan
- data collection
- project overview
- Dialogue Judge
- Human Review
- Data Explorer
- Reliability
- Dialogue Results
- Layer 2
- Layer 3
- Dialogue Report
- Integrated Report
- Golden CSS and visual styling

The tracked entrypoint delegates to the Golden UI renderer:

```python
from companionguard_app.golden_ui import run_app
run_app()
```

Restoring the Golden Recovery Commit restores the corresponding production
frontend code and workflow routing.

## 4. Tracked deployment seed

The official deployment seed is:

```text
data/deployment_seed/CompanionGuard-Formal-Full-Benchmark-2026-09/
```

Tracked files:

- `project.json`
- `raw_cases.jsonl`
- `collection_sessions.jsonl`
- `collection_queues.jsonl`
- `judge_results.jsonl`
- `human_adjudication.csv`
- `final_results.csv`
- `test_plans.json`

Audit snapshot of the seed:

| File | Records/lines |
|---|---:|
| `raw_cases.jsonl` | 210 |
| `collection_sessions.jsonl` | 210 |
| `collection_queues.jsonl` | 3 |
| `judge_results.jsonl` | 175 |
| `human_adjudication.csv` | 1 data record |
| `final_results.csv` | 1 data record |

The seed size at audit time was approximately 1.82 MB. It does not contain:

- `evidence/`
- `reports/`
- `llm_usage.jsonl`
- `runtime_sessions/`
- `snapshot_manifest.json`

Do not modify the deployment seed as part of ordinary recovery documentation
work.

## 5. Runtime persistence boundary

Git protects:

- source code
- Golden UI
- prompts
- criteria
- tracked configuration
- tests
- tracked deployment seed

Git does not automatically protect:

- `data/projects/`
- runtime evidence
- runtime reports
- `llm_usage.jsonl`
- evaluator temporary workspaces
- Streamlit Secrets
- Streamlit Cloud console state
- later formal data not published into the deployment seed

`data/projects/` is excluded by `.gitignore`. Runtime files must not be
described as fully backed up merely because the application source is backed
up. Runtime evidence, reports, and later user-generated results require a
separate backup or export process.

## 6. Current deployment initializer behavior

The current initializer materializes the seed only when the runtime project is
absent:

```text
data/projects/<project_id>/ does not exist
    → copy from data/deployment_seed/<project_id>/
```

If the target runtime project already exists, the current system does not
automatically overwrite it when the seed changes. There is currently no:

- published version manifest
- content hash based refresh
- automatic published-runtime refresh

Those capabilities belong to later Storage V2 work and are not part of this
recovery guide.

## 7. Secret and environment key names

This document records key names only. It contains no Secret values.

### Role-specific keys

Supported roles:

- `JUDGE`
- `EVIDENCE`
- `DIALOGUE_REPORT`
- `INTEGRATED_REPORT`
- `GROUNDING_VALIDATOR`
- `ACADEMIC_POLISH`

Each role may use:

```text
COMPANIONGUARD_<ROLE>_API_KEY
COMPANIONGUARD_<ROLE>_MODEL
COMPANIONGUARD_<ROLE>_PROVIDER_TYPE
COMPANIONGUARD_<ROLE>_PROVIDER_NAME
COMPANIONGUARD_<ROLE>_BASE_URL
COMPANIONGUARD_<ROLE>_REASONING_EFFORT
COMPANIONGUARD_<ROLE>_TEMPERATURE
```

### Legacy / DeepSeek fallback keys

```text
DEEPSEEK_API_KEY
DEEPSEEK_MODEL
DEEPSEEK_REPORT_MODEL
DEEPSEEK_GROUNDING_MODEL
DEEPSEEK_BASE_URL
DEEPSEEK_REASONING_EFFORT
DEEPSEEK_TEMPERATURE
```

### Server-side LLM guard keys

```text
COMPANIONGUARD_SERVER_LLM_ENABLED
COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT
COMPANIONGUARD_SERVER_LLM_SESSION_CALL_LIMIT
```

**DO NOT store Secret values in Git.** Store actual Secret values in Streamlit
Cloud Secrets and/or a user-controlled password manager or secure backup.
Do not create `.streamlit/secrets.toml` in the repository.

## 8. Disaster Recovery Checklist

The following is a reference checklist. It was not executed as part of
creating this document.

1. Locate the recovery tag:
   `competition-production-stable-20260917`.
2. Verify that it resolves to:
   `2df5d7b51c78b2bd2d51f01d83e45b81a9166bf5`.
3. If required during an actual incident, restore production `main` to that
   commit.
4. Confirm that the tracked seed exists at:
   `data/deployment_seed/CompanionGuard-Formal-Full-Benchmark-2026-09/`.
5. Confirm the Streamlit Cloud settings:
   - Repository: `2585288336-sys/CompanionGuard`
   - Branch: `main`
   - Entrypoint: `streamlit_app.py`
6. Restore the required Secret values through Streamlit Cloud Secrets. Never
   commit them.
7. Redeploy or reboot the Streamlit app.
8. Verify Home and the navigation shell.
9. Verify official project discovery and project loading.
10. Verify Dialogue Judge and Human Review.
11. Verify Layer 2 and Layer 3.
12. Verify Dialogue Results, Dialogue Report, and Integrated Report.
13. Verify that the deployment initializer can initialize the official project
    from the tracked seed.
14. Check whether runtime evidence and reports have a separate backup. Do not
    assume they are restored by Git recovery.

### Reference commands

The following commands are inspection examples only:

```bash
git show --no-patch --oneline competition-production-stable-20260917
git rev-parse competition-production-stable-20260917^{tree}
git branch --list 'archive/competition-production-stable-20260917'
git ls-tree -r --name-only \
  competition-production-stable-20260917 \
  data/deployment_seed/CompanionGuard-Formal-Full-Benchmark-2026-09
```

The following commands are destructive recovery actions and must be used only
during an actual disaster recovery, after independently confirming the target
and obtaining the required operational approval:

```bash
# ONLY USE DURING AN ACTUAL DISASTER RECOVERY
git switch main
git reset --hard competition-production-stable-20260917

# ONLY USE DURING AN ACTUAL DISASTER RECOVERY
git push origin main --force-with-lease
```

Do not run those recovery commands during ordinary development or audit work.

## 9. Protection rating

| Recovery area | Rating | Reason |
|---|---|---|
| Source Code Recovery | **PROTECTED** | Recovery commit, main, tag, and archive branch are available. |
| UI Recovery | **PROTECTED** | Golden UI, routes, CSS, and tests are tracked in the recovery commit. |
| Published Seed/Data Recovery | **PARTIALLY PROTECTED** | Initial official seed is tracked; runtime evidence, reports, and later unpublished data are not. |
| Deployment Configuration Recovery | **PARTIALLY PROTECTED** | Entrypoint and key names are documented; Cloud console state, URL binding, and Secret values remain external. |

## 10. Recovery documentation boundary

The following must remain external or be maintained separately from Secret
values:

- Streamlit Cloud app binding
- production URL ownership/configuration
- repository and branch mapping in the Cloud console
- actual Secret values
- backups of runtime evidence and reports

This file is a recovery guide, not a replacement for runtime backup, Secret
backup, or Streamlit Cloud account access.
