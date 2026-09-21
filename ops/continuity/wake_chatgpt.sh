#!/bin/zsh
set -eu

BASE="/Volumes/Crypto-504/Crypto-Signal/Development"
STATE="$BASE/runtime/continuity"
PAUSE_FILE="$STATE/user_pause"

[ -f "$PAUSE_FILE" ] && {
  echo "WAKE_TRANSPORT_PAUSED:$PAUSE_FILE"
  exit 0
}

exec /usr/bin/python3 \
  "$BASE/ops/continuity/host_gui_lock.py" \
  /usr/bin/python3 \
  "$BASE/ops/continuity/wake_chatgpt.py" \
  "$@"
