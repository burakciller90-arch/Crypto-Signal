#!/bin/bash
set -u

ROOT="/Volumes/Crypto-504/Crypto-Signal"
SUP="$ROOT/ssd-service-supervisor.sh"
PIDFILE="$ROOT/ssd-service-supervisor.pid"
LOCAL_ROOT="$HOME/Library/Application Support/CryptoSignalSupervisor"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalSupervisor"
START="$LOCAL_ROOT/start-ssd-supervisor.command"
LOCK="$LOCAL_ROOT/watchdog.lock"
mkdir -p "$LOCAL_ROOT" "$LOCAL_LOG"

pid="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -n "$pid" ]   && kill -0 "$pid" >/dev/null 2>&1   && ps -p "$pid" -o command= 2>/dev/null | grep -F "$SUP" >/dev/null 2>&1; then
  exit 0
fi

if [ -f "$LOCK" ]; then
  now="$(date +%s)"
  then="$(stat -f %m "$LOCK" 2>/dev/null || echo 0)"
  if [ $((now-then)) -lt 90 ]; then
    exit 0
  fi
fi

date >"$LOCK"
printf '%s REQUESTING_TERMINAL_SUPERVISOR_START=YES\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" >>"$LOCAL_LOG/watchdog.log"
/usr/bin/open -gj -a Terminal "$START"
sleep 12
rm -f "$LOCK"
exit 0
