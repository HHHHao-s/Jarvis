#!/usr/bin/env python3
"""Pipeline orchestration helpers for the Jarvis daily digest system.

Called by Claude during pipeline/evolve runs to manage state,
record outcomes, and prepare search plans.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ8 = timezone(timedelta(hours=8))
PROJECT_ROOT = Path(__file__).parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "state.json"
SOURCES_FILE = PROJECT_ROOT / "data" / "sources.json"


def now() -> str:
    return datetime.now(TZ8).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(TZ8).strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)


def article_id(url: str) -> str:
    """Generate article ID from URL."""
    return hashlib.md5(url.encode()).hexdigest()[:8]


# --- Commands ---


def cmd_prepare(_args):
    """Print the search plan — which sources to query and how."""
    sources_data = read_json(SOURCES_FILE)
    active = [s for s in sources_data.get("sources", []) if s.get("active")]
    active.sort(key=lambda s: s.get("weight", 5), reverse=True)

    print(f"=== Search Plan for {today()} ===\n")
    print(f"Active sources: {len(active)}/{len(sources_data.get('sources', []))}\n")

    for i, s in enumerate(active):
        queries = s.get("search_queries", [])
        perf = s.get("performance", {})
        print(f"{i+1}. [{s['id']}] {s['name']} (weight={s.get('weight')}, "
              f"runs={perf.get('runs', 0)}, avg_articles={perf.get('avg_articles', 0)})")
        print(f"   Focus: {', '.join(s.get('focus', []))}")
        print(f"   Queries: {', '.join(queries[:3])}")
        print()

    # Output JSON for programmatic use
    print("--- JSON ---")
    plan = {
        "date": today(),
        "sources": [
            {
                "id": s["id"],
                "name": s["name"],
                "weight": s.get("weight", 5),
                "focus": s.get("focus", []),
                "queries": s.get("search_queries", [])[:3],
            }
            for s in active
        ],
    }
    print(json.dumps(plan, ensure_ascii=False))


def cmd_record(args):
    """Record a pipeline run outcome."""
    state = read_json(STATE_FILE)
    p = state.setdefault("pipeline", {})
    p["last_run"] = now()
    p["total_runs"] = p.get("total_runs", 0) + 1

    if args.success:
        p["last_success"] = now()
        p["total_successes"] = p.get("total_successes", 0) + 1
        p["consecutive_failures"] = 0
    else:
        p["total_failures"] = p.get("total_failures", 0) + 1
        p["consecutive_failures"] = p.get("consecutive_failures", 0) + 1

    entry = {
        "timestamp": now(),
        "date": args.date or today(),
        "success": args.success,
        "sources_queried": args.sources_queried or 0,
        "articles_found": args.articles_found or 0,
        "articles_added": args.articles_added or 0,
        "categories": args.categories.split(",") if args.categories else [],
        "error": args.error or "",
    }
    p.setdefault("run_history", []).append(entry)
    p["run_history"] = p["run_history"][-90:]

    if args.success:
        d = state.setdefault("digests", {})
        d["last_date"] = args.date or today()
        d["total_posts"] = d.get("total_posts", 0) + 1
        d["total_articles"] = d.get("total_articles", 0) + (args.articles_added or 0)
        # Update category distribution
        if args.categories:
            cat_dist = d.setdefault("category_distribution", {})
            for cat in args.categories.split(","):
                cat = cat.strip()
                cat_dist[cat] = cat_dist.get(cat, 0) + 1

    state["last_updated"] = now()
    write_json(STATE_FILE, state)
    status = "SUCCESS" if args.success else "FAILURE"
    print(f"Recorded pipeline run: {status}")
    print(f"  Date: {args.date or today()}")
    print(f"  Articles: {args.articles_found or 0} found, {args.articles_added or 0} added")
    print(f"  Total runs: {p['total_runs']}, successes: {p['total_successes']}")


def cmd_evolve_record(args):
    """Record an evolution run."""
    state = read_json(STATE_FILE)
    e = state.setdefault("evolution", {})
    e["last_run"] = now()
    e["total_runs"] = e.get("total_runs", 0) + 1
    gen = e.get("current_generation", 0) + 1
    e["current_generation"] = gen

    entry = {
        "timestamp": now(),
        "generation": gen,
        "summary": args.summary or "",
        "changes": args.changes or "",
        "insights": args.insights or "",
    }
    e.setdefault("run_history", []).append(entry)
    e["run_history"] = e["run_history"][-52]

    state["last_updated"] = now()
    write_json(STATE_FILE, state)
    print(f"Recorded evolution: generation {gen}")
    print(f"  Summary: {args.summary or 'N/A'}")
    print(f"  Total evolutions: {e['total_runs']}")


def cmd_update_source(args):
    """Update a source's performance metrics."""
    sources_data = read_json(SOURCES_FILE)
    for s in sources_data.get("sources", []):
        if s["id"] == args.source_id:
            perf = s.setdefault("performance", {})
            runs = perf.get("runs", 0)
            old_avg = perf.get("avg_articles", 0)
            old_qual = perf.get("avg_quality", 0)
            perf["runs"] = runs + 1
            perf["avg_articles"] = round(
                (old_avg * runs + args.articles) / (runs + 1), 1
            )
            perf["avg_quality"] = round(
                (old_qual * runs + args.quality) / (runs + 1), 1
            )
            perf["last_run"] = now()
            print(f"Updated source '{args.source_id}': "
                  f"articles_avg={perf['avg_articles']}, "
                  f"quality_avg={perf['avg_quality']}")
            break
    else:
        print(f"ERROR: source '{args.source_id}' not found", file=sys.stderr)
        sys.exit(1)

    sources_data["updated_at"] = now()
    write_json(SOURCES_FILE, sources_data)


