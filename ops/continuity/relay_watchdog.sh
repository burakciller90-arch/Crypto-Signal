#!/bin/zsh
set -eu

SH="/Users/Shared/.crypto-signal-wake-relay"
HB="$SH/relay_heartbeat"
PIDFILE="$SH/relay.pid"
NOW=$(date +%s)
NEEDS_START=0

if [ ! -f "$PIDFILE" ]; then
  NEEDS_START=1
else
  PID=$(cat "$PIDFILE" 2>/dev/null || true)
  if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
    NEEDS_START=1
  elif [ ! -f "$HB" ]; then
    NEEDS_START=1
  else
    MTIME=$(stat -f %m "$HB")
    AGE=$(( NOW - MTIME ))
    if [ "$AGE" -gt 45 ]; then
      kill "$PID" >/dev/null 2>&1 || true
      rm -f "$PIDFILE"
      NEEDS_START=1
    fi
  fi
fi

if [ "$NEEDS_START" -eq 1 ]; then
  /usr/bin/open "$SH/relay_start.command"
fi
