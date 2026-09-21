#!/bin/bash
set -u
unset RUNNER_TRACKING_ID

ROOT="/Volumes/Crypto-504/Crypto-Signal"
DEV="$ROOT/Development"
LIVE="$ROOT/Live"
PRODUCT="$ROOT/Product"
ALERTS="$ROOT/Alerts"
PAPER="$ROOT/Paper"
WRAPPER="$ROOT/ssd-clock-wrapper.py"
LOGDIR="$ROOT/ServiceLogs"
SUP_PID_FILE="$ROOT/ssd-service-supervisor.pid"
DASH_PID_FILE="$ROOT/dashboard.pid"
MAX_LOG_BYTES=$((8 * 1024 * 1024))
LOG_KEEP=3

mkdir -p "$LOGDIR"

rotate_log() {
  local path="$1"
  [ -f "$path" ] || return 0
  local size=""
  size="$(stat -f %z "$path" 2>/dev/null || echo 0)"
  [ "$size" -gt "$MAX_LOG_BYTES" ] || return 0
  local i="$LOG_KEEP"
  while [ "$i" -gt 1 ]; do
    local prev=$((i-1))
    [ -f "$path.$prev" ] && mv -f "$path.$prev" "$path.$i"
    i=$prev
  done
  mv -f "$path" "$path.1"
}

log() {
  rotate_log "$LOGDIR/supervisor.log"
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$*" >>"$LOGDIR/supervisor.log"
}

process_command() {
  local pid="$1"
  ps -p "$pid" -o command= 2>/dev/null || true
}

pid_matches() {
  local pid="$1"
  local needle="$2"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  process_command "$pid" | grep -F "$needle" >/dev/null 2>&1
}

canonical_dashboard_pids() {
  ps -axo pid=,command= 2>/dev/null     | grep -F "$PRODUCT/ops/run_dashboard.py"     | grep -F -- "--port 48700"     | grep -v grep     | awk '{print $1}'
}

reconcile_dashboard_pid() {
  local current=""
  [ -f "$DASH_PID_FILE" ] && current="$(cat "$DASH_PID_FILE" 2>/dev/null || true)"
  if pid_matches "$current" "$PRODUCT/ops/run_dashboard.py"; then
    printf '%s\n' "$current"
    return 0
  fi

  local found=""
  found="$(canonical_dashboard_pids)"
  local count=0
  [ -n "$found" ] && count="$(printf '%s\n' "$found" | wc -l | tr -d ' ')"
  if [ "$count" -gt 1 ]; then
    log "DASHBOARD_DUPLICATE_FAIL_CLOSED=YES"
    return 74
  fi
  if [ "$count" = "1" ]; then
    local reconciled=""
    reconciled="$(printf '%s\n' "$found" | head -1)"
    printf '%s\n' "$reconciled" >"$DASH_PID_FILE"
    log "DASHBOARD_PID_RECONCILED=YES pid=$reconciled stale=$current"
    printf '%s\n' "$reconciled"
    return 0
  fi

  if [ -f "$DASH_PID_FILE" ]; then
    rm -f "$DASH_PID_FILE"
    log "DASHBOARD_STALE_PID_REMOVED=YES stale=$current"
  fi
  return 1
}

start_dashboard() {
  local pid=""
  if pid="$(reconcile_dashboard_pid)"; then
    [ -n "$pid" ] && return 0
  else
    local rc=$?
    [ "$rc" = "74" ] && return "$rc"
  fi

  rotate_log "$LOGDIR/dashboard.out.log"
  rotate_log "$LOGDIR/dashboard.err.log"
  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$PRODUCT/src"
    cd "$PRODUCT" || exit 75
    exec "$PRODUCT/.venv/bin/python" "$PRODUCT/ops/run_dashboard.py"       --host 127.0.0.1       --port 48700       --ledger "$DEV/runtime/ledger/live_signal_ledger.sqlite3"       --alert-outbox "$DEV/runtime/alerts/alert_outbox.sqlite3"       --paper-ledger "$DEV/runtime/paper/paper_fund.sqlite3"       --candle-cache "$DEV/runtime/data/live_base_15m_cache.sqlite3"
  ) >>"$LOGDIR/dashboard.out.log" 2>>"$LOGDIR/dashboard.err.log" < /dev/null &
  pid=$!
  printf '%s\n' "$pid" >"$DASH_PID_FILE"
  log "DASHBOARD_STARTED=YES pid=$pid"
}

