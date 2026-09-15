from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRITERIA_DIR = PROJECT_ROOT / "criteria"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
COLLECTOR_CONFIG_PATH = CONFIG_DIR / "collector.json"
RAW_CASES_PATH = DATA_DIR / "raw_cases.jsonl"
COLLECTION_SESSIONS_PATH = DATA_DIR / "collection_sessions.jsonl"
COLLECTION_QUEUES_PATH = DATA_DIR / "collection_queues.jsonl"
EVIDENCE_DIR = DATA_DIR / "evidence"
JUDGE_RESULTS_PATH = DATA_DIR / "judge_results.jsonl"
ADJUDICATION_PATH = DATA_DIR / "human_adjudication.csv"
FINAL_RESULTS_PATH = DATA_DIR / "final_results.csv"
LLM_USAGE_PATH = DATA_DIR / "llm_usage.jsonl"
PROMPTS_DIR = PROJECT_ROOT / "prompts"

OVERRIDE_REASONS = [
    "MISSED_TARGET_BEHAVIOR",
    "FALSE_POSITIVE_TARGET_BEHAVIOR",
    "MISREAD_CONTEXT",
    "BOUNDARY_RULE_MISAPPLIED",
    "EVIDENCE_NOT_SUPPORTED",
    "REVIEW_REQUIRED",
    "OTHER",
]

CASE_VALIDITIES = ["VALID", "INVALID", "REVIEW"]

VALIDITY_REASONS = [
    "OFF_TOPIC_RESPONSE",
    "MISSING_CONTEXT",
    "TRUNCATED_RESPONSE",
    "COLLECTION_ERROR",
    "DUPLICATE_OR_CONTAMINATED_CASE",
    "UNRESOLVED_VALIDITY",
    "OTHER",
]

MODULE_LABELS = {
    "relationship_safety": "Module A｜关系安全 / Relationship Safety",
    "extreme_behavior_and_crisis_response": "Module B｜极端行为与危机应对 / Extreme Behavior & Crisis Response",
    "minor_protection": "Module C｜未成年人保护 / Minor Protection",
    "information_and_rights_protection": "Module D｜信息与权益保护 / Information & Rights Protection",
    "prohibited_content_special_test": "禁止性内容生成专项测试组 / Prohibited Content",
}

OFFICIAL_MODULE_ORDER = list(MODULE_LABELS)
