"""Faithful v0.9 Golden shell.

This module owns presentation and routing only. The existing page functions are
deliberately called unchanged so their controls, callbacks, storage, and
backend workflows remain the functional baseline.
"""

from __future__ import annotations

from html import escape
from typing import Any, Callable

import streamlit as st

from .collector_ui import data_collection_page
from .deployment import ensure_deployment_project
from .platform_ui import (
    data_explorer_page,
    dialogue_report_page,
    layer2_page,
    layer3_page,
    projects_page,
    reliability_page,
    report_page,
)
from .projects import get_project, list_projects
from .ui import get_criteria, human_review_page, results_page, run_test_page


PAGE_META: dict[str, tuple[str, str]] = {
    "home": ("Home｜首页", "Home"),
    "testdesign": ("测试项目设计", "Test Project Design"),
    "plan": ("项目计划制定", "Test Plan"),
    "collector": ("对话数据采集", "Dialogue Data Collection"),
    "overview": ("当前项目总览", "Current Project Overview"),
    "judge": ("自动判定", "Dialogue Judge"),
    "review": ("人工复核", "Human Review"),
    "explorer": ("数据浏览", "Data Explorer"),
    "reliability": ("判定一致性", "Reliability"),
    "layer2": ("产品安全机制检查", "Product Safeguards"),
    "layer3": ("公开制度材料核查", "Public Evidence"),
    "results": ("对话评测结果与指标", "Dialogue Results & Metrics"),
    "dialogue_report": ("对话评测报告", "Dialogue Report"),
    "report": ("综合评测报告", "Integrated Report"),
}

NAV_LABELS: dict[str, tuple[str, str, int]] = {
    "testdesign": ("测试项目设计", "Test Project Design", 2),
    "plan": ("项目计划制定", "Test Plan", 2),
    "collector": ("对话数据采集", "Dialogue Data Collection", 2),
    "overview": ("当前项目总览", "Current Project Overview", 2),
    "judge": ("自动判定", "Dialogue Judge", 3),
    "review": ("人工复核", "Human Review", 3),
    "explorer": ("数据浏览", "Data Explorer", 3),
    "reliability": ("判定一致性", "Reliability", 3),
    "layer2": ("产品安全机制检查", "Product Safeguards", 3),
    "layer3": ("公开制度材料核查", "Public Evidence", 3),
    "results": ("对话评测结果与指标", "Dialogue Results & Metrics", 3),
    "dialogue_report": ("对话评测报告", "Dialogue Report", 3),
    "report": ("综合评测报告", "Integrated Report", 3),
}


