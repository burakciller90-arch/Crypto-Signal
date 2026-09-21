#!/bin/zsh
set -u

BASE="/Volumes/Crypto-504/Crypto-Signal/Development"
STATE="$BASE/runtime/continuity"
WAKE="$STATE/wake"
TARGET="$WAKE/current_chat_url"
EXPECTED="$WAKE/expected_chat_url"
SHARED="/Users/Shared/.crypto-signal-wake-relay"
SHARED_TARGET="$SHARED/current_chat_url"
SHARED_EXPECTED="$SHARED/expected_chat_url"
SHARED_NAMESPACE="$SHARED/project_namespace"
BRIDGE="$BASE/ops/continuity/bridge_watchdog.py"
PIDFILE="$STATE/bridge.pid"

mkdir -p "$WAKE"
LOG="$STATE/bootstrap.log"
STATUS_FILE="$STATE/bootstrap.status"
exec > >(tee -a "$LOG") 2>&1
printf 'START %s\n' "$(date '+%Y-%m-%d %H:%M:%S %z')" > "$STATUS_FILE"
echo "Crypto Signal continuity bootstrap"
echo "Requesting Terminal -> Safari automation access..."

URL=$(/usr/bin/osascript <<'APPLESCRIPT'
tell application "Safari"
  try
    return URL of current tab of front window as text
  on error errMsg number errNum
    error errMsg number errNum
  end try
end tell
APPLESCRIPT
)
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "ERROR: Terminal could not read Safari current tab."
  echo "In macOS Automation permission prompt, allow Terminal to control Safari."
  echo "Then run this helper again."
  echo "FAIL automation_read rc=$RC" > "$STATUS_FILE"
  sleep 15
  exit 2
fi

case "$URL" in
  https://chatgpt.com/c/*) ;;
  *)
    echo "ERROR: Safari current tab is not a ChatGPT conversation:"
    echo "$URL"
    echo "Select this Crypto Signal chat tab in Safari and run helper again."
    echo "FAIL wrong_chat_url $URL" > "$STATUS_FILE"
    sleep 15
    exit 3
    ;;
esac

mkdir -p "$SHARED"
write_atomic() {
  destination="$1"
  mode="$2"
  value="$3"
  tmp="$destination.$"
  printf '%s\n' "$value" > "$tmp"
  chmod "$mode" "$tmp"
  mv "$tmp" "$destination"
}

write_atomic "$TARGET" 600 "$URL"
write_atomic "$EXPECTED" 600 "$URL"
write_atomic "$SHARED_TARGET" 660 "$URL"
write_atomic "$SHARED_EXPECTED" 660 "$URL"
write_atomic "$SHARED_NAMESPACE" 660 "crypto-signal"
echo "Bound exact chat URL to local/shared current+expected state."
JS_RESULT=$(/usr/bin/osascript - "$URL" <<'APPLESCRIPT'
on run argv
  set targetUrl to item 1 of argv
  tell application "Safari"
    repeat with w in windows
      repeat with t in tabs of w
        if (URL of t as text) is targetUrl then
          try
            return do JavaScript "document.location.href" in t
          on error errMsg number errNum
            return "JAVASCRIPT_ERROR:" & errNum & ":" & errMsg
          end try
        end if
      end repeat
    end repeat
  end tell
  return "TARGET_NOT_FOUND"
end run
APPLESCRIPT
)

case "$JS_RESULT" in
  https://chatgpt.com/c/*)
    echo "Safari JavaScript-from-Apple-Events test: PASS"
    ;;
  *)
    echo "ERROR: Safari JavaScript automation test failed:"
    echo "$JS_RESULT"
    echo "Enable Safari Develop -> Allow JavaScript from Apple Events, then rerun."
    echo "FAIL javascript_automation $JS_RESULT" > "$STATUS_FILE"
    sleep 20
    exit 4
    ;;
esac
OLDPID=""
[ -f "$PIDFILE" ] && OLDPID=$(cat "$PIDFILE" 2>/dev/null || true)
if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
  echo "Bridge already running: PID $OLDPID"
else
  nohup /usr/bin/python3 "$BRIDGE" \
    >> "$STATE/bridge.stdout.log" 2>&1 </dev/null &
  NEWPID=$!
  echo "Bridge started: PID $NEWPID"
fi

echo "CRYPTO_SIGNAL_CONTINUITY_BOOTSTRAP=PASS"
echo "PASS $(date '+%Y-%m-%d %H:%M:%S %z')" > "$STATUS_FILE"
echo "You may close this Terminal window."
sleep 8
