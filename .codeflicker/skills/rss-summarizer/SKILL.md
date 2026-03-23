---
name: RSS Daily Digest
description: 读取 data/pending.yaml 中的原始 RSS 文章列表，对每篇文章生成中文摘要、标签和分类，然后将所有内容汇总并写入 data/temp/digest_batch.json，最后调用 Python 脚本生成 Jekyll Chirpy 日报 Markdown 文件（docs/_posts/YYYY-MM-DD-daily-digest.md）。当用户说"生成今天的日报"或"处理待总结文章"时使用此 Skill。
---

# RSS Daily Digest Skill

## 触发条件
用户说"生成今天的日报"、"处理 pending 文章"、"生成日报"时自动激活。

## 工作流程

### 第一步：读取待处理文章
读取文件 `data/pending.yaml`，内容为文章列表，每项结构：
```yaml
- id: md5hash
  title: 文章标题
  url: 原文链接
  source: RSS源名称
  category: 预设分类
  raw_summary: RSS原始摘要内容
```
若文件为空列表或不存在，输出提示后结束，不创建任何文件。

### 第二步：逐篇处理
对每篇文章，**仅基于 `title` 和 `raw_summary` 字段**，不抓取原文：

1. **评估可读性星级**：综合以下维度，给出 1-5 星评分：
   - **重要性**：是否涉及重大事件、突破性进展、影响广泛的决策
   - **信息密度**：内容是否有实质性信息，而非标题党或广告
   - **独特性**：是否提供新视角或独家内容，而非重复报道
   - **时效性**：是否是近期值得关注的新鲜内容

   评分标准：
   - ⭐⭐⭐⭐⭐ 必读，极具价值，重大事件或深度洞见
   - ⭐⭐⭐⭐ 值得一读，有实质内容
   - ⭐⭐⭐ 一般，信息有限但有参考价值
   - ⭐⭐ 较弱，内容平淡或重复
   - ⭐ 不推荐，标题党/广告/无实质内容

3. **翻译成中文标题**：如果标题是英文，翻译成中文；如果已经是中文，保持不变。

4. **生成中文摘要**：2-3句话，简明概括核心观点，用中文。

5. **打标签**：3-5个中文标签，内容不限于技术，可以是政治、经济、科学、文化、体育、社会等任何领域。

6. **判断分类**：根据文章实际内容自由判断，例如：
   - `Tech` / `AI` / `商业` / `国际` / `社会` / `科学` / `文化` / `体育` / `政治` / `经济` / `环境` / `健康` / `Other`

### 第三步：将处理结果写入 digest_batch.yaml
将所有文章的处理结果（**不是直接写 Markdown**）汇总写入 `data/temp/digest_batch.yaml`，格式如下：

```yaml
date: "YYYY-MM-DD"
articles:
  - id: 从pending.yaml中原样保留
    title: 文章中文标题
    url: 原文链接
    source: RSS源名称
    category: Tech
    rating: 4
    tags:
      - 标签1
      - 标签2
      - 标签3
    summary: |-
      2-3句中文摘要，可以换行，
      不需要任何转义。
```

- `date` 为当天日期，格式 `YYYY-MM-DD`
- `id` 必须原样保留（来自 pending.yaml），不要修改
- `rating` 为整数 1-5，对应上述星级评分
- `category` 使用你在第二步判断的分类
- `tags` 为列表，3-5个标签
- `summary` 使用 YAML 块标量（`|-`），直接书写多行文本，**无需转义任何字符**

### 第四步：调用 Python 脚本生成 Markdown
使用 bash 工具执行以下命令：
```bash
python3 scripts/generate_post.py --input data/temp/digest_batch.yaml
```

**重要**：
- 必须等待脚本执行成功（输出包含 `SUCCESS:`）后再继续
- 如果脚本报错（输出包含 `ERROR:`），停止流程并报告错误，**不清空 pending**

### 第五步：清空 pending
**确认第四步脚本执行成功后**，将 `data/pending.yaml` 内容清空为 `[]\n`。
若第四步失败，保留 pending 数据以便重试。

## 注意事项
- **AI 不直接写 Markdown 文件**，所有 Markdown 格式化由 `scripts/generate_post.py` 负责
- `digest_batch.yaml` 只是中间临时文件，不需要手动维护
- `generate_post.py` 脚本具备幂等性：同一篇文章（相同 id）多次运行不会重复写入
- 支持一天多次生成：新文章会增量追加到当天已有日报中
- `date` 字段格式必须为 `YYYY-MM-DD`
