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

OVERRIDE_REASONS = [
    "MISSED_TARGET_BEHAVIOR",
    "FALSE_POSITIVE_TARGET_BEHAVIOR",
    "MISREAD_CONTEXT",
    "BOUNDARY_RULE_MISAPPLIED",
    "EVIDENCE_NOT_SUPPORTED",
    "REVIEW_REQUIRED",
    "OTHER",
]

MODULE_LABELS = {
    "relationship_safety": "Relationship Safety",
    "extreme_behavior_and_crisis_response": "Extreme Behavior & Crisis Response",
    "minor_protection": "Minor Protection",
    "information_and_rights_protection": "Information & Privacy",
    "prohibited_content_special_test": "Prohibited Content",
}

OFFICIAL_MODULE_ORDER = list(MODULE_LABELS)
