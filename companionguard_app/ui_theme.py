"""Chinese-first v0.9 presentation helpers.

This module is deliberately presentation-only. It does not load, transform, or
persist project data; callers remain responsible for using the existing data
contract and machine values.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def inject_theme() -> None:
    """Apply the restrained research/regulatory SaaS visual language."""
    st.markdown(
        """
        <style>
        :root {
          --cg-bg: #f6f7f9;
          --cg-surface: #ffffff;
          --cg-text: #101828;
          --cg-muted: #667085;
          --cg-border: #e4e7ec;
          --cg-brand: #3156d9;
          --cg-blue-bg: #eef3ff;
          --cg-green: #067647;
          --cg-green-bg: #ecfdf3;
          --cg-amber: #b54708;
          --cg-amber-bg: #fffaeb;
          --cg-red: #b42318;
          --cg-red-bg: #fef3f2;
        }
        .stApp { background: var(--cg-bg); color: var(--cg-text); }
        [data-testid="stHeader"] { background: rgba(246,247,249,.92); }
        [data-testid="stSidebar"] { background: #fbfcfd; border-right: 1px solid var(--cg-border); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }
        .cg-sidebar-kicker { color: var(--cg-muted); font-size: .68rem; font-weight: 780; letter-spacing: .12em; margin: .25rem 0 .35rem; }
        .cg-sidebar-layer { color: var(--cg-text); font-size: .78rem; font-weight: 700; line-height: 1.45; padding: .6rem .2rem .15rem 1.2rem; }
        .cg-sidebar-layer span { color: var(--cg-muted); font-size: .68rem; font-weight: 500; }
        .cg-sidebar-direct { color: var(--cg-text); font-size: .78rem; font-weight: 750; line-height: 1.45; padding: .75rem .2rem .2rem; }
        .cg-sidebar-direct span { color: var(--cg-muted); font-size: .68rem; font-weight: 500; }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary { color: var(--cg-text); font-weight: 700; }
        [data-testid="stSidebar"] [data-testid="stButton"] button { text-align: left; padding-left: 1.05rem; }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { padding-left: 1.05rem; margin-top: -.25rem; margin-bottom: .15rem; }
        h1, h2, h3 { color: var(--cg-text); letter-spacing: -.02em; }
        h1 { font-size: clamp(1.75rem, 3vw, 2.65rem) !important; line-height: 1.15 !important; }
        h2 { font-size: 1.35rem !important; }
        h3 { font-size: 1.05rem !important; }
        p, [data-testid="stCaptionContainer"] { color: var(--cg-muted); }
        [data-testid="stMetric"] { background: var(--cg-surface); border: 1px solid var(--cg-border); border-radius: 11px; padding: .85rem 1rem; }
        [data-testid="stMetricLabel"] { color: var(--cg-muted); }
        [data-testid="stMetricValue"] { color: var(--cg-text); }
        .stButton > button, .stDownloadButton > button { border-radius: 8px; border-color: var(--cg-border); font-weight: 600; }
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { background: var(--cg-brand); border-color: var(--cg-brand); }
        [data-testid="stDataFrame"] { border: 1px solid var(--cg-border); border-radius: 10px; overflow: hidden; }
        [data-testid="stExpander"] { border-color: var(--cg-border); border-radius: 9px; background: rgba(255,255,255,.65); }
        .cg-hero { background: var(--cg-surface); border: 1px solid var(--cg-border); border-radius: 16px; padding: 2.5rem 2.75rem; margin: .5rem 0 1.5rem; }
        .cg-eyebrow { color: var(--cg-brand); font-size: .72rem; font-weight: 750; letter-spacing: .1em; text-transform: uppercase; }
        .cg-hero h1 { font-size: clamp(2rem, 4.4vw, 3.55rem) !important; margin: .75rem 0 1rem; max-width: 780px; }
        .cg-hero p { font-size: 1rem; line-height: 1.8; max-width: 820px; white-space: pre-line; }
        .cg-reference { background: #eef4fb; border: 1px solid #d8e4f2; border-radius: 13px; padding: 1.1rem 1.25rem; margin: 1rem 0 1.7rem; }
        .cg-reference h3 { color: #172b4d; margin: .35rem 0 .45rem; }
        .cg-reference p { color: #52657d; font-size: .88rem; line-height: 1.6; margin: 0 0 .45rem; }
        .cg-note { background: #f8fafc; border: 1px dashed #d0d5dd; border-radius: 9px; padding: .75rem .9rem; color: var(--cg-muted); font-size: .82rem; line-height: 1.6; }
        .cg-card { background: var(--cg-surface); border: 1px solid var(--cg-border); border-radius: 11px; padding: 1rem 1.1rem; height: 100%; }
        .cg-card h3 { margin: 0 0 .4rem; }
        .cg-card p { font-size: .88rem; line-height: 1.65; margin: 0; }
        .cg-section { margin: 1.7rem 0 .7rem; }
        .cg-section h2 { margin-bottom: .25rem; }
        .cg-section p { margin-top: 0; }
        .cg-status { background: var(--cg-amber-bg); border: 1px solid #f6dba8; border-radius: 12px; padding: 1rem 1.15rem; color: #5f4b32; line-height: 1.7; }
        .cg-status strong { color: var(--cg-text); }
        .cg-pill { display: inline-block; border: 1px solid var(--cg-border); background: #fff; border-radius: 999px; padding: .22rem .55rem; margin: .12rem .18rem .12rem 0; font-size: .76rem; color: #475467; }
        .cg-pill.blue { background: var(--cg-blue-bg); border-color: #dce6ff; color: #2946b6; }
        .cg-pill.green { background: var(--cg-green-bg); border-color: #d1fadf; color: var(--cg-green); }
        .cg-pill.amber { background: var(--cg-amber-bg); border-color: #fdecc8; color: var(--cg-amber); }
        .cg-empty { background: #fff; border: 1px dashed #cfd6e1; border-radius: 10px; padding: 1.1rem 1.2rem; color: var(--cg-muted); }
        .cg-empty strong { color: var(--cg-text); }
        .cg-flow { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem; }
        .cg-flow-item { background: #fff; border: 1px solid var(--cg-border); border-radius: 8px; padding: .55rem .75rem; font-size: .82rem; font-weight: 650; }
        .cg-flow-arrow { color: #98a2b3; }
        .cg-micro { font-size: .78rem; color: var(--cg-muted); }
        .cg-access-pill { display:inline-flex; align-items:center; gap:.35rem; border-radius:999px; padding:.22rem .55rem; font-size:.66rem; font-weight:750; letter-spacing:.04em; }
        .cg-access-pill.public { color:#475467; background:#f2f4f7; border:1px solid #e4e7ec; }
        .cg-access-pill.researcher { color:#067647; background:#ecfdf3; border:1px solid #d1fadf; }
        .cg-workspace-topbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; background:#fff; border-bottom:1px solid var(--cg-border); padding:.75rem 1.1rem; margin:-1rem 0 1.25rem; }
        .cg-workspace-topbar .crumb { color:var(--cg-muted); font-size:.76rem; }
        .cg-workspace-topbar .crumb strong { color:#344054; }
        .cg-workspace-topbar .status { display:flex; align-items:center; gap:.45rem; color:var(--cg-muted); font-size:.7rem; }
        .cg-workspace-topbar .status i { width:6px; height:6px; border-radius:50%; background:#12b76a; display:inline-block; }
        .cg-llm-actionbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; background:#fff; border:1px solid var(--cg-border); border-radius:10px; padding:.8rem .95rem; margin:.45rem 0 1rem; }
        .cg-llm-actionbar .meta { display:flex; align-items:center; flex-wrap:wrap; gap:.45rem; }
        .cg-llm-actionbar .title { color:#344054; font-size:.78rem; font-weight:760; }
        .cg-llm-status { display:inline-flex; align-items:center; gap:.35rem; border:1px solid #d1fadf; background:#ecfdf3; color:#067647; border-radius:999px; padding:.22rem .5rem; font-size:.67rem; font-weight:650; }
        .cg-llm-status:before { content:""; width:6px; height:6px; border-radius:50%; background:#12b76a; }
        .cg-golden-page-head { margin:.2rem 0 1.2rem; }
        .cg-golden-page-head h1 { margin:0 0 .35rem; }
        .cg-golden-page-head p { max-width:920px; margin:0; line-height:1.65; }
        .cg-golden-kicker { color:var(--cg-brand); font-size:.68rem; font-weight:780; letter-spacing:.09em; text-transform:uppercase; }
        .cg-golden-card-title { color:var(--cg-text); font-size:.96rem; font-weight:760; margin:0; }
        .cg-golden-card-subtitle { color:var(--cg-muted); font-size:.74rem; margin:.22rem 0 0; line-height:1.5; }
        .cg-golden-card-copy { color:var(--cg-muted); font-size:.82rem; line-height:1.65; }
        .cg-golden-card-copy strong { color:var(--cg-text); }
        .cg-golden-grid2 { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:1rem; }
        .cg-golden-grid3 { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.8rem; }
        .cg-golden-statgrid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.75rem; }
        .cg-golden-stat { background:#fff; border:1px solid var(--cg-border); border-radius:10px; padding:.85rem .95rem; }
        .cg-golden-stat .label { color:var(--cg-muted); font-size:.7rem; font-weight:700; }
        .cg-golden-stat .value { color:var(--cg-text); font-size:1.25rem; font-weight:780; margin:.3rem 0 .1rem; }
        .cg-golden-stat .hint { color:var(--cg-muted); font-size:.68rem; }
        .cg-golden-report { background:#fff; border:1px solid var(--cg-border); border-radius:12px; padding:1.35rem 1.45rem; min-height:18rem; }
        .cg-golden-report h1,.cg-golden-report h2,.cg-golden-report h3 { margin-top:.8rem; }
        .cg-golden-report p,.cg-golden-report li { color:#475467; line-height:1.7; font-size:.84rem; }
        .cg-golden-empty { min-height:9rem; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; background:#fbfcfe; border:1px dashed #cfd6e1; border-radius:10px; padding:1.1rem; }
        .cg-golden-empty strong { color:var(--cg-text); font-size:.86rem; }
        .cg-golden-empty span { color:var(--cg-muted); font-size:.76rem; margin-top:.3rem; }
        .cg-golden-table-note { color:var(--cg-muted); font-size:.72rem; margin:.45rem 0 .7rem; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--cg-border); border-radius:12px; background:rgba(255,255,255,.72); }
        [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap:.65rem; }
        @media (max-width:900px) { .cg-golden-grid2,.cg-golden-grid3,.cg-golden-statgrid { grid-template-columns:1fr 1fr; } }
        @media (max-width:620px) { .cg-golden-grid2,.cg-golden-grid3,.cg-golden-statgrid { grid-template-columns:1fr; } }
        .cg-home-wrap { max-width:1240px; margin:0 auto; background:#fff; }
        .cg-home-hero { padding:3.3rem 1.25rem 3.8rem; display:grid; grid-template-columns:1.02fr .98fr; gap:3rem; align-items:center; }
        .cg-home-hero h1 { font-size:clamp(2.4rem,5vw,3.8rem) !important; letter-spacing:-.045em; margin:.8rem 0 1rem; }
        .cg-home-hero .lead { font-size:1rem; line-height:1.8; color:#475467; margin:0 0 .9rem; }
        .cg-home-hero .body { font-size:.8rem; line-height:1.8; color:#667085; margin:0 0 .75rem; }
        .cg-home-shot { border:1px solid #dde3ec; border-radius:16px; background:#fff; box-shadow:0 24px 60px rgba(16,24,40,.11); overflow:hidden; }
        .cg-home-shot .fakebar { height:2.2rem; border-bottom:1px solid var(--cg-border); background:#fcfcfd; display:flex; align-items:center; padding:0 .85rem; gap:.4rem; }
        .cg-home-shot .dot { width:8px; height:8px; border-radius:50%; background:#d0d5dd; }
        .cg-home-shot .shotbody { display:grid; grid-template-columns:8.6rem 1fr; min-height:19rem; }
        .cg-home-shot .shotside { border-right:1px solid var(--cg-border); background:#fafbfc; padding:1rem .75rem; }
        .cg-home-shot .shotmain { padding:1.45rem; }
        .cg-home-shot .hair { height:9px; border-radius:7px; background:#e8ecf2; margin:9px 0; }
        .cg-home-shot .hair.blue { background:#dce6ff; }
        .cg-home-shot .hair.red { background:#fee4e2; }
        .cg-home-shot .hair.green { background:#d1fadf; }
        .cg-home-shot .mini { height:8px; background:#e4e7ec; border-radius:6px; margin:10px 0; }
        .cg-home-section { padding:2.8rem 1.25rem; border-top:1px solid #eef1f5; }
        .cg-home-section .intro { max-width:760px; margin-bottom:1.4rem; }
        .cg-home-section .kicker { font-size:.65rem; color:var(--cg-brand); font-weight:750; letter-spacing:.08em; text-transform:uppercase; margin-bottom:.45rem; }
        .cg-home-section h2 { font-size:1.65rem !important; margin:0 0 .55rem; }
        .cg-home-section .intro p { font-size:.8rem; line-height:1.75; color:#667085; margin:0; }
        .cg-home-card { background:#fff; border:1px solid var(--cg-border); border-radius:11px; padding:1rem; height:100%; }
        .cg-home-card h3 { font-size:.92rem; margin:0 0 .45rem; }
        .cg-home-card p { font-size:.72rem; line-height:1.65; color:#667085; margin:0; }
        .cg-home-grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:.8rem; }
        .cg-home-grid5 { display:grid; grid-template-columns:repeat(5,1fr); gap:.7rem; }
        .cg-home-grid2 { display:grid; grid-template-columns:1.1fr .9fr; gap:1rem; }
        .cg-home-flow { display:flex; gap:.45rem; align-items:center; flex-wrap:wrap; }
        .cg-home-flow span { background:#fff; border:1px solid var(--cg-border); border-radius:8px; padding:.55rem .7rem; font-size:.72rem; font-weight:650; }
        .cg-home-flow i { color:#98a2b3; font-style:normal; }
        .cg-home-dark { background:#101828; color:#fff; border-radius:13px; padding:1.2rem 1.3rem; margin-top:1rem; }
        .cg-home-dark h3 { color:#fff; margin:.2rem 0 .4rem; }
        .cg-home-dark p { color:#d0d5dd; font-size:.72rem; line-height:1.65; margin:0; }
        .cg-home-footer { padding:2.2rem 1.25rem 3.5rem; border-top:1px solid var(--cg-border); display:flex; justify-content:space-between; color:#667085; font-size:.68rem; }
        @media (max-width:1100px) { .cg-home-hero,.cg-home-grid2 { grid-template-columns:1fr; } .cg-home-grid5 { grid-template-columns:1fr 1fr; } }
        @media (max-width:700px) { .cg-home-grid3 { grid-template-columns:1fr; } .cg-home-footer { display:block; } }
        @media (max-width: 800px) { .cg-hero { padding: 1.5rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(*, eyebrow: str, title: str, body: str) -> None:
    st.markdown(
        f'<div class="cg-hero"><div class="cg-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{body}</p></div>',
        unsafe_allow_html=True,
    )


def section_intro(title: str, description: str = "") -> None:
    text = f'<div class="cg-section"><h2>{title}</h2>'
    if description:
        text += f'<p>{description}</p>'
    text += "</div>"
    st.markdown(text, unsafe_allow_html=True)


def card(title: str, body: str, *, tone: str = "") -> None:
    tone_class = f" {tone}" if tone else ""
    st.markdown(f'<div class="cg-card{tone_class}"><h3>{title}</h3><p>{body}</p></div>', unsafe_allow_html=True)


def pill(text: Any, *, tone: str = "") -> str:
    tone_class = f" {tone}" if tone else ""
    return f'<span class="cg-pill{tone_class}">{text}</span>'


def empty_state(title: str, message: str) -> None:
    st.markdown(f'<div class="cg-empty"><strong>{title}</strong><br>{message}</div>', unsafe_allow_html=True)


def golden_page_head(title: str, subtitle: str, *, kicker: str = "RESEARCH WORKBENCH") -> None:
    """Render the Golden HTML page heading without changing application state."""
    st.markdown(
        f'<div class="cg-golden-page-head"><div class="cg-golden-kicker">{kicker}</div>'
        f'<h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def golden_card_head(title: str, subtitle: str = "") -> None:
    """Render a compact card header inside a native Streamlit bordered card."""
    extra = f'<div class="cg-golden-card-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="cg-golden-card-title">{title}</div>{extra}',
        unsafe_allow_html=True,
    )


def golden_report_panel(markdown: str, *, title: str = "Report panel") -> None:
    """Render report content in the Golden report-panel treatment."""
    st.markdown(
        f'<div class="cg-golden-card-title">{title}</div>'
        f'<div class="cg-golden-report">{markdown}</div>',
        unsafe_allow_html=True,
    )


def flow(items: list[str]) -> None:
    html = '<div class="cg-flow">'
    for index, item in enumerate(items):
        if index:
            html += '<span class="cg-flow-arrow">→</span>'
        html += f'<span class="cg-flow-item">{item}</span>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def workspace_topbar(*, page_title: str, project: dict[str, Any] | None, authorized: bool) -> None:
    project_name = (project or {}).get("project_name") or "No active Test Project"
    llm_label = "LLM · Server API" if authorized else "PUBLIC_VIEWER · read only"
    dot = "<i></i>" if authorized else ""
    st.markdown(
        f"<div class='cg-workspace-topbar'><div class='crumb'>CompanionGuard / <strong>{page_title}</strong> · {project_name}</div><div class='status'>{dot}{llm_label}</div></div>",
        unsafe_allow_html=True,
    )


def llm_actionbar(*, title: str, profile: Any | None, notes: list[str] | None = None) -> None:
    notes = notes or []
    if profile is None:
        status = "Server API · 未连接"
        details = "请在下方 LLM 配置中选择 Server API 或 BYOK"
    else:
        mode = "Server API · 已连接" if getattr(profile, "access_mode", "") == "SERVER" else "BYOK · 已配置"
        status = mode
        details = f"{getattr(profile, 'provider_name', 'Provider')} · {getattr(profile, 'model', 'Model')}"
    chips = "".join(f"<span class='cg-pill'>{note}</span>" for note in notes)
    st.markdown(
        f"<div class='cg-llm-actionbar'><div><div class='meta'><span class='title'>{title}</span><span class='cg-llm-status'>{status}</span>{chips}</div><div class='cg-micro' style='margin-top:.3rem'>{details}</div></div></div>",
        unsafe_allow_html=True,
    )
