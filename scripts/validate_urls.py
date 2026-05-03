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

    whitelist = {}  # url -> {source, title}
    total_cleaned = 0

    for md_file in sorted(tmp_dir.glob("*.md")):
        source_id = md_file.stem
        content = md_file.read_text(encoding="utf-8")
        lines = content.split("\n")
        cleaned = []
        removed = 0

        for line in lines:
            m = URL_PATTERN.search(line)
            if m:
                title, url = m.group(1), m.group(2)
                if is_syntactic(url):
                    whitelist[url] = {"source": source_id, "title": title}
                    cleaned.append(line)
                else:
                    removed += 1
            else:
                cleaned.append(line)

        if removed > 0:
            md_file.write_text("\n".join(cleaned), encoding="utf-8")
            print(f"  [{md_file.name}] cleaned {removed} bad URLs")

        total_cleaned += removed

    whitelist_path = Path(args.dir).parent / "url_whitelist.json"
    whitelist_path.write_text(json.dumps(whitelist, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWhitelist: {len(whitelist)} URLs from {len(list(tmp_dir.glob('*.md')))} files → {whitelist_path}")
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

    print(f"Validating {len(articles)} articles (whitelist: {len(whitelist)} URLs)\n")

    good = []
    bad = []

    for a in articles:
        url = a.get("url", "").strip()

        # Phase 1: Must match whitelist exactly
        if whitelist and url not in whitelist:
            bad.append((a, "not in whitelist (sub-agent fabricated or modified URL)"))
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
            json.dumps([{"reason": r, "title": a.get("title", ""), "url": a.get("url", "")}
                        for a, r in bad], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


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
