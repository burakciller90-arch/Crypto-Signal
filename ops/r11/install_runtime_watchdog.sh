#!/bin/bash
set -euo pipefail

ROOT="${CRYPTO_SIGNAL_ROOT:-/Volumes/Crypto-504/Crypto-Signal}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_ROOT="$HOME/Library/Application Support/CryptoSignalRuntime"
LOCAL_LOG="$HOME/Library/Logs/CryptoSignalRuntime"
LABEL="com.cryptosignal.runtime-terminal-watchdog"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
TARGET="gui/$(id -u)/$LABEL"

test "$(id -u)" = "504"
test -d "$ROOT/Development"
test -f "$REPO_ROOT/ops/ssd_runtime_supervisor.sh"
test -f "$REPO_ROOT/ops/r11/start_ssd_runtime.command"
test -f "$REPO_ROOT/ops/r11/runtime_terminal_watchdog.sh"

mkdir -p "$LOCAL_ROOT" "$LOCAL_LOG" "$HOME/Library/LaunchAgents" "$ROOT/ServiceLogs"

cp "$REPO_ROOT/ops/ssd_runtime_supervisor.sh" "$ROOT/ssd-service-supervisor.sh"
cp "$REPO_ROOT/ops/r11/start_ssd_runtime.command" "$LOCAL_ROOT/start-ssd-runtime.command"
cp "$REPO_ROOT/ops/r11/runtime_terminal_watchdog.sh" "$LOCAL_ROOT/runtime-terminal-watchdog.sh"
chmod 700   "$ROOT/ssd-service-supervisor.sh"   "$LOCAL_ROOT/start-ssd-runtime.command"   "$LOCAL_ROOT/runtime-terminal-watchdog.sh"

existing_sup="$(
  /bin/ps -axo pid=,comm=,args= 2>/dev/null     | /usr/bin/awk -v needle="$ROOT/ssd-service-supervisor.sh" '
        ($2 == "bash" || $2 == "/bin/bash") && index($0, needle) > 0 {
          print $1
          exit
        }
      '
)"
if [ -n "$existing_sup" ] && /bin/kill -0 "$existing_sup" >/dev/null 2>&1; then
  echo "R11_REFRESHING_EXISTING_SUPERVISOR=YES pid=$existing_sup"
  /bin/kill "$existing_sup" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    /bin/kill -0 "$existing_sup" >/dev/null 2>&1 || break
    /bin/sleep 0.25
  done
  if /bin/kill -0 "$existing_sup" >/dev/null 2>&1; then
    /bin/kill -KILL "$existing_sup" >/dev/null 2>&1 || true
  fi
  if [ "$(cat "$ROOT/ssd-service-supervisor.pid" 2>/dev/null || true)" = "$existing_sup" ]; then
    /bin/rm -f "$ROOT/ssd-service-supervisor.pid"
  fi
fi

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
    <string>$LOCAL_ROOT/runtime-terminal-watchdog.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>30</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$LOCAL_LOG/runtime-terminal-watchdog-launchagent.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOCAL_LOG/runtime-terminal-watchdog-launchagent.err.log</string>
</dict>
</plist>
PLIST

chmod 644 "$PLIST"
plutil -lint "$PLIST"
launchctl bootout "$TARGET" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

/bin/rm -f "$HOME/Library/LaunchAgents/com.cryptosignal.dashboard.ssdtest.plist"
launchctl bootout "gui/$(id -u)/com.cryptosignal.dashboard.ssdtest" >/dev/null 2>&1 || true

if ! /usr/bin/open -gj -a Terminal "$LOCAL_ROOT/start-ssd-runtime.command"; then
  echo "R11_TERMINAL_OPEN_FAILED_FALLBACK_DIRECT=YES"
  "$LOCAL_ROOT/start-ssd-runtime.command"
fi
/bin/sleep 4

if ! /bin/ps -axo command= 2>/dev/null   | /usr/bin/grep -F "$ROOT/ssd-service-supervisor.sh"   | /usr/bin/grep -v grep >/dev/null 2>&1; then
  echo "R11_TERMINAL_START_MISSING_FALLBACK_DIRECT=YES"
  "$LOCAL_ROOT/start-ssd-runtime.command"
fi

launchctl print "$TARGET" >/dev/null
/bin/ps -axo command=   | /usr/bin/grep -F "$ROOT/ssd-service-supervisor.sh"   | /usr/bin/grep -v grep >/dev/null

echo "R11_RUNTIME_TERMINAL_WATCHDOG_INSTALL_PASS=YES"
