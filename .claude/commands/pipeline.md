# 每日全球日报生成管道

执行完整的日报生成流程：获取信息 → 生成摘要 → 写文章 → 发邮件 → 推送。

## 执行步骤

### 第一步：读取状态和信息源
用 Read 工具读取以下文件：
- `data/state.json` — 管道运行历史、学习记录
- `data/sources.json` — 信息源列表及权重

### 第二步：收集新闻
对每个 `active: true` 的信息源，按其 `search_queries` 使用 WebSearch 搜索最新新闻。
按权重从高到低依次处理，每个源选取 3-8 篇最相关的文章。

搜索策略：
- 优先搜索当日或昨日的新闻
- 同一信息源的多个搜索词横向覆盖不同角度
- 遇到付费墙或无法访问的内容，跳过该文章
- 每个源最多搜索 3 个查询词

### 第三步：筛选和处理文章
对收集到的文章进行质量筛选：
- 去重：相同 URL 或高度相似的标题只保留一篇
- 时效性：优先当日的新闻，最多回溯 3 天
- 多样性：确保覆盖至少 5 个不同分类
- 质量标准：选择有实质内容的文章，跳过纯广告、点击诱饵

为每篇文章生成：
- **id**：取 URL 的 MD5 前 8 位（使用 `echo -n "URL" | md5sum | cut -c1-8` 或 Python `hashlib.md5(url.encode()).hexdigest()[:8]`）
- **title**：中文翻译标题（原文标题保留在 summary 中引用）
- **summary**：80-150 字的中文摘要，客观准确，提取核心事实
- **category**：从分类体系中选择（AI, Tech, 商业, 科学, 国际, 文化, 环境, 社会, 健康, 政治, 经济, 体育）
- **tags**：3-6 个相关标签
- **rating**：1-5 星评分（重要性/趣味性）
- **source**：信息源名称

### 第四步：生成 YAML 并写文章
将处理好的文章组装成 YAML 格式，格式如下：

```yaml
date: "YYYY-MM-DD"
articles:
  - id: "a1b2c3d4"
    title: "文章中文标题"
    url: "https://example.com/article"
    source: "TechCrunch"
    summary: "文章的中文摘要，80-150字左右..."
    tags: ["AI", "LLM", "开源"]
    category: "AI"
    rating: 4
    processed_at: "YYYY-MM-DDTHH:MM:SS+08:00"
```

将 YAML 写入临时文件 `data/input.yaml`，然后调用：
```bash
uv run python scripts/generate_post.py --input data/input.yaml
```

注意：
- 如果 generate_post.py 报错，检查 YAML 格式是否正确
- 如果所有文章都已存在（去重），脚本会正常退出

### 第五步：发送邮件通知
根据 generate_post.py 的输出确定文章数量，然后：

成功时：
```bash
uv run python scripts/send_email.py digest --date YYYY-MM-DD --post docs/_posts/YYYY-MM-DD-daily-digest.md
```

失败时：
```bash
uv run python scripts/send_email.py error --message "具体错误信息"
```

### 第六步：更新状态并推送
更新 `data/state.json` 中的管道运行记录（使用 state_manager.py 的函数或直接编辑 JSON）：
- pipeline.last_run, pipeline.last_success
- pipeline.total_runs, pipeline.total_successes
- pipeline.run_history 追加本次运行记录
- digests 统计更新

然后提交并推送：
```bash
git add docs/_posts/ data/ && git commit -m "Daily digest YYYY-MM-DD" && git push
```

注意：commit message 使用英文格式 "Daily digest YYYY-MM-DD"

### 第七步：输出摘要
最后输出本次运行的摘要报告，包括：
- 处理的信息源数量
- 收集的文章总数和新增数
- 覆盖的分类
- 网页链接

## 异常处理
- 如果网络搜索无结果，跳过该信息源并在摘要中注明
- 如果所有信息源均无结果，发送 error 邮件并退出
- 如果 generate_post.py 失败，记录错误并发送 error 邮件
- 如果 git push 失败（网络问题），记录但不影响管道状态
- 任何未预期的异常都要发送 error 邮件通知
