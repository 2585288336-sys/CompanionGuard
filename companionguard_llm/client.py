from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from .profiles import LLMProfile


class LLMResponseError(RuntimeError):
    """A provider response that cannot be used by the requested operation."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


class LLMClient(Protocol):
    profile: LLMProfile

    def generate_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        schema_name: str,
        schema: dict[str, Any],
        max_output_tokens: int = 4096,
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
    if not value:
        raise LLMResponseError("GROUNDING_EMPTY_RESPONSE")
    try:
        result = json.loads(value)
    except json.JSONDecodeError as original_error:
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
            raise LLMResponseError("GROUNDING_NON_JSON_RESPONSE", str(original_error)) from original_error
    if not isinstance(result, dict):
        raise ValueError("LLM JSON response must be an object")
    return result


def _with_response_metadata(usage: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep provider usage plus normalized response completion metadata."""
    result = dict(usage.model_dump() if hasattr(usage, "model_dump") else (usage or {}))
    for key, value in metadata.items():
        if value is not None:
            result[key] = value
    return result


def _reasoning_tokens(usage: Any) -> int | None:
    if usage is None:
        return None
    details = getattr(usage, "output_tokens_details", None)
    if details is not None:
        return getattr(details, "reasoning_tokens", None)
    if isinstance(usage, dict):
        details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
        return details.get("reasoning_tokens")
    return None


def is_deepseek_provider(profile: LLMProfile) -> bool:
    """Identify DeepSeek from non-secret provider metadata only."""
    return any(
        "deepseek" in str(value or "").lower()
        for value in (profile.provider_name, profile.base_url)
    )


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
        self.adapter_type = profile.provider_type
        self.thinking_mode = None
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
        max_output_tokens: int = 4096,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        kwargs: dict[str, Any] = {
            "model": self.profile.model,
            "instructions": system_prompt,
            "input": json.dumps(payload, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema}},
            "max_output_tokens": max_output_tokens,
        }
        if self.profile.reasoning_effort != "none":
            kwargs["reasoning"] = {"effort": self.profile.reasoning_effort}
        else:
            kwargs["temperature"] = self.profile.temperature
        response = self._get_client().responses.create(**kwargs)
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        metadata = {
            "response_status": status,
            "finish_reason": getattr(incomplete, "reason", None) if incomplete is not None else None,
            "incomplete_reason": getattr(incomplete, "reason", None) if incomplete is not None else None,
            "reasoning_tokens": _reasoning_tokens(getattr(response, "usage", None)),
        }
        if status != "completed":
            raise RuntimeError(
                f"LLM response status={getattr(response, 'status', None)}; "
                f"details={getattr(response, 'incomplete_details', None) or getattr(response, 'error', None)}"
            )
        result = _parse_json_object(response.output_text)
        _validate_schema(result, schema)
        usage = _with_response_metadata(getattr(response, "usage", None), metadata)
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
        status = getattr(response, "status", None)
        incomplete = getattr(response, "incomplete_details", None)
        metadata = {
            "response_status": status,
            "finish_reason": getattr(incomplete, "reason", None) if incomplete is not None else None,
            "incomplete_reason": getattr(incomplete, "reason", None) if incomplete is not None else None,
            "reasoning_tokens": _reasoning_tokens(getattr(response, "usage", None)),
        }
        usage = _with_response_metadata(getattr(response, "usage", None), metadata)
        return response.output_text or "", usage


class OpenAIChatCompatibleClient:
    """Broad OpenAI-style Chat Completions adapter with local schema validation."""

    def __init__(self, profile: LLMProfile, *, timeout: float = 90.0) -> None:
        self.profile = profile
        self.model = profile.model
        self.reasoning_effort = profile.reasoning_effort
        self.temperature = profile.temperature
        self.provider_name = profile.provider_name
        self.adapter_type = profile.provider_type
        self.thinking_mode = (
            "disabled" if profile.reasoning_effort == "none" else "enabled"
        ) if is_deepseek_provider(profile) else None
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
        kwargs: dict[str, Any] = {
            "model": self.profile.model,
            "messages": [
                {"role": "system", "content": system_prompt + suffix},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": self.profile.temperature,
            "max_tokens": max_output_tokens,
        }
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        if self.thinking_mode is not None:
            kwargs["reasoning_effort"] = self.profile.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": self.thinking_mode}}
        response = self._get_client().chat.completions.create(**kwargs)
        choice = response.choices[0]
        text = choice.message.content or ""
        metadata = {
            "response_status": "completed",
            "finish_reason": getattr(choice, "finish_reason", None),
            "incomplete_reason": "max_output_tokens" if getattr(choice, "finish_reason", None) == "length" else None,
            "reasoning_tokens": _reasoning_tokens(getattr(response, "usage", None)),
        }
        usage = _with_response_metadata(getattr(response, "usage", None), metadata)
        return text, usage

    def generate_json(self, *, system_prompt: str, payload: dict[str, Any], schema_name: str, schema: dict[str, Any], max_output_tokens: int = 4096):
        text, usage = self._call(system_prompt=system_prompt, payload=payload, max_output_tokens=max_output_tokens, schema=schema)
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
        max_output_tokens: int = 4096,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        schema_instruction = (
            "\n\nReturn ONLY a JSON object matching this JSON Schema. Do not use markdown fences.\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        body = {
            "model": self.profile.model,
            "max_tokens": max_output_tokens,
            "temperature": self.profile.temperature,
            "system": system_prompt + schema_instruction,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        response = self._post(body)
        text = self._text(response)
        result = _parse_json_object(text)
        _validate_schema(result, schema)
        usage = _with_response_metadata(response.get("usage"), {
            "response_status": "completed",
            "finish_reason": response.get("stop_reason"),
            "incomplete_reason": "max_tokens" if response.get("stop_reason") == "max_tokens" else None,
        })
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
        body = {
            "model": self.profile.model,
            "max_tokens": max_output_tokens,
            "temperature": self.profile.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        }
        response = self._post(body)
        return self._text(response), _with_response_metadata(response.get("usage"), {
            "response_status": "completed",
            "finish_reason": response.get("stop_reason"),
            "incomplete_reason": "max_tokens" if response.get("stop_reason") == "max_tokens" else None,
        })


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
