#!/usr/bin/env python3
"""Extract token usage from Claude Code stream-json output and record to state.

Usage:
  python scripts/extract_tokens.py                     # pipeline mode (default)
  python scripts/extract_tokens.py --mode evolve       # evolve mode
  python scripts/extract_tokens.py --log data/xxx.jsonl --mode pipeline
"""
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "state.json"
TZ8 = timezone(timedelta(hours=8))

DEFAULT_LOG = {
    "pipeline": ROOT / "data" / "tmp" / "pipeline_output.jsonl",
    "evolve": ROOT / "data" / "tmp" / "evolve_output.jsonl",
}


def extract(log_path: Path) -> dict:
    """Parse stream-json log and extract token usage."""
    if not log_path.exists():
        return {"error": f"Log file not found: {log_path}"}

    final = {}

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only use the final result event — intermediate usage is cumulative, not delta
            if event.get("type") == "result":
                final = event.get("usage") or {}

    total_input = final.get("input_tokens", 0)
    total_output = final.get("output_tokens", 0)
    cache_read = final.get("cache_read_input_tokens", 0)
    cache_write = final.get("cache_creation_input_tokens", 0)

    return {
        "input": total_input,
        "output": total_output,
        "total": total_input + total_output,
        "cache_read": cache_read,
        "cache_write": cache_write,
    }


def save_to_state(usage: dict, mode: str):
    """Append token usage to the latest run history entry."""
    if not STATE_FILE.exists():
        print("State file not found, skipping save.")
        return

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    entry = {"recorded_at": datetime.now(TZ8).isoformat(timespec="seconds"), **usage}

    if mode == "pipeline":
        p = state.setdefault("pipeline", {})
        history = p.get("run_history", [])
        if history:
            history[-1]["tokens"] = entry

        # Cumulative pipeline tokens
        pt = p.setdefault("total_tokens", {"input": 0, "output": 0, "total": 0})
        pt["input"] += usage["input"]
        pt["output"] += usage["output"]
        pt["total"] += usage["total"]

    elif mode == "evolve":
        e = state.setdefault("evolution", {})
        history = e.get("run_history", [])
        if history:
            history[-1]["tokens"] = entry

        # Cumulative evolution tokens
        et = e.setdefault("total_tokens", {"input": 0, "output": 0, "total": 0})
        et["input"] += usage["input"]
        et["output"] += usage["output"]
        et["total"] += usage["total"]

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Token usage saved to state.json → {mode}.run_history[-1].tokens")


def main():
    p = argparse.ArgumentParser(description="Extract Claude Code token usage")
    p.add_argument("--log", help="Path to JSONL log file")
    p.add_argument("--mode", choices=["pipeline", "evolve"], default="pipeline")
    args = p.parse_args()

    log_path = Path(args.log) if args.log else DEFAULT_LOG[args.mode]
    usage = extract(log_path)

    if "error" in usage:
        print(f"ERROR: {usage['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"Input tokens:  {usage['input']:>10,}")
    print(f"Output tokens: {usage['output']:>10,}")
    print(f"Total tokens:  {usage['total']:>10,}")
    if usage.get("cache_read"):
        print(f"Cache read:    {usage['cache_read']:>10,}")
    if usage.get("cache_write"):
        print(f"Cache write:   {usage['cache_write']:>10,}")

    save_to_state(usage, args.mode)


if __name__ == "__main__":
    main()