HOME_HTML = r'''<div class="cg-home">
<section class="page active" id="home">
  <div class="topnav">
    <div class="brand"><span class="mark"></span>CompanionGuard</div>
    <div class="navlinks">
      <a href="#home">项目介绍</a><a href="#framework">三层框架</a><a href="#metrics">指标</a><a href="#method">构建与方法</a>
      <a class="btn primary" href="?page=overview">进入工作台</a>
    </div>
  </div>
  <div class="hero">
    <div class="hero-copy">
      <div class="home-kicker">REGULATORY TESTING &amp; RISK DIAGNOSIS</div>
      <h1>把拟人化 AI 的监管要求，转化为可执行、可复核的测试</h1>
      <p class="lead">CompanionGuard（陪伴卫士）——拟人化 AI 监管评测与风险诊断系统，是一套面向拟人化 AI 服务的监管测试与风险诊断框架。</p>
      <p class="body">项目从《人工智能拟人化互动服务管理暂行办法》的监管要求出发，将抽象的监管规则与义务转化为可以在真实产品上执行、记录和复核的测试要求，重点观察过度迎合、情感依赖、退出挽留、危机应对、未成年人保护、敏感信息诱导等拟人化互动中的风险。</p>
      <p class="body">在测试结果层面，CompanionGuard 建立了面向风险诊断的指标体系，包括风险发现率、压力鲁棒性、多轮鲁棒性、明确触发后的风险转变、专项风险指标和 Judge–Human Reliability。指标不仅记录“是否出现问题”，还用于判断风险集中在哪里、用户施压或多轮互动后模型能否继续保持安全边界，以及自动判定本身是否可靠。</p>
      <p class="body">CompanionGuard 支持建立自定义测试项目。用户可以选择需要评测的 AI 产品，配置测试范围、实验条件和分析指标，并通过统一流程完成测试、判定、人工复核和结果分析。</p>
      <div class="actions"><a class="btn primary hero-workspace-btn" href="?page=overview">进入工作台</a><a class="btn" href="#method">查看构建与方法</a></div>
      <div class="micro"><b>Finding</b> 表示在预设监管测试场景中观察到的风险表现，用于定位具体问题和支持后续审核；它不直接等同于法律意义上的不合规认定。</div>
    </div>
    <div>
      <div class="shot"><div class="fakebar"><i class="dot"></i><i class="dot"></i><i class="dot"></i><span class="small">CompanionGuard Formal Full Benchmark 2026-09</span></div><div class="shotbody"><div class="shotside"><div class="hair blue" style="width:80%"></div><div class="mini" style="width:64%"></div><div class="mini" style="width:78%"></div><div class="mini" style="width:70%"></div><div class="mini" style="width:55%;margin-top:28px"></div></div><div class="shotmain"><div class="shot-title"><div><div class="hair dark" style="width:175px"></div><div class="hair" style="width:245px"></div></div><span class="pill blue">FORMAL</span></div><div class="grid3 mock-grid"><div class="simple"><div class="small">Layer 1</div><b>对话行为</b></div><div class="simple"><div class="small">Layer 2</div><b>产品机制</b></div><div class="simple"><div class="small">Layer 3</div><b>制度材料</b></div></div><div class="simple mock-result"><div class="small">Risk Diagnosis · 结果分析</div><div class="hair red" style="width:64%"></div><div class="hair blue" style="width:84%"></div><div class="hair green" style="width:48%"></div></div></div></div></div>
      <div class="reference-project"><div class="eyebrow">PRELOADED REFERENCE PROJECT</div><h3>CompanionGuard Formal Full Benchmark 2026-09</h3><p>网站预置的完整示范项目，对三款代表性 AI 陪伴产品执行同一套监管测试方案，用于展示从测试设计到最终报告的完整流程。</p><span class="tag">3 个代表性产品</span><span class="tag">Layer 1 + Layer 2 + Layer 3</span><span class="tag">自动 Judge + 人工复核</span></div>
    </div>
  </div>
''' + r'''
  <div class="home-section divider-section"><div class="section-intro"><div class="kicker">Regulation → Testable Evidence</div><h2>从《人工智能拟人化互动服务管理暂行办法》监管要求到真实产品测试</h2><p>监管规范通常以原则和义务的形式提出要求，而产品测试需要把这些要求进一步拆解为能够被观察、记录和复核的具体问题。</p></div><div class="statement-grid"><div class="question-stack"><div class="question">模型实际会怎样回应？</div><div class="question">用户进一步施压后，原有边界还能否保持？</div><div class="question">产品是否设置了相应保护机制？</div><div class="question">公开材料能否支持对制度安排的核查？</div></div><div><div class="finding-note">CompanionGuard 将这些监管要求进一步拆解为可观察行为、标准测试场景、产品检查项和公开材料核查项，使抽象规则能够进入真实产品测试。</div><div class="flow"><span class="flowbox">监管要求</span><span class="arrow">→</span><span class="flowbox">可观察要求</span><span class="arrow">→</span><span class="flowbox">测试场景 / 产品检查</span><span class="arrow">→</span><span class="flowbox">证据记录</span><span class="arrow">→</span><span class="flowbox">结构化判定</span><span class="arrow">→</span><span class="flowbox">人工复核</span><span class="arrow">→</span><span class="flowbox">Finding</span></div></div></div></div>
  <div class="home-section divider-section" id="framework"><div class="section-intro"><div class="kicker">Three-Layer Regulatory Evaluation</div><h2>三层监管评测框架</h2><p>同一项监管要求，可能分别体现在模型回答、产品功能和企业公开制度中。CompanionGuard 对三类证据分别检查，再结合分析。</p></div><div class="grid3"><div class="framework-card"><div class="layer">Layer 1</div><h3>对话行为测试</h3><p>通过标准化测试场景观察模型实际回答。重点记录模型是否出现目标风险、问题发生在哪一轮，以及标准条件、压力条件和多轮条件下的表现是否发生变化。</p></div><div class="framework-card"><div class="layer">Layer 2</div><h3>产品安全机制检查</h3><p>检查外部测试人员能够实际观察、操作或触发的产品保护机制，包括 AI 身份提示、未成年人模式、危机干预、依赖与使用时长提醒、退出机制、数据权利以及申诉投诉入口等。</p></div><div class="framework-card"><div class="layer">Layer 3</div><h3>公开制度材料核查</h3><p>核查企业公开正式材料中能够确认的制度信息，包括敏感交互数据处理、未成年人信息保护、危机处置规则、投诉举报流程和算法备案等事项。</p></div></div><div class="note">三层结果可以相互印证，也可能出现差异。CompanionGuard 保留这些差异，不把行为、产品机制和公开制度压缩成一个统一的安全分或合规分。</div></div>
  <div class="home-section divider-section"><div class="section-intro"><div class="kicker">Core Regulatory Scope</div><h2>核心测试范围</h2><p>五类测试范围分别对应拟人化互动中具有不同证据位置和风险机制的问题。</p></div><div class="range-grid"><div class="range-card"><h3>关系安全</h3><p>检查模型是否过度迎合用户、强化排他性关系、支持以 AI 替代现实人际关系，或在用户准备退出时施加挽留压力。</p></div><div class="range-card"><h3>极端行为与危机应对</h3><p>检查模型是否支持暴力行为，以及面对自伤、自杀等高风险情境时，能否提供符合要求的安全回应；同时检查语言暴力和人格伤害。</p></div><div class="range-card"><h3>未成年人保护</h3><p>检查未成年人虚拟亲密关系边界，以及模型是否鼓励或正常化不安全行为、极端情绪和不良嗜好。</p></div><div class="range-card"><h3>信息与权益保护</h3><p>检查模型是否诱导用户披露工作秘密、商业秘密、第三方隐私、个人信息或其他敏感内容。</p></div><div class="range-card"><h3>禁止性内容专项测试</h3><p>使用固定单轮测试检查七类明确禁止内容，补充传统内容安全评测。</p></div></div></div>
  <div class="home-section divider-section"><div class="section-intro"><div class="kicker">Custom Test Projects</div><h2>支持自定义测试项目</h2><p>CompanionGuard 不限于一套固定 benchmark。用户可以根据实际审核任务建立新的测试项目，并选择产品、测试范围、实验条件、分析指标和证据范围。</p></div><div class="project-config"><div class="config-list"><div class="config-item"><b>测试产品</b><span>选择需要纳入评测的拟人化 AI、AI 陪伴产品或其他目标模型。</span></div><div class="config-item"><b>测试范围</b><span>选择需要执行的模块、准则和测试场景。</span></div><div class="config-item"><b>实验条件</b><span>配置标准条件、压力条件、多轮条件以及专项测试。</span></div><div class="config-item"><b>分析指标</b><span>选择总体风险、条件鲁棒性、专项风险和 Judge–Human Reliability 等指标。</span></div><div class="config-item"><b>证据范围</b><span>按项目需要组合对话测试、产品机制检查和公开材料核查。</span></div><div class="config-item"><b>统一工作流</b><span>通过同一 Project 完成测试、判定、人工复核与结果分析。</span></div></div><div class="reference-project"><div class="eyebrow">REFERENCE CONFIGURATION</div><h3>CompanionGuard Formal Full Benchmark 2026-09</h3><p>预置的完整参考方案。用户也可以在同一框架下建立更小的专项测试，或者针对新的产品和监管问题配置独立项目。</p><span class="tag">统一监管测试方案</span><span class="tag">三层证据</span><span class="tag">可配置 Project</span></div></div></div>
  <div class="home-section divider-section"><div class="section-intro"><div class="kicker">Dialogue Conditions</div><h2>对话测试与实验条件</h2><p>核心对话场景通过分阶段信息设计，区分用户状态、风险事实和明确请求，并在不同实验条件下观察模型表现。</p></div><div class="condition-grid"><div class="condition-card"><div class="codebig">C0</div><h3>标准条件 / Baseline Condition</h3><p>在自然、集中表达的测试场景中观察模型的基本表现。</p><div class="question-line">在常规交互下，模型能否遵守相应安全要求？</div></div><div class="condition-card"><div class="codebig amber-text">C1</div><h3>压力条件 / Pressure Condition</h3><p>保持关键事实不变，只增强用户的互动压力，例如要求模型站队、拒绝安全建议或推动模型改变原有回应。</p><div class="question-line">当用户进一步施压时，模型能否继续保持原有边界？</div></div><div class="condition-card"><div class="codebig purple-text">C2</div><h3>多轮条件 / Sequential Multi-turn Condition</h3><p>将场景信息逐轮呈现，形成连续互动。</p><div class="question-line">随着上下文逐步累积，模型能否在多轮对话中持续保持相应要求？</div></div></div><div class="note">三种实验条件分别观察不同问题，因此分别记录和比较，不合并为一种笼统的“高难度测试”。</div></div>
  <div class="home-section divider-section"><div class="section-intro"><div class="kicker">Structured Judgment</div><h2>LLM Judge + 人工复核</h2><p>CompanionGuard 使用受准则约束的 LLM-as-Judge 进行结构化初判，并保留人工确认与改判链路。</p></div><div class="judge-layout"><div class="judge-box"><h3>LLM Judge 依据预定义边界判定</h3><p class="small">每项测试在执行前定义 Target Behaviors、Non-target Behaviors 和边界规则。Judge 不能自由评论“回答好不好”，而是围绕已定义 Criterion 做结构化初判。</p><div class="judge-output"><span class="pill red">FINDING</span><span class="pill green">NO_FINDING</span><span class="pill amber">REVIEW</span></div><p class="small">Finding 还需要保留模型原回答中的证据。</p></div><div class="judge-box"><h3>自动判定与人工判断可追溯</h3><p class="small">自动 Judge 用于提高大规模评测效率，人工复核用于确认 Finding、处理边界案例和记录改判。系统同时记录自动判断、人工判断和最终标签，使每一次改判都可以追溯。</p><div class="flow"><span class="flowbox">Auto Judgment</span><span class="arrow">→</span><span class="flowbox">Human Review</span><span class="arrow">→</span><span class="flowbox">Final Label</span></div></div></div></div>
  <div class="home-section divider-section" id="metrics"><div class="section-intro"><div class="kicker">Metrics &amp; Risk Diagnosis</div><h2>如何理解评测结果</h2><p>CompanionGuard 不只记录“有没有发现问题”，还通过不同指标说明问题出现在哪里、在什么条件下更容易出现，以及模型面对更复杂互动时能否继续保持安全要求。</p></div><div class="metric-framework-title">指标框架</div><div class="metric-feature"><div class="metric-card wide"><div class="metric-en">FINDING · 风险发现</div><h3>定位具体场景中的目标风险</h3><p><b>Finding</b> 表示模型在某个预设测试场景中出现了符合目标风险定义的行为。它是后续分析的基本单位，告诉审核人员哪一个场景出现了什么问题，但不直接等同于法律意义上的“不合规”。</p></div><div class="metric-card"><div class="metric-en">OVERALL MACRO FINDING RATE · 总体风险发现率</div><h3>总体风险发现率｜问题分布有多广</h3><p>用于观察多个测试模块中的 Finding 分布情况，并帮助判断风险是分散出现还是集中于某个模块或准则。总体比例需要与高风险场景的具体结果结合阅读。</p></div><div class="metric-card"><div class="metric-en">PRESSURE ROBUSTNESS GAP · 压力鲁棒性</div><h3>压力鲁棒性｜用户施压后还能否守住边界</h3><p>比较 C1 压力条件与 C0 标准条件下的风险发现率，用于观察用户进一步施压时模型的边界保持能力。</p></div><div class="metric-card"><div class="metric-en">MULTI-TURN ROBUSTNESS GAP · 多轮鲁棒性</div><h3>多轮鲁棒性｜对话持续后表现是否变化</h3><p>比较 C2 多轮条件与 C0 标准条件，观察相同风险信息从一次集中表达变成逐轮累积后，模型表现是否发生变化。</p></div><div class="metric-card"><div class="metric-en">ELICITATION FLIP · 明确触发后的风险转变</div><h3>明确要求之后是否发生转变</h3><p>关注模型从 <code>NO_FINDING</code> 转为 <code>FINDING</code> 的情况，用于判断问题是在风险状态出现时已经存在，还是在用户明确推动模型越过边界后才出现。</p></div><div class="metric-card"><div class="metric-en">SPECIALIZED METRICS · 专项指标</div><h3>定位具体安全能力</h3><div class="metric-name-list">急性风险保护失败率 · 两轮追问中的关系限制失败 · 未成年人内容风险发现率 · 禁止性内容分类风险发现率</div><p>这些指标分别定位不同监管问题中的具体安全能力，而不是把不同类型风险合并成一个难以解释的总比例。</p></div><div class="metric-card"><div class="metric-en">JUDGE–HUMAN RELIABILITY · 判定一致性</div><h3>自动判定的可靠性</h3><p>使用完全一致率、Cohen's Kappa、Finding Precision 与 Finding Recall 等指标评价评测工具本身的可靠性，而不是产品安全水平。</p></div></div></div>
  <div class="home-section divider-section" id="method"><div class="section-intro"><div class="kicker">Construction &amp; Method</div><h2>构建与方法</h2><p>首页仅展示 CompanionGuard 的主要设计。完整方法说明保留监管映射、正式判定边界、标准测试语句和可复现性细节。</p></div><div class="method-steps"><div class="method-step"><div class="n">01</div><h3>从监管要求确定测试对象</h3><p>先确定《人工智能拟人化互动服务管理暂行办法》监管规范要求平台避免什么行为、履行什么义务，再将其拆解为可以观察和记录的测试要求。</p></div><div class="method-step"><div class="n">02</div><h3>设计标准化测试场景</h3><p>使用统一场景和判定边界，使不同产品在相同条件下接受测试。</p></div><div class="method-step"><div class="n">03</div><h3>设置不同实验条件</h3><p>通过标准、压力和多轮条件，检查模型在不同互动方式下是否保持一致表现。</p></div><div class="method-step"><div class="n">04</div><h3>分别采集三层证据</h3><p>对话行为、产品机制和公开制度材料分别记录，避免把不同证据来源混为一谈。</p></div><div class="method-step"><div class="n">05</div><h3>自动判定与人工复核</h3><p>LLM Judge 完成结构化初判，人工负责确认 Finding、处理边界案例和记录改判。</p></div><div class="method-step"><div class="n">06</div><h3>从指标进入风险分析</h3><p>指标用于定位风险集中位置、实验条件差异和判定可靠性，并进一步支持产品比较、跨层分析和监管报告。</p></div></div><div class="downloadbox"><div><b>查看完整方法说明</b><p>完整文档进一步说明监管条款与测试模块的对应关系、L1–L5 对话结构、C0 / C1 / C2 实验条件、各类 Criterion 判定规则、Judge 与人工复核、指标体系、Layer 2 / Layer 3 检查表、标准测试语句以及研究伦理、效度与可复现性。</p></div><a class="btn primary" href="#method">下载《CompanionGuard Benchmark 构建与方法设计说明》</a></div></div>
  <div class="footer"><span>CompanionGuard · Regulatory Testing &amp; Risk Diagnosis</span><span>App v0.9 · Data Schema v1.0</span></div>
</section></div>'''


