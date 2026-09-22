#!/bin/bash
set -euo pipefail

# Installs a tiny internal-disk bootstrap that owns no market/runtime data.
# It only detects /Volumes/Crypto-504 availability transitions and restarts
# the canonical SSD supervisor / GitHub runner from their SSD paths.
# There is deliberately no internal-Mac runtime fallback.

ROOT="/Volumes/Crypto-504/Crypto-Signal"
LOCAL_ROOT="$HOME/Library/Application Support/CryptoSignalRecovery"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalRecovery"
WATCHDOG="$LOCAL_ROOT/hotplug-watchdog.sh"
STATE_FILE="$LOCAL_ROOT/ssd-state"
LABEL="com.cryptosignal.ssd-hotplug-recovery"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
TARGET="gui/$(id -u)/$LABEL"

if [ "$(id -u)" != "504" ]; then
  echo "R15_HOTPLUG_INSTALL_ERROR=UID_MUST_BE_504" >&2
  exit 2
fi

mkdir -p "$LOCAL_ROOT" "$LOCAL_LOG" "$HOME/Library/LaunchAgents"

cat > "$WATCHDOG" <<'WATCH'
#!/bin/bash
set -u

ROOT="/Volumes/Crypto-504/Crypto-Signal"
DEV="$ROOT/Development"
RUNNER="$ROOT/Runner"
LOCAL_ROOT="$HOME/Library/Application Support/CryptoSignalRecovery"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalRecovery"
STATE_FILE="$LOCAL_ROOT/ssd-state"
LOCK_DIR="$LOCAL_ROOT/watchdog.lock"
LOG="$LOCAL_LOG/hotplug-watchdog.log"
ERR="$LOCAL_LOG/hotplug-watchdog.err.log"

mkdir -p "$LOCAL_ROOT" "$LOCAL_LOG"

stamp() {
  date '+%Y-%m-%d %H:%M:%S %z'
}

log() {
  printf '%s %s\n' "$(stamp)" "$*" >>"$LOG"
}

