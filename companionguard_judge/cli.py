from __future__ import annotations
import argparse
import os
from pathlib import Path

from companionguard_llm.client import make_client
from companionguard_llm.profiles import LLMProfile
from .pipeline import dry_run, load_criteria, read_jsonl, run_batch


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CompanionGuard criterion-bound LLM Judge")
    p.add_argument("--input", required=True, help="Input cases JSONL")
    p.add_argument("--criteria-dir", default="criteria")
    p.add_argument("--output", default="outputs/judge_results.jsonl")
    p.add_argument("--provider-type", choices=["openai_responses", "openai_chat_compatible", "anthropic"], default=os.environ.get("COMPANIONGUARD_JUDGE_PROVIDER_TYPE", "openai_responses"))
    p.add_argument("--provider-name", default=os.environ.get("COMPANIONGUARD_JUDGE_PROVIDER_NAME", "LLM Provider"))
    p.add_argument("--base-url", default=os.environ.get("COMPANIONGUARD_JUDGE_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    p.add_argument("--model", default=os.environ.get("COMPANIONGUARD_JUDGE_MODEL") or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    p.add_argument("--reasoning-effort", choices=["none", "low", "high", "max"], default=os.environ.get("COMPANIONGUARD_JUDGE_REASONING_EFFORT", "none"))
    p.add_argument("--temperature", type=float, default=float(os.environ.get("COMPANIONGUARD_JUDGE_TEMPERATURE", "0")))
    p.add_argument("--semantic-retries", type=int, choices=[0, 1, 2], default=1)
    p.add_argument("--limit", type=int)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    input_path = Path(args.input)
    criteria_dir = Path(args.criteria_dir)
    if args.dry_run:
        criteria = load_criteria(criteria_dir); cases = read_jsonl(input_path); errors = dry_run(cases, criteria)
        if errors:
            print("Dry-run failed:")
            for e in errors: print(" -", e)
            return 2
        print(f"Dry-run OK: {len(cases)} cases, {len(criteria)} criteria loaded.")
        return 0

    api_key = os.environ.get("COMPANIONGUARD_JUDGE_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("COMPANIONGUARD_JUDGE_API_KEY is not set (legacy DEEPSEEK_API_KEY is also accepted).")
        return 2
    profile = LLMProfile(role="judge", provider_type=args.provider_type, provider_name=args.provider_name, model=args.model, api_key=api_key, base_url=args.base_url, reasoning_effort=args.reasoning_effort, temperature=args.temperature, access_mode="SERVER")
    try:
        ok, failed = run_batch(client=make_client(profile), input_path=input_path, criteria_dir=criteria_dir, output_path=Path(args.output), semantic_retries=args.semantic_retries, overwrite=args.overwrite, limit=args.limit)
    except ValueError as e:
        print(e); return 2
    print(f"Done: ok={ok}, error={failed}")
    return 0 if failed == 0 else 1
