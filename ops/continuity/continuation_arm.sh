#!/bin/zsh
set -eu

BASE="/Volumes/Crypto-504/Crypto-Signal/Development"
STATE="$BASE/runtime/continuity"
ROOT="$STATE/leases"
PAUSE_FILE="$STATE/user_pause"
SHARED_PAUSE_FILE="/Users/Shared/.crypto-signal-wake-relay/user_pause"
ACTIVE="$ROOT/active"
CANCELED="$ROOT/canceled"
CHECKPOINTS="$ROOT/checkpoints"

mkdir -p "$ACTIVE" "$CANCELED" "$CHECKPOINTS"
if [ -f "$PAUSE_FILE" ] || [ -f "$SHARED_PAUSE_FILE" ]; then
  echo "CONTINUATION_ARM_PAUSED local=$PAUSE_FILE shared=$SHARED_PAUSE_FILE" >&2
  exit 77
fi

[ "$#" -eq 3 ] || {
  echo "USAGE: continuation_arm.sh task_id delay_seconds checkpoint_source" >&2
  exit 64
}
TASK="$1"
DELAY="$2"
SOURCE="$3"

[[ "$DELAY" == <-> ]] || {
  echo "INVALID_DELAY" >&2
  exit 65
}
[ "$DELAY" -ge 10 ] && [ "$DELAY" -le 86400 ] || {
  echo "DELAY_OUT_OF_RANGE" >&2
  exit 65
}
[ -f "$SOURCE" ] || {
  echo "CHECKPOINT_SOURCE_MISSING" >&2
  exit 66
}

NOW=$(date +%s)
DUE=$(( NOW + DELAY ))
CREATED=$(date '+%Y-%m-%d %H:%M:%S %z')
TASK_KEY=$(printf '%s' "$TASK" | shasum -a 256 | awk '{print $1}')
CHECKPOINT="$CHECKPOINTS/${TASK_KEY[1,24]}-$NOW-$$.checkpoint"
cp "$SOURCE" "$CHECKPOINT"
chmod 0444 "$CHECKPOINT"
CHECKPOINT_SHA=$(shasum -a 256 "$CHECKPOINT" | awk '{print $1}')

for f in "$ACTIVE"/*.lease(N); do
  existing_task=$(sed -n '1p' "$f" 2>/dev/null || true)
  if [ "$existing_task" = "$TASK" ]; then
    mv "$f" "$CANCELED/${f:t}.superseded.$NOW"
  fi
done

SEED="$TASK|$CHECKPOINT_SHA|$DUE"
DIGEST=$(printf '%s' "$SEED" | shasum -a 256 | awk '{print $1}')
EVENT_ID="continuation:$DIGEST"
KEY=$(printf '%s' "$EVENT_ID" | shasum -a 256 | awk '{print $1}')
LEASE="$ACTIVE/$KEY.lease"
TMP="$LEASE.$$"
{
  printf '%s\n' "$TASK"
  printf '%s\n' "$EVENT_ID"
  printf '%s\n' "$DUE"
  printf '%s\n' "$CHECKPOINT"
  printf '%s\n' "$CHECKPOINT_SHA"
  printf '%s\n' "$CREATED"
} > "$TMP"
chmod 0600 "$TMP"
mv "$TMP" "$LEASE"

printf 'CONTINUATION_LEASE_ARMED task=%s event=%s due_epoch=%s checkpoint=%s checkpoint_sha256=%s\n' \
  "$TASK" "$EVENT_ID" "$DUE" "$CHECKPOINT" "$CHECKPOINT_SHA"
