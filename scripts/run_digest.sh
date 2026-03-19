#!/usr/bin/env bash
set -eo pipefail

# 脚本在 scripts/ 下，REPO_DIR 需要上一级才是项目根目录
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$REPO_DIR/logs/digest.log"
ENV_FILE="$REPO_DIR/.env"
PENDING_FILE="$REPO_DIR/data/pending.json"

mkdir -p "$REPO_DIR/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# 加载 .env，用子 shell 避免 set -u 对未定义变量报错
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE" || true
  set +a
fi

log "Step 1: Fetching RSS feeds..."
python3 "$REPO_DIR/scripts/fetch_rss.py" 2>&1 | tee -a "$LOG_FILE"

# 安全读取 pending 数量，文件不存在或为空时返回 0
ARTICLE_COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PENDING_FILE'))
    print(len(d))
except Exception:
    print(0)
")

if [ "$ARTICLE_COUNT" -eq 0 ]; then
  log "No new articles, skipping AI step."
  exit 0
fi

log "Step 2: Running AI summarization via flickcli ($ARTICLE_COUNT articles)..."
cd "$REPO_DIR"
flickcli -q --approval-mode yolo "生成今天的日报" 2>&1 | tee -a "$LOG_FILE"

log "Step 3: Committing and pushing..."
git -C "$REPO_DIR" add docs/_posts/ data/seen.json

# 用 git status 检测是否有变更（含新增文件），无变更则跳过
if git -C "$REPO_DIR" diff --cached --quiet; then
  log "No changes to commit."
  exit 0
fi

git -C "$REPO_DIR" commit -m "Daily digest $(date '+%Y-%m-%d')"
git -C "$REPO_DIR" push

log "Done."
