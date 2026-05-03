# Jarvis — 全球日报 自进化系统

## 项目概述

Jarvis 是一个自动化的全球日报生成系统。它每天从多个信息源获取新闻，利用 AI 进行摘要和分类，生成 Jekyll 格式的日报文章，并自动发布到 GitHub Pages。

核心特性：
- **每日自动运行**：通过 crontab 定时触发
- **自进化**：周期性分析过去表现，优化信息源权重和提示词
- **全状态持久化**：每次调用都是无状态的，所有上下文保存在磁盘上
- **邮件通知**：通过 QQ 邮箱 SMTP 发送成功/失败/自定义通知

在线地址：https://hhhhao-s.github.io/Jarvis

## 目录结构

```
Jarvis/
├── data/                    # 持久化状态（每次运行必须读写）
│   ├── state.json           # 管道状态、进化历史、学习记录
│   └── sources.json         # 信息源配置及性能数据
├── scripts/                 # Python 脚本
│   ├── generate_post.py     # 从 YAML 生成 Jekyll 日报文章
│   ├── send_email.py        # 发送邮件通知 (digest/error/notify)
│   ├── schedule_cron.py     # 管理 crontab 定时任务
│   └── state_manager.py     # 状态读写模块
├── docs/                    # Jekyll 站点根目录
│   ├── _posts/              # 日报文章 (*.md)
│   └── _config.yml          # 站点配置
├── .claude/                 # Claude Code 配置
│   ├── commands/            # 自定义斜杠命令
│   │   ├── pipeline.md      # 每日日报生成流程
│   │   ├── evolve.md        # 自进化流程
│   │   ├── generate-post.md # 生成文章命令
│   │   ├── schedule-cron.md # 定时任务管理
│   │   └── send-email.md    # 发送邮件命令
│   └── settings.local.json  # 本地权限配置
├── .github/workflows/deploy.yml  # GitHub Actions 自动部署
└── pyproject.toml           # Python 项目配置
```

## 核心流程

### 每日管道 (pipeline)
1. 读取 `data/state.json` 和 `data/sources.json`
2. 对每个活跃信息源，使用 WebSearch 搜索最新新闻
3. 筛选高质量文章，AI 生成中文摘要，分配分类和标签
4. 生成 YAML 并通过 `generate_post.py` 写入 `docs/_posts/`
5. 发送成功/失败邮件通知
6. Git commit & push（触发 GitHub Pages 部署）
7. 更新 `data/state.json` 记录本次运行

### 自进化 (evolve)
1. 读取最近 7-14 天的日报文章
2. 分析各信息源的贡献度、文章质量、用户反馈
3. 识别改进空间：分类偏斜、信息源枯竭、摘要质量问题
4. 调整信息源权重
5. 记录进化洞察到 `data/state.json`
6. 发送进化摘要邮件

## 关键约定

### 无状态设计
每一次 Claude 调用都是全新的，不包含之前的对话上下文。因此：
- 所有必要的上下文必须从磁盘文件读取
- 所有运行结果必须写回磁盘
- 操作完成后必须 git push 确保状态同步

### 文章 ID 生成
使用 URL + 标题的 MD5 前 8 位作为文章 ID，确保去重

### 分类体系
AI, Tech, 商业, 科学, 国际, 文化, 环境, 社会, 健康, 政治, 经济, 体育, Other

### 邮件配置
SMTP 配置在 `.env` 文件中（已 gitignore）：
- SMTP_HOST=smtp.qq.com
- SMTP_PORT=465
- SMTP_USER/PASS/FROM/TO

## 定时运行

使用 `scripts/schedule_cron.py` 管理 crontab：
```bash
# 添加每日管道（每天 08:07 运行）
uv run python scripts/schedule_cron.py add \
  --schedule "7 8 * * *" \
  --command 'claude -p "/pipeline"' \
  --label "daily-digest"

# 添加每周自进化（每周日 09:13 运行）
uv run python scripts/schedule_cron.py add \
  --schedule "13 9 * * 0" \
  --command 'claude -p "/evolve"' \
  --label "weekly-evolve"
```
