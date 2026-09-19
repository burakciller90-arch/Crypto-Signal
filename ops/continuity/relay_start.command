#!/bin/zsh
set -eu

SH="/Users/Shared/.crypto-signal-wake-relay"
PIDFILE="$SH/relay.pid"
LOG="$SH/relay.stdout.log"

if [ -f "$PIDFILE" ]; then
  PID=$(cat "$PIDFILE" 2>/dev/null || true)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    exit 0
  fi
fi

nohup /usr/bin/python3 "$SH/relay_daemon.py" >> "$LOG" 2>&1 </dev/null &
echo $! > "$SH/relay.bootstrap.pid"
exit 0