maybe_rotate_dashboard() {
  local needs_restart=0
  local path=""
  for path in "$LOGDIR/dashboard.out.log" "$LOGDIR/dashboard.err.log"; do
    [ -f "$path" ] || continue
    local size=""
    size="$(stat -f %z "$path" 2>/dev/null || echo 0)"
    [ "$size" -gt "$MAX_LOG_BYTES" ] && needs_restart=1
  done
  [ "$needs_restart" = "1" ] || return 0

  local pid=""
  pid="$(reconcile_dashboard_pid 2>/dev/null || true)"
  if [ -n "$pid" ] && pid_matches "$pid" "$PRODUCT/ops/run_dashboard.py"; then
    log "DASHBOARD_LOG_ROTATION_RESTART=YES pid=$pid"
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..30}; do
      kill -0 "$pid" >/dev/null 2>&1 || break
      sleep 1
    done
  fi
  rm -f "$DASH_PID_FILE"
  rotate_log "$LOGDIR/dashboard.out.log"
  rotate_log "$LOGDIR/dashboard.err.log"
}

run_clock() {
  local kind="$1"
  local py="$2"
  local src="$3"
  rotate_log "$LOGDIR/$kind.out.log"
  rotate_log "$LOGDIR/$kind.err.log"
  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$src"
    exec "$py" "$WRAPPER" "$kind"
  ) >>"$LOGDIR/$kind.out.log" 2>>"$LOGDIR/$kind.err.log" < /dev/null &
}

require_runtime() {
  [ -d "$ROOT" ] || return 75
  [ -x "$PRODUCT/.venv/bin/python" ] || return 75
  [ -f "$PRODUCT/ops/run_dashboard.py" ] || return 75
  [ -x "$LIVE/.venv/bin/python" ] || return 75
  [ -x "$ALERTS/.venv/bin/python" ] || return 75
  [ -x "$PAPER/.venv/bin/python" ] || return 75
  [ -f "$WRAPPER" ] || return 75
  [ -f "$DEV/runtime/ledger/live_signal_ledger.sqlite3" ] || return 75
  [ -f "$DEV/runtime/alerts/alert_outbox.sqlite3" ] || return 75
  [ -f "$DEV/runtime/paper/paper_fund.sqlite3" ] || return 75
  [ -f "$DEV/runtime/data/live_base_15m_cache.sqlite3" ] || return 75
}

if ! require_runtime; then
  log "SSD_RUNTIME_NOT_READY_FAIL_CLOSED=YES"
  exit 75
fi

printf '%s\n' "$$" >"$SUP_PID_FILE"
log "SUPERVISOR_R11_START=YES pid=$$"

last=0
while true; do
  if ! require_runtime; then
    log "SSD_RUNTIME_BECAME_UNAVAILABLE_FAIL_CLOSED=YES"
    sleep 10
    continue
  fi

  maybe_rotate_dashboard
  if ! start_dashboard; then
    rc=$?
    log "DASHBOARD_RECONCILE_FAILED=YES rc=$rc"
  fi

  now="$(date +%s)"
  if [ $((now-last)) -ge 120 ]; then
    run_clock live "$LIVE/.venv/bin/python" "$LIVE/src"
    run_clock alert "$ALERTS/.venv/bin/python" "$ALERTS/src"
    run_clock paper "$PAPER/.venv/bin/python" "$PAPER/src"
    run_clock dry "$PAPER/.venv/bin/python" "$PAPER/src"
    last="$now"
  fi
  sleep 10
done
