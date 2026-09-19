#!/bin/zsh
set -eu

BASE="/Users/crypto-signal-agent/Crypto-Signal"
STATE="$BASE/runtime/continuity"
WORKERS="$STATE/workers"
ACTIVE="$WORKERS/active_task"
ENQUEUE="$BASE/ops/continuity/wake_enqueue.sh"
AGENT="$HOME/.local/bin/agent"
MODEL="${CRYPTO_SIGNAL_COMPOSER_MODEL:-composer-2.5}"

[ "$#" -eq 3 ] || {
  echo "USAGE: supervisor_dispatch.sh task_id prompt_file output_file" >&2
  exit 64
}
TASK_ID="$1"
PROMPT_FILE="$2"
OUTPUT_FILE="$3"

mkdir -p "$WORKERS"
[ -f "$PROMPT_FILE" ] || { echo "PROMPT_MISSING"; exit 2; }
[ ! -e "$ACTIVE" ] || { echo "ACTIVE_TASK_EXISTS"; exit 3; }
[ -x "$AGENT" ] || { echo "CURSOR_AGENT_MISSING"; exit 78; }

STATUS=$("$AGENT" status 2>&1 || true)
echo "$STATUS" | grep -qi 'logged in' || {
  echo "CURSOR_AGENT_NOT_LOGGED_IN"
  exit 78
}
TASK_KEY=$(printf '%s' "$TASK_ID" | shasum -a 256 | awk '{print substr($1,1,12)}')
WORKTREE_NAME="crypto-$TASK_KEY"
STARTED=$(date '+%Y-%m-%d %H:%M:%S %z')
printf '%s|%s|%s|%s|%s\n' \
  "$TASK_ID" "$$" "$MODEL" "$WORKTREE_NAME" "$STARTED" > "$ACTIVE"
chmod 600 "$ACTIVE"

TASK_PROMPT=$(cat "$PROMPT_FILE")
PROMPT="You are a bounded Cursor Composer worker for Crypto Signal.
Before acting, read in order:
1. $BASE/READ_FIRST_CRYPTO_SIGNAL.md
2. $BASE/CURRENT_STATUS.md
3. $BASE/PROJECT_CHRONICLE.md latest relevant entries.
Then inspect current code and tests mechanically.

Work only on task: $TASK_ID
Work only in the isolated Cursor worktree created for this run.
Do not touch Durdurulmaz, Quantum Capital, runtime/continuity, credentials, or REAL_CAPITAL policy.
Do not broaden scope.
Run focused tests and required quality gates.
If you make valid changes, commit them in your worktree with a clear worker-scoped commit message.
Your report is evidence only; ChatGPT supervisor will independently review before integration.

Task details:
$TASK_PROMPT"
set +e
"$AGENT" -p --trust --auto-review \
  --model "$MODEL" \
  --workspace "$BASE" \
  --worktree "$WORKTREE_NAME" \
  --output-format text \
  "$PROMPT" > "$OUTPUT_FILE" 2>&1
RC=$?
set -e

FINISHED=$(date '+%Y-%m-%d %H:%M:%S %z')
WORKTREE_PATH=$(find "$HOME/.cursor/worktrees" -maxdepth 4 -type d \
  -name "$WORKTREE_NAME" -print -quit 2>/dev/null || true)

{
  echo
  echo "=== SUPERVISOR DISPATCH METADATA ==="
  echo "task=$TASK_ID"
  echo "model=$MODEL"
  echo "rc=$RC"
  echo "worktree_name=$WORKTREE_NAME"
  echo "worktree_path=$WORKTREE_PATH"
  echo "finished=$FINISHED"
} >> "$OUTPUT_FILE"

rm -f "$ACTIVE"
SEED="$TASK_ID|$MODEL|$OUTPUT_FILE|$RC|$FINISHED|$WORKTREE_PATH"
EVENT_HASH=$(printf '%s' "$SEED" | shasum -a 256 | awk '{print $1}')
EVENT_ID="worker-completion:$EVENT_HASH"
MSG="@Remote Desktop Commander CRYPTO_SIGNAL_WORKER_DONE — task=$TASK_ID model=$MODEL rc=$RC output=$OUTPUT_FILE worktree=$WORKTREE_PATH. Worker result is evidence, never automatic PASS. Re-read Crypto governance/current state, inspect exact worktree diff/commit and run mechanical tests before integrating. If stale/superseded, NOOP. REAL_CAPITAL=0."

set +e
QUEUE_RESULT=$("$ENQUEUE" "$EVENT_ID" "$MSG" \
  "$TASK_ID" "composer" "$OUTPUT_FILE" "$RC" "$FINISHED" 2>&1)
QUEUE_RC=$?
set -e

echo "WORKER_COMPLETE task=$TASK_ID rc=$RC queue_rc=$QUEUE_RC"
echo "$QUEUE_RESULT"
exit "$RC"
