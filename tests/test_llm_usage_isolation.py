from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import companionguard_app.service as service
from companionguard_app.runtime_scope import (
    PublishedWriteError,
    RuntimeScope,
    WorkspacePathViolationError,
    assert_writable_target,
    resolve_project_root,
)
from companionguard_app.service import run_report_writer
from companionguard_llm.guard import check_server_guard
from companionguard_llm.profiles import LLMProfile


class FakeClient:
    def generate_text(self, *, system_prompt, payload, max_output_tokens):
        return "draft", {"input_tokens": 3, "output_tokens": 2}


def _profile(*, access_mode: str = "BYOK") -> LLMProfile:
    return LLMProfile(
        role="integrated_report",
        provider_type="openai_chat_compatible",
        provider_name="fake",
        model="fake-model",
        api_key="test-only",
        access_mode=access_mode,
    )


def _workspace(tmp_path: Path, session_id: str, sandbox_id: str) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    root = resolve_project_root(
        "official",
        scope=RuntimeScope.WORKSPACE,
        session_id=session_id,
        sandbox_id=sandbox_id,
        data_root=data_root,
    )
    root.mkdir(parents=True)
    return data_root, root


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_workspace_usage_isolated_between_sessions(tmp_path: Path):
    data_root_a, workspace_a = _workspace(tmp_path, "session-a", "sandbox-a")
    data_root_b, workspace_b = _workspace(tmp_path, "session-b", "sandbox-b")
    profile = _profile()

    with patch("companionguard_app.service.make_client", return_value=FakeClient()):
        run_report_writer(
            role="integrated_report",
            report_context={},
            llm_profile=profile,
            session_id="session-a",
            project_id="official",
            scope=RuntimeScope.WORKSPACE,
            workspace_root=workspace_a,
            data_root=data_root_a,
        )
        run_report_writer(
            role="integrated_report",
            report_context={},
            llm_profile=profile,
            session_id="session-b",
            project_id="official",
            scope=RuntimeScope.WORKSPACE,
            workspace_root=workspace_b,
            data_root=data_root_b,
        )

    usage_a = _rows(workspace_a / "llm_usage.jsonl")
    usage_b = _rows(workspace_b / "llm_usage.jsonl")
    assert len(usage_a) == len(usage_b) == 2
    assert usage_a[0]["session_id"] == "session-a"
    assert usage_b[0]["session_id"] == "session-b"
    assert all(row["session_id"] != "session-b" for row in usage_a)
    assert all(row["session_id"] != "session-a" for row in usage_b)


def test_server_usage_records_project_and_separate_global_quota_state(tmp_path: Path):
    data_root, workspace = _workspace(tmp_path, "session-a", "sandbox-a")
    global_quota_path = tmp_path / "server-quota.jsonl"
    profile = _profile(access_mode="SERVER")

    with patch("companionguard_app.service.make_client", return_value=FakeClient()), patch.object(service, "LLM_USAGE_PATH", global_quota_path):
        run_report_writer(
            role="integrated_report",
            report_context={},
            llm_profile=profile,
            session_id="session-a",
            project_id="official",
            scope=RuntimeScope.WORKSPACE,
            workspace_root=workspace,
            data_root=data_root,
        )

    assert len(_rows(workspace / "llm_usage.jsonl")) == 2
    quota_rows = _rows(global_quota_path)
    assert len(quota_rows) == 2
    assert quota_rows[0]["access_mode"] == "SERVER"
    assert workspace / "llm_usage.jsonl" != global_quota_path


def test_server_quota_limits_still_use_global_server_rows(tmp_path: Path, monkeypatch):
    quota_path = tmp_path / "server-quota.jsonl"
    today = datetime.now(timezone.utc).date().isoformat()
    quota_path.write_text(
        json.dumps({"date": today, "access_mode": "SERVER", "session_id": "session-a"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANIONGUARD_SERVER_LLM_ENABLED", "1")
    monkeypatch.setenv("COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT", "1")
    monkeypatch.setenv("COMPANIONGUARD_SERVER_LLM_SESSION_CALL_LIMIT", "1")

    with pytest.raises(RuntimeError, match="daily call limit"):
        check_server_guard(usage_path=quota_path, session_id="session-b")

    quota_path.write_text(
        json.dumps({"date": today, "access_mode": "SERVER", "session_id": "session-a"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COMPANIONGUARD_SERVER_LLM_DAILY_CALL_LIMIT", "10")
    with pytest.raises(RuntimeError, match="session call limit"):
        check_server_guard(usage_path=quota_path, session_id="session-a")


def test_published_usage_write_is_rejected_before_llm(tmp_path: Path):
    data_root = tmp_path / "data"
    published = data_root / "projects" / "official"
    published.mkdir(parents=True)
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("LLM client must not be constructed for Published usage")

    with patch("companionguard_app.service.make_client", side_effect=fail_if_called):
        with pytest.raises(PublishedWriteError):
            run_report_writer(
                role="integrated_report",
                report_context={},
                llm_profile=_profile(),
                scope=RuntimeScope.PUBLISHED,
                workspace_root=published,
                data_root=data_root,
            )

    assert called is False
    assert not (published / "llm_usage.jsonl").exists()


def test_usage_target_preserves_phase_4a5_path_bound_protection(tmp_path: Path):
    data_root, current = _workspace(tmp_path, "session-a", "sandbox-a")
    other_session = resolve_project_root(
        "official",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-b",
        sandbox_id="sandbox-b",
        data_root=data_root,
    )
    sibling = resolve_project_root(
        "official",
        scope=RuntimeScope.WORKSPACE,
        session_id="session-a",
        sandbox_id="sandbox-b",
        data_root=data_root,
    )
    published = resolve_project_root("official", scope=RuntimeScope.PUBLISHED, data_root=data_root)
    arbitrary = tmp_path / "arbitrary" / "llm_usage.jsonl"

    for target in (
        other_session / "llm_usage.jsonl",
        sibling / "llm_usage.jsonl",
        published / "llm_usage.jsonl",
        arbitrary,
    ):
        with pytest.raises(WorkspacePathViolationError):
            assert_writable_target(RuntimeScope.WORKSPACE, target, workspace_root=current, data_root=data_root)

    assert_writable_target(RuntimeScope.WORKSPACE, current / "llm_usage.jsonl", workspace_root=current, data_root=data_root) == current / "llm_usage.jsonl"
