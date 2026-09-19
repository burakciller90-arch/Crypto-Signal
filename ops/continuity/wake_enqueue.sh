#!/bin/zsh
set -eu

BASE="/Users/crypto-signal-agent/Crypto-Signal"
STATE="$BASE/runtime/continuity"
WAKE_ROOT="$STATE/wake"
PAUSE_FILE="$STATE/user_pause"
QUEUE="$WAKE_ROOT/queue"
RECEIPTS="$WAKE_ROOT/receipts"

mkdir -p "$QUEUE" "$RECEIPTS"
[ -f "$PAUSE_FILE" ] && {
  echo "WAKE_ENQUEUE_PAUSED:$PAUSE_FILE"
  exit 0
}

[ "$#" -ge 2 ] || {
  echo "USAGE: wake_enqueue.sh event_id message [task role output rc finished]" >&2
  exit 64
}
EVENT_ID="$1"
MESSAGE=$(printf '%s' "$2" | tr '\n\r' '  ')
TASK="${3:-}"
ROLE="${4:-}"
OUTPUT="${5:-}"
RC="${6:-}"
FINISHED="${7:-}"

EVENT_KEY=$(printf '%s' "$EVENT_ID" | shasum -a 256 | awk '{print $1}')
FILE="$QUEUE/$EVENT_KEY.wake"
RECEIPT="$RECEIPTS/$EVENT_KEY.state"

if [ -f "$RECEIPT" ]; then
  echo "ALREADY_RECEIPTED:$FILE"
  exit 0
fi
if [ -f "$FILE" ]; then
  queued_event=$(sed -n '1p' "$FILE")
  queued_message=$(sed -n '7p' "$FILE")
  if [ "$queued_event" != "$EVENT_ID" ] || [ "$queued_message" != "$MESSAGE" ]; then
    echo "EVENT_ID_MESSAGE_CONFLICT:$FILE" >&2
    exit 65
  fi
  echo "ALREADY_QUEUED:$FILE"
  exit 0
fi

TMP="$FILE.$$"
{
  printf '%s\n' "$EVENT_ID"
  printf '%s\n' "$TASK"
  printf '%s\n' "$ROLE"
  printf '%s\n' "$OUTPUT"
  printf '%s\n' "$RC"
  printf '%s\n' "$FINISHED"
  printf '%s\n' "$MESSAGE"
} > "$TMP"
chmod 600 "$TMP"
mv "$TMP" "$FILE"
echo "QUEUED:$FILE"
