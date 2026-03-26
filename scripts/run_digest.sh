#!/usr/bin/env bash
set -eo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"
LOG_FILE="$REPO_DIR/logs/digest.log"
ENV_FILE="$REPO_DIR/.env"
PENDING_FILE="$REPO_DIR/data/pending.yaml"
DATE="$(date '+%Y-%m-%d')"
POST_FILE="$REPO_DIR/docs/_posts/${DATE}-daily-digest.md"

mkdir -p "$REPO_DIR/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

send_error() {
  python3 "$REPO_DIR/scripts/send_email.py" error \
    --message "$1" \
    --log-file "$LOG_FILE" 2>&1 | tee -a "$LOG_FILE" || true
}

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE" || true
  set +a
fi

log "Step 0: Syncing git repository..."
git -C "$REPO_DIR" pull --rebase 2>&1 | tee -a "$LOG_FILE"

log "Step 1: Fetching RSS feeds..."
if ! python3 "$REPO_DIR/scripts/fetch_rss.py" 2>&1 | tee -a "$LOG_FILE"; then
  send_error "fetch_rss.py 执行失败"
  exit 1
fi

ARTICLE_COUNT=$(python3 -c "
import yaml, sys
try:
    d = yaml.safe_load(open('$PENDING_FILE'))
    print(len(d) if isinstance(d, list) else 0)
except Exception:
    print(0)
")

if [ "$ARTICLE_COUNT" -eq 0 ]; then
  log "No new articles, skipping AI step."
  exit 0
fi

log "Step 2: Running AI summarization via flickcli ($ARTICLE_COUNT articles)..."
cd "$REPO_DIR"
if ! flickcli -m claude-4.6-sonnet -q --approval-mode yolo "生成今天的日报" 2>&1 | tee -a "$LOG_FILE"; then
  send_error "AI 摘要生成失败"
  exit 1
fi

log "Step 3: Committing and pushing..."
git -C "$REPO_DIR" add docs/_posts/ data/seen.yaml data/pending.yaml

if git -C "$REPO_DIR" diff --cached --quiet; then
  log "No changes to commit."
  exit 0
fi

git -C "$REPO_DIR" commit -m "Daily digest $DATE"
if ! git -C "$REPO_DIR" push; then
  send_error "git push 失败"
  exit 1
fi

log "Step 4: Sending email notification..."
python3 "$REPO_DIR/scripts/send_email.py" digest \
  --date "$DATE" \
  --post "$POST_FILE" 2>&1 | tee -a "$LOG_FILE"

log "Done."
