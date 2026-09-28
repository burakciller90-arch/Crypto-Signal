#!/bin/bash
set -u
unset RUNNER_TRACKING_ID

ROOT="${CRYPTO_SIGNAL_ROOT:-/Volumes/Crypto-504/Crypto-Signal}"
DEV="$ROOT/Development"
LIVE="$ROOT/Live"
PRODUCT="$ROOT/Product"
ALERTS="$ROOT/Alerts"
PAPER="$ROOT/Paper"
WRAPPER="$ROOT/ssd-clock-wrapper.py"
LOGDIR="$ROOT/ServiceLogs"
BYBIT_REST_BASE_URL="${CRYPTO_SIGNAL_BYBIT_REST_BASE_URL:-https://api.bybit.tr}"
BYBIT_OPTIONS_REST_BASE_URL="${CRYPTO_SIGNAL_BYBIT_OPTIONS_REST_BASE_URL:-$BYBIT_REST_BASE_URL}"
BYBIT_WS_URL="${CRYPTO_SIGNAL_BYBIT_WS_URL:-wss://stream.bybit.tr/v5/public/spot}"
BYBIT_LIQUIDATION_WS_URL="${CRYPTO_SIGNAL_BYBIT_LIQUIDATION_WS_URL:-wss://stream.bybit.com/v5/public/linear}"
BINANCE_REST_BASE_URL="${CRYPTO_SIGNAL_BINANCE_REST_BASE_URL:-https://api.binance.me}"
BINANCE_API_VARIANT="${CRYPTO_SIGNAL_BINANCE_API_VARIANT:-tr_main}"

case "$BYBIT_REST_BASE_URL" in
  https://*) ;;
  *)
    echo "RUNTIME_INVALID_BYBIT_REST_URL=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac
case "$BYBIT_OPTIONS_REST_BASE_URL" in
  https://*) ;;
  *)
    echo "RUNTIME_INVALID_BYBIT_OPTIONS_REST_URL=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac
case "$BYBIT_WS_URL" in
  wss://*) ;;
  *)
    echo "RUNTIME_INVALID_BYBIT_WS_URL=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac
case "$BYBIT_LIQUIDATION_WS_URL" in
  wss://*) ;;
  *)
    echo "RUNTIME_INVALID_BYBIT_LIQUIDATION_WS_URL=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac
case "$BINANCE_REST_BASE_URL" in
  https://*) ;;
  *)
    echo "RUNTIME_INVALID_BINANCE_REST_URL=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac
case "$BINANCE_API_VARIANT" in
  global|tr_main) ;;
  *)
    echo "RUNTIME_INVALID_BINANCE_API_VARIANT=YES FAIL_CLOSED=YES REAL_CAPITAL=0" >&2
    exit 75
    ;;
esac

for required in "$DEV" "$LIVE" "$PRODUCT" "$ALERTS" "$PAPER"; do
  if [ ! -d "$required" ]; then
    echo "RUNTIME_REQUIRED_DIR_MISSING=$required" >&2
    exit 75
  fi
done
for required in   "$PRODUCT/.venv/bin/python"   "$PRODUCT/ops/run_dashboard.py"   "$DEV/.venv/bin/python"   "$DEV/ops/run_live_evidence_clock.py"   "$ALERTS/.venv/bin/python"   "$PAPER/.venv/bin/python"   "$WRAPPER"; do
  if [ ! -e "$required" ]; then
    echo "RUNTIME_REQUIRED_FILE_MISSING=$required" >&2
    exit 75
  fi
done

mkdir -p "$LOGDIR"
exec >>"$LOGDIR/supervisor.log" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S %z') supervisor_r11_start pid=$ root=$ROOT bybit_rest=$BYBIT_REST_BASE_URL bybit_ws=$BYBIT_WS_URL binance_rest=$BINANCE_REST_BASE_URL binance_variant=$BINANCE_API_VARIANT"

dashboard_pid_is_expected() {
  local pid="$1"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  ps -p "$pid" -o command= 2>/dev/null     | grep -F "$PRODUCT/ops/run_dashboard.py"     | grep -F -- "--port 48700" >/dev/null 2>&1
}

dashboard_health_ok() {
  curl -fsS --max-time 3 http://127.0.0.1:48700/api/health >/dev/null 2>&1
}

stop_dashboard_pid() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  dashboard_pid_is_expected "$pid" || return 0
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..10}; do
    kill -0 "$pid" >/dev/null 2>&1 || return 0
    sleep 0.2
  done
  kill -KILL "$pid" >/dev/null 2>&1 || true
}

