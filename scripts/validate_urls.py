#!/usr/bin/env python3
"""URL validation for the Jarvis pipeline.

Usage:
  python scripts/validate_urls.py lock data/tmp/       # extract URL whitelist from tmp files
  python scripts/validate_urls.py check data/input.yaml # cross-reference against whitelist + HTTP
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

URL_PATTERN = re.compile(r'\[([^\]]*)\]\((https?://[^\s\)]+)\)')
BROKEN_DOMAINS = {'javascript:void(0)', 'example.com', 'localhost', '127.0.0.1'}
WHITELIST_FILE = "data/tmp/url_whitelist.json"


def is_syntactic(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        return False
    if len(url) < 15:
        return False
    for d in BROKEN_DOMAINS:
        if d in url.lower():
            return False
    return True


def cmd_lock(args):
    """Extract all valid URLs from tmp markdown files and save as whitelist."""
    tmp_dir = Path(args.dir)
    if not tmp_dir.exists():
        print(f"Directory not found: {tmp_dir}", file=sys.stderr)
        sys.exit(1)

    whitelist = {}  # source-id -> {url: {source, title}}
    total_cleaned = 0
    total_urls = 0

    for md_file in sorted(tmp_dir.glob("*.md")):
        source_id = md_file.stem
        content = md_file.read_text(encoding="utf-8")
        lines = content.split("\n")
        cleaned = []
        removed = 0
        source_wl = {}

        for line in lines:
            m = URL_PATTERN.search(line)
            if m:
                title, url = m.group(1), m.group(2)
                if is_syntactic(url):
                    source_wl[url] = {"source": source_id, "title": title}
                    cleaned.append(line)
                else:
                    removed += 1
            else:
                cleaned.append(line)

        if source_wl:
            whitelist[source_id] = source_wl
            total_urls += len(source_wl)

        if removed > 0:
            md_file.write_text("\n".join(cleaned), encoding="utf-8")
            print(f"  [{md_file.name}] {len(source_wl)} URLs, cleaned {removed} bad")

        total_cleaned += removed

    whitelist_path = Path(args.dir) / "url_whitelist.json"
    whitelist_path.write_text(json.dumps(whitelist, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWhitelist: {total_urls} URLs across {len(whitelist)} sources → {whitelist_path}")
    if total_cleaned:
        print(f"Cleaned: {total_cleaned} bad URLs removed from tmp files")


def check_http(url: str, timeout: int = 8) -> tuple[str, bool]:
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'Jarvis/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return url, resp.status < 400
    except urllib.error.HTTPError as e:
        return url, e.code < 400
    except Exception:
        return url, False


def cmd_check(args):
    """Cross-reference articles against whitelist, then optionally HTTP check."""
    yaml_path = Path(args.input)
    whitelist_path = Path(WHITELIST_FILE)
    if not yaml_path.exists():
        print(f"File not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    whitelist = {}
    if whitelist_path.exists():
        whitelist = json.loads(whitelist_path.read_text(encoding="utf-8"))

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    if not articles:
        print("No articles to validate.")
        return

    total_wl = sum(len(v) for v in whitelist.values())
    print(f"Validating {len(articles)} articles (whitelist: {total_wl} URLs across {len(whitelist)} sources)\n")

    good = []
    bad = []

    for a in articles:
        url = a.get("url", "").strip()
        source = a.get("source", "")

        # Phase 1: Must match the source's whitelist exactly
        source_wl = whitelist.get(source, {}) if whitelist else {}
        if whitelist and url not in source_wl:
            bad.append((a, f"not in whitelist for source '{source}' (fabricated or modified URL)"))
            continue

        # Phase 2: Syntactic check
        if not is_syntactic(url):
            bad.append((a, "invalid URL format"))
            continue

        good.append(a)

    # Phase 3: HTTP check
    if args.check_http and good:
        print(f"HTTP checking {len(good)} URLs...\n")
        urls = [a["url"] for a in good]
        results = {}
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futures = {ex.submit(check_http, u, args.timeout): u for u in urls}
            for f in as_completed(futures):
                u, ok = f.result()
                results[u] = ok

        still_good = []
        for a in good:
            if results.get(a["url"], False):
                still_good.append(a)
            else:
                bad.append((a, "HTTP unreachable"))
        good = still_good

    # Report
    for a, reason in bad:
        print(f"  REMOVED [{a.get('source', '?')}] {a.get('title', '?')[:50]}")
        print(f"    URL: {a.get('url', 'N/A')[:80]}")
        print(f"    Reason: {reason}\n")

    if good:
        data["articles"] = good
        yaml_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    print(f"Result: {len(good)} kept, {len(bad)} removed ({len(articles)} total)")

    if bad:
        bad_path = yaml_path.parent / "removed_articles.json"
        bad_path.write_text(
            json.dumps([{"reason": r, "source": a.get("source", "?"), "title": a.get("title", ""), "url": a.get("url", "")}
                        for a, r in bad], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Update pipeline_stats.json to reflect filtered article count
    stats_path = yaml_path.parent / "pipeline_stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        sources = sorted(set(a.get("source", "?") for a in good))
        categories = sorted(set(a.get("category", "Other") for a in good))
        removed_sources = sorted(set(a.get("source", "?") for a, _ in bad))
        stats["articles_found"] = len(good)
        stats["articles_added"] = len(good)
        stats["sources_queried"] = len(sources)
        stats["categories"] = categories
        stats["removed_sources"] = removed_sources
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="URL validation for Jarvis pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    lock = sub.add_parser("lock", help="Extract URL whitelist from tmp files")
    lock.add_argument("dir", help="Path to data/tmp/")
    lock.set_defaults(func=cmd_lock)

    check = sub.add_parser("check", help="Cross-reference YAML articles against whitelist")
    check.add_argument("input", help="Path to data/input.yaml")
    check.add_argument("--check-http", action="store_true")
    check.add_argument("--parallel", type=int, default=10)
    check.add_argument("--timeout", type=int, default=8)
    check.set_defaults(func=cmd_check)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
