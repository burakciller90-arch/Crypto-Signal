#!/bin/bash
set -euo pipefail

UID_EXPECTED="504"
ROOT="/Volumes/Crypto-504/Crypto-Signal"
STABLE="$ROOT/MarketTape"
PYTHON="$ROOT/Development/.venv/bin/python"
SUPERVISOR="$STABLE/ops/market_tape/run_market_tape_supervisor.py"
CONTROL="/Users/crypto-signal-agent/.crypto-signal-runtime"
PID_FILE="$CONTROL/market-tape-supervisor.pid"
STOP_FILE="$CONTROL/market-tape-supervisor.stop"
LOG_DIR="/Users/crypto-signal-agent/Library/Logs/CryptoSignal"
LOG="$LOG_DIR/market-tape-supervisor.log"

if [ "$(id -u)" != "$UID_EXPECTED" ]; then
  echo "MARKET_TAPE_SUPERVISOR_START_ERROR=UID_MISMATCH expected=$UID_EXPECTED actual=$(id -u)" >&2
  exit 75
fi

for required in "$ROOT" "$STABLE" "$PYTHON" "$SUPERVISOR"; do
  if [ ! -e "$required" ]; then
    echo "MARKET_TAPE_SUPERVISOR_START_ERROR=REQUIRED_PATH_MISSING path=$required" >&2
    exit 75
  fi
done

mkdir -p "$CONTROL" "$LOG_DIR"
chmod 700 "$CONTROL"
rm -f "$STOP_FILE"

if [ -s "$PID_FILE" ]; then
  existing="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$existing" ] && kill -0 "$existing" 2>/dev/null; then
    echo "MARKET_TAPE_SUPERVISOR_ALREADY_RUNNING pid=$existing"
    echo "REAL_CAPITAL=0"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

unset RUNNER_TRACKING_ID || true
nohup "$PYTHON" "$SUPERVISOR" >>"$LOG" 2>&1 </dev/null &
launcher_pid=$!

for _ in {1..20}; do
  if [ -s "$PID_FILE" ]; then
    supervisor_pid="$(cat "$PID_FILE")"
    if kill -0 "$supervisor_pid" 2>/dev/null; then
      echo "MARKET_TAPE_SUPERVISOR_START_PASS=YES pid=$supervisor_pid launcher_pid=$launcher_pid"
      echo "REAL_CAPITAL=0"
      exit 0
    fi
  fi
  sleep 1
done

echo "MARKET_TAPE_SUPERVISOR_START_ERROR=PROCESS_DID_NOT_STABILIZE" >&2
tail -80 "$LOG_DIR/market-tape-supervisor.log" >&2 || true
exit 76