adopt_healthy_dashboard() {
  curl -fsS --max-time 3 http://127.0.0.1:48700/api/health >/dev/null 2>&1 || return 1
  local pid=""
  pid="$(/usr/sbin/lsof -nP -iTCP:48700 -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
  dashboard_pid_is_expected "$pid" || return 1
  echo "$pid" > "$ROOT/dashboard.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') dashboard_adopted pid=$pid"
  return 0
}

start_dashboard() {
  local pid=""
  if [ -f "$ROOT/dashboard.pid" ]; then
    pid="$(cat "$ROOT/dashboard.pid" 2>/dev/null || true)"
  fi
  if dashboard_pid_is_expected "$pid"; then
    if dashboard_health_ok; then
      return 0
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') dashboard_unhealthy pid=$pid action=restart"
    stop_dashboard_pid "$pid"
  elif [ -n "$pid" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') stale_dashboard_pid=$pid"
  fi
  rm -f "$ROOT/dashboard.pid"

  if adopt_healthy_dashboard; then
    return 0
  fi

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$PRODUCT/src"
    cd "$PRODUCT" || exit 75
    exec "$PRODUCT/.venv/bin/python" "$PRODUCT/ops/run_dashboard.py"       --host 127.0.0.1       --port 48700       --ledger "$DEV/runtime/ledger/live_signal_ledger.sqlite3"       --alert-outbox "$DEV/runtime/alerts/alert_outbox.sqlite3"       --paper-ledger "$DEV/runtime/paper/paper_fund.sqlite3"       --candle-cache "$DEV/runtime/data/live_base_15m_cache.sqlite3"
  ) >>"$LOGDIR/dashboard.out.log" 2>>"$LOGDIR/dashboard.err.log" < /dev/null &
  pid=$!
  echo "$pid" > "$ROOT/dashboard.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') dashboard_started pid=$pid"
}

run_clock() {
  local kind="$1"
  local py="$2"
  local src="$3"
  if [ ! -x "$py" ] || [ ! -d "$src" ] || [ ! -f "$WRAPPER" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %z') clock_not_ready kind=$kind"
    return 0
  fi
  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$src"
    exec "$py" "$WRAPPER" "$kind"
  ) >>"$LOGDIR/$kind.out.log" 2>>"$LOGDIR/$kind.err.log" < /dev/null &
}

market_tape_pid_is_owned() {
  local pid="$1"
  local runner="$DEV/ops/run_market_tape_stream.py"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  /bin/ps -ww -p "$pid" -o uid=,args= 2>/dev/null \
    | /usr/bin/awk -v runner="$runner" '
        {
          if ($1 != 504) {
            exit 1
          }
          for (i = 2; i <= NF; i++) {
            if ($i == runner) {
              exit 0
            }
          }
          exit 1
        }
      '
}

market_tape_pid_is_expected() {
  local pid="$1"
  local runner="$DEV/ops/run_market_tape_stream.py"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  /bin/ps -ww -p "$pid" -o uid=,args= 2>/dev/null \
    | /usr/bin/awk -v runner="$runner" -v ws="$BYBIT_WS_URL" '
        {
          if ($1 != 504) {
            exit 1
          }
          runner_ok = 0
          ws_ok = 0
          for (i = 2; i <= NF; i++) {
            if ($i == runner) {
              runner_ok = 1
            }
            if ($i == "--bybit-ws-url" && i < NF && $(i + 1) == ws) {
              ws_ok = 1
            }
          }
          exit(runner_ok && ws_ok ? 0 : 1)
        }
      '
}

market_tape_pidfile_age_seconds() {
  local pidfile="$1"
  local modified=""
  [ -f "$pidfile" ] || return 1
  modified="$(stat -f '%m' "$pidfile" 2>/dev/null || true)"
  [ -n "$modified" ] || return 1
  echo $(( $(date +%s) - modified ))
}

