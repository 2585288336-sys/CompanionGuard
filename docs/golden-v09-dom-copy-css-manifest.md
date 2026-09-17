# CompanionGuard UI v0.9 — Golden DOM / Copy / CSS Manifest

Source: `CompanionGuard_UI_v0.9_Overall_UI_Final (1) (4).html` (the supplied
visual and copy master). This is a read-only implementation manifest; it does
not describe application behavior or authorize data changes.

## Global source tokens

| Token | Golden value |
|---|---|
| `--bg` | `#f6f7f9` |
| `--s` | `#fff` |
| `--t` | `#101828` |
| `--m` | `#667085` |
| `--b` | `#e4e7ec` |
| `--blue` | `#3156d9` |
| `--bluebg` | `#eef3ff` |
| body font | `-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif` |

## Home DOM and exact copy

Home is a standalone `<section class="page active" id="home">`; it has no
workspace sidebar, breadcrumb, project selector, or workflow footer.

| DOM element | Exact copy / content | Golden CSS |
|---|---|---|
| `.review` | `CompanionGuard UI/UX Refactor v0.9 — Design Review` + `纯前端审查稿 · 不读取、不写入正式数据 · 示例数字仅用于布局` | height `34px`; background `#101828`; text `12px`; text `#d0d5dd`; bold text `#fff` |
| `.topnav` | brand + `项目介绍` / `三层框架` / `指标` / `构建与方法` + `进入工作台` | height `72px`; max-width `1240px`; padding `0 20px` |
| `.brand` / `.mark` | `CompanionGuard` | brand gap `10px`; weight `750`; size `17px`; mark `28px × 28px`; radius `8px` |
| `.navlinks` | `项目介绍` · `三层框架` · `指标` · `构建与方法` | gap `26px`; size `13px`; color `#475467` |
| `.hero` | two-column hero | max-width `1240px`; padding `88px 20px 104px`; columns `1.02fr .98fr`; gap `64px`; background `#fff` |
| `.hero-copy .home-kicker` | `REGULATORY TESTING & RISK DIAGNOSIS` | size `11px`; weight `750`; letter-spacing `.1em`; blue |
| `.hero h1` | `把拟人化 AI 的监管要求，转化为可执行、可复核的测试` | size `56px`; line-height `1.05`; letter-spacing `-.045em`; margin `18px 0 22px` |
| `.hero-copy .lead` | `CompanionGuard 是一套面向拟人化 AI 服务的监管测试与风险诊断框架。` | size `17px`; line-height `1.8`; color `#475467`; margin-bottom `15px` |
| `.hero-copy .body` | `项目从《人工智能拟人化互动服务管理暂行办法》的监管要求出发，将抽象的监管规则与义务转化为可以在真实产品上执行、记录和复核的测试要求，重点观察过度迎合、情感依赖、退出挽留、危机应对、未成年人保护、敏感信息诱导等拟人化互动中的风险。` / `在测试结果层面，CompanionGuard 建立了面向风险诊断的指标体系，包括风险发现率、压力鲁棒性、多轮鲁棒性、明确触发后的风险转变、专项风险指标和 Judge–Human Reliability。指标不仅记录“是否出现问题”，还用于判断风险集中在哪里、用户施压或多轮互动后模型能否继续保持安全边界，以及自动判定本身是否可靠。` / `CompanionGuard 支持建立自定义测试项目。用户可以选择需要评测的 AI 产品，配置测试范围、实验条件和分析指标，并通过统一流程完成测试、判定、人工复核和结果分析。` | size `13px`; line-height `1.8`; color `#667085`; margin-bottom `12px` |
| `.actions` | `进入工作台` / `查看构建与方法` | gap `10px`; margin-top `22px` |
| `.hero-workspace-btn` | `进入工作台` | padding `13px 24px`; size `14px`; weight `780`; radius `9px`; min-height `44px` |
| `.hero-copy .micro` | `Finding 表示在预设监管测试场景中观察到的风险表现，用于定位具体问题和支持后续审核；它不直接等同于法律意义上的不合规认定。` | size `11.5px`; line-height `1.65`; margin-top `18px`; padding-top `16px`; color `#667085` |
| `.shot` | full mock product screenshot illustration | border `1px solid #dde3ec`; radius `16px`; shadow `0 24px 60px rgba(16,24,40,.11)` |
| `.fakebar` / `.shotbody` | mock browser bar + sidebar/content illustration | fakebar height `42px`; shot columns `140px 1fr`; shotbody min-height `400px`; shotmain padding `24px` |
| `.reference-project` | `PRELOADED REFERENCE PROJECT`; `CompanionGuard Formal Full Benchmark 2026-09`; `网站预置的完整示范项目，对三款代表性 AI 陪伴产品执行同一套监管测试方案，用于展示从测试设计到最终报告的完整流程。`; tags `3 个代表性产品` / `Layer 1 + Layer 2 + Layer 3` / `自动 Judge + 人工复核` | background `#eef4fb`; border `#d8e4f2`; radius `14px`; padding `24px`; title `19px`; body `12px`, line-height `1.7` |

