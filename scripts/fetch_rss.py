#!/usr/bin/env python3
# 负责从 RSS 源拉取文章，去重后写入 data/pending.yaml，供后续 AI 总结使用

import yaml
import feedparser
import httpx
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 项目根目录下的配置和数据文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SEEN_PATH = Path(__file__).parent.parent / "data" / "seen.yaml"       # 已处理文章的 ID 记录，用于去重
PENDING_PATH = Path(__file__).parent.parent / "data" / "pending.yaml" # 本次待 AI 处理的新文章


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN_PATH.exists():
        with open(SEEN_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return set(data) if isinstance(data, list) else set()
    return set()


def save_seen(seen: set):
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        yaml.dump(sorted(seen), f, allow_unicode=True, default_flow_style=False)


def load_pending() -> list[dict]:
    if PENDING_PATH.exists():
        with open(PENDING_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, list) else []
    return []


def save_pending(articles: list[dict]):
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        yaml.dump(articles, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def article_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def fetch_rss(feed_cfg: dict, timeout: int, ua: str, max_age_days: int) -> list[dict]:
    headers = {"User-Agent": ua}
    try:
        resp = httpx.get(feed_cfg["url"], headers=headers, timeout=timeout, follow_redirects=True)
        parsed = feedparser.parse(resp.text)
    except Exception as e:
        log(f"  [ERROR] 抓取失败 {feed_cfg['name']}: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    total = len(parsed.entries)
    skipped_age = 0
    articles = []

    for entry in parsed.entries:
        url = entry.get("link", "")
        if not url:
            continue

        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                skipped_age += 1
                continue

        title = entry.get("title", "").strip()
        raw_summary = entry.get("summary", entry.get("description", "")).strip()
        articles.append({
            "id": article_id(url),
            "title": title,
            "url": url,
            "source": feed_cfg["name"],
            "category": feed_cfg["category"],
            "raw_summary": raw_summary[:3000],
        })

    log(f"  RSS 共 {total} 条，过期跳过 {skipped_age} 条，剩余 {len(articles)} 条")
    return articles


def main():
    start = datetime.now()
    log("=" * 50)
    log("开始抓取 RSS 文章")

    cfg = load_config()
    seen = load_seen()
    timeout = cfg["fetch"]["timeout"]
    ua = cfg["fetch"]["user_agent"]
    max_age_days = cfg["fetch"]["max_age_days"]

    log(f"已处理文章数 (seen): {len(seen)}")

    existing_pending = load_pending()
    existing_pending_ids = {a["id"] for a in existing_pending}
    log(f"当前 pending 中待处理文章数: {len(existing_pending)}")
    log(f"抓取时间范围: 最近 {max_age_days} 天")
    log("-" * 50)

    new_articles = []
    for feed_cfg in cfg["rss_feeds"]:
        log(f"[{feed_cfg['name']}] 开始抓取 {feed_cfg['url']}")
        articles = fetch_rss(feed_cfg, timeout, ua, max_age_days)

        limit = feed_cfg.get("max_articles", 10)
        added = 0
        skipped_seen = 0
        skipped_pending = 0

        for a in articles:
            if added >= limit:
                break
            if a["id"] in seen:
                skipped_seen += 1
                continue
            if a["id"] in existing_pending_ids:
                skipped_pending += 1
                continue
            new_articles.append(a)
            added += 1
            log(f"    + {a['title'][:60]}")

        log(f"  新增 {added} 篇 | 已处理跳过 {skipped_seen} 篇 | 已在pending跳过 {skipped_pending} 篇 | 上限 {limit}")

    log("-" * 50)

    if not new_articles:
        log("没有新文章，结束。")
        log(f"耗时 {(datetime.now() - start).seconds} 秒")
        log("=" * 50)
        return

    merged = existing_pending + new_articles
    save_pending(merged)
    log(f"新增 {len(new_articles)} 篇文章写入 pending，pending 总计 {len(merged)} 篇")

    new_ids = [a["id"] for a in new_articles]
    seen.update(new_ids)
    save_seen(seen)
    log(f"seen.yaml 已更新，共记录 {len(seen)} 篇")
    log(f"耗时 {(datetime.now() - start).seconds} 秒")
    log("=" * 50)


if __name__ == "__main__":
    main()
