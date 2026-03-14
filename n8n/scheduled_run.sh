#!/usr/bin/env bash
# Scheduled pipeline run: generate a new episode and publish to Metricool
# Called by cron every 6 hours

set -euo pipefail

REPO_DIR="/Users/eliotchang/Local/Github/Figment/survive.history"
LOG_DIR="$REPO_DIR/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/pipeline_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=========================================="
echo "  Scheduled Pipeline Run: $(date)"
echo "=========================================="

cd "$REPO_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Source .env for API keys (GH_TOKEN, etc.) not available in cron's keyring
if [ -f "$REPO_DIR/.env" ]; then
    set -a
    source <(grep -E '^[A-Z_]+=.' "$REPO_DIR/.env" | sed 's/#.*//')
    set +a
fi

PYTHONUNBUFFERED=1 python3 -u n8n/run_pipeline.py --publish 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "Pipeline succeeded. Committing and pushing episode files..."
    git add -A
    git commit -m "Auto-publish: new episode $(date +%Y-%m-%d_%H:%M)" --allow-empty 2>/dev/null || true
    git push origin main 2>/dev/null || true
    echo "Git push complete."
else
    echo ""
    echo "Pipeline FAILED with exit code $EXIT_CODE"
fi

# Keep only last 20 log files
ls -t "$LOG_DIR"/pipeline_*.log 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true

echo ""
echo "Done at $(date). Log: $LOG_FILE"
