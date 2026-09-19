#!/bin/zsh
set -eu

BASE="/Users/crypto-signal-agent/Crypto-Signal"
ROOT="$BASE/runtime/continuity/leases"
ACTIVE="$ROOT/active"
CANCELED="$ROOT/canceled"

mkdir -p "$ACTIVE" "$CANCELED"
[ "$#" -eq 1 ] || {
  echo "USAGE: continuation_cancel.sh task_id" >&2
  exit 64
}

TASK="$1"
NOW=$(date +%s)
COUNT=0
for f in "$ACTIVE"/*.lease(N); do
  existing_task=$(sed -n '1p' "$f" 2>/dev/null || true)
  if [ "$existing_task" = "$TASK" ]; then
    mv "$f" "$CANCELED/${f:t}.canceled.$NOW"
    COUNT=$(( COUNT + 1 ))
  fi
done

printf 'CONTINUATION_LEASE_CANCELED task=%s count=%s\n' "$TASK" "$COUNT"
