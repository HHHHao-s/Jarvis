# 每日全球日报生成管道

执行完整的日报生成流程：获取信息 → 保存到 tmp → sub-agent 分析 → 生成 YAML → 写文章 → 发邮件 → 推送。

关键原则：**搜索结果量巨大，必须落盘后交给 sub-agent 并行处理，不能在主 context 中直接分析。**

## 执行步骤

### 第一步：读取状态和信息源
用 Read 工具读取：
- `data/state.json` — 管道运行历史
- `data/sources.json` — 信息源列表及权重

### 第二步：收集新闻并保存到 tmp
创建 tmp 目录：
```bash
mkdir -p data/tmp
```

对每个 `active: true` 的信息源，按权重从高到低依次使用 WebSearch 搜索。每批搜索 5-6 个源，并行发出。

搜索策略：
- 每个源 1-2 个查询词（不要 3 个，节省 token）
- 优先搜索当日新闻
- 遇到付费墙或无结果则跳过

**关键：每批搜索结果拿到后，立刻将原始内容写入 `data/tmp/<source-id>.md`**，格式：
```markdown
# <Source Name> — <Date>
## Raw Search Results
<粘贴完整搜索结果>
```

### 第三步：并行启动 sub-agent 分析
搜索结果全部保存到 tmp 后，按 3-4 个源一组，分批启动 Agent（subagent_type: general-purpose），每个 agent 负责分析一组文件并输出 YAML。

Agent prompt 模板：
```
Read the following files in data/tmp/: <file-list>
For each source, select the 3-5 most important, substantive news articles.
Curate across categories (AI, Tech, 商业, 科学, 国际, 文化, 环境, 社会, 健康, 政治, 经济, 体育) to ensure diversity.
For each article, produce a YAML entry with:
- id: MD5 hash of URL (first 8 hex chars)
- title: Chinese title
- url: original URL
- source: source name
- summary: 80-150 Chinese character summary
- tags: 3-6 relevant tags
- category: one of the standard categories
- rating: 1-5 stars
- processed_at: current time in ISO format with +08:00

Write the curated YAML to data/tmp/batch-<N>.yaml
Format:
```yaml
articles:
  - id: "..."
    title: "..."
    ...
```

Do NOT write code, just produce the YAML file using Write tool.
```

启动 agent 时使用 `run_in_background: true` 让它们并行运行。

### 第四步：合并 YAML 并生成文章
等所有 agent 完成后，合并所有 batch YAML：
```bash
python -c "
import yaml
from pathlib import Path
from datetime import datetime, timezone, timedelta

tz8 = timezone(timedelta(hours=8))
today = datetime.now(tz8).strftime('%Y-%m-%d')
now = datetime.now(tz8).isoformat(timespec='seconds')

all_articles = []
seen_ids = set()
for f in sorted(Path('data/tmp').glob('batch-*.yaml')):
    data = yaml.safe_load(f.read_text())
    for a in data.get('articles', []):
        aid = a.get('id', '')
        if aid and aid not in seen_ids:
            seen_ids.add(aid)
            a.setdefault('processed_at', now)
            all_articles.append(a)

output = {'date': today, 'articles': all_articles}
Path('data/input.yaml').write_text(yaml.dump(output, allow_unicode=True, default_flow_style=False), encoding='utf-8')
print(f'Merged {len(all_articles)} articles ({len(seen_ids)} after dedup)')
"
```

然后生成文章：
```bash
uv run python scripts/generate_post.py --input data/input.yaml
```

### 第五步：发送邮件通知
成功时：
```bash
uv run python scripts/send_email.py digest --date YYYY-MM-DD --post docs/_posts/YYYY-MM-DD-daily-digest.md
```

失败时：
```bash
uv run python scripts/send_email.py error --message "具体错误信息"
```

### 第六步：更新状态并推送
```bash
uv run python scripts/pipeline.py record \
  --success \
  --date YYYY-MM-DD \
  --sources-queried N \
  --articles-found N \
  --articles-added N \
  --categories "AI,Tech,..."
```

然后提交并推送：
```bash
git add docs/_posts/ data/ && git commit -m "Daily digest YYYY-MM-DD" && git push
```

注意：`data/tmp/` 和 `data/input.yaml` 已在 .gitignore 中，不会被提交。

### 第七步：输出摘要
最后输出本次运行的摘要报告：
- 信息源数量和名称
- 文章总数和新增数
- 覆盖的分类
- 在线地址：https://hhhhao-s.github.io/Jarvis

## 异常处理
- 网络搜索无结果：跳过该源，在 tmp 文件中标注
- 所有源均无结果：发送 error 邮件退出
- generate_post.py 失败：发送 error 邮件，不推送
- git push 失败：记录但不影响管道状态
- sub-agent 失败：重试一次，仍失败则跳过该批次
