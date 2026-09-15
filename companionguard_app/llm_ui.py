from __future__ import annotations

import uuid

import streamlit as st

from companionguard_llm.profiles import LLMProfile, ROLE_NAMES, load_server_profile


def llm_session_id() -> str:
    key = "companionguard_llm_session_id"
    if key not in st.session_state:
        st.session_state[key] = uuid.uuid4().hex
    return st.session_state[key]


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or "").strip()


def _server_profile_from_secrets(role: str) -> LLMProfile | None:
    prefix = f"COMPANIONGUARD_{role.upper()}_"
    api_key = _secret(prefix + "API_KEY")
    provider_type = _secret(prefix + "PROVIDER_TYPE")
    provider_name = _secret(prefix + "PROVIDER_NAME")
    model = _secret(prefix + "MODEL")
    base_url = _secret(prefix + "BASE_URL")
    reasoning_effort = _secret(prefix + "REASONING_EFFORT") or "none"
    temperature_raw = _secret(prefix + "TEMPERATURE") or "0"

    if not api_key and role in {"judge", "evidence"}:
        api_key = _secret("DEEPSEEK_API_KEY")
        if api_key:
            provider_type = provider_type or "openai_compatible"
            provider_name = provider_name or "DeepSeek"
            model = model or _secret("DEEPSEEK_MODEL") or "deepseek-v4-pro"
            base_url = base_url or _secret("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
            reasoning_effort = _secret("DEEPSEEK_REASONING_EFFORT") or reasoning_effort
            temperature_raw = _secret("DEEPSEEK_TEMPERATURE") or temperature_raw
    if not api_key:
        return None
    if not model:
        return None
    return LLMProfile(
        role=role,
        provider_type=provider_type or "openai_compatible",
        provider_name=provider_name or "Server Provider",
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=float(temperature_raw),
        reasoning_effort=reasoning_effort,
        access_mode="SERVER",
    )


def server_profile(role: str) -> LLMProfile | None:
    return load_server_profile(role) or _server_profile_from_secrets(role)


def render_llm_profile_selector(role: str, *, key_prefix: str, allow_server: bool = True) -> LLMProfile | None:
    """Render a role-specific, vendor-decoupled LLM selector.

    API keys live only in Streamlit session state/widget memory. They are never
    returned as serializable project settings by this helper.
    """
    if role not in ROLE_NAMES:
        raise ValueError(f"Unknown LLM role: {role}")
    srv = server_profile(role) if allow_server else None
    modes = ["CompanionGuard Server Model", "BYOK"] if srv else ["BYOK"]
    mode = st.radio(
        f"{ROLE_NAMES[role]} access",
        modes,
        horizontal=True,
        key=f"{key_prefix}_access_mode",
        help="Server模式使用部署方配置；BYOK可选择受支持的任意厂商适配器。Key仅保存在当前session。",
    )
    if mode == "CompanionGuard Server Model":
        assert srv is not None
        st.caption(f"当前角色 / Role: {ROLE_NAMES[role]} · Server profile: {srv.provider_name} · {srv.model}. 此配置仅用于当前 LLM role；API key 不暴露给项目文件。")
        return srv

    provider_type = st.selectbox(
        "Provider adapter",
        ["openai_chat_compatible", "openai_responses", "anthropic"],
        format_func=lambda x: {"openai_chat_compatible": "OpenAI-style Chat Completions", "openai_responses": "OpenAI Responses-compatible", "anthropic": "Anthropic Messages API"}[x],
        key=f"{key_prefix}_provider_type",
    )
    provider_name = st.text_input(
        "Provider name",
        value="Custom Provider",
        key=f"{key_prefix}_provider_name",
        help="仅用于结果元数据，例如 DeepSeek / OpenAI / Qwen / Moonshot / Anthropic。",
    ).strip()
    model = st.text_input("Model", key=f"{key_prefix}_model").strip()
    if provider_type in {"openai_chat_compatible", "openai_responses"}:
        base_url = st.text_input(
            "Base URL",
            placeholder="例如 https://api.deepseek.com 或兼容厂商endpoint",
            key=f"{key_prefix}_base_url",
        ).strip()
        reasoning_effort = st.selectbox(
            "Reasoning effort",
            ["none", "low", "high", "max"],
            key=f"{key_prefix}_reasoning",
            help="仅在所选兼容API支持该参数时使用；不支持时请选择 none。",
        )
    else:
        base_url = st.text_input(
            "Base URL",
            value="https://api.anthropic.com",
            key=f"{key_prefix}_base_url",
        ).strip()
        reasoning_effort = "none"
    temperature = float(st.number_input("Temperature", min_value=0.0, max_value=2.0, value=0.0, step=0.1, key=f"{key_prefix}_temperature"))
    api_key = st.text_input(
        "API Key",
        type="password",
        key=f"{key_prefix}_api_key",
        help="只在当前Streamlit session中使用；不写入JSONL、CSV、project.json、日志或Git。",
    )
    if not api_key or not model or (provider_type in {"openai_chat_compatible", "openai_responses"} and not base_url):
        return None
    profile = LLMProfile(
        role=role,
        provider_type=provider_type,
        provider_name=provider_name or "BYOK Provider",
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        access_mode="BYOK",
    )
    st.caption(
        f"当前角色 / Role: {ROLE_NAMES[role]} · {profile.provider_name} · {profile.model} · "
        f"adapter={profile.provider_type}. 不继承其他 LLM role 的 Provider/Model 参数。"
    )
    return profile
