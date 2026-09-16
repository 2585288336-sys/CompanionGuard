"""Minimal session-only authorization for the Research Workbench.

The public viewer is the default.  The password is read only from Streamlit
Secrets or the server environment and is never returned to the UI or project
data.  This deliberately does not attempt to be a general identity system.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st


ACCESS_MODE_KEY = "companionguard_access_mode"
AUTHORIZED_MODE = "AUTHORIZED_RESEARCHER"
PUBLIC_MODE = "PUBLIC_VIEWER"


def configured_research_password() -> str:
    try:
        value = st.secrets.get("COMPANIONGUARD_RESEARCH_PASSWORD", "")
    except Exception:
        value = ""
    return str(value or os.environ.get("COMPANIONGUARD_RESEARCH_PASSWORD", "")).strip()


def is_authorized_researcher() -> bool:
    return st.session_state.get(ACCESS_MODE_KEY) == AUTHORIZED_MODE


def set_public_viewer() -> None:
    st.session_state[ACCESS_MODE_KEY] = PUBLIC_MODE


def render_access_control() -> bool:
    """Render the sidebar gate and return the current session access mode."""
    if ACCESS_MODE_KEY not in st.session_state:
        set_public_viewer()

    st.sidebar.markdown("<div class='cg-sidebar-kicker'>ACCESS MODE</div>", unsafe_allow_html=True)
    if is_authorized_researcher():
        st.sidebar.markdown("<span class='cg-access-pill researcher'>AUTHORIZED_RESEARCHER</span>", unsafe_allow_html=True)
        st.sidebar.caption("研究工作台已授权 · 写入仅限当前 session 项目")
        if st.sidebar.button("退出研究模式 / Return to public", key="research_logout", use_container_width=True):
            set_public_viewer()
            st.rerun()
        return True

    st.sidebar.markdown("<span class='cg-access-pill public'>PUBLIC_VIEWER</span>", unsafe_allow_html=True)
    with st.sidebar.expander("进入研究工作台 / Research access", expanded=False):
        password = configured_research_password()
        if not password:
            st.caption("研究授权尚未在服务器 Secrets 中配置。")
        else:
            entered = st.text_input("授权密码", type="password", key="research_password_input")
            if st.button("进入 AUTHORIZED_RESEARCHER", type="primary", key="research_login", use_container_width=True):
                if hmac.compare_digest(entered, password):
                    st.session_state[ACCESS_MODE_KEY] = AUTHORIZED_MODE
                    st.session_state.pop("research_password_input", None)
                    st.success("研究模式已授权。")
                    st.rerun()
                st.error("授权密码不正确。")
            st.caption("密码只在服务器端校验；不会写入 Project、浏览器脚本或日志。")
    return False


def require_researcher(action: str = "此操作") -> bool:
    """Return whether a write/LLM action is currently permitted."""
    if is_authorized_researcher():
        return True
    st.warning(f"{action}仅对 AUTHORIZED_RESEARCHER 开放。当前为 PUBLIC_VIEWER，只读浏览不会触发写入或 LLM 调用。")
    return False
