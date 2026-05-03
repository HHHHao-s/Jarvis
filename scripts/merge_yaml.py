#!/usr/bin/env python3
"""Merge batch YAML files from sub-agents into input.yaml and output pipeline stats."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

TZ8 = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = ROOT / "data" / "tmp"
OUTPUT = ROOT / "data" / "tmp" / "input.yaml"
STATS_FILE = ROOT / "data" / "tmp" / "pipeline_stats.json"


def main():
    batch_files = sorted(TMP_DIR.glob("batch-*.yaml"))
    if not batch_files:
        print("No batch YAML files found.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(TZ8).isoformat(timespec="seconds")
    today = datetime.now(TZ8).strftime("%Y-%m-%d")

    all_articles = []
    seen_ids = set()
    for f in batch_files:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        for a in data.get("articles", []):
            aid = a.get("id", "")
            if aid and aid not in seen_ids:
                seen_ids.add(aid)
                a.setdefault("processed_at", now)
                all_articles.append(a)

    OUTPUT.write_text(
        yaml.dump({"date": today, "articles": all_articles},
                  allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    # Compute stats
    sources = sorted(set(a.get("source", "?") for a in all_articles))
    categories = sorted(set(a.get("category", "Other") for a in all_articles))

    stats = {
        "date": today,
        "sources_queried": len(sources),
        "articles_found": len(all_articles),
        "articles_added": len(seen_ids),
        "categories": categories,
    }

    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Merged {len(all_articles)} articles from {len(sources)} sources, {len(batch_files)} batches")
    print(f"Categories: {', '.join(categories)}")
    print(f"Stats saved to {STATS_FILE}")


if __name__ == "__main__":
    main()