err() {
  printf '%s %s\n' "$(stamp)" "$*" >>"$ERR"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK_DIR" >/dev/null 2>&1 || true' EXIT

previous="$(cat "$STATE_FILE" 2>/dev/null || echo unknown)"

if ! /sbin/mount | /usr/bin/grep -F " on /Volumes/Crypto-504 " >/dev/null 2>&1; then
  if [ "$previous" != "missing" ]; then
    log "SSD_STATE=MISSING"
  fi
  printf 'missing\n' >"$STATE_FILE"
  exit 0
fi

required=(
  "$ROOT/ssd-service-supervisor.sh"
  "$RUNNER/runsvc.sh"
  "$RUNNER/bin/Runner.Listener"
  "$DEV/runtime/ledger/live_signal_ledger.sqlite3"
  "$DEV/runtime/data/live_base_15m_cache.sqlite3"
  "$DEV/runtime/paper/paper_fund.sqlite3"
)
for path in "${required[@]}"; do
  if [ ! -e "$path" ]; then
    err "SSD_STATE=PRESENT_BUT_INCOMPLETE missing=$path"
    printf 'retry\n' >"$STATE_FILE"
    exit 0
  fi
done

quick_check() {
  local db="$1"
  [ -f "$db" ] || return 0
  local result
  result="$(/usr/bin/sqlite3 "$db" 'PRAGMA quick_check;' 2>>"$ERR" || true)"
  if [ "$result" != "ok" ]; then
    err "SQLITE_QUICK_CHECK_FAIL db=$db result=$result"
    return 1
  fi
  return 0
}

supervisor_alive() {
  /bin/ps -axo command= 2>/dev/null     | /usr/bin/grep -F "$ROOT/ssd-service-supervisor.sh"     | /usr/bin/grep -v grep >/dev/null 2>&1
}

runner_alive() {
  /bin/ps -axo command= 2>/dev/null     | /usr/bin/grep -F "$RUNNER/bin/Runner.Listener run --startuptype service"     | /usr/bin/grep -v grep >/dev/null 2>&1
}

dashboard_healthy() {
  /usr/bin/curl -fsS --max-time 3 http://127.0.0.1:48700/api/health     >/dev/null 2>&1
}

stop_pidfile_process() {
  local pidfile="$1"
  local expected="$2"
  local pid=""
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [ -n "$pid" ] || return 0
  if /bin/kill -0 "$pid" >/dev/null 2>&1     && /bin/ps -p "$pid" -o command= 2>/dev/null | /usr/bin/grep -F "$expected" >/dev/null 2>&1; then
    /bin/kill "$pid" >/dev/null 2>&1 || true
    /bin/sleep 1
  fi
}

start_supervisor() {
  if supervisor_alive && dashboard_healthy; then
    return 0
  fi

  quick_check "$DEV/runtime/ledger/live_signal_ledger.sqlite3" || return 1
  quick_check "$DEV/runtime/data/live_base_15m_cache.sqlite3" || return 1
  quick_check "$DEV/runtime/paper/paper_fund.sqlite3" || return 1
  quick_check "$DEV/runtime/alerts/alert_outbox.sqlite3" || return 1

  stop_pidfile_process "$ROOT/dashboard.pid" "run_dashboard.py"
  stop_pidfile_process "$ROOT/ssd-service-supervisor.pid" "$ROOT/ssd-service-supervisor.sh"

  (
    unset RUNNER_TRACKING_ID
    nohup "$ROOT/ssd-service-supervisor.sh"       >>"$ROOT/ServiceLogs/hotplug-supervisor-bootstrap.out.log"       2>>"$ROOT/ServiceLogs/hotplug-supervisor-bootstrap.err.log"       </dev/null &
    echo $! >"$ROOT/ssd-service-supervisor.pid"
  )
  log "SUPERVISOR_RESTART_REQUESTED=YES"
  return 0
}

start_runner() {
  local force_restart="$1"

  if [ "$force_restart" != "YES" ] && runner_alive; then
    return 0
  fi

  if [ "$force_restart" = "YES" ]; then
    /bin/ps -axo pid=,command= 2>/dev/null       | /usr/bin/grep -F "$RUNNER/"       | /usr/bin/grep -E 'runsvc\.sh|Runner\.Listener|Runner\.Worker'       | /usr/bin/grep -v grep       | while read -r pid _rest; do
          [ -n "$pid" ] && /bin/kill "$pid" >/dev/null 2>&1 || true
        done
    /bin/sleep 2
  fi

  if runner_alive; then
    return 0
  fi

  mkdir -p "$ROOT/RunnerLogs"
  (
    cd "$RUNNER" || exit 75
    unset RUNNER_TRACKING_ID
    export HOME="/Users/crypto-signal-agent"
    export ACTIONS_RUNNER_SVC=1
    nohup ./runsvc.sh       >>"$ROOT/RunnerLogs/hotplug-runner.out.log"       2>>"$ROOT/RunnerLogs/hotplug-runner.err.log"       </dev/null &
    echo $! >"$ROOT/ssd-runner-hotplug.pid"
  )
  log "RUNNER_RESTART_REQUESTED=YES force=$force_restart"
  return 0
}

mount_transition="NO"
if [ "$previous" = "missing" ]; then
  mount_transition="YES"
  log "SSD_STATE=REMOUNTED"
elif [ "$previous" = "unknown" ]; then
  log "SSD_STATE=PRESENT_INITIAL"
fi

start_supervisor || {
  printf 'retry\n' >"$STATE_FILE"
  exit 0
}
start_runner "$mount_transition" || {
  printf 'retry\n' >"$STATE_FILE"
  exit 0
}

ok=0
for _ in {1..45}; do
  if supervisor_alive && runner_alive && dashboard_healthy; then
    ok=1
    break
  fi
  /bin/sleep 1
done

if [ "$ok" = "1" ]; then
  printf 'ready\n' >"$STATE_FILE"
  if [ "$previous" != "ready" ]; then
    log "SSD_HOTPLUG_RECOVERY_PASS=YES"
  fi
else
  printf 'retry\n' >"$STATE_FILE"
  err "SSD_HOTPLUG_RECOVERY_PASS=NO supervisor=$(supervisor_alive && echo YES || echo NO) runner=$(runner_alive && echo YES || echo NO) dashboard=$(dashboard_healthy && echo YES || echo NO)"
fi

exit 0
WATCH
chmod 700 "$WATCHDOG"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$WATCHDOG</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>20</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$LOCAL_LOG/launchagent.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOCAL_LOG/launchagent.err.log</string>
</dict>
</plist>
PLIST
chmod 644 "$PLIST"
/usr/bin/plutil -lint "$PLIST"

# Do not manufacture a mount transition during installation. If the canonical
# processes are currently healthy we mark ready; otherwise the watchdog will
# repair only the missing plane on its first cycle.
if /sbin/mount | /usr/bin/grep -F " on /Volumes/Crypto-504 " >/dev/null 2>&1; then
  printf 'unknown\n' >"$STATE_FILE"
else
  printf 'missing\n' >"$STATE_FILE"
fi

/bin/launchctl bootout "$TARGET" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "gui/$(id -u)" "$PLIST"
/bin/sleep 2
/bin/launchctl print "$TARGET" >/dev/null

echo "R15_SSD_HOTPLUG_RECOVERY_INSTALLED=YES"
echo "R15_SSD_HOTPLUG_RECOVERY_REAL_CAPITAL=0"
echo "R15_SSD_HOTPLUG_RECOVERY_NO_INTERNAL_RUNTIME_FALLBACK=YES"
