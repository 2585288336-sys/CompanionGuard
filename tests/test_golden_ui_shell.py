from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "companionguard_app" / "golden_ui.py"
ENTRYPOINT = ROOT / "streamlit_app.py"


def test_entrypoint_uses_home_first_and_workspace_shell_second():
    source = ENTRYPOINT.read_text(encoding="utf-8")
    assert "from companionguard_app.golden_ui import run_app" in source
    assert "run_app()" in source


def test_golden_home_required_copy_is_embedded_verbatim():
    source = GOLDEN.read_text(encoding="utf-8")
    required = [
        "CompanionGuard（陪伴卫士）——拟人化 AI 监管评测与风险诊断系统",
        "REGULATORY TESTING &amp; RISK DIAGNOSIS",
        "把拟人化 AI 的监管要求，转化为可执行、可复核的测试",
        "从《人工智能拟人化互动服务管理暂行办法》监管要求到真实产品测试",
        "三层监管评测框架",
        "核心测试范围",
        "支持自定义测试项目",
        "对话测试与实验条件",
        "LLM Judge + 人工复核",
        "如何理解评测结果",
        "构建与方法",
        "查看完整方法说明",
        "App v0.9 · Data Schema v1.0",
    ]
    for text in required:
        assert text in source, text


def test_golden_shell_preserves_contrast_and_overflow_guards():
    source = GOLDEN.read_text(encoding="utf-8")
    assert ".btn.primary{background:#3156d9;border-color:#3156d9;color:#fff}" in source
    assert ".downloadbox{display:flex" in source
    assert "color:#d0d5dd" in source
    assert "overflow-x:hidden" in source
    assert "min-width:0" in source
    assert "100vw" not in source


def test_golden_size_tokens_and_sidebar_hierarchy_are_explicit():
    source = GOLDEN.read_text(encoding="utf-8")
    for token in (
        "font-size:56px",
        "line-height:1.05",
        "letter-spacing:-.045em",
        "font-size:17px",
        "font-size:30px",
        "font-size:25px",
        "padding:9px 14px",
        "grid-template-columns:244px 1fr",
        "font-size:11.7px",
        "font-size:10.8px",
        "font-size:11.4px",
        "padding:7px 10px 7px 11px",
    ):
        assert token in source, token


def test_six_baseline_workflows_are_still_routed():
    source = GOLDEN.read_text(encoding="utf-8")
    for function_name in (
        "run_test_page",
        "human_review_page",
        "layer2_page",
        "layer3_page",
        "dialogue_report_page",
        "report_page",
    ):
        assert f"{function_name}(" in source, function_name
