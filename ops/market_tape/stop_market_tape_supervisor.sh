#!/bin/bash
set -euo pipefail

UID_EXPECTED="504"
CONTROL="/Users/crypto-signal-agent/.crypto-signal-runtime"
PID_FILE="$CONTROL/market-tape-supervisor.pid"
STOP_FILE="$CONTROL/market-tape-supervisor.stop"

if [ "$(id -u)" != "$UID_EXPECTED" ]; then
  echo "MARKET_TAPE_SUPERVISOR_STOP_ERROR=UID_MISMATCH expected=$UID_EXPECTED actual=$(id -u)" >&2
  exit 75
fi

mkdir -p "$CONTROL"
chmod 700 "$CONTROL"
touch "$STOP_FILE"

pid=""
if [ -s "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
fi

if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  kill -TERM "$pid" 2>/dev/null || true
  for _ in {1..25}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
  fi
fi

if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
  echo "MARKET_TAPE_SUPERVISOR_STOP_ERROR=PROCESS_STILL_ALIVE pid=$pid" >&2
  exit 76
fi

rm -f "$PID_FILE"
if [ -n "$pid" ]; then
  echo "MARKET_TAPE_SUPERVISOR_STOP_PASS=YES pid=$pid"
else
  echo "MARKET_TAPE_SUPERVISOR_STOP_PASS=YES pid=none"
fi
echo "REAL_CAPITAL=0"
