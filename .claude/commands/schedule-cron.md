# Schedule Cron

Manage crontab entries for Jarvis scheduled tasks using `scripts/schedule_cron.py`.

## Usage

### Add a daily task

Schedule a command to run daily at a specific time:

```
uv run python scripts/schedule_cron.py add --command "<command>" [--schedule "<cron expr>"] [--label "<name>"]
```

**Defaults:** `--schedule` defaults to `0 9 * * *` (daily at 9am), `--label` auto-generates if omitted.

#### Common examples

Schedule daily digest generation + email at 8am:

```
uv run python scripts/schedule_cron.py add \
  --schedule "0 8 * * *" \
  --command "uv run python scripts/generate_post.py --input docs/input.yaml && uv run python scripts/send_email.py digest --date \$(date +\%Y-\%m-\%d)" \
  --label "daily-digest"
```

Schedule a simple task at 10pm daily:

```
uv run python scripts/schedule_cron.py add \
  --schedule "0 22 * * *" \
  --command "echo 'Hello from Jarvis'" \
  --label "nightly-hello"
```

Schedule every 30 minutes:

```
uv run python scripts/schedule_cron.py add \
  --schedule "*/30 * * * *" \
  --command "uv run python main.py" \
  --label "frequent-check"
```

### List all Jarvis tasks

```
uv run python scripts/schedule_cron.py list
```

### Remove a task

```
uv run python scripts/schedule_cron.py remove <label>
```

### Show raw crontab

```
uv run python scripts/schedule_cron.py show
```

## Cron Syntax Quick Reference

| Expression | Meaning |
|-----------|---------|
| `0 9 * * *` | Every day at 9:00 AM |
| `0 8 * * 1-5` | Weekdays at 8:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 */2 * * *` | Every 2 hours |
| `30 8 1 * *` | 1st of each month at 8:30 AM |

Format: `minute hour day-of-month month day-of-week`

## Notes

- Each task is tagged with a `# jarvis-scheduled:<label>` comment in crontab for identification.
- The command always runs from the project root directory.
- Use `crontab -e` to edit manually if needed, but keep the marker comments intact for `list`/`remove` to work.
- Schedule expressions use your machine's local timezone.
