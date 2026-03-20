#!/usr/bin/env python3
import argparse
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / '.env'


def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


def get_smtp_config():
    host = os.environ.get('SMTP_HOST', 'smtp.qq.com')
    port = int(os.environ.get('SMTP_PORT', '465'))
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASS', '')
    from_name = os.environ.get('SMTP_FROM', '全球日报')
    to = os.environ.get('SMTP_TO', '')
    if not user or not password or not to:
        print('ERROR: SMTP_USER, SMTP_PASS, SMTP_TO must be set in .env', file=sys.stderr)
        sys.exit(1)
    return {
        'host': host,
        'port': port,
        'user': user,
        'password': password,
        'from_name': from_name,
        'to': [addr.strip() for addr in to.split(',')],
    }


def send_email(cfg: dict, subject: str, body: str, html: bool = False):
    msg = MIMEMultipart('alternative')
    msg['From'] = f'{cfg["from_name"]} <{cfg["user"]}>'
    msg['To'] = ', '.join(cfg['to'])
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html' if html else 'plain', 'utf-8'))

    port = cfg['port']
    if port == 465:
        server = smtplib.SMTP_SSL(cfg['host'], port, timeout=30)
    else:
        server = smtplib.SMTP(cfg['host'], port, timeout=30)
        server.starttls()

    try:
        server.login(cfg['user'], cfg['password'])
        server.sendmail(cfg['user'], cfg['to'], msg.as_string())
    finally:
        server.quit()


def build_digest_email(date: str, post_path: str) -> tuple[str, str]:
    subject = f'全球日报 {date} 已生成'
    path = Path(post_path)
    article_count = 0
    categories = []
    if path.exists():
        content = path.read_text(encoding='utf-8')
        import re
        article_count = len(re.findall(r'<!-- article-id:', content))
        categories = re.findall(r'^## (.+)$', content, re.MULTILINE)

    url = f'https://hhhhao-s.github.io/Jarvis/posts/{date}-daily-digest/'
    body = f'''<h2>全球日报 {date} 已生成</h2>
<p><b>文章数量</b>: {article_count} 篇</p>
<p><b>涵盖分类</b>: {', '.join(categories) if categories else '无'}</p>
<p><b>在线阅读</b>: <a href="{url}">{url}</a></p>
<p><b>生成时间</b>: {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")}</p>
'''
    return subject, body


def build_error_email(error_msg: str, log_tail: str = '') -> tuple[str, str]:
    tz8 = timezone(timedelta(hours=8))
    now = datetime.now(tz8).strftime('%Y-%m-%d %H:%M:%S')
    subject = f'日报生成异常通知 {now}'
    body = f'''<h2 style="color:red;">日报生成出现异常</h2>
<p><b>时间</b>: {now}</p>
<p><b>异常信息</b>:</p>
<pre style="background:#f4f4f4;padding:12px;border-radius:4px;">{error_msg}</pre>
'''
    if log_tail:
        body += f'''<p><b>最近日志</b>:</p>
<pre style="background:#f4f4f4;padding:12px;border-radius:4px;">{log_tail}</pre>
'''
    return subject, body


def parse_args():
    p = argparse.ArgumentParser(description='Send email notification')
    sub = p.add_subparsers(dest='command', required=True)

    d = sub.add_parser('digest', help='Send digest success notification')
    d.add_argument('--date', required=True, help='Digest date YYYY-MM-DD')
    d.add_argument('--post', required=True, help='Path to generated markdown file')

    e = sub.add_parser('error', help='Send error notification')
    e.add_argument('--message', '-m', required=True, help='Error message')
    e.add_argument('--log-file', help='Log file to include tail')
    e.add_argument('--log-lines', type=int, default=50, help='Number of log lines to include')

    return p.parse_args()


def main():
    load_env()
    args = parse_args()
    cfg = get_smtp_config()

    if args.command == 'digest':
        subject, body = build_digest_email(args.date, args.post)
    elif args.command == 'error':
        log_tail = ''
        if args.log_file:
            lp = Path(args.log_file)
            if lp.exists():
                lines = lp.read_text(encoding='utf-8', errors='replace').splitlines()
                log_tail = '\n'.join(lines[-args.log_lines:])
        subject, body = build_error_email(args.message, log_tail)
    else:
        print(f'Unknown command: {args.command}', file=sys.stderr)
        sys.exit(1)

    try:
        send_email(cfg, subject, body, html=True)
        print(f'SUCCESS: Email sent to {", ".join(cfg["to"])}')
    except Exception as e:
        print(f'ERROR: Failed to send email: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
