from __future__ import annotations

import os
from dataclasses import dataclass

ROLE_NAMES = {
    "judge": "Dialogue Judge",
    "dialogue_report": "Dialogue Report Writer",
    "evidence": "Layer 3 Evidence Assistant",
    "integrated_report": "Integrated Report Writer",
}


@dataclass(frozen=True)
class LLMProfile:
    role: str
    provider_type: str
    provider_name: str
    model: str
    api_key: str
    base_url: str = ""
    temperature: float = 0.0
    reasoning_effort: str = "none"
    access_mode: str = "BYOK"

    def public_metadata(self) -> dict[str, object]:
        return {
            "role": self.role,
            "provider_type": self.provider_type,
            "provider": self.provider_name,
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "access_mode": self.access_mode,
        }


def _env(role: str, suffix: str) -> str:
    return os.environ.get(f"COMPANIONGUARD_{role.upper()}_{suffix}", "").strip()


def load_server_profile(role: str) -> LLMProfile | None:
    """Load a role-scoped server LLM profile.

    Preferred variables are COMPANIONGUARD_<ROLE>_*. For backward compatibility,
    the judge/evidence roles can fall back to the legacy DEEPSEEK_* variables.
    API keys are returned only in memory and must never be serialized.
    """
    if role not in ROLE_NAMES:
        raise ValueError(f"Unknown LLM role: {role}")

    provider_type = _env(role, "PROVIDER_TYPE")
    provider_name = _env(role, "PROVIDER_NAME")
    model = _env(role, "MODEL")
    api_key = _env(role, "API_KEY")
    base_url = _env(role, "BASE_URL")
    reasoning = _env(role, "REASONING_EFFORT") or "none"
    temperature_raw = _env(role, "TEMPERATURE") or "0"

    if not api_key and role in {"judge", "evidence"}:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key:
            provider_type = provider_type or "openai_compatible"
            provider_name = provider_name or "DeepSeek"
            model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
            base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            reasoning = os.environ.get("DEEPSEEK_REASONING_EFFORT", reasoning)
            temperature_raw = os.environ.get("DEEPSEEK_TEMPERATURE", temperature_raw)

    if not api_key:
        return None
    provider_type = provider_type or "openai_compatible"
    provider_name = provider_name or "Server Provider"
    if not model:
        raise ValueError(f"Server profile for role={role} has API key but no model.")
    if provider_type in {"openai_compatible", "openai_responses", "openai_chat_compatible"} and not base_url:
        base_url = "https://api.openai.com/v1"
    if provider_type == "anthropic" and not base_url:
        base_url = "https://api.anthropic.com"
    try:
        temperature = float(temperature_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid temperature for role={role}: {temperature_raw}") from exc

    return LLMProfile(
        role=role,
        provider_type=provider_type,
        provider_name=provider_name,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        reasoning_effort=reasoning,
        access_mode="SERVER",
    )
