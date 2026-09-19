#!/bin/zsh
set -u
AGENT="$HOME/.local/bin/agent"

if [ ! -x "$AGENT" ]; then
  echo "Cursor agent is not installed."
  sleep 15
  exit 2
fi

echo "Crypto Signal Cursor worker authentication"
"$AGENT" login
RC=$?
echo
"$AGENT" status 2>&1 || true
echo "CURSOR_LOGIN_RC=$RC"
sleep 8
exit "$RC"