GOLDEN_CSS = r'''<style>
:root{--bg:#f6f7f9;--s:#fff;--t:#101828;--m:#667085;--b:#e4e7ec;--blue:#3156d9;--bluebg:#eef3ff;--red:#b42318;--redbg:#fef3f2;--amber:#b54708;--amberbg:#fffaeb;--green:#067647;--greenbg:#ecfdf3;--purple:#6941c6;--purplebg:#f4f3ff}
.cg-home,.cg-workspace{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif;color:#101828;background:#f6f7f9;overflow-x:hidden;min-width:0}.cg-home{margin:-28px -32px -72px}.cg-home *,.cg-workspace *{box-sizing:border-box}.cg-home a{text-decoration:none;color:inherit}
.cg-home .topnav{height:72px;max-width:1240px;margin:auto;padding:0 20px;background:#fff;display:flex;align-items:center;justify-content:space-between}.cg-home .brand,.cg-workspace .brand{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:750;color:#101828}.mark{width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#3156d9 0 55%,#91a8ff 55%)}.cg-home .navlinks{display:flex;align-items:center;gap:26px;color:#475467;font-size:13px}.cg-home .navlinks a:not(.btn):hover{color:#3156d9}
.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid #e4e7ec;border-radius:8px;background:#fff;color:#344054;font-size:12px;font-weight:600;padding:9px 14px;min-height:34px;cursor:pointer}.btn.primary{background:#3156d9;border-color:#3156d9;color:#fff}.hero-workspace-btn{padding:13px 24px;font-size:14px;font-weight:780;border-radius:9px;min-height:44px}.cg-home .hero{max-width:1240px;margin:auto;padding:88px 20px 104px;background:#fff;display:grid;grid-template-columns:1.02fr .98fr;gap:64px}.home-kicker{font-size:11px;font-weight:750;letter-spacing:.1em;color:#3156d9}.hero h1{font-size:56px;line-height:1.05;letter-spacing:-.045em;margin:18px 0 22px;color:#101828}.hero-copy .lead{font-size:17px;line-height:1.8;color:#475467;margin:0 0 15px}.hero-copy .body{font-size:13px;line-height:1.8;color:#667085;margin:0 0 12px}.actions{display:flex;gap:10px;margin-top:22px}.hero-copy .micro{font-size:11.5px;line-height:1.65;color:#667085;margin-top:18px;padding-top:16px;border-top:1px solid #eef1f5}.shot{border:1px solid #dde3ec;border-radius:16px;box-shadow:0 24px 60px rgba(16,24,40,.11);overflow:hidden;background:#fff}.fakebar{height:42px;background:#f8fafc;border-bottom:1px solid #e4e7ec;display:flex;align-items:center;padding:0 14px;gap:7px}.dot{width:8px;height:8px;border-radius:50%;background:#cbd5e1}.fakebar .small{margin-left:8px}.shotbody{display:grid;grid-template-columns:140px 1fr;min-height:400px}.shotside{padding:16px 12px;background:#fbfcfe;border-right:1px solid #eef1f5}.shotmain{padding:24px}.hair,.mini{height:9px;background:#e4e7ec;border-radius:4px;margin-bottom:10px}.hair.dark{height:12px;background:#344054}.hair.blue{background:#b9c7ff}.hair.red{background:#f5a29a}.hair.green{background:#95dfb0}.mini{height:7px}.shot-title{display:flex;justify-content:space-between;align-items:flex-start}.mock-grid{margin-top:22px!important}.mock-grid .simple{padding:13px}.simple{border:1px solid #e4e7ec;border-radius:8px;background:#fff}.simple b{font-size:15px}.mock-result{margin-top:12px;padding:15px}.small{font-size:10.5px;color:#667085;line-height:1.55}.pill{display:inline-flex;padding:4px 8px;border:1px solid #e4e7ec;border-radius:999px;background:#fff;font-size:10px;color:#475467;font-weight:650}.pill.blue{background:#eef3ff;border-color:#dce6ff;color:#2946b6}.pill.red{background:#fef3f2;border-color:#fee4e2;color:#b42318}.pill.green{background:#ecfdf3;border-color:#d1fadf;color:#067647}.pill.amber{background:#fffaeb;border-color:#fdecc8;color:#b54708}.reference-project{background:#eef4fb;border:1px solid #d8e4f2;border-radius:14px;padding:24px}.eyebrow{font-size:10px;letter-spacing:.08em;font-weight:750;color:#3156d9}.reference-project h3{font-size:19px;margin:10px 0 8px;color:#101828}.reference-project p{font-size:12px;line-height:1.7;color:#475467;margin:0 0 14px}.tag{display:inline-block;background:#fff;border:1px solid #d8e4f2;color:#475467;border-radius:999px;padding:5px 8px;font-size:10px;margin:3px 4px 0 0}
.home-section{max-width:1200px;margin:auto;padding:62px 20px}.divider-section{border-top:1px solid #e4e7ec}.section-intro{max-width:760px;margin-bottom:28px}.kicker{font-size:10px;color:#3156d9;font-weight:750;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}.section-intro h2{font-size:30px;letter-spacing:-.025em;margin:0 0 10px;color:#101828}.section-intro>p{font-size:13px;line-height:1.75;color:#667085;margin:0}.statement-grid,.project-config{display:grid;grid-template-columns:1.1fr .9fr;gap:18px}.question-stack{display:flex;flex-direction:column;gap:9px}.question{background:#fff;border:1px solid #e4e7ec;border-radius:10px;padding:14px 15px;font-size:13px;font-weight:650;color:#344054}.finding-note{background:#f8faff;border:1px solid #dce6ff;border-radius:11px;padding:16px 18px;font-size:12px;line-height:1.7;color:#344054}.flow{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-top:16px}.flowbox{background:#fff;border:1px solid #dce6ff;border-radius:9px;padding:13px 16px;font-size:12px;font-weight:650;color:#344054}.arrow{color:#98a2b3}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.framework-card{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:22px}.layer,.method-step .n{font-size:10px;font-weight:800;letter-spacing:.08em;color:#3156d9}.framework-card h3{font-size:16px;margin:8px 0;color:#101828}.framework-card p{font-size:12px;line-height:1.7;color:#667085;margin:0}.note{background:#f8fafc;border:1px solid #e4e7ec;border-radius:10px;padding:13px 15px;font-size:11.5px;line-height:1.7;color:#475467;margin-top:16px}.range-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.range-card,.config-item,.condition-card,.judge-box,.metric-card,.method-step{background:#fff;border:1px solid #e4e7ec;border-radius:11px}.range-card{padding:18px}.range-card h3{font-size:13px;margin:0 0 8px;color:#101828}.range-card p{font-size:11.5px;line-height:1.65;color:#667085;margin:0}.config-list{display:grid;grid-template-columns:1fr 1fr;gap:10px}.config-item{padding:16px;border-radius:10px}.config-item b{display:block;font-size:12px;margin-bottom:5px;color:#344054}.config-item span{font-size:11px;line-height:1.6;color:#667085}.condition-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.condition-card{padding:20px;border-radius:12px}.codebig{font-size:28px;font-weight:800;color:#3156d9}.amber-text{color:#b54708}.purple-text{color:#6941c6}.condition-card h3{font-size:14px;margin:6px 0;color:#101828}.condition-card p{font-size:11.5px;line-height:1.65;color:#667085;margin:0 0 12px}.question-line{border-top:1px solid #eef1f5;padding-top:11px;font-size:11px;font-weight:700;color:#344054}.judge-layout{display:grid;grid-template-columns:.85fr 1.15fr;gap:18px}.judge-box{padding:22px;border-radius:12px}.judge-box h3{font-size:15px;margin:0 0 8px;color:#101828}.judge-output{display:flex;gap:8px;margin:14px 0}.metric-framework-title{font-size:16px;font-weight:750;color:#344054;margin:0 0 12px}.metric-feature{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.metric-card{padding:19px;border-radius:12px}.metric-card.wide{grid-column:span 2}.metric-en{font-size:13.5px;line-height:1.35;letter-spacing:.015em;color:#3156d9;font-weight:800;margin-bottom:8px}.metric-card h3{font-size:13px;margin:0 0 8px;color:#101828}.metric-card p{font-size:11.5px;line-height:1.7;color:#667085;margin:0}.metric-name-list{font-size:11px;line-height:1.8;color:#344054;margin-bottom:8px}.method-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.method-step{padding:18px;border-radius:11px}.method-step h3{font-size:13px;margin:7px 0 6px;color:#101828}.method-step p{font-size:11px;line-height:1.65;color:#667085;margin:0}.downloadbox{display:flex;justify-content:space-between;align-items:center;gap:24px;background:#101828;color:#fff;border-radius:13px;padding:24px 26px;margin-top:24px}.downloadbox b{font-size:15px}.downloadbox p{font-size:12px;line-height:1.6;color:#d0d5dd;margin:6px 0 0}.footer{max-width:1200px;margin:auto;border-top:1px solid #e4e7ec;padding:46px 20px 70px;display:flex;justify-content:space-between;color:#667085;font-size:11px}
.cg-workspace{display:grid;grid-template-columns:244px 1fr;min-height:calc(100vh - 34px)}.cg-workspace .sidebar-shell{overflow-y:auto;max-height:100vh;background:#fbfcfd;border-right:1px solid #e4e7ec;padding:18px 14px;min-height:calc(100vh - 34px)}.sidebrand{padding:4px 10px 20px}.projectbox{background:#fff;border:1px solid #e4e7ec;border-radius:9px;padding:11px 12px;margin:0 5px 16px}.projectbox .k{font-size:10px;text-transform:uppercase;color:#98a2b3;letter-spacing:.08em}.projectbox .v{font-size:13px;font-weight:700;margin:5px 0 8px;color:#101828}.projectbox .project-note{font-size:9.5px;line-height:1.4;color:#98a2b3}.navtree{padding:6px 8px 18px}.navhome{display:block;padding:10px 12px;margin:2px 0 8px;border-radius:8px;font-size:12px;font-weight:760;color:#344054}.navgroup{margin:7px 0 9px}.navgroup-toggle,.navlayer-toggle{width:100%;color:#344054;text-align:left;padding:8px 10px;border:0;background:transparent;border-radius:8px}.navgroup-toggle .row,.navlayer-toggle .row{display:flex;align-items:center;gap:7px}.navgroup-toggle .caret,.navlayer-toggle .caret{width:12px;color:#98a2b3;font-size:10px}.navgroup-toggle .zh{font-size:11.7px;font-weight:800;line-height:1.25}.navgroup-toggle .en{display:block;margin:3px 0 0 19px;font-size:9.5px;line-height:1.2;color:#98a2b3}.navgroup-body{padding:2px 0 2px 10px}.navlayer{margin:5px 0 6px 2px}.navlayer-toggle{padding:7px 8px}.navlayer-toggle .zh{font-size:10.8px;font-weight:760;line-height:1.3;color:#475467}.navlayer-toggle .en{display:block;margin:3px 0 0 19px;font-size:9px;line-height:1.2;color:#98a2b3}.navlayer-body{padding:2px 0 1px 14px}.navleaf{width:100%;display:block;padding:7px 10px 7px 11px;margin:2px 0;border:0;border-radius:7px;background:transparent;color:#475467;text-align:left;font-size:11.4px;font-weight:680;line-height:1.25;cursor:pointer;white-space:pre-line}.navleaf:hover{background:#f5f7fa}.navleaf.active{background:#eef2ff;color:#273b8f}.navstatic{padding:10px 10px 8px 29px;margin:8px 0;border-top:1px solid #eef1f5}.navstatic .zh{font-size:11.7px;font-weight:800;line-height:1.3;color:#344054}.navstatic .en{font-size:9.5px;line-height:1.2;color:#98a2b3;margin-top:3px}.workspace-content{min-width:0}.workspace-bar{height:62px;margin:-28px -32px 0;background:#fff;border-bottom:1px solid #e4e7ec;display:flex;justify-content:space-between;align-items:center;padding:0 28px}.crumb{font-size:12px;color:#667085}.crumb b{color:#344054}.baract{display:flex;gap:8px;align-items:center}.workspace-canvas{padding:28px 32px 72px;max-width:1500px;margin:0 auto}.workspace-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.workspace-head h1{font-size:25px;margin:0 0 6px;color:#101828}.workspace-head p{font-size:12.5px;color:#475467;margin:0;line-height:1.62}.workspace-pill{padding:4px 8px;border:1px solid #e4e7ec;border-radius:999px;font-size:10px;color:#475467;font-weight:650}.workspace-pill.blue{background:#eef3ff;border-color:#dce6ff;color:#2946b6}.workspace-canvas .stButton>button,.workspace-canvas .stDownloadButton>button{font-size:12px;line-height:1.2;min-height:34px;padding:9px 14px;border-radius:8px}.workspace-canvas input,.workspace-canvas textarea,.workspace-canvas [data-baseweb="select"]{font-size:12px}.workspace-canvas [data-testid="stWidgetLabel"]{font-size:11px}.cg-sidebar-select label{font-size:10px!important;color:#98a2b3!important}.cg-sidebar-select [data-baseweb="select"]{font-size:11px!important}.cg-sidebar button{font-family:inherit}.cg-sidebar [data-testid="stButton"]{margin:0!important}.cg-sidebar [data-testid="stButton"] button{border:0!important;box-shadow:none!important;width:100%;background:transparent!important;text-align:left!important;color:#475467!important;padding:7px 10px 7px 11px!important;margin:2px 0!important;border-radius:7px!important;font-size:11.4px!important;font-weight:680!important;line-height:1.25!important;white-space:pre-line!important;min-height:0!important}.cg-sidebar [data-testid="stButton"] button:hover{background:#f5f7fa!important}.cg-sidebar [data-testid="stButton"] button[kind="primary"],.cg-sidebar [data-testid="stButton"] button:focus{background:#eef2ff!important;color:#273b8f!important}.cg-sidebar .projectbox + [data-testid="stVerticalBlock"]{gap:0}.cg-shell-nav-spacer{height:0}
@media(max-width:1100px){.cg-home .hero{grid-template-columns:1fr;gap:36px}.range-grid{grid-template-columns:1fr 1fr}.downloadbox{align-items:flex-start;flex-direction:column}}@media(max-width:760px){.cg-home .topnav{height:auto;min-height:72px;align-items:flex-start;padding-top:16px;padding-bottom:16px;gap:16px;flex-direction:column}.cg-home .navlinks{gap:12px;flex-wrap:wrap}.hero h1{font-size:42px}.statement-grid,.project-config,.judge-layout,.metric-feature{grid-template-columns:1fr}.metric-card.wide{grid-column:auto}.grid3,.condition-grid,.method-steps{grid-template-columns:1fr}.range-grid{grid-template-columns:1fr}.cg-workspace{grid-template-columns:1fr}.cg-workspace .sidebar-shell{min-height:auto;max-height:none}.workspace-bar{padding:0 16px}.workspace-canvas{padding:20px 16px 52px}}
[data-testid="stSidebar"] [data-testid="stButton"]{margin:0!important}[data-testid="stSidebar"] [data-testid="stButton"] button{border:0!important;box-shadow:none!important;width:100%;background:transparent!important;text-align:left!important;color:#475467!important;padding:7px 10px 7px 11px!important;margin:2px 0!important;border-radius:7px!important;font-size:11.4px!important;font-weight:680!important;line-height:1.25!important;white-space:pre-line!important;min-height:0!important}[data-testid="stSidebar"] [data-testid="stButton"] button:hover{background:#f5f7fa!important}[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]{background:#eef2ff!important;color:#273b8f!important}[data-testid="stSidebar"] [data-testid="stSelectbox"]{margin:0 5px 10px}[data-testid="stSidebar"] [data-testid="stSelectbox"] label{font-size:10px!important;color:#98a2b3!important}[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"]{font-size:11px!important}.navlayer-toggle{padding-left:14px!important}[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:10.4px!important}.report-llm-heading{font-size:15px!important;font-weight:750!important;color:#3156d9!important}[data-testid="stMain"] button[kind="primary"]{background:#3156d9!important;color:#fff!important;border-color:#3156d9!important}
.workspace-head h1{font-size:25px!important;font-weight:780!important;color:#101828}.workspace-head p{font-size:12.5px!important;font-weight:550!important;color:#667085!important}.crumb{font-size:12px!important;font-weight:550!important;color:#667085}.crumb b{font-weight:600!important;color:#667085}.navgroup-toggle .zh{font-size:13.5px!important;font-weight:800!important;line-height:1.3!important;color:#344054!important}.navgroup-toggle .en{font-size:10.5px!important;font-weight:500!important;color:#98a2b3!important}.navlayer-toggle{padding-left:16px!important}.navlayer-toggle .zh{font-size:12.4px!important;font-weight:750!important;color:#475467!important}.navlayer-toggle .en{font-size:10px!important;font-weight:500!important;color:#98a2b3!important}.report-document-marker{display:none}.report-document-marker~*{}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h1{font-size:25px!important;font-weight:750!important;line-height:1.25!important;color:#101828!important;margin:0 0 16px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h2{font-size:20px!important;font-weight:720!important;line-height:1.3!important;color:#1d2939!important;margin:24px 0 10px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h3{font-size:16px!important;font-weight:700!important;line-height:1.35!important;color:#344054!important;margin:18px 0 8px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] p,[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] li{font-size:13px!important;line-height:1.75!important;color:#475467!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] small{font-size:11px!important;color:#667085!important}
[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:11.4px!important}.report-action-heading{margin:18px 0 8px}.report-action-eyebrow{font-size:10.5px!important;line-height:1.2!important;letter-spacing:.08em!important;color:#667085!important;font-weight:600!important;text-transform:uppercase}.report-action-title{font-size:15px!important;font-weight:750!important;line-height:1.35!important;color:#3156d9!important}.report-action-subtitle{font-size:11.5px!important;line-height:1.35!important;color:#667085!important;font-weight:550!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h1{font-size:25px!important;font-weight:750!important;line-height:1.25!important;color:#101828!important;margin:0 0 16px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h2{font-size:20px!important;font-weight:720!important;line-height:1.3!important;color:#1d2939!important;margin:24px 0 10px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h3{font-size:16px!important;font-weight:700!important;line-height:1.35!important;color:#344054!important;margin:18px 0 8px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] p,[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] li{font-size:13px!important;line-height:1.75!important;color:#475467!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] small{font-size:11px!important;color:#667085!important}.workspace-bar{margin:-28px -32px -12px!important}[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:10.8px!important;font-weight:640!important;line-height:1.32!important}
.workspace-head h1{font-size:25px!important;font-weight:780!important;color:#101828}.workspace-head p{font-size:12.5px!important;font-weight:550!important;color:#667085!important}.crumb{font-size:12px!important;font-weight:550!important;color:#667085}.crumb b{font-weight:600!important;color:#667085}.navgroup-toggle .zh{font-size:13.5px!important;font-weight:800!important;line-height:1.3!important;color:#344054!important}.navgroup-toggle .en{font-size:10.5px!important;font-weight:500!important;color:#98a2b3!important}.navlayer-toggle{padding-left:16px!important}.navlayer-toggle .zh{font-size:12.4px!important;font-weight:750!important;color:#475467!important}.navlayer-toggle .en{font-size:10px!important;font-weight:500!important;color:#98a2b3!important}.report-document-marker{display:none}.report-document-marker~*{}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h1{font-size:25px!important;font-weight:750!important;line-height:1.25!important;color:#101828!important;margin:0 0 16px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h2{font-size:20px!important;font-weight:720!important;line-height:1.3!important;color:#1d2939!important;margin:24px 0 10px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] h3{font-size:16px!important;font-weight:700!important;line-height:1.35!important;color:#344054!important;margin:18px 0 8px!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] p,[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] li{font-size:13px!important;line-height:1.75!important;color:#475467!important}[data-testid="stVerticalBlock"]:has(.report-document-marker) [data-testid="stMarkdownContainer"] small{font-size:11px!important;color:#667085!important}
</style>'''


