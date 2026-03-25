---
name: email-notifier
description: 通过 QQ 邮箱 SMTP 发送邮件通知。支持两种场景：日报生成成功后发送摘要通知，以及流程出错时发送错误日志。当用户说"发送日报通知邮件"或"发送错误通知"时使用此 Skill。
---

# Email Notifier Skill

## 触发条件
- 日报生成成功后，用户说"发邮件通知"、"发送日报邮件"
- 流程出错时，用户说"发送错误通知"、"发错误邮件"

## 前提条件
项目根目录 `.env` 文件中需配置以下变量：
```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的QQ邮箱@qq.com
SMTP_PASS=QQ邮箱授权码
SMTP_FROM=全球日报
SMTP_TO=收件人邮箱（多个用逗号分隔）
```

## 使用方式

### 场景一：日报成功通知
日报生成成功后，使用 bash 工具执行：
```bash
python3 scripts/send_email.py digest --date YYYY-MM-DD --post docs/_posts/YYYY-MM-DD-daily-digest.md
```
- `--date`：日报日期
- `--post`：生成的 markdown 文件路径

脚本会自动统计文章数量和分类，发送 HTML 格式的摘要邮件。

### 场景二：错误通知
流程出错时，使用 bash 工具执行：
```bash
python3 scripts/send_email.py error --message "错误描述" --log-file logs/digest.log --log-lines 50
```
- `--message`：错误描述信息（必填）
- `--log-file`：日志文件路径（可选，会附带最后 N 行日志）
- `--log-lines`：包含的日志行数，默认 50

## 判断结果
- 输出包含 `SUCCESS:` 表示发送成功
- 输出包含 `ERROR:` 表示发送失败
