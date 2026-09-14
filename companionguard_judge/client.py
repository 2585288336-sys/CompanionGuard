from __future__ import annotations
import json
from typing import Any
from openai import OpenAI


class DeepSeekJudgeClient:
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
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)

    def judge(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": json.dumps(payload, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema}},
            "reasoning": {"effort": self.reasoning_effort},
            "max_output_tokens": 4096,
        }
        if self.reasoning_effort == "none":
            kwargs["temperature"] = self.temperature

        response = self.client.responses.create(**kwargs)
        if response.status != "completed":
            raise RuntimeError(f"DeepSeek response status={response.status}; details={response.incomplete_details or response.error}")
        result = json.loads(response.output_text)
        usage = response.usage.model_dump() if response.usage is not None and hasattr(response.usage, "model_dump") else None
        return result, usage