def inject_golden_css() -> None:
    """Apply the source CSS plus narrow Streamlit wrapper normalization."""
    st.markdown(GOLDEN_CSS, unsafe_allow_html=True)
    st.markdown(
        """<style>
        [data-testid="stAppViewContainer"]{background:#f6f7f9}
        [data-testid="stMainBlockContainer"]{padding:28px 32px 72px!important;max-width:none!important}
        [data-testid="stHeader"]{background:transparent}
        section[data-testid="stSidebar"]{width:244px!important;min-width:244px!important;background:#fbfcfd}
        section[data-testid="stSidebar"]>div{width:244px!important}
        [data-testid="stSidebarContent"]{padding:0!important}
        [data-testid="stMarkdownContainer"]{overflow-wrap:anywhere}
        </style>""",
        unsafe_allow_html=True,
    )


def _set_page(page_id: str) -> None:
    st.session_state["nav_page"] = page_id
    try:
        st.query_params["page"] = page_id
    except Exception:
        pass


def home_page() -> None:
    st.markdown(HOME_HTML, unsafe_allow_html=True)


def _label(page_id: str) -> str:
    zh, en, level = NAV_LABELS[page_id]
    # The line break is rendered by the Golden nav CSS as the fixed two-line leaf.
    indent = "\u2003" if level == 2 else "\u2003\u2003" if level == 3 else ""
    return f"{indent}{zh}\n{indent}{en}"


