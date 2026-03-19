#!/usr/bin/env python3
# 负责从 RSS 源拉取文章，去重后写入 data/pending.json，供后续 AI 总结使用

import json
import yaml
import feedparser
import httpx
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 项目根目录下的配置和数据文件路径
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
SEEN_PATH = Path(__file__).parent.parent / "data" / "seen.json"       # 已处理文章的 ID 记录，用于去重
PENDING_PATH = Path(__file__).parent.parent / "data" / "pending.json" # 本次待 AI 处理的新文章


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_config():
    # 加载 config.yaml，包含 RSS 源列表和抓取参数
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_seen():
    # 加载已处理文章 ID 集合；首次运行时文件不存在，返回空集合
    if SEEN_PATH.exists():
        with open(SEEN_PATH) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    # 将更新后的已处理 ID 集合持久化到磁盘
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_PATH, "w") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)


def load_pending() -> list[dict]:
    # 加载当前 pending.json 中尚未被 AI 处理的文章
    if PENDING_PATH.exists():
        with open(PENDING_PATH) as f:
            return json.load(f)
    return []


def article_id(url: str) -> str:
    # 用 URL 的 MD5 作为文章唯一 ID，避免重复处理同一篇文章
    return hashlib.md5(url.encode()).hexdigest()


def fetch_rss(feed_cfg: dict, timeout: int, ua: str, max_age_days: int) -> list[dict]:
    # 抓取单个 RSS 源，返回文章列表
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

        # 过滤太久远的文章：优先用 published_parsed，fallback 到 updated_parsed
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                skipped_age += 1
                continue  # 超过 max_age_days，跳过

        title = entry.get("title", "").strip()
        # 优先取 summary 字段，fallback 到 description；截断至 3000 字符避免 AI 输入过长
        raw_summary = entry.get("summary", entry.get("description", "")).strip()
        articles.append({
            "id": article_id(url),
            "title": title,
            "url": url,
            "source": feed_cfg["name"],
            "category": feed_cfg["category"],  # config.yaml 中预设的分类，AI 可覆盖
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
    max_age_days = cfg["fetch"]["max_age_days"]  # 只抓取该天数内发布的文章

    log(f"已处理文章数 (seen): {len(seen)}")

    # 读取已有 pending，合并时用于去重，避免覆盖上次未处理的文章
    existing_pending = load_pending()
    existing_pending_ids = {a["id"] for a in existing_pending}
    log(f"当前 pending 中待处理文章数: {len(existing_pending)}")
    log(f"抓取时间范围: 最近 {max_age_days} 天")
    log("-" * 50)

    new_articles = []
    for feed_cfg in cfg["rss_feeds"]:
        log(f"[{feed_cfg['name']}] 开始抓取 {feed_cfg['url']}")
        articles = fetch_rss(feed_cfg, timeout, ua, max_age_days)

        # 每个源独立限制数量，取 config 中该源的 max_articles 配置
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

    # 将新文章追加到已有 pending 中，而不是覆盖
    merged = existing_pending + new_articles
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2))
    log(f"新增 {len(new_articles)} 篇文章写入 pending，pending 总计 {len(merged)} 篇")

    # 立即更新 seen.json，防止重复抓取（即使 AI 步骤失败也不会重复处理）
    new_ids = [a["id"] for a in new_articles]
    seen.update(new_ids)
    save_seen(seen)
    log(f"seen.json 已更新，共记录 {len(seen)} 篇")
    log(f"耗时 {(datetime.now() - start).seconds} 秒")
    log("=" * 50)


if __name__ == "__main__":
    main()
