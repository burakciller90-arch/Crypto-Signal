#!/bin/bash
set -u
unset RUNNER_TRACKING_ID

ROOT="${CRYPTO_SIGNAL_ROOT:-/Volumes/Crypto-504/Crypto-Signal}"
DEV="$ROOT/Development"
LIVE="$ROOT/Live"
PRODUCT="$ROOT/Product"
ALERTS="$ROOT/Alerts"
PAPER="$ROOT/Paper"
WRAPPER="$ROOT/ssd-clock-wrapper.py"
LOGDIR="$ROOT/ServiceLogs"
MARKET_TAPE="$ROOT/MarketTape"
MARKET_TAPE_START="$MARKET_TAPE/ops/market_tape/start_market_tape_supervisor.sh"
MARKET_TAPE_SUPERVISOR="$MARKET_TAPE/ops/market_tape/run_market_tape_supervisor.py"
MARKET_TAPE_RUNTIME="$MARKET_TAPE/ops/run_market_tape_runtime.py"
MARKET_TAPE_COLD_PYTHON="$ROOT/RuntimeEnvs/market-tape-cold/bin/python"
MARKET_TAPE_CONTROL="/Users/crypto-signal-agent/.crypto-signal-runtime"
MARKET_TAPE_PIDFILE="$MARKET_TAPE_CONTROL/market-tape-supervisor.pid"
MARKET_TAPE_ENABLE_FILE="$MARKET_TAPE_CONTROL/market-tape.enabled"

for required in "$DEV" "$LIVE" "$PRODUCT" "$ALERTS" "$PAPER"; do
  if [ ! -d "$required" ]; then
    echo "RUNTIME_REQUIRED_DIR_MISSING=$required" >&2
    exit 75
  fi
done
for required in   "$PRODUCT/.venv/bin/python"   "$PRODUCT/ops/run_dashboard.py"   "$LIVE/.venv/bin/python"   "$ALERTS/.venv/bin/python"   "$PAPER/.venv/bin/python"   "$WRAPPER"; do
  if [ ! -e "$required" ]; then
    echo "RUNTIME_REQUIRED_FILE_MISSING=$required" >&2
    exit 75
  fi
done

mkdir -p "$LOGDIR"
exec >>"$LOGDIR/supervisor.log" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S %z') supervisor_r11_start pid=$$ root=$ROOT"

dashboard_pid_is_expected() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  ps -p "$pid" -o command= 2>/dev/null     | grep -F "$PRODUCT/ops/run_dashboard.py"     | grep -F -- "--port 48700" >/dev/null 2>&1
}

adopt_healthy_dashboard() {
  curl -fsS --max-time 3 http://127.0.0.1:48700/api/health >/dev/null 2>&1 || return 1
  local pid=""
  pid="$(/usr/sbin/lsof -nP -iTCP:48700 -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  dashboard_pid_is_expected "$pid" || return 1
  echo "$pid" > "$ROOT/dashboard.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') dashboard_adopted pid=$pid"
  return 0
}

start_dashboard() {
  local pid=""
  if [ -f "$ROOT/dashboard.pid" ]; then
    pid="$(cat "$ROOT/dashboard.pid" 2>/dev/null || true)"
  fi
  if dashboard_pid_is_expected "$pid"; then
    return 0
  fi

  if [ -n "$pid" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') stale_dashboard_pid=$pid"
  fi
  rm -f "$ROOT/dashboard.pid"

  if adopt_healthy_dashboard; then
    return 0
  fi

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$PRODUCT/src"
    cd "$PRODUCT" || exit 75
    exec "$PRODUCT/.venv/bin/python" "$PRODUCT/ops/run_dashboard.py"       --host 127.0.0.1       --port 48700       --ledger "$DEV/runtime/ledger/live_signal_ledger.sqlite3"       --alert-outbox "$DEV/runtime/alerts/alert_outbox.sqlite3"       --paper-ledger "$DEV/runtime/paper/paper_fund.sqlite3"       --candle-cache "$DEV/runtime/data/live_base_15m_cache.sqlite3"
  ) >>"$LOGDIR/dashboard.out.log" 2>>"$LOGDIR/dashboard.err.log" < /dev/null &
  pid=$!
  echo "$pid" > "$ROOT/dashboard.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') dashboard_started pid=$pid"
}

