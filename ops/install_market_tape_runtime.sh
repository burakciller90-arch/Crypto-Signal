#!/bin/bash
set -euo pipefail

LABEL="com.cryptosignal.markettape"
UID_EXPECTED="504"
ROOT="/Volumes/Crypto-504/Crypto-Signal"
STABLE="$ROOT/MarketTape"
PLIST_SOURCE="$STABLE/ops/market_tape/launchd/$LABEL.plist"
PLIST_TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
COLD_ENV="$ROOT/RuntimeEnvs/market-tape-cold"
COLD_ENV_NEXT="$ROOT/RuntimeEnvs/market-tape-cold.next"
COLD_ENV_PREVIOUS="$ROOT/RuntimeEnvs/market-tape-cold.previous"
COLD_PYTHON="$COLD_ENV/bin/python"
UV="/Users/crypto-signal-agent/.local/bin/uv"
PYARROW_VERSION="22.0.0"

if [ "$(id -u)" != "$UID_EXPECTED" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=UID_MISMATCH expected=$UID_EXPECTED actual=$(id -u)" >&2
  exit 2
fi

if [ ! -d "$ROOT" ] || [ ! -d "$STABLE" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=SSD_STABLE_ROOT_MISSING" >&2
  exit 3
fi

for required in   "$ROOT/Development/.venv/bin/python"   "$STABLE/src/crypto_signal"   "$STABLE/ops/run_market_tape_runtime.py"   "$STABLE/ops/market_tape/archive_hot_to_parquet.py"   "$STABLE/ops/market_tape/run_market_tape_launchd.sh"   "$PLIST_SOURCE"   "$UV"; do
  if [ ! -e "$required" ]; then
    echo "MARKET_TAPE_INSTALL_ERROR=REQUIRED_FILE_MISSING path=$required" >&2
    exit 4
  fi
done

if ! /usr/bin/plutil -lint "$PLIST_SOURCE" >/dev/null; then
  echo "MARKET_TAPE_INSTALL_ERROR=PLIST_INVALID" >&2
  exit 5
fi

mkdir -p "$ROOT/RuntimeEnvs"
current_pyarrow=""
if [ -x "$COLD_PYTHON" ]; then
  current_pyarrow="$("$COLD_PYTHON" -c 'import pyarrow; print(pyarrow.__version__)' 2>/dev/null || true)"
fi
if [ "$current_pyarrow" != "$PYARROW_VERSION" ]; then
  rm -rf "$COLD_ENV_NEXT"
  "$UV" venv --python 3.12 "$COLD_ENV_NEXT"
  "$UV" pip install --python "$COLD_ENV_NEXT/bin/python" "pyarrow==$PYARROW_VERSION"
  next_pyarrow="$("$COLD_ENV_NEXT/bin/python" -c 'import pyarrow, pyarrow.parquet; print(pyarrow.__version__)')"
  if [ "$next_pyarrow" != "$PYARROW_VERSION" ]; then
    echo "MARKET_TAPE_INSTALL_ERROR=COLD_ENV_VERIFY_FAILED version=$next_pyarrow" >&2
    rm -rf "$COLD_ENV_NEXT"
    exit 6
  fi
  rm -rf "$COLD_ENV_PREVIOUS"
  if [ -d "$COLD_ENV" ]; then
    mv "$COLD_ENV" "$COLD_ENV_PREVIOUS"
  fi
  mv "$COLD_ENV_NEXT" "$COLD_ENV"
fi

verified_pyarrow="$("$COLD_PYTHON" -c 'import pyarrow, pyarrow.parquet; print(pyarrow.__version__)')"
if [ "$verified_pyarrow" != "$PYARROW_VERSION" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=COLD_ENV_VERSION_MISMATCH version=$verified_pyarrow" >&2
  exit 7
fi
echo "MARKET_TAPE_COLD_ENV_PASS=YES pyarrow=$verified_pyarrow"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/ServiceLogs"
cp "$PLIST_SOURCE" "$PLIST_TARGET"
chmod 600 "$PLIST_TARGET"

/bin/launchctl disable "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
/bin/launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true

if [ "${MARKET_TAPE_INSTALL_ENABLE_LAUNCHD:-0}" = "1" ]; then
  echo "MARKET_TAPE_INSTALL_ERROR=DIRECT_LAUNCHD_TCC_UNSUPPORTED" >&2
  echo "MARKET_TAPE_LAUNCHAGENT_DISABLED_BY_TCC_POLICY=YES" >&2
  exit 78
fi

echo "MARKET_TAPE_LAUNCHAGENT_DISABLED_BY_DEFAULT=YES"
echo "MARKET_TAPE_LAUNCHAGENT_PREPARE_ONLY_PASS=YES"
echo "LABEL=$LABEL"
echo "STABLE_ROOT=$STABLE"
echo "REAL_CAPITAL=0"