### Home sections

Every section is `.home-section divider-section` with max-width `1200px`,
margin auto, padding `62px 20px`, and a top divider. Intro uses
`.section-intro` max-width `760px`, margin-bottom `28px`; kicker is `10px`,
weight `750`, letter-spacing `.08em`; H2 is `30px`, letter-spacing `-.025em`,
margin `0 0 10px`; intro body is `13px`, line-height `1.75`, color `#667085`.

| Section / selector | Exact content and structure | Grid / card CSS |
|---|---|---|
| first `.home-section` | kicker `Regulation → Testable Evidence`; H2 `从《人工智能拟人化互动服务管理暂行办法》监管要求到真实产品测试`; intro `监管规范通常以原则和义务的形式提出要求，而产品测试需要把这些要求进一步拆解为能够被观察、记录和复核的具体问题。`; four questions: `模型实际会怎样回应？` / `用户进一步施压后，原有边界还能否保持？` / `产品是否设置了相应保护机制？` / `公开材料能否支持对制度安排的核查？`; finding note and flow `监管要求 → 可观察要求 → 测试场景 / 产品检查 → 证据记录 → 结构化判定 → 人工复核 → Finding` | `.statement-grid` columns `1.1fr .9fr`, gap `18px`; `.question-stack` gap `9px`; `.question` padding `14px 15px`, size `13px`, weight `650`, radius `10px`; `.finding-note` padding `16px 18px`, size `12px`, line-height `1.7`, radius `11px`; `.flow` gap `9px`; `.flowbox` padding `13px 16px`, size `12px`, radius `9px` |
| `#framework` | kicker `Three-Layer Regulatory Evaluation`; H2 `三层监管评测框架`; intro `同一项监管要求，可能分别体现在模型回答、产品功能和企业公开制度中。CompanionGuard 对三类证据分别检查，再结合分析。`; three framework cards: Layer 1 `对话行为测试` and its full description; Layer 2 `产品安全机制检查` and its full description; Layer 3 `公开制度材料核查` and its full description; note `三层结果可以相互印证，也可能出现差异。CompanionGuard 保留这些差异，不把行为、产品机制和公开制度压缩成一个统一的安全分或合规分。` | `.grid3` columns `repeat(3,1fr)`, gap `14px`; `.framework-card` padding `22px`, radius `12px`; layer `10px`/weight `800`; H3 `16px`; body `12px`/`1.7` |
| Core Regulatory Scope | kicker `Core Regulatory Scope`; H2 `核心测试范围`; intro `五类测试范围分别对应拟人化互动中具有不同证据位置和风险机制的问题。`; five complete cards: `关系安全` / `极端行为与危机应对` / `未成年人保护` / `信息与权益保护` / `禁止性内容专项测试`, with their full HTML descriptions | `.range-grid` columns `repeat(5,1fr)`, gap `12px`; cards padding `18px`, radius `11px`; H3 `13px`; body `11.5px`/`1.65` |
| Custom Test Projects | kicker `Custom Test Projects`; H2 `支持自定义测试项目`; intro `CompanionGuard 不限于一套固定 benchmark。用户可以根据实际审核任务建立新的测试项目，并选择产品、测试范围、实验条件、分析指标和证据范围。`; six config items: `测试产品` / `测试范围` / `实验条件` / `分析指标` / `证据范围` / `统一工作流`; reference configuration card and tags `统一监管测试方案` / `三层证据` / `可配置 Project` | `.project-config` columns `1.1fr .9fr`, gap `18px`; `.config-list` 2 columns, gap `10px`; item padding `16px`, radius `10px`; reference padding `24px`, radius `14px` |
| Dialogue Conditions | kicker `Dialogue Conditions`; H2 `对话测试与实验条件`; intro `核心对话场景通过分阶段信息设计，区分用户状态、风险事实和明确请求，并在不同实验条件下观察模型表现。`; C0 `标准条件 / Baseline Condition`, C1 `压力条件 / Pressure Condition`, C2 `多轮条件 / Sequential Multi-turn Condition`, with their complete descriptions and three question lines; note `三种实验条件分别观察不同问题，因此分别记录和比较，不合并为一种笼统的“高难度测试”。` | `.condition-grid` columns `repeat(3,1fr)`, gap `14px`; card padding `20px`, radius `12px`; code size `28px`, weight `800`; H3 `14px`; body `11.5px`/`1.65`; question line padding-top `11px`, size `11px` |
| Structured Judgment | kicker `Structured Judgment`; H2 `LLM Judge + 人工复核`; intro `CompanionGuard 使用受准则约束的 LLM-as-Judge 进行结构化初判，并保留人工确认与改判链路。`; two judge boxes: `LLM Judge 依据预定义边界判定` with Target/Non-target/boundary copy and `FINDING` / `NO_FINDING` / `REVIEW`; `自动判定与人工判断可追溯` with complete traceability copy and `Auto Judgment → Human Review → Final Label` | `.judge-layout` columns `.85fr 1.15fr`, gap `18px`; `.judge-box` padding `22px`, radius `12px`; `.judge-output` gap `8px`, margin `14px 0` |
| `#metrics` | kicker `Metrics & Risk Diagnosis`; H2 `如何理解评测结果`; complete intro; metric framework `指标框架`; complete metric cards: `FINDING · 风险发现`, `OVERALL MACRO FINDING RATE · 总体风险发现率`, `PRESSURE ROBUSTNESS GAP · 压力鲁棒性`, `MULTI-TURN ROBUSTNESS GAP · 多轮鲁棒性`, `ELICITATION FLIP · 明确触发后的风险转变`, `SPECIALIZED METRICS · 专项指标`, `JUDGE–HUMAN RELIABILITY · 判定一致性`, with all descriptions from source | `.metric-feature` 2 columns, gap `14px`; cards padding `19px`, radius `12px`; metric English `13.5px`/`1.35`, weight `800`; card H3 `13px`; body `11.5px`/`1.7` |
| `#method` | kicker `Construction & Method`; H2 `构建与方法`; intro `首页仅展示 CompanionGuard 的主要设计。完整方法说明保留监管映射、正式判定边界、标准测试语句和可复现性细节。`; method steps 01–06 with complete source copy; download block title `查看完整方法说明`, full explanatory paragraph, and `下载《CompanionGuard Benchmark 构建与方法设计说明》` | `.method-steps` 3 columns, gap `12px`; step padding `18px`, radius `11px`; number `10px`/weight `800`; H3 `13px`; body `11px`/`1.65`; `.downloadbox` background `#101828`, color `#fff`, padding `24px 26px`, radius `13px`, gap `24px`; description `12px`/`1.6`, `#d0d5dd` |
| `.footer` | `CompanionGuard · Regulatory Testing & Risk Diagnosis` / `App v0.9 · Data Schema v1.0` | max-width `1200px`; border-top; padding `46px 20px 70px`; size `11px`; color `#667085` |

