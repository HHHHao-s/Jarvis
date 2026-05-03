# 每日全球日报生成管道

流程：主 agent 编排 → sub-agent 搜+写 → 脚本链 lock/merge/check/generate → 邮件 → 推送。

核心原则：**主 agent 不接触任何搜索结果**。搜索和总结全在 sub-agent 里完成。

## 1. 读取信息源

Read `data/sources.json`。

## 2. 准备目录

```bash
mkdir -p data/tmp
```

## 3. 并行启动 Sub-agent

为每个 `active: true` 的信息源启动一个 Agent（general-purpose），**同一轮消息中全部并行发出**，不加 `run_in_background`。

Agent prompt（每个 agent 处理一个源）：

```
You are processing source: <source-name> (id: <source-id>)

Step 1 — Search: WebSearch with queries: <search_queries>
Write raw results to data/tmp/<source-id>.md:
  # <source-name> — today
  ## Raw Search Results
  <paste complete search results>

Step 2 — Curate: Select 3-5 most substantive articles from the results. Ensure category diversity (AI, Tech, 商业, 科学, 国际, 文化, 环境, 社会, 健康, 政治, 经济, 体育).

Step 3 — Write YAML to data/tmp/batch-<source-id>.yaml:
  articles:
    - id: MD5 first 8 of URL
      title: Chinese title (10-25 chars)
      url: copied exactly from search results
      source: <source-name>
      summary: 80-150 Chinese chars
      tags: [3-6 Chinese tags]
      category: one of the standard categories
      rating: 1-5
      processed_at: current ISO time +08:00

Only use Write tool for output files, no code.
```

Agent 失败则重试一次。

## 4. 脚本链

等所有 agent 完成后：

```bash
python scripts/validate_urls.py lock data/tmp/
python scripts/merge_yaml.py
python scripts/validate_urls.py check data/tmp/input.yaml --check-http
```

如果上一步有文章被过滤（`data/tmp/removed_articles.json` 存在且非空），主 agent 执行恢复：

1. Read `data/tmp/removed_articles.json` 和 `data/tmp/url_whitelist.json`
2. 对每篇被移除的文章，在 whitelist[source] 中按标题相似度匹配正确 URL（仅在该源自己的白名单里找）
3. 匹配到的文章，修正 URL 后加回 `data/tmp/input.yaml`
4. 更新 `data/tmp/pipeline_stats.json` 反映恢复后的数量
5. 无法匹配的文章保留移除

```bash
uv run python scripts/generate_post.py --input data/tmp/input.yaml
```

## 5. 邮件通知

成功：
```bash
uv run python scripts/send_email.py digest --date YYYY-MM-DD --post docs/_posts/YYYY-MM-DD-daily-digest.md
```

失败：
```bash
uv run python scripts/send_email.py error --message "错误信息"
```

## 6. 记录状态并推送

```bash
uv run python scripts/pipeline.py record --success --stats-file data/tmp/pipeline_stats.json

git add docs/_posts/ data/ && git commit -m "Daily digest $(date +%Y-%m-%d)" && git push
```

## 7. 输出摘要

报告：信息源数量、文章总数、覆盖分类、https://hhhhao-s.github.io/Jarvis

## 异常处理

| 场景 | 处理 |
|------|------|
| 单个源搜索无结果 | agent 标注 tmp 文件为空，跳过 |
| Agent 失败 | 重试一次，仍失败跳过该源 |
| 所有源均无结果 | 发 error 邮件，退出 |
| generate_post 失败 | 发 error 邮件，不推送 |
| git push 失败 | 记录但不影响管道状态 |
