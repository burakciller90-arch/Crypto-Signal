#!/bin/bash
set -euo pipefail

ROOT="/Volumes/Crypto-504/Crypto-Signal"
STABLE="$ROOT/MarketTape"
PYTHON="$ROOT/Development/.venv/bin/python"
RUNTIME="$STABLE/ops/run_market_tape_runtime.py"

if [ "$(id -u)" != "504" ]; then
  echo "MARKET_TAPE_LAUNCH_ERROR=UID_MISMATCH expected=504 actual=$(id -u)" >&2
  exit 75
fi

if [ ! -d "$ROOT" ] || [ ! -d "$STABLE" ]; then
  echo "MARKET_TAPE_LAUNCH_ERROR=SSD_STABLE_ROOT_MISSING" >&2
  exit 75
fi

for required in "$PYTHON" "$STABLE/src/crypto_signal" "$RUNTIME"; do
  if [ ! -e "$required" ]; then
    echo "MARKET_TAPE_LAUNCH_ERROR=REQUIRED_FILE_MISSING path=$required" >&2
    exit 75
  fi
done

export HOME="/Users/crypto-signal-agent"
export PYTHONPATH="$STABLE/src"
cd "$STABLE"
exec "$PYTHON" "$RUNTIME"
