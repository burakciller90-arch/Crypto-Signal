#!/bin/bash
set -euo pipefail

LABEL="com.cryptosignal.markettape"
UID_EXPECTED="504"
ROOT="/Volumes/Crypto-504/Crypto-Signal"
STABLE="$ROOT/MarketTape"
PLIST_SOURCE="$STABLE/ops/market_tape/launchd/$LABEL.plist"
PLIST_TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [ "$(id -u)" != "$UID_EXPECTED" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=UID_MISMATCH expected=$UID_EXPECTED actual=$(id -u)" >&2
  exit 2
fi

if [ ! -d "$ROOT" ] || [ ! -d "$STABLE" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=SSD_STABLE_ROOT_MISSING" >&2
  exit 3
fi

for required in   "$ROOT/Development/.venv/bin/python"   "$STABLE/src/crypto_signal"   "$STABLE/ops/run_market_tape_runtime.py"   "$STABLE/ops/market_tape/run_market_tape_launchd.sh"   "$PLIST_SOURCE"; do
  if [ ! -e "$required" ]; then
    echo "MARKET_TAPE_INSTALL_ERROR=REQUIRED_FILE_MISSING path=$required" >&2
    exit 4
  fi
done

if ! /usr/bin/plutil -lint "$PLIST_SOURCE" >/dev/null; then
  echo "MARKET_TAPE_INSTALL_ERROR=PLIST_INVALID" >&2
  exit 5
fi

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/ServiceLogs"
cp "$PLIST_SOURCE" "$PLIST_TARGET"
chmod 600 "$PLIST_TARGET"

/bin/launchctl disable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
/bin/launchctl enable "$DOMAIN/$LABEL"
/bin/launchctl bootstrap "$DOMAIN" "$PLIST_TARGET"
/bin/launchctl kickstart -k "$DOMAIN/$LABEL"

sleep 3
/bin/launchctl print "$DOMAIN/$LABEL" >/dev/null

echo "MARKET_TAPE_LAUNCHAGENT_INSTALL_PASS=YES"
echo "LABEL=$LABEL"
echo "STABLE_ROOT=$STABLE"
echo "REAL_CAPITAL=0"