market_tape_supervisor_pid_is_expected() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  ps -p "$pid" -o user=,command= 2>/dev/null \
    | grep -F "crypto-signal-agent" \
    | grep -F "$MARKET_TAPE_SUPERVISOR" >/dev/null 2>&1
}

ensure_market_tape_supervisor() {
  local pid=""
  if [ ! -f "$MARKET_TAPE_ENABLE_FILE" ]; then
    return 0
  fi
  if [ -f "$MARKET_TAPE_PIDFILE" ]; then
    pid="$(cat "$MARKET_TAPE_PIDFILE" 2>/dev/null || true)"
  fi
  if market_tape_supervisor_pid_is_expected "$pid"; then
    return 0
  fi

  if [ -n "$pid" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') stale_market_tape_supervisor_pid=$pid"
  fi

  for required in \
    "$MARKET_TAPE" \
    "$MARKET_TAPE_START" \
    "$MARKET_TAPE_SUPERVISOR" \
    "$MARKET_TAPE_RUNTIME" \
    "$MARKET_TAPE_COLD_PYTHON"; do
    if [ ! -e "$required" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_not_ready path=$required"
      return 0
    fi
  done

  mkdir -p "$MARKET_TAPE_CONTROL"
  chmod 700 "$MARKET_TAPE_CONTROL"

  if /bin/bash "$MARKET_TAPE_START" \
      >>"$LOGDIR/market-tape-bootstrap.out.log" \
      2>>"$LOGDIR/market-tape-bootstrap.err.log"; then
    pid="$(cat "$MARKET_TAPE_PIDFILE" 2>/dev/null || true)"
    if market_tape_supervisor_pid_is_expected "$pid"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_supervisor_ready pid=$pid"
      return 0
    fi
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_supervisor_start_failed"
  return 0
}

run_clock() {
  local kind="$1"
  local py="$2"
  local src="$3"
  if [ ! -x "$py" ] || [ ! -d "$src" ] || [ ! -f "$WRAPPER" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') clock_not_ready kind=$kind"
    return 0
  fi
  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$src"
    exec "$py" "$WRAPPER" "$kind"
  ) >>"$LOGDIR/$kind.out.log" 2>>"$LOGDIR/$kind.err.log" < /dev/null &
}

bound_logs() {
  local helper="$DEV/ops/bound_runtime_logs.py"
  local python="$DEV/.venv/bin/python"
  if [ -x "$python" ] && [ -f "$helper" ]; then
    PYTHONPATH="$DEV/src" "$python" "$helper"       --log-dir "$LOGDIR"       --max-bytes 16777216       --keep-bytes 8388608       >>"$LOGDIR/log-rotation.log" 2>>"$LOGDIR/log-rotation.err.log" || true
  fi
}

shutdown() {
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') supervisor_r11_stop pid=$$"
  exit 0
}
trap shutdown TERM INT

last_clock=0
last_rotation=0
last_market_tape=0
while true; do
  start_dashboard
  now="$(date +%s)"

  if [ $((now-last_market_tape)) -ge 30 ]; then
    ensure_market_tape_supervisor
    last_market_tape="$now"
  fi

  if [ $((now-last_clock)) -ge 120 ]; then
    run_clock live "$LIVE/.venv/bin/python" "$LIVE/src"
    run_clock alert "$ALERTS/.venv/bin/python" "$ALERTS/src"
    run_clock paper "$PAPER/.venv/bin/python" "$PAPER/src"
    run_clock dry "$PAPER/.venv/bin/python" "$PAPER/src"
    last_clock="$now"
  fi

  if [ $((now-last_rotation)) -ge 300 ]; then
    bound_logs
    last_rotation="$now"
  fi

  sleep 10
done