## Workspace DOM and exact shell copy

Workspace is generated by `shell(id,title,sub,body)` and has the structure:
`.page.workspace` → `.sidebar` + `.content` → `.bar` + `.canvas` → `.head` +
body + workflow navigation controls.

| DOM element | Exact copy / structure | Golden CSS |
|---|---|---|
| `.workspace` | sidebar + content | grid columns `244px 1fr` |
| `.sidebar` | `sidebrand`, `projectbox`, `navtree` | overflow-y auto; max-height `100vh`; background `#fbfcfd`; border-right; padding `18px 14px`; min-height `calc(100vh - 34px)` |
| `.sidebrand .brand` | `CompanionGuard` | `.sidebrand` padding `4px 10px 20px`; brand `17px`/weight `750`; mark `28px × 28px`, radius `8px` |
| `.projectbox` | `Test Project · 测试项目`; `CompanionGuard Formal Full Benchmark 2026-09`; `FORMAL`; `切换项目` | padding `11px 12px`; margin `0 5px 16px`; radius `9px`; value `13px`/weight `700`; project metadata key `10px` |
| `.navtree` / `.navhome` | `Home｜首页` | navtree padding `6px 8px 18px`; navhome padding `10px 12px`; margin `2px 0 8px`; radius `8px`; size `12px`; weight `760` |
| `.navgroup` | `01 项目与测试` / `Project Setup`; `02 三层证据评测` / `Three-Layer Evaluation`; `04 报告` / `Reports` | margin `7px 0 9px`; toggle padding `8px 10px`; Chinese `11.7px`/weight `800`/line-height `1.25`/color `#344054`; English margin `3px 0 0 19px`, `9.5px`/`1.2`/`#98a2b3`; body padding `2px 0 2px 10px` |
| `.navlayer` | `Layer 1｜对话行为测试` / `Dialogue Testing`; `Layer 2｜产品安全机制检查` / `Product Safeguard Checks`; `Layer 3｜公开制度材料核查` / `Public Evidence Audit` | margin `5px 0 6px 2px`; toggle padding `7px 8px`; Chinese `10.8px`/weight `760`/line-height `1.3`; English margin `3px 0 0 19px`, `9px`; body padding `2px 0 1px 14px` |
| `.navleaf` | `自动判定` / `Dialogue Judge`; `人工复核` / `Human Review`; `数据浏览` / `Data Explorer`; `判定一致性` / `Reliability`; Layer 2/3 children; report children | padding `7px 10px 7px 11px`; margin `2px 0`; radius `7px`; Chinese `11.4px`/weight `680`/line-height `1.25`; English `9.4px`/line-height `1.2`/margin-top `3px`; active background `#eef2ff`, active color `#273b8f` |
| `.navstatic` | `03 对话评测结果与指标` / `Dialogue Results & Metrics` | padding `10px 10px 8px 29px`; margin `8px 0`; border-top `1px solid #eef1f5`; Chinese `11.7px`/weight `800`/line-height `1.3`; English `9.5px`/line-height `1.2`; active background `#eef2ff` |
| `.bar` / `.crumb` | `CompanionGuard / {page title}`; pills `产品列表 · 来自 project.json` / `FORMAL`; action `主页` | bar height `62px`; padding `0 28px`; crumb `12px`; crumb bold `#344054`; bar actions gap `8px` |
| `.canvas` / `.head` | page title + page subtitle; `Data Schema v1.0` | canvas padding `28px 32px 72px`; max-width `1500px`; head margin-bottom `20px`; H1 `25px`, subtitle `12.5px`/line-height `1.62` |
| workflow navigation | `← Previous`; `Next →` | Retains the existing page navigation controls without reconstruction-phase explanatory copy |

## Route copy manifest

The HTML route metadata uses these exact titles and subtitles:

`testdesign` → `测试项目设计` / `Test Project Design`; `plan` → `项目计划制定` /
`Test Plan`; `collector` → `对话数据采集` / `Dialogue Data Collection`;
`overview` → `当前项目总览` / `Current Project Overview`; `judge` → `自动判定` /
`Dialogue Judge`; `review` → `人工复核` / `Human Review`; `explorer` → `数据浏览`
/ `Data Explorer`; `reliability` → `判定一致性` / `Reliability`; `layer2` →
`产品安全机制检查` / `Product Safeguards`; `layer3` → `公开制度材料核查` /
`Public Evidence`; `results` → `对话评测结果与指标` / `Dialogue Results & Metrics`;
`dialogueReport` → `对话评测报告` / `Dialogue Report`; `report` → `综合评测报告` /
`Integrated Report`.

## Interaction boundary

The supplied HTML uses JavaScript for visual-page navigation. In the application,
these same fixed display strings and hierarchy must be backed by real
Streamlit/session-state routing. The manifest does not authorize replacing any
existing page workflow, control, persistence call, upload, selector, form, or
report pipeline.