def cmd_status(_args):
    """Print current system status."""
    state = read_json(STATE_FILE)
    sources_data = read_json(SOURCES_FILE)

    p = state.get("pipeline", {})
    e = state.get("evolution", {})
    d = state.get("digests", {})

    print("=== Jarvis System Status ===\n")
    print(f"Pipeline:")
    print(f"  Last run: {p.get('last_run', 'never')}")
    print(f"  Success rate: {p.get('total_successes', 0)}/{p.get('total_runs', 0)}")
    print(f"  Consecutive failures: {p.get('consecutive_failures', 0)}")
    print()
    print(f"Digests:")
    print(f"  Total posts: {d.get('total_posts', 0)}")
    print(f"  Total articles: {d.get('total_articles', 0)}")
    print(f"  Last date: {d.get('last_date', 'N/A')}")
    print()
    print(f"Evolution:")
    print(f"  Generation: {e.get('current_generation', 0)}")
    print(f"  Total runs: {e.get('total_runs', 0)}")
    print(f"  Last run: {e.get('last_run', 'never')}")
    print()
    print(f"Sources ({len(sources_data.get('sources', []))} total):")
    active_count = 0
    for s in sources_data.get("sources", []):
        status = "ACTIVE" if s.get("active") else "INACTIVE"
        if s.get("active"):
            active_count += 1
        perf = s.get("performance", {})
        print(f"  [{s['id']}] {s['name']} — {status}, weight={s.get('weight')}, "
              f"runs={perf.get('runs', 0)}, avg={perf.get('avg_articles', 0)}")
    print(f"  Active: {active_count}, Inactive: {len(sources_data.get('sources', [])) - active_count}")
    print()

    errors = state.get("errors", [])
    if errors:
        print(f"Recent errors ({len(errors)}):")
        for err in errors[-5:]:
            print(f"  [{err.get('timestamp', '?')}] {err.get('type', '?')}: {err.get('message', '?')[:80]}")


def cmd_sources_json(_args):
    """Output active sources as JSON for Claude to consume."""
    sources_data = read_json(SOURCES_FILE)
    active = [s for s in sources_data.get("sources", []) if s.get("active")]
    active.sort(key=lambda s: s.get("weight", 5), reverse=True)
    print(json.dumps({"date": today(), "sources": active}, ensure_ascii=False))


def cmd_last_digests(args):
    """List recent digest files for analysis."""
    posts_dir = PROJECT_ROOT / "docs" / "_posts"
    n = args.n or 14
    if not posts_dir.exists():
        print("No posts directory found.")
        return

    files = sorted(posts_dir.glob("*.md"), reverse=True)[:n]
    for f in files:
        stat = f.stat()
        size_kb = stat.st_size / 1024
        print(f"{f.name} ({size_kb:.1f} KB)")

    # Output paths as JSON
    print("\n--- JSON ---")
    print(json.dumps([str(f.relative_to(PROJECT_ROOT)) for f in files], ensure_ascii=False))


# --- CLI ---


def parse_args():
    p = argparse.ArgumentParser(description="Jarvis pipeline orchestration helpers")
    sub = p.add_subparsers(dest="command")

    prep = sub.add_parser("prepare", help="Print search plan for today's run")

    rec = sub.add_parser("record", help="Record a pipeline run outcome")
    rec.add_argument("--success", action=argparse.BooleanOptionalAction, required=True)
    rec.add_argument("--date", help="Digest date YYYY-MM-DD")
    rec.add_argument("--sources-queried", type=int)
    rec.add_argument("--articles-found", type=int)
    rec.add_argument("--articles-added", type=int)
    rec.add_argument("--categories")
    rec.add_argument("--error")

    evo = sub.add_parser("evolve-record", help="Record an evolution run")
    evo.add_argument("--summary")
    evo.add_argument("--changes")
    evo.add_argument("--insights")

    us = sub.add_parser("update-source", help="Update source performance")
    us.add_argument("--source-id", required=True)
    us.add_argument("--articles", type=int, required=True)
    us.add_argument("--quality", type=float, required=True)

    sub.add_parser("status", help="Show system status")
    sub.add_parser("sources", help="Output active sources as JSON")

    last = sub.add_parser("last-digests", help="List recent digest files")
    last.add_argument("-n", type=int, default=14)

    return p.parse_args()


def main():
    args = parse_args()
    if args.command == "prepare":
        cmd_prepare(args)
    elif args.command == "record":
        cmd_record(args)
    elif args.command == "evolve-record":
        cmd_evolve_record(args)
    elif args.command == "update-source":
        cmd_update_source(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "sources":
        cmd_sources_json(args)
    elif args.command == "last-digests":
        cmd_last_digests(args)
    else:
        print("No command specified. Use --help for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
