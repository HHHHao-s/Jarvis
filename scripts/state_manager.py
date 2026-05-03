"""State persistence for the Jarvis pipeline.

Each invocation is stateless — every run reads/writes state from disk.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ8 = timezone(timedelta(hours=8))
PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "state.json"
SOURCES_FILE = PROJECT_ROOT / "data" / "sources.json"


def now() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)


def load_state() -> dict:
    return read_json(STATE_FILE)


def save_state(state: dict):
    state["last_updated"] = now()
    write_json(STATE_FILE, state)


def load_sources() -> dict:
    return read_json(SOURCES_FILE)


def save_sources(sources: dict):
    sources["updated_at"] = now()
    write_json(SOURCES_FILE, sources)


def record_pipeline_run(state: dict, success: bool, details: dict):
    """Record a pipeline run in state."""
    p = state.setdefault("pipeline", {})
    p["last_run"] = now()
    p["total_runs"] = p.get("total_runs", 0) + 1

    if success:
        p["last_success"] = now()
        p["total_successes"] = p.get("total_successes", 0) + 1
        p["consecutive_failures"] = 0
    else:
        p["total_failures"] = p.get("total_failures", 0) + 1
        p["consecutive_failures"] = p.get("consecutive_failures", 0) + 1

    run_entry = {
        "timestamp": now(),
        "success": success,
        **details,
    }
    history = p.setdefault("run_history", [])
    history.append(run_entry)
    # Keep last 90 runs
    p["run_history"] = history[-90:]

    if success:
        if "date" in details:
            d = state.setdefault("digests", {})
            d["last_date"] = details["date"]
            d["total_posts"] = d.get("total_posts", 0) + (details.get("is_new_post", False) and 1 or 0)
            d["total_articles"] = d.get("total_articles", 0) + details.get("articles_added", 0)

    save_state(state)


def record_evolution_run(state: dict, generation: int, changes: list, insights: str):
    """Record an evolution run."""
    e = state.setdefault("evolution", {})
    e["last_run"] = now()
    e["total_runs"] = e.get("total_runs", 0) + 1
    e["current_generation"] = generation

    entry = {
        "timestamp": now(),
        "generation": generation,
        "changes": changes,
        "insights": insights[:500],
    }
    history = e.setdefault("run_history", [])
    history.append(entry)
    e["run_history"] = history[-52]  # Keep last 52 (weekly for a year)

    save_state(state)


def record_error(state: dict, error_type: str, message: str):
    """Record an error for learning."""
    errors = state.setdefault("errors", [])
    errors.append({
        "timestamp": now(),
        "type": error_type,
        "message": message[:300],
    })
    state["errors"] = errors[-50]
    save_state(state)


def get_source_performance(state: dict, source_id: str) -> dict:
    """Get performance data for a specific source."""
    sources = load_sources()
    for s in sources.get("sources", []):
        if s["id"] == source_id:
            return s.get("performance", {})
    return {}


def update_source_performance(source_id: str, articles_count: int, avg_quality: float):
    """Update source performance metrics."""
    sources = load_sources()
    for s in sources.get("sources", []):
        if s["id"] == source_id:
            perf = s.setdefault("performance", {})
            runs = perf.get("runs", 0)
            old_avg = perf.get("avg_articles", 0)
            old_qual = perf.get("avg_quality", 0)
            perf["runs"] = runs + 1
            perf["avg_articles"] = round((old_avg * runs + articles_count) / (runs + 1), 1)
            perf["avg_quality"] = round((old_qual * runs + avg_quality) / (runs + 1), 1)
            perf["last_run"] = now()
            break
    save_sources(sources)


def adjust_source_weights(sources: dict, adjustments: dict):
    """Adjust source weights based on evolution insights."""
    rules = sources.get("evolution_rules", {})
    min_w = rules.get("min_weight", 1)
    max_w = rules.get("max_weight", 10)

    for s in sources.get("sources", []):
        if s["id"] in adjustments:
            delta = adjustments[s["id"]]
            old = s["weight"]
            s["weight"] = max(min_w, min(max_w, old + delta))
            if s["weight"] != old:
                s.setdefault("weight_history", []).append({
                    "timestamp": now(),
                    "old": old,
                    "new": s["weight"],
                    "reason": f"Evolution adjustment: {delta:+d}",
                })

    save_sources(sources)


def get_pipeline_summary(state: dict) -> str:
    """Human-readable summary of pipeline state."""
    p = state.get("pipeline", {})
    e = state.get("evolution", {})
    d = state.get("digests", {})

    return (
        f"Pipeline: {p.get('total_successes', 0)}/{p.get('total_runs', 0)} successes, "
        f"last: {p.get('last_run') or 'never'}\n"
        f"Digests: {d.get('total_posts', 0)} posts, {d.get('total_articles', 0)} articles\n"
        f"Evolution: gen {e.get('current_generation', 0)}, "
        f"{e.get('total_runs', 0)} runs, last: {e.get('last_run') or 'never'}"
    )


if __name__ == "__main__":
    state = load_state()
    print(get_pipeline_summary(state))
