# Send Email

Send email notifications via SMTP using `scripts/send_email.py`.

## Prerequisites

SMTP credentials must be configured in `.env` at the project root:

```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_email@qq.com
SMTP_PASS=your_smtp_password
SMTP_FROM=全球日报
SMTP_TO=recipient@example.com
```

## Usage

### Send digest success notification

```
uv run python scripts/send_email.py digest --date <YYYY-MM-DD> --post <path/to/post.md>
```

Sends a notification that the daily digest has been generated, with article count, categories, and online link.

### Send error notification

```
uv run python scripts/send_email.py error --message "<error message>" [--log-file <path>] [--log-lines <N>]
```

Sends an error notification with the error message and optional log tail.

## Notes

- HTML email format is used by default
- Multiple recipients: comma-separated in `SMTP_TO`
- Port 465 uses SMTP_SSL, other ports use STARTTLS
