from __future__ import annotations

from types import SimpleNamespace

from companionguard_app.reporting import build_dialogue_report_context, build_writer_facing_context
from companionguard_app.report_validation import validate_report_hard
from companionguard_app.service import report_profile_diagnostics
from companionguard_llm.client import OpenAIChatCompatibleClient
from companionguard_llm.profiles import LLMProfile


class FakeChatCompletions:
    def __init__(self, *, content: str = "ok", finish_reason: str | None = "stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=self.content),
                finish_reason=self.finish_reason,
            )],
            usage={"prompt_tokens": 5, "completion_tokens": 7},
        )


class FakeOpenAI:
    def __init__(self, completions: FakeChatCompletions):
        self.chat = SimpleNamespace(completions=completions)


def _profile(role: str, *, provider_name: str, base_url: str, reasoning: str) -> LLMProfile:
    return LLMProfile(
        role=role,
        provider_type="openai_chat_compatible",
        provider_name=provider_name,
        model="deepseek-chat" if "deepseek" in provider_name.lower() else "generic-chat",
        api_key="fixture-only",
        base_url=base_url,
        reasoning_effort=reasoning,
    )


def _call(profile: LLMProfile, limit: int, *, schema: dict | None = None, finish_reason: str | None = "stop"):
    completions = FakeChatCompletions(content='{"ok": true}' if schema else "ok", finish_reason=finish_reason)
    client = OpenAIChatCompatibleClient(profile)
    client._client = FakeOpenAI(completions)
    if schema:
        client.generate_json(system_prompt="system", payload={}, schema_name="fixture", schema=schema, max_output_tokens=limit)
    else:
        _, usage = client.generate_text(system_prompt="system", payload={}, max_output_tokens=limit)
    return completions.kwargs, usage if not schema else None


def test_dialogue_final_chat_request_is_deepseek_disabled_and_32k():
    kwargs, _ = _call(_profile("dialogue_report", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="none"), 32000)
    assert kwargs["max_tokens"] == 32000
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


def test_integrated_final_chat_request_is_deepseek_enabled_and_64k():
    kwargs, _ = _call(_profile("integrated_report", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="high"), 64000)
    assert kwargs["max_tokens"] == 64000
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_integrated_fallback_low_and_grounding_low_use_enabled_64k_and_16k():
    fallback_kwargs, _ = _call(_profile("integrated_report", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="low"), 64000)
    grounding_kwargs, _ = _call(_profile("grounding_validator", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="low"), 16000, schema={"type": "object"})
    assert fallback_kwargs["max_tokens"] == 64000
    assert grounding_kwargs["max_tokens"] == 16000
    assert fallback_kwargs["reasoning_effort"] == grounding_kwargs["reasoning_effort"] == "low"
    assert fallback_kwargs["extra_body"] == grounding_kwargs["extra_body"] == {"thinking": {"type": "enabled"}}


def test_generic_chat_provider_does_not_receive_deepseek_extra_body():
    kwargs, _ = _call(_profile("dialogue_report", provider_name="Generic", base_url="https://api.example.test/v1", reasoning="none"), 32000)
    assert "extra_body" not in kwargs


def test_profile_diagnostics_are_non_secret_and_resolve_thinking_mode():
    diagnostics = report_profile_diagnostics(
        _profile("dialogue_report", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="none"),
        requested_output_limit=32000,
    )
    assert diagnostics["thinking_mode"] == "disabled"
    assert diagnostics["requested_output_limit"] == 32000
    assert "api_key" not in diagnostics


def test_chat_adapter_preserves_provider_length_finish_reason():
    kwargs, usage = _call(_profile("dialogue_report", provider_name="DeepSeek", base_url="https://api.deepseek.com", reasoning="none"), 32000, finish_reason="length")
    assert kwargs["max_tokens"] == 32000
    assert usage["finish_reason"] == "length"
    assert usage["incomplete_reason"] == "max_output_tokens"


def test_criterion_finding_rate_has_deterministic_display_and_numeric_contract():
    rows = [
        {"phase": "FORMAL", "product": "P", "criterion_id": "C-1", "criterion_name": "Criterion", "module": "m", "final_label": label}
        for label in ("FINDING", "FINDING", "NO_FINDING")
    ]
    context = build_dialogue_report_context(project={"project_id": "p", "products": [{"label": "P"}]}, final_rows=rows)
    assert context["criteria"]["C-1"]["finding_rate_display"] == "66.7%"
    writer = build_writer_facing_context(context)
    assert writer["dialogue_analysis"]["criteria"][0]["finding_rate_display"] == "66.7%"
    assert "formal_case_count" not in writer["coverage"]
    assert writer["coverage"]["total_formal_case_count"] == 3
    assert writer["coverage"]["adjudicated_formal_case_count"] == 3
    assert writer["coverage"]["valid_formal_case_count"] == 3
    assert writer["coverage"]["invalid_formal_case_count"] == 0
    assert validate_report_hard(report_text="比例为66.7%。", context=context, report_type="dialogue")["overall_status"] == "PASS"
    assert validate_report_hard(report_text="比例为67.7%。", context=context, report_type="dialogue")["overall_status"] == "FAIL"