market_tape_pid_is_healthy() {
  local pid="$1"
  local py="$DEV/.venv/bin/python"
  local runtime_db="$DEV/runtime/market_tape/collector_runtime.sqlite3"
  [ -x "$py" ] || return 1
  [ -f "$runtime_db" ] || return 1
  "$py" - "$runtime_db" "$pid" <<'PY' >/dev/null 2>&1
import json
import sqlite3
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
pid = int(sys.argv[2])
now_ms = time.time_ns() // 1_000_000
uri = f"{path.resolve().as_uri()}?mode=ro"
with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    row = db.execute(
        """
        SELECT instance_identity, process_id, payload_json
        FROM collector_instances
        ORDER BY started_at_ms DESC, instance_identity DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None or int(row["process_id"]) != pid:
        raise SystemExit(1)
    heartbeat = db.execute(
        """
        SELECT payload_json
        FROM collector_heartbeats
        WHERE instance_identity=?
        ORDER BY sequence_no DESC
        LIMIT 1
        """,
        (str(row["instance_identity"]),),
    ).fetchone()
    if heartbeat is None:
        raise SystemExit(1)
payload = json.loads(str(heartbeat["payload_json"]))
observed_at_ms = int(payload["observed_at_ms"])
if observed_at_ms > now_ms or now_ms - observed_at_ms > 30_000:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

stop_market_tape_pid() {
  local pid="$1"
  market_tape_pid_is_owned "$pid" || return 0
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    kill -0 "$pid" >/dev/null 2>&1 || return 0
    sleep 0.1
  done
  kill -KILL "$pid" >/dev/null 2>&1 || true
}

adopt_market_tape_stream() {
  local lock="$DEV/runtime/market_tape/market_tape_stream.lock"
  local pid=""
  [ -f "$lock" ] || return 1
  pid="$(/usr/sbin/lsof -t "$lock" 2>/dev/null | head -1 || true)"
  if ! market_tape_pid_is_expected "$pid"; then
    if market_tape_pid_is_owned "$pid"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_stale_config pid=$pid action=restart"
      stop_market_tape_pid "$pid"
    fi
    return 1
  fi
  echo "$pid" > "$ROOT/market-tape-stream.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_adopted pid=$pid"
  return 0
}

start_market_tape_stream() {
  local pid=""
  local pidfile="$ROOT/market-tape-stream.pid"
  local py="$DEV/.venv/bin/python"
  local runner="$DEV/ops/run_market_tape_stream.py"
  local runtime="$DEV/runtime/market_tape"
  local db="$runtime/market_tape.sqlite3"
  local raw="$runtime/raw_market_tape.sqlite3"
  local lock="$runtime/market_tape_stream.lock"
  local collector_runtime="$runtime/collector_runtime.sqlite3"
  local gaps="$runtime/market_data_gaps.sqlite3"

  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if market_tape_pid_is_expected "$pid"; then
      if market_tape_pid_is_healthy "$pid"; then
        return 0
      fi
      age="$(market_tape_pidfile_age_seconds "$pidfile" || echo 999999)"
      if [ "$age" -le 45 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_startup_grace pid=$pid age_s=$age"
        return 0
      fi
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_unhealthy pid=$pid age_s=$age action=restart"
      stop_market_tape_pid "$pid"
    elif market_tape_pid_is_owned "$pid"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_stale_config pid=$pid action=restart"
      stop_market_tape_pid "$pid"
    fi
    rm -f "$pidfile"
  fi

  if adopt_market_tape_stream; then
    return 0
  fi

  for required in "$py" "$runner" "$db" "$raw"; do
    if [ ! -e "$required" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_not_ready missing=$required FAIL_CLOSED=YES REAL_CAPITAL=0"
      return 0
    fi
  done

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$DEV:$DEV/src"
    cd "$DEV" || exit 75
    exec "$py" "$runner" \
      --db "$db" \
      --raw-db "$raw" \
      --lock-path "$lock" \
      --runtime-status-db "$collector_runtime" \
      --gap-ledger-db "$gaps" \
      --bybit-ws-url "$BYBIT_WS_URL" \
      --symbols BTCUSDT ETHUSDT SOLUSDT \
      --depth 50 \
      --orderbook-snapshot-interval-ms 1000 \
      --heartbeat-interval-ms 10000 \
      --max-ingestion-silence-ms 60000 \
      --max-events 0
  ) >>"$LOGDIR/market-tape.out.log" 2>>"$LOGDIR/market-tape.err.log" < /dev/null &
  pid="$!"
  echo "$pid" > "$pidfile"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_started pid=$pid REAL_CAPITAL=0"
}

liquidation_pid_is_owned() {
  local pid="$1"
  local runner="$DEV/ops/run_liquidation_market_tape_stream.py"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  /bin/ps -ww -p "$pid" -o uid=,args= 2>/dev/null \
    | /usr/bin/awk -v runner="$runner" '
        {
          if ($1 != 504) {
            exit 1
          }
          for (i = 2; i <= NF; i++) {
            if ($i == runner) {
              exit 0
            }
          }
          exit 1
        }
      '
}

liquidation_pid_is_expected() {
  local pid="$1"
  local runner="$DEV/ops/run_liquidation_market_tape_stream.py"
  local uid=""
  local command=""
  [ -n "$pid" ] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1

  uid="$(/bin/ps -p "$pid" -o uid= 2>/dev/null | /usr/bin/tr -d ' ')"
  [ "$uid" = "504" ] || return 1
  command="$(/bin/ps -ww -p "$pid" -o command= 2>/dev/null || true)"
  [ -n "$command" ] || return 1

  printf '%s\n' "$command" \
    | /usr/bin/grep -F "$runner" >/dev/null 2>&1 || return 1
  printf '%s\n' "$command" \
    | /usr/bin/grep -F -- "--bybit-ws-url $BYBIT_LIQUIDATION_WS_URL" \
      >/dev/null 2>&1 || return 1
  printf '%s\n' "$command" \
    | /usr/bin/grep -F -- "--max-messages 0" >/dev/null 2>&1 || return 1
  printf '%s\n' "$command" \
    | /usr/bin/grep -F -- "--heartbeat-interval-ms 10000" \
      >/dev/null 2>&1 || return 1
  printf '%s\n' "$command" \
    | /usr/bin/grep -F -- "--max-transport-silence-ms 45000" \
      >/dev/null 2>&1 || return 1
}

liquidation_pid_is_healthy() {
  local pid="$1"
  local py="$DEV/.venv/bin/python"
  local runtime_db="$DEV/runtime/market_tape/liquidation_collector_runtime.sqlite3"
  [ -x "$py" ] || return 1
  [ -f "$runtime_db" ] || return 1
  "$py" - "$runtime_db" "$pid" <<'PY' >/dev/null 2>&1
import json
import sqlite3
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
pid = int(sys.argv[2])
now_ms = time.time_ns() // 1_000_000
uri = f"{path.resolve().as_uri()}?mode=ro"
with sqlite3.connect(uri, uri=True, timeout=5.0) as db:
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    instance = db.execute(
        """
        SELECT instance_identity, process_id
        FROM collector_instances
        WHERE provider='bybit' AND source='liquidation_stream'
        ORDER BY started_at_ms DESC, instance_identity DESC
        LIMIT 1
        """
    ).fetchone()
    if instance is None or int(instance["process_id"]) != pid:
        raise SystemExit(1)
    heartbeat = db.execute(
        """
        SELECT payload_json
        FROM collector_heartbeats
        WHERE instance_identity=?
        ORDER BY sequence_no DESC
        LIMIT 1
        """,
        (str(instance["instance_identity"]),),
    ).fetchone()
    coverage = db.execute(
        """
        SELECT payload_json
        FROM liquidation_connection_coverage
        WHERE instance_identity=?
        ORDER BY sequence_no DESC
        LIMIT 1
        """,
        (str(instance["instance_identity"]),),
    ).fetchone()
    if heartbeat is None or coverage is None:
        raise SystemExit(1)
heartbeat_payload = json.loads(str(heartbeat["payload_json"]))
coverage_payload = json.loads(str(coverage["payload_json"]))
for payload in (heartbeat_payload, coverage_payload):
    observed_at_ms = int(payload["observed_at_ms"])
    if observed_at_ms > now_ms or now_ms - observed_at_ms > 30_000:
        raise SystemExit(1)
if str(coverage_payload["state"]) != "connected":
    raise SystemExit(1)
raise SystemExit(0)
PY
}

stop_liquidation_pid() {
  local pid="$1"
  liquidation_pid_is_owned "$pid" || return 0
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    kill -0 "$pid" >/dev/null 2>&1 || return 0
    sleep 0.1
  done
  kill -KILL "$pid" >/dev/null 2>&1 || true
}

adopt_liquidation_stream() {
  local lock="$DEV/runtime/market_tape/liquidation_stream.lock"
  local pid=""
  [ -f "$lock" ] || return 1
  pid="$(/usr/sbin/lsof -t "$lock" 2>/dev/null | head -1 || true)"
  if ! liquidation_pid_is_expected "$pid"; then
    if liquidation_pid_is_owned "$pid"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_stale_config pid=$pid action=restart"
      stop_liquidation_pid "$pid"
    fi
    return 1
  fi
  echo "$pid" > "$ROOT/liquidation-stream.pid"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_adopted pid=$pid"
  return 0
}

start_liquidation_stream() {
  local pid=""
  local age=""
  local pidfile="$ROOT/liquidation-stream.pid"
  local py="$DEV/.venv/bin/python"
  local runner="$DEV/ops/run_liquidation_market_tape_stream.py"
  local runtime="$DEV/runtime/market_tape"
  local db="$runtime/market_tape.sqlite3"
  local raw="$runtime/raw_market_tape.sqlite3"
  local lock="$runtime/liquidation_stream.lock"
  local collector_runtime="$runtime/liquidation_collector_runtime.sqlite3"

  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if liquidation_pid_is_expected "$pid"; then
      if liquidation_pid_is_healthy "$pid"; then
        return 0
      fi
      age="$(market_tape_pidfile_age_seconds "$pidfile" || echo 999999)"
      if [ "$age" -le 60 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_startup_grace pid=$pid age_s=$age"
        return 0
      fi
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_unhealthy pid=$pid age_s=$age action=restart"
      stop_liquidation_pid "$pid"
    elif liquidation_pid_is_owned "$pid"; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_stale_config pid=$pid action=restart"
      stop_liquidation_pid "$pid"
    fi
    rm -f "$pidfile"
  fi

  if adopt_liquidation_stream; then
    return 0
  fi

  for required in "$py" "$runner" "$db" "$raw"; do
    if [ ! -e "$required" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_not_ready missing=$required FAIL_CLOSED=YES REAL_CAPITAL=0"
      return 0
    fi
  done

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$DEV:$DEV/src"
    cd "$DEV" || exit 75
    exec "$py" "$runner" \
      --db "$db" \
      --raw-db "$raw" \
      --lock-path "$lock" \
      --runtime-status-db "$collector_runtime" \
      --bybit-ws-url "$BYBIT_LIQUIDATION_WS_URL" \
      --symbols BTCUSDT ETHUSDT SOLUSDT \
      --heartbeat-interval-ms 10000 \
      --max-transport-silence-ms 45000 \
      --max-messages 0
  ) >>"$LOGDIR/liquidation.out.log" 2>>"$LOGDIR/liquidation.err.log" < /dev/null &
  pid="$!"
  echo "$pid" > "$pidfile"
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') liquidation_started pid=$pid REAL_CAPITAL=0"
}

run_market_tape_snapshot_clock() {
  local py="$DEV/.venv/bin/python"
  local runner="$DEV/ops/run_market_tape_snapshot.py"
  local runtime="$DEV/runtime/market_tape"
  local db="$runtime/market_tape.sqlite3"
  local source_contract="$runtime/source_contract.sqlite3"
  local options="$runtime/options_surface.sqlite3"
  local lock="$runtime/market_tape_snapshot.lock"

  for required in "$py" "$runner" "$db"; do
    if [ ! -e "$required" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') market_tape_snapshot_not_ready missing=$required FAIL_CLOSED=YES REAL_CAPITAL=0"
      return 0
    fi
  done

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$DEV:$DEV/src"
    cd "$DEV" || exit 75
    exec "$py" "$runner" \
      --db "$db" \
      --lock-path "$lock" \
      --bybit-base-url "$BYBIT_REST_BASE_URL" \
      --symbols BTCUSDT ETHUSDT SOLUSDT \
      --book-depth 50 \
      --trade-limit 60 \
      --oi-interval 15min \
      --oi-limit 16
  ) >>"$LOGDIR/market-tape-snapshot.out.log" 2>>"$LOGDIR/market-tape-snapshot.err.log" < /dev/null &
}

run_wc2_live_clock() {
  local runtime="$DEV/runtime"
  local py="$DEV/.venv/bin/python"
  local runner="$DEV/ops/run_live_evidence_clock.py"
  local ledger="$runtime/ledger/live_signal_ledger.sqlite3"
  local candle="$runtime/data/live_base_15m_cache.sqlite3"
  local divergence="$runtime/data/provider_divergence.sqlite3"
  local policy="$runtime/wc2/wc2_forward_policy.sqlite3"
  local epoch2="$runtime/paper/paper_fund_epoch2.sqlite3"
  local protocol="$runtime/wc2/wc2_collection_protocol.wc2-collection-protocol.sqlite3"
  local prepared="$runtime/wc2/wc2.wc2-prepared.sqlite3"
  local decision="$runtime/decision/decision_evidence.sqlite3"
  local stream="$runtime/stream/intelligence_stream.sqlite3"
  local market_tape="$runtime/market_tape/market_tape.sqlite3"
  local options_surface="$runtime/market_tape/options_surface.sqlite3"
  local event_source="$runtime/events/event_source.sqlite3"
  local cohort="$runtime/wc2/wc2_untouched_forward.sqlite3"
  local shadow_intent="$runtime/wc2/wc2.shadow-intent.sqlite3"
  local shadow_cycle="$runtime/wc2/wc2.shadow-cycle.sqlite3"
  local execution_protocol="$runtime/wc2/wc2_paper_execution.wc2-paper-execution-protocol.sqlite3"
  local execution_runtime="$runtime/wc2/wc2_paper_execution.wc2-paper-execution-runtime.sqlite3"
  local execution_journal="$runtime/wc2/wc2_paper_execution.wc2-paper-execution.sqlite3"
  local venue_rules="$runtime/paper/paper_fund.sqlite3"

  for required in "$py" "$runner" "$ledger" "$candle" "$market_tape" "$event_source" "$policy" "$epoch2" "$protocol" "$execution_protocol" "$execution_runtime" "$venue_rules"; do
    if [ ! -e "$required" ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S %z') wc2_live_not_ready missing=$required FAIL_CLOSED=YES REAL_CAPITAL=0"
      return 0
    fi
  done

  (
    unset RUNNER_TRACKING_ID
    export PYTHONPATH="$DEV:$DEV/src"
    cd "$DEV" || exit 75
    exec "$py" "$runner" \
      --db "$ledger" \
      --candle-cache "$candle" \
      --provider-divergence "$divergence" \
      --bybit-base-url "$BYBIT_REST_BASE_URL" \
      --binance-base-url "$BINANCE_REST_BASE_URL" \
      --binance-api-variant "$BINANCE_API_VARIANT" \
      --stream-enabled \
      --stream-ledger "$stream" \
      --stream-market-tape "$market_tape" \
      --stream-event-source "$event_source" \
      --stream-family-symbols BTCUSDT ETHUSDT SOLUSDT \
      --wc2-enabled \
      --wc2-policy "$policy" \
      --wc2-epoch2 "$epoch2" \
      --wc2-collection-protocol "$protocol" \
      --wc2-prepared "$prepared" \
      --wc2-decision-evidence "$decision" \
      --wc2-cohort "$cohort" \
      --wc2-shadow-intent "$shadow_intent" \
      --wc2-shadow-cycle "$shadow_cycle" \
      --wc2-execution-enabled \
      --wc2-execution-protocol "$execution_protocol" \
      --wc2-execution-runtime "$execution_runtime" \
      --wc2-execution-journal "$execution_journal" \
      --wc2-venue-rules "$venue_rules"
  ) >>"$LOGDIR/live.out.log" 2>>"$LOGDIR/live.err.log" < /dev/null &
}

bound_logs() {
  local helper="$DEV/ops/bound_runtime_logs.py"
  local python="$DEV/.venv/bin/python"
  if [ -x "$python" ] && [ -f "$helper" ]; then
    PYTHONPATH="$DEV/src" "$python" "$helper"       --log-dir "$LOGDIR"       --max-bytes 16777216       --keep-bytes 8388608       >>"$LOGDIR/log-rotation.log" 2>>"$LOGDIR/log-rotation.err.log" || true
  fi
}

shutdown() {
  echo "$(date '+%Y-%m-%d %H:%M:%S %z') supervisor_r11_stop pid=$$"
  exit 0
}
trap shutdown TERM INT

last_data_clock=0
last_aux_clock=0
last_rotation=0
while true; do
  start_dashboard
  start_liquidation_stream
  start_market_tape_stream
  now="$(date +%s)"

  if [ $((now-last_data_clock)) -ge 60 ]; then
    run_market_tape_snapshot_clock
    run_wc2_live_clock
    last_data_clock="$now"
  fi

  if [ $((now-last_aux_clock)) -ge 120 ]; then
    run_clock alert "$ALERTS/.venv/bin/python" "$ALERTS/src"
    run_clock paper "$PAPER/.venv/bin/python" "$PAPER/src"
    run_clock dry "$PAPER/.venv/bin/python" "$PAPER/src"
    last_aux_clock="$now"
  fi

  if [ $((now-last_rotation)) -ge 300 ]; then
    bound_logs
    last_rotation="$now"
  fi

  sleep 10
done
