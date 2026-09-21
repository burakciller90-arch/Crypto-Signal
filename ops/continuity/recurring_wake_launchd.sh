#!/bin/zsh
set -euo pipefail

STATE="/Users/crypto-signal-agent/Crypto-Signal/runtime/continuity"
SCRIPT_DIR="${0:A:h}"
mkdir -p "$STATE"

NOW_EPOCH="$(date +%s)"
STAMP="$(date '+%Y%m%dT%H%M%z')"
ATTEMPT="$STATE/recurring_wake_last_local_attempt"
RESULT="$STATE/recurring_wake_last_local_result"

printf 'epoch=%s\nstamp=%s\n' "$NOW_EPOCH" "$STAMP" > "$ATTEMPT"
EVENT_ID="crypto-local-30m:$STAMP"

set +e
/usr/bin/python3 "$SCRIPT_DIR/recurring_wake.py" "$EVENT_ID"
RC=$?
set -e

printf 'epoch=%s\nstamp=%s\nrc=%s\n' "$(date +%s)" "$STAMP" "$RC" > "$RESULT"
exit "$RC"
