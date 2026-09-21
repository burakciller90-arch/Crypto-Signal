#!/bin/bash
set -u
unset RUNNER_TRACKING_ID

ROOT="/Volumes/Crypto-504/Crypto-Signal"
SUP="$ROOT/ssd-service-supervisor.sh"
PIDFILE="$ROOT/ssd-service-supervisor.pid"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalSupervisor"
mkdir -p "$LOCAL_LOG"

existing="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -n "$existing" ]   && kill -0 "$existing" >/dev/null 2>&1   && ps -p "$existing" -o command= 2>/dev/null | grep -F "$SUP" >/dev/null 2>&1; then
  printf '%s SUPERVISOR_ALREADY_ALIVE=YES pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$existing" >>"$LOCAL_LOG/start.log"
  exit 0
fi

if [ ! -x "$SUP" ]; then
  printf '%s SSD_SUPERVISOR_NOT_READY=YES\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$LOCAL_LOG/start.err.log"
  exit 75
fi

if [ ! -d "$ROOT/Development" ] || [ ! -d "$ROOT/Product" ]; then
  printf '%s SSD_RUNTIME_LAYOUT_NOT_READY=YES\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$LOCAL_LOG/start.err.log"
  exit 75
fi

nohup "$SUP" >>"$LOCAL_LOG/bootstrap.out.log" 2>>"$LOCAL_LOG/bootstrap.err.log" </dev/null &
pid=$!
printf '%s\n' "$pid" >"$PIDFILE"
printf '%s SUPERVISOR_START_REQUESTED=YES pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$pid" >>"$LOCAL_LOG/start.log"
sleep 3
if ! kill -0 "$pid" >/dev/null 2>&1; then
  printf '%s SUPERVISOR_START_FAILED=YES pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" "$pid" >>"$LOCAL_LOG/start.err.log"
  exit 76
fi
exit 0
