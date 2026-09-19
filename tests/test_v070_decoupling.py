from __future__ import annotations

import json
from pathlib import Path

from companionguard_app.reporting import build_dialogue_report_context, build_integrated_report_context
from companionguard_app.testplans import load_test_plans, upsert_test_plan
from companionguard_app.runtime_scope import RuntimeScope
from companionguard_llm.client import AnthropicMessagesClient, OpenAIChatCompatibleClient, OpenAICompatibleClient, make_client
from companionguard_llm.profiles import LLMProfile, ROLE_NAMES
from companionguard_llm.search import DisabledSearchProvider, SearchNotConfigured


def test_four_llm_roles_are_independent_profiles():
    assert set(ROLE_NAMES) == {"judge", "dialogue_report", "evidence", "integrated_report", "grounding_validator", "academic_polish"}
    profiles = [
        LLMProfile(role=role, provider_type="openai_chat_compatible", provider_name=f"P-{role}", model=f"M-{role}", api_key="secret", base_url="https://example.invalid/v1")
        for role in ROLE_NAMES
    ]
    assert len({p.model for p in profiles}) == 4
    assert all("api_key" not in p.public_metadata() for p in profiles)


def test_provider_registry_supports_multiple_protocols_without_business_logic_changes():
    p1 = LLMProfile(role="judge", provider_type="openai_responses", provider_name="A", model="m", api_key="k", base_url="https://example.invalid/v1")
    p2 = LLMProfile(role="judge", provider_type="openai_chat_compatible", provider_name="B", model="m", api_key="k", base_url="https://example.invalid/v1")
    p3 = LLMProfile(role="judge", provider_type="anthropic", provider_name="C", model="m", api_key="k", base_url="https://example.invalid")
    assert isinstance(make_client(p1), OpenAICompatibleClient)
    assert isinstance(make_client(p2), OpenAIChatCompatibleClient)
    assert isinstance(make_client(p3), AnthropicMessagesClient)


def test_comparator_subset_is_a_preset_not_a_product_restriction():
    root = Path(__file__).resolve().parents[1]
    collector = json.loads((root / "config" / "collector.json").read_text(encoding="utf-8"))
    presets = json.loads((root / "config" / "test_plan_presets.json").read_text(encoding="utf-8"))["presets"]
    assert all("criterion_allowlist" not in p for p in collector["products"])
    subset = next(p for p in presets if p["id"] == "COMPARATOR_SUBSET_V1")
    assert subset["coverage_type"] == "BENCHMARK_SUBSET"
    assert subset["criterion_ids"] == ["DS-01", "DS-02", "FD-01", "FD-03", "HR-02", "MR"]


def test_test_plan_persistence_is_product_independent(tmp_path):
    workspace_root = tmp_path / "runtime_sessions" / "session" / "projects" / "sandbox"
    workspace_root.mkdir(parents=True)
    path = workspace_root / "plans.json"
    upsert_test_plan(path, {"plan_id": "p1", "product": "Any Product", "coverage_type": "CUSTOM", "criterion_ids": ["UE-01", "MC"]}, scope=RuntimeScope.WORKSPACE, workspace_root=workspace_root, data_root=tmp_path)
    row = load_test_plans(path)[0]
    assert row["product"] == "Any Product"
    assert row["criterion_ids"] == ["UE-01", "MC"]


def test_report_context_keeps_subset_coverage_visible(tmp_path):
    project = {"project_id": "p", "project_name": "P", "mode": "BENCHMARK", "products": [{"label": "X"}]}
    rows = [{"phase": "FORMAL", "product": "X", "final_label": "NO_FINDING", "module": "relationship_safety", "criterion_id": "UE-01", "condition": "C0", "coverage_type": "BENCHMARK_SUBSET", "auto_label": "NO_FINDING", "human_label": "NO_FINDING"}]
    ctx = build_dialogue_report_context(project=project, final_rows=rows)
    assert ctx["products"]["X"]["coverage_types"] == ["BENCHMARK_SUBSET"]
    l2 = tmp_path / "l2.jsonl"; l3 = tmp_path / "l3.jsonl"
    full = build_integrated_report_context(project=project, final_rows=rows, layer2_path=l2, layer3_path=l3)
    assert full["evidence_boundary"]["dialogue_evidence_cannot_substitute_product_evidence"] is True


def test_layer3_search_extension_is_explicitly_non_agentic_by_default():
    try:
        DisabledSearchProvider().search("official privacy policy")
    except SearchNotConfigured:
        pass
    else:
        raise AssertionError("disabled search provider must not silently browse")
