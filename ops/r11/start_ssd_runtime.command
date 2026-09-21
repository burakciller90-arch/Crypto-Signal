#!/bin/bash
set -u

ROOT="${CRYPTO_SIGNAL_ROOT:-/Volumes/Crypto-504/Crypto-Signal}"
SUP="$ROOT/ssd-service-supervisor.sh"
PIDFILE="$ROOT/ssd-service-supervisor.pid"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalRuntime"
LOGDIR="$ROOT/ServiceLogs"

mkdir -p "$LOCAL_LOG"

find_supervisor_pid() {
  /bin/ps -axo pid=,command= 2>/dev/null     | /usr/bin/awk -v needle="$SUP" 'index($0, needle) > 0 {print $1; exit}'
}

pid="$(find_supervisor_pid)"
if [ -n "$pid" ] && /bin/kill -0 "$pid" >/dev/null 2>&1; then
  if [ -d "$ROOT" ] && [ -w "$ROOT" ]; then
    printf '%s\n' "$pid" > "$PIDFILE"
  fi
  printf '%s RUNTIME_ALREADY_ALIVE=YES pid=%s root=%s\n'     "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')" "$pid" "$ROOT"     >>"$LOCAL_LOG/runtime-terminal-watchdog.log"
  exit 0
fi

if [ ! -d "$ROOT" ] || [ ! -x "$SUP" ]; then
  printf '%s SSD_RUNTIME_NOT_READY=YES root=%s\n'     "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')" "$ROOT"     >>"$LOCAL_LOG/runtime-terminal-watchdog.err.log"
  exit 75
fi

mkdir -p "$LOGDIR"
unset RUNNER_TRACKING_ID
export HOME="/Users/crypto-signal-agent"

printf '%s STARTING_SSD_RUNTIME=YES root=%s\n'   "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')" "$ROOT"   >>"$LOCAL_LOG/runtime-terminal-watchdog.log"

nohup "$SUP"   >>"$LOGDIR/runtime-terminal-bootstrap.out.log"   2>>"$LOGDIR/runtime-terminal-bootstrap.err.log"   </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PIDFILE"

ok=0
for _ in {1..45}; do
  if /bin/kill -0 "$pid" >/dev/null 2>&1       && /usr/bin/curl -fsS --max-time 3 http://127.0.0.1:48700/api/health >/dev/null 2>&1; then
    ok=1
    break
  fi
  /bin/sleep 1
done

if [ "$ok" != "1" ]; then
  printf '%s SSD_RUNTIME_START_FAILED pid=%s root=%s\n'     "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')" "$pid" "$ROOT"     >>"$LOCAL_LOG/runtime-terminal-watchdog.err.log"
  exit 70
fi

printf '%s SSD_RUNTIME_STARTED=YES pid=%s root=%s\n'   "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')" "$pid" "$ROOT"   >>"$LOCAL_LOG/runtime-terminal-watchdog.log"
exit 0
