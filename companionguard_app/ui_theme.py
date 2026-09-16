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


def flow(items: list[str]) -> None:
    html = '<div class="cg-flow">'
    for index, item in enumerate(items):
        if index:
            html += '<span class="cg-flow-arrow">→</span>'
        html += f'<span class="cg-flow-item">{item}</span>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)
