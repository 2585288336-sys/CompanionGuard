from __future__ import annotations

from companionguard_llm.client import OpenAICompatibleClient
from companionguard_llm.profiles import LLMProfile


class DeepSeekJudgeClient(OpenAICompatibleClient):
    """Backward-compatible wrapper for legacy scripts.

    New application code should construct an LLMProfile and use the provider
    abstraction. This class remains so older CLI workflows do not break.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-pro",
        reasoning_effort: str = "none",
        temperature: float = 0.0,
        timeout: float = 90.0,
    ) -> None:
        super().__init__(
            LLMProfile(
                role="judge",
                provider_type="openai_compatible",
                provider_name="DeepSeek",
                model=model,
                api_key=api_key,
                base_url=base_url,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                access_mode="LEGACY",
            ),
            timeout=timeout,
        )
