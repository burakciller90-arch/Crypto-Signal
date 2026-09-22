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
RUNNER_HANG_FILE="$LOCAL_ROOT/runner-hang-state"
RUNNER_HANG_CPU_MIN=90
RUNNER_HANG_STREAK_LIMIT=3
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

runner_listener_pid() {
  /bin/ps -axo pid=,command= 2>/dev/null \
    | /usr/bin/awk -v needle="$RUNNER/bin/Runner.Listener run --startuptype service" \
        'index($0, needle) {print $1; exit}'
}

runner_alive() {
  [ -n "$(runner_listener_pid)" ]
}

runner_worker_alive() {
  /bin/ps -axo command= 2>/dev/null \
    | /usr/bin/grep -F "$RUNNER/bin/Runner.Worker" \
    | /usr/bin/grep -v grep >/dev/null 2>&1
}

runner_service_tree() {
  local listener=""
  local service=""
  local wrapper=""
  local command=""

  listener="$(runner_listener_pid)"
  [ -n "$listener" ] || return 1

  service="$(/bin/ps -p "$listener" -o ppid= 2>/dev/null | /usr/bin/tr -d ' ')"
  [ -n "$service" ] || return 1
  command="$(/bin/ps -p "$service" -o command= 2>/dev/null || true)"
  [ "$command" = "./externals/node20/bin/node ./bin/RunnerService.js" ] || return 1

  wrapper="$(/bin/ps -p "$service" -o ppid= 2>/dev/null | /usr/bin/tr -d ' ')"
  [ -n "$wrapper" ] || return 1
  command="$(/bin/ps -p "$wrapper" -o command= 2>/dev/null || true)"
  [ "$command" = "/bin/bash ./runsvc.sh" ] || return 1

  for pid in "$listener" "$service" "$wrapper"; do
    [ "$(/bin/ps -p "$pid" -o user= 2>/dev/null | /usr/bin/tr -d ' ')" = "crypto-signal-agent" ] || return 1
  done

  printf '%s %s %s\n' "$wrapper" "$service" "$listener"
}

stop_runner_service_tree() {
  local tree=""
  local wrapper=""
  local service=""
  local listener=""
  local pid=""
  local command=""

  if runner_worker_alive; then
    err "RUNNER_TREE_STOP_ABORT=ACTIVE_WORKER"
    return 1
  fi

  tree="$(runner_service_tree || true)"
  if [ -z "$tree" ]; then
    err "RUNNER_TREE_STOP_ABORT=UNVERIFIED_ANCESTRY"
    return 1
  fi
  read -r wrapper service listener <<<"$tree"

  log "RUNNER_TREE_STOP_REQUESTED wrapper=$wrapper service=$service listener=$listener"

  /bin/kill "$wrapper" >/dev/null 2>&1 || true
  /bin/kill "$service" >/dev/null 2>&1 || true
  /bin/kill "$listener" >/dev/null 2>&1 || true

  for _ in {1..15}; do
    if ! /bin/kill -0 "$listener" >/dev/null 2>&1 \
      && ! /bin/kill -0 "$service" >/dev/null 2>&1 \
      && ! /bin/kill -0 "$wrapper" >/dev/null 2>&1; then
      log "RUNNER_TREE_STOP_PASS=YES wrapper=$wrapper service=$service listener=$listener"
      return 0
    fi
    /bin/sleep 1
  done

  if runner_worker_alive; then
    err "RUNNER_TREE_FORCE_ABORT=WORKER_APPEARED"
    return 1
  fi

  for pid in "$listener" "$service" "$wrapper"; do
    if /bin/kill -0 "$pid" >/dev/null 2>&1; then
      command="$(/bin/ps -p "$pid" -o command= 2>/dev/null || true)"
      case "$pid" in
        "$listener")
          printf '%s' "$command" | /usr/bin/grep -F "$RUNNER/bin/Runner.Listener run --startuptype service" >/dev/null || return 1
          ;;
        "$service")
          [ "$command" = "./externals/node20/bin/node ./bin/RunnerService.js" ] || return 1
          ;;
        "$wrapper")
          [ "$command" = "/bin/bash ./runsvc.sh" ] || return 1
          ;;
      esac
      /bin/kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  done
  /bin/sleep 2

  if /bin/kill -0 "$listener" >/dev/null 2>&1 \
    || /bin/kill -0 "$service" >/dev/null 2>&1 \
    || /bin/kill -0 "$wrapper" >/dev/null 2>&1; then
    err "RUNNER_TREE_STOP_PASS=NO wrapper=$wrapper service=$service listener=$listener"
    return 1
  fi

  log "RUNNER_TREE_STOP_PASS=YES wrapper=$wrapper service=$service listener=$listener forced=YES"
  return 0
}

reset_runner_hang_state() {
  printf 'pid=\nstreak=0\n' >"$RUNNER_HANG_FILE"
}

runner_hang_detected() {
  local pid=""
  local cpu_raw=""
  local cpu_int=0
  local previous_pid=""
  local previous_streak=0
  local streak=0

  pid="$(runner_listener_pid)"
  if [ -z "$pid" ]; then
    reset_runner_hang_state
    return 1
  fi

  if runner_worker_alive; then
    reset_runner_hang_state
    return 1
  fi

  cpu_raw="$(/bin/ps -p "$pid" -o %cpu= 2>/dev/null | /usr/bin/tr -d ' ' || true)"
  cpu_int="$(/usr/bin/awk -v value="${cpu_raw:-0}" 'BEGIN {printf "%d\n", value + 0}')"

  if [ -f "$RUNNER_HANG_FILE" ]; then
    previous_pid="$(/usr/bin/sed -n 's/^pid=//p' "$RUNNER_HANG_FILE" | /usr/bin/head -1)"
    previous_streak="$(/usr/bin/sed -n 's/^streak=//p' "$RUNNER_HANG_FILE" | /usr/bin/head -1)"
  fi
  case "$previous_streak" in
    ''|*[!0-9]*) previous_streak=0 ;;
  esac

  if [ "$cpu_int" -ge "$RUNNER_HANG_CPU_MIN" ]; then
    if [ "$previous_pid" = "$pid" ]; then
      streak=$((previous_streak + 1))
    else
      streak=1
    fi
  else
    streak=0
  fi

  printf 'pid=%s\nstreak=%s\ncpu=%s\n' "$pid" "$streak" "$cpu_int" >"$RUNNER_HANG_FILE"

  if [ "$streak" -ge "$RUNNER_HANG_STREAK_LIMIT" ]; then
    log "RUNNER_HANG_DETECTED=YES pid=$pid cpu=$cpu_int streak=$streak worker=NO"
    return 0
  fi
  return 1
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
    if runner_hang_detected; then
      force_restart="YES"
      log "RUNNER_HANG_RECOVERY_REQUESTED=YES"
    else
      return 0
    fi
  fi

  if [ "$force_restart" = "YES" ] && runner_alive; then
    stop_runner_service_tree || return 1
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
  reset_runner_hang_state
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
