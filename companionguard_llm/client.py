from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from .profiles import LLMProfile


class LLMClient(Protocol):
    profile: LLMProfile

    def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]: ...

    def judge(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]: ...

    def generate_text(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_output_tokens: int = 4096,
    ) -> tuple[str, dict[str, Any] | None]: ...


def _validate_schema(obj: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        rendered = "; ".join(e.message for e in errors[:8])
        raise ValueError(f"LLM JSON did not match schema: {rendered}")


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse strict JSON, accepting a single fenced/surrounded JSON object."""
    value = _strip_json_fence(text)
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        result = None
        for index, char in enumerate(value):
            if char != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(value[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                result = candidate
                break
        if result is None:
            raise
    if not isinstance(result, dict):
        raise ValueError("LLM JSON response must be an object")
    return result


class OpenAICompatibleClient:
    """OpenAI Responses API compatible client.

    This adapter is provider-agnostic: DeepSeek, OpenAI and other services can
    be used when they expose a compatible endpoint. Provider metadata comes
    from the LLMProfile rather than being hard-coded into the Judge pipeline.
    """

    def __init__(self, profile: LLMProfile, *, timeout: float = 90.0) -> None:
        self.profile = profile
        self.model = profile.model
        self.reasoning_effort = profile.reasoning_effort
        self.temperature = profile.temperature
        self.provider_name = profile.provider_name
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.profile.api_key, base_url=self.profile.base_url or None, timeout=self.timeout, max_retries=2)
        return self._client

    def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        kwargs: dict[str, Any] = {
            "model": self.profile.model,
            "instructions": system_prompt,
            "input": json.dumps(payload, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema}},
            "max_output_tokens": 4096,
        }
        if self.profile.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.profile.reasoning_effort}
        else:
            kwargs["temperature"] = self.profile.temperature
        response = self._get_client().responses.create(**kwargs)
        if getattr(response, "status", None) != "completed":
            raise RuntimeError(
                f"LLM response status={getattr(response, 'status', None)}; "
                f"details={getattr(response, 'incomplete_details', None) or getattr(response, 'error', None)}"
            )
        result = json.loads(response.output_text)
        _validate_schema(result, schema)
        usage = response.usage.model_dump() if getattr(response, "usage", None) is not None and hasattr(response.usage, "model_dump") else None
        return result, usage

    def judge(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        return self.generate_json(system_prompt=system_prompt, payload=payload, schema_name=schema_name, schema=schema)

    def generate_text(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_output_tokens: int = 4096,
    ) -> tuple[str, dict[str, Any] | None]:
        kwargs: dict[str, Any] = {
            "model": self.profile.model,
            "instructions": system_prompt,
            "input": json.dumps(payload, ensure_ascii=False),
            "max_output_tokens": max_output_tokens,
        }
        if self.profile.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.profile.reasoning_effort}
        else:
            kwargs["temperature"] = self.profile.temperature
        response = self._get_client().responses.create(**kwargs)
        if getattr(response, "status", None) != "completed":
            raise RuntimeError(f"LLM response status={getattr(response, 'status', None)}")
        usage = response.usage.model_dump() if getattr(response, "usage", None) is not None and hasattr(response.usage, "model_dump") else None
        return response.output_text, usage


class OpenAIChatCompatibleClient:
    """Broad OpenAI-style Chat Completions adapter with local schema validation."""

    def __init__(self, profile: LLMProfile, *, timeout: float = 90.0) -> None:
        self.profile = profile
        self.model = profile.model
        self.reasoning_effort = "none"
        self.temperature = profile.temperature
        self.provider_name = profile.provider_name
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.profile.api_key, base_url=self.profile.base_url or None, timeout=self.timeout, max_retries=2)
        return self._client

    def _call(self, *, system_prompt: str, payload: dict[str, Any], max_output_tokens: int, schema: dict[str, Any] | None = None):
        suffix = ""
        if schema is not None:
            suffix = "\n\nReturn ONLY a JSON object matching this JSON Schema. Do not use markdown fences.\n" + json.dumps(schema, ensure_ascii=False)
        response = self._get_client().chat.completions.create(
            model=self.profile.model,
            messages=[
                {"role": "system", "content": system_prompt + suffix},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=self.profile.temperature,
            max_tokens=max_output_tokens,
            **({"response_format": {"type": "json_object"}} if schema is not None else {}),
        )
        text = response.choices[0].message.content or ""
        usage = response.usage.model_dump() if getattr(response, "usage", None) is not None and hasattr(response.usage, "model_dump") else None
        return text, usage

    def generate_json(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any]):
        text, usage = self._call(system_prompt=system_prompt, payload=payload, max_output_tokens=4096, schema=schema)
        result = _parse_json_object(text)
        _validate_schema(result, schema)
        return result, usage

    def judge(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any]):
        return self.generate_json(system_prompt=system_prompt, payload=payload, schema_name=schema_name, schema=schema)

    def generate_text(self, *, system_prompt: str, payload: dict[str, Any], max_output_tokens: int = 4096):
        return self._call(system_prompt=system_prompt, payload=payload, max_output_tokens=max_output_tokens)


class AnthropicMessagesClient:
    """Minimal Anthropic Messages API adapter using the standard library.

    It intentionally has no SDK dependency. JSON schema enforcement is local:
    the model is instructed to return JSON only, then CompanionGuard validates
    it with jsonschema before business-level validation.
    """

    def __init__(self, profile: LLMProfile, *, timeout: float = 90.0) -> None:
        self.profile = profile
        self.model = profile.model
        self.reasoning_effort = profile.reasoning_effort
        self.temperature = profile.temperature
        self.provider_name = profile.provider_name
        self.timeout = timeout

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        base = (self.profile.base_url or "https://api.anthropic.com").rstrip("/")
        req = urllib.request.Request(
            f"{base}/v1/messages",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.profile.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic HTTP {exc.code}: {detail[:1000]}") from exc

    @staticmethod
    def _text(response: dict[str, Any]) -> str:
        chunks = [x.get("text", "") for x in response.get("content", []) if x.get("type") == "text"]
        return "".join(chunks).strip()

    def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        schema_instruction = (
            "\n\nReturn ONLY a JSON object matching this JSON Schema. Do not use markdown fences.\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        body = {
            "model": self.profile.model,
            "max_tokens": 4096,
            "temperature": self.profile.temperature,
            "system": system_prompt + schema_instruction,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        response = self._post(body)
        result = json.loads(_strip_json_fence(self._text(response)))
        _validate_schema(result, schema)
        return result, response.get("usage")

    def judge(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        return self.generate_json(system_prompt=system_prompt, payload=payload, schema_name=schema_name, schema=schema)

    def generate_text(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        max_output_tokens: int = 4096,
    ) -> tuple[str, dict[str, Any] | None]:
        body = {
            "model": self.profile.model,
            "max_tokens": max_output_tokens,
            "temperature": self.profile.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        response = self._post(body)
        return self._text(response), response.get("usage")


def make_client(profile: LLMProfile) -> LLMClient:
    if profile.provider_type in {"openai_compatible", "openai_responses"}:
        return OpenAICompatibleClient(profile)
    if profile.provider_type == "openai_chat_compatible":
        return OpenAIChatCompatibleClient(profile)
    if profile.provider_type == "anthropic":
        return AnthropicMessagesClient(profile)
    raise ValueError(
        f"Unsupported provider_type={profile.provider_type!r}. "
        "Add an adapter implementing generate_json/generate_text rather than coupling business logic to a vendor."
    )
