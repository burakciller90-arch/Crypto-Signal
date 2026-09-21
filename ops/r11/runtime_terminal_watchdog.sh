#!/bin/bash
set -u

LOCAL_ROOT="$HOME/Library/Application Support/CryptoSignalRuntime"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalRuntime"
START="$LOCAL_ROOT/start-ssd-runtime.command"
LOCK="$LOCAL_ROOT/runtime-terminal-watchdog.lock"
SUP="/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh"

mkdir -p "$LOCAL_ROOT" "$LOCAL_LOG"

/bin/ps -axo command= 2>/dev/null   | /usr/bin/grep -F "$SUP"   | /usr/bin/grep -v grep >/dev/null 2>&1 && exit 0

if [ -f "$LOCK" ]; then
  now="$(/bin/date +%s)"
  then="$(/usr/bin/stat -f %m "$LOCK" 2>/dev/null || echo 0)"
  if [ $((now-then)) -lt 90 ]; then
    exit 0
  fi
fi

/bin/date > "$LOCK"
printf '%s REQUESTING_TERMINAL_RUNTIME_START=YES\n'   "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')"   >>"$LOCAL_LOG/runtime-terminal-watchdog.log"

/usr/bin/open -gj -a Terminal "$START"
/bin/sleep 12
/bin/rm -f "$LOCK"
exit 0