def _nav_button(page_id: str, *, active: bool) -> None:
    st.sidebar.button(
        _label(page_id),
        key=f"golden-nav::{page_id}",
        on_click=_set_page,
        args=(page_id,),
        type="primary" if active else "secondary",
        use_container_width=True,
    )


def _group_heading(zh: str, en: str, *, layer: bool = False) -> None:
    cls = "navlayer-toggle" if layer else "navgroup-toggle"
    st.sidebar.markdown(
        f'<div class="{cls}"><div class="row"><span class="caret">⌄</span><span class="zh">{escape(zh)}</span></div><span class="en">{escape(en)}</span></div>',
        unsafe_allow_html=True,
    )


def _project_selector() -> dict[str, Any] | None:
    projects = list_projects()
    if not projects:
        st.sidebar.markdown(
            '<div class="projectbox"><div class="k">Test Project · 测试项目</div><div class="v">暂无可用项目</div><div class="project-note">Project data will appear here when a writable project is available.</div></div>',
            unsafe_allow_html=True,
        )
        return None
    ids = [str(p["project_id"]) for p in projects]
    active_id = st.session_state.get("active_project_id")
    if active_id not in ids:
        active_id = ids[0]
        st.session_state["active_project_id"] = active_id
    active = get_project(active_id)
    project_name = str((active or {}).get("project_name") or "CompanionGuard Formal Full Benchmark 2026-09")
    st.sidebar.markdown(
        f'<div class="projectbox"><div class="k">Test Project · 测试项目</div><div class="v">{escape(project_name)}</div><div style="display:flex;gap:6px;align-items:center;justify-content:space-between"><span class="pill blue">FORMAL</span><span class="btn" style="padding:5px 8px;font-size:10px">切换项目</span></div><div class="project-note"><b>Compatibility target</b><br>formal-collection-freeze-20260915-products<br><br><b>Schema</b><br>Data v1.0 · no migration expected</div></div>',
        unsafe_allow_html=True,
    )
    with st.sidebar.container():
        st.markdown('<div class="cg-sidebar-select">', unsafe_allow_html=True)
        selected = st.selectbox(
            "切换项目",
            ids,
            index=ids.index(active_id),
            format_func=lambda pid: str(next(p.get("project_name", pid) for p in projects if str(p["project_id"]) == pid)),
            key="golden-project-selector",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    if selected != active_id:
        st.session_state["active_project_id"] = selected
        st.rerun()
    return active


def render_workspace_sidebar(page_id: str) -> dict[str, Any] | None:
    st.sidebar.markdown('<div class="cg-sidebar"><div class="sidebrand"><div class="brand"><span class="mark"></span>CompanionGuard</div></div></div>', unsafe_allow_html=True)
    project = _project_selector()
    st.sidebar.markdown('<div class="cg-sidebar"><div class="navtree"><a class="navhome" href="?page=home">Home｜首页</a>', unsafe_allow_html=True)
    _group_heading("01 项目与测试", "Project Setup")
    for item in ("testdesign", "plan", "collector", "overview"):
        _nav_button(item, active=page_id == item)
    _group_heading("02 三层证据评测", "Three-Layer Evaluation")
    _group_heading("Layer 1｜对话行为测试", "Dialogue Testing", layer=True)
    for item in ("judge", "review", "explorer", "reliability", "results"):
        _nav_button(item, active=page_id == item)
    _group_heading("Layer 2｜产品安全机制检查", "Product Safeguard Checks", layer=True)
    _nav_button("layer2", active=page_id == "layer2")
    _group_heading("Layer 3｜公开制度材料核查", "Public Evidence Audit", layer=True)
    _nav_button("layer3", active=page_id == "layer3")
    _group_heading("03 报告", "Reports")
    for item in ("dialogue_report", "report"):
        _nav_button(item, active=page_id == item)
    st.sidebar.markdown("</div></div>", unsafe_allow_html=True)
    return project


def render_workspace_topbar(page_id: str) -> None:
    zh, en = PAGE_META[page_id]
    st.markdown(
        f'''<div class="workspace-bar"><div class="crumb">CompanionGuard <span>/</span> <b>{escape(zh)}</b></div><div class="baract"><span class="workspace-pill blue">产品列表 · 来自 project.json</span><span class="workspace-pill">FORMAL</span><a class="btn" href="?page=home">主页</a></div></div>''',
        unsafe_allow_html=True,
    )


def render_workspace_head(page_id: str) -> None:
    zh, en = PAGE_META[page_id]
    st.markdown(
        f'''<div class="workspace-head"><div><h1>{escape(zh)}</h1><p>{escape(en)}</p></div><span class="workspace-pill blue">Data Schema v1.0</span></div>''',
        unsafe_allow_html=True,
    )


def current_project_overview_page() -> None:
    project = get_project(st.session_state.get("active_project_id"))
    st.markdown('<div class="card"><div class="cardhead"><span class="workspace-pill blue">FORMAL</span></div><div class="cardbody">', unsafe_allow_html=True)
    if project:
        st.markdown(f"**{project.get('project_name', 'CompanionGuard Formal Full Benchmark 2026-09')}**  \nProject ID: `{project.get('project_id')}`", unsafe_allow_html=True)
        st.caption("保留原有项目数据、测试流程与结果文件。")
    else:
        st.info("请选择一个测试项目。")
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_page(page_id: str) -> None:
    if page_id == "testdesign":
        projects_page()
    elif page_id in {"plan", "collector"}:
        data_collection_page()
    elif page_id == "overview":
        current_project_overview_page()
    elif page_id == "judge":
        run_test_page()
    elif page_id == "review":
        human_review_page()
    elif page_id == "explorer":
        data_explorer_page()
    elif page_id == "reliability":
        reliability_page(get_criteria())
    elif page_id == "results":
        results_page()
    elif page_id == "dialogue_report":
        dialogue_report_page(get_criteria())
    elif page_id == "layer2":
        layer2_page()
    elif page_id == "layer3":
        layer3_page()
    elif page_id == "report":
        report_page(get_criteria())


def _workflow_nav(page_id: str) -> None:
    ordered = [p for p in PAGE_META if p != "home"]
    idx = ordered.index(page_id)
    left, right = st.columns([1, 1])
    with left:
        if idx > 0 and st.button("← Previous", key=f"golden-prev::{page_id}"):
            _set_page(ordered[idx - 1])
            st.rerun()
    with right:
        if idx < len(ordered) - 1 and st.button("Next →", key=f"golden-next::{page_id}", type="primary"):
            _set_page(ordered[idx + 1])
            st.rerun()


def run_app() -> None:
    ensure_deployment_project()
    requested_page = st.query_params.get("page")
    remembered_page = st.session_state.get("nav_page", "home")
    shell_page = requested_page if requested_page in PAGE_META else remembered_page
    st.set_page_config(
        page_title="CompanionGuard",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="collapsed" if shell_page == "home" else "expanded",
    )
    inject_golden_css()
    query_page = requested_page
    if query_page in PAGE_META:
        st.session_state["nav_page"] = query_page
    page_id = st.session_state.get("nav_page", "home")
    if page_id not in PAGE_META:
        page_id = "home"
        st.session_state["nav_page"] = page_id
    if page_id == "home":
        home_page()
        return
    render_workspace_sidebar(page_id)
    render_workspace_topbar(page_id)
    st.markdown('<div class="workspace-canvas">', unsafe_allow_html=True)
    render_workspace_head(page_id)
    render_page(page_id)
    _workflow_nav(page_id)
    st.markdown("</div>", unsafe_allow_html=True)
