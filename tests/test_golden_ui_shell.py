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


def test_golden_home_excludes_obsolete_design_review_banner():
    source = GOLDEN.read_text(encoding="utf-8")
    for obsolete in (
        "UI/UX Refactor v0.9",
        "纯前端审查稿",
        "不读取、不写入正式数据",
        "示例数字仅用于布局",
    ):
        assert obsolete not in source, obsolete
    assert ".cg-home .review" not in source


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


def test_competition_micro_refinements_are_scoped_to_presentation():
    source = GOLDEN.read_text(encoding="utf-8")
    platform = (ROOT / "companionguard_app" / "platform_ui.py").read_text(encoding="utf-8")
    assert 'for item in ("judge", "review", "explorer", "reliability", "results")' in source
    assert '_group_heading("03 报告", "Reports")' in source
    assert '.navlayer-toggle{padding-left:16px!important}' in source
    assert '[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:10.8px!important;font-weight:640!important;line-height:1.32!important}' in source
    assert '[data-testid="stMain"] button[kind="primary"]{background:#3156d9!important;color:#fff!important' in source
    assert 'class="report-action-title"' in platform


def test_workspace_route_level_headings_are_not_repeated_in_body():
    ui = (ROOT / "companionguard_app" / "ui.py").read_text(encoding="utf-8")
    platform = (ROOT / "companionguard_app" / "platform_ui.py").read_text(encoding="utf-8")
    collector = (ROOT / "companionguard_app" / "collector_ui.py").read_text(encoding="utf-8")
    for duplicate in (
        'st.header("LLM 判定 / LLM Judge")',
        'st.header("人工复核 / Human Review")',
        'st.header("对话测试结果 / Dialogue Results")',
        'st.header("测试项目 / Test Projects")',
        'st.header("采集数据查看 / Data Explorer")',
        'st.header("Layer 2｜产品安全机制检查 / Product Safeguard Checks")',
        'st.header("Layer 3 Lite｜公开合规证据核查 / Public Compliance Evidence Audit")',
        'st.header("Judge—人工一致性 / Judge–Human Reliability")',
        'st.header("Layer 1｜对话测试报告 / Dialogue Report")',
        'st.header("确定性分析摘要 / Deterministic Analysis Summary")',
    ):
        assert duplicate not in ui + platform + collector
    assert 'st.subheader("对话采集 / Data Collection")' in collector


def test_report_llm_labels_are_plain_text_and_report_css_is_scoped():
    platform = (ROOT / "companionguard_app" / "platform_ui.py").read_text(encoding="utf-8")
    golden = GOLDEN.read_text(encoding="utf-8")
    assert "<span class='report-llm-heading'>" not in platform
    assert "report-llm-heading'" not in platform
    assert 'st.expander("展开配置 / Open configuration"' in platform
    assert 'class="report-document-marker"' in platform
    assert '[data-testid="stVerticalBlock"]:has(.report-document-marker)' in golden
    assert ".report-action-eyebrow{font-size:10.5px" in golden
    assert ".report-action-title{font-size:15px!important;font-weight:750px" not in golden
    assert ".report-action-title{font-size:15px!important;font-weight:750!important" in golden
    assert "color:#3156d9!important" in golden


def test_sidebar_hierarchy_is_ordered_by_size_and_indent():
    golden = GOLDEN.read_text(encoding="utf-8")
    assert ".navgroup-toggle .zh{font-size:13.5px!important;font-weight:800!important" in golden
    assert ".navlayer-toggle .zh{font-size:12.4px!important;font-weight:750!important" in golden
    assert ".navlayer-toggle{padding-left:16px!important}" in golden
    assert '[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:10.8px!important;font-weight:640!important;line-height:1.32!important}' in golden


def test_workspace_spacing_and_overview_has_no_body_duplicate_title():
    golden = GOLDEN.read_text(encoding="utf-8")
    assert '.workspace-bar{margin:-28px -32px -12px!important}' in golden
    assert '[data-testid="stMainBlockContainer"]{padding:28px 32px 72px!important' in golden
    assert '.workspace-head h1{font-size:25px!important;font-weight:780!important;color:#101828}' in golden
    assert 'class="card"><div class="cardhead"><span class="workspace-pill blue">FORMAL</span>' in golden
    assert '<h2>当前项目总览</h2>' not in golden


def test_sidebar_active_leaf_does_not_override_leaf_typography():
    golden = GOLDEN.read_text(encoding="utf-8")
    leaf_rule = '[data-testid="stSidebar"] [data-testid="stButton"] button{font-size:10.8px!important;font-weight:640!important;line-height:1.32!important}'
    assert golden.count(leaf_rule) == 1
    assert '[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]' in golden
