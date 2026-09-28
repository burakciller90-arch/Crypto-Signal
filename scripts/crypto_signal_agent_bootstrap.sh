#!/usr/bin/env bash
set -euo pipefail

WB_ROOT="${CRYPTO_SIGNAL_WORKBENCH_ROOT:-/Volumes/Crypto-504/Crypto-Signal-Workbench}"
WB_REPO="${CRYPTO_SIGNAL_WORKBENCH_REPO:-$WB_ROOT/repo}"
RUNTIME_ROOT="${CRYPTO_SIGNAL_RUNTIME_ROOT:-/Volumes/Crypto-504/Crypto-Signal}"
DEV="${CRYPTO_SIGNAL_DEVELOPMENT_ROOT:-$RUNTIME_ROOT/Development}"
DIV_DB="${CRYPTO_SIGNAL_DIVERGENCE_DB:-$DEV/runtime/data/provider_divergence.sqlite3}"

SELF_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "CRYPTO_AGENT_BOOTSTRAP_VERSION=1"
echo "BOOTSTRAP_UTC=$(/bin/date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "REAL_CAPITAL=0"
echo "SELF_ROOT=$SELF_ROOT"
echo "WORKBENCH_ROOT=$WB_ROOT"
echo "WORKBENCH_REPO=$WB_REPO"
echo "RUNTIME_ROOT=$RUNTIME_ROOT"
echo "DEVELOPMENT_ROOT=$DEV"
echo "CURRENT_UID=$(id -u)"
echo "CURRENT_USER=$(id -un)"

echo "=== CHECKOUT GIT ==="
if /usr/bin/git -C "$SELF_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "CHECKOUT_HEAD=$(/usr/bin/git -C "$SELF_ROOT" rev-parse HEAD)"
  echo "CHECKOUT_BRANCH=$(/usr/bin/git -C "$SELF_ROOT" branch --show-current || true)"
  echo "CHECKOUT_DIRTY_COUNT=$(/usr/bin/git -C "$SELF_ROOT" status --porcelain | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
else
  echo "CHECKOUT_GIT=NO"
fi

echo "=== WORKBENCH GIT ==="
if [[ -d "$WB_REPO/.git" ]]; then
  echo "WORKBENCH_PRESENT=YES"
  echo "WORKBENCH_HEAD=$(/usr/bin/git -C "$WB_REPO" rev-parse HEAD)"
  echo "WORKBENCH_BRANCH=$(/usr/bin/git -C "$WB_REPO" branch --show-current || true)"
  echo "WORKBENCH_DIRTY_COUNT=$(/usr/bin/git -C "$WB_REPO" status --porcelain | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
  echo "WORKBENCH_ORIGIN=$(/usr/bin/git -C "$WB_REPO" remote get-url origin || true)"
else
  echo "WORKBENCH_PRESENT=NO"
fi

echo "=== DEVELOPMENT RUNTIME ==="
if [[ -d "$DEV" ]]; then
  echo "DEVELOPMENT_PRESENT=YES"
  if /usr/bin/git -C "$DEV" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "DEVELOPMENT_GIT=YES"
    echo "DEVELOPMENT_HEAD=$(/usr/bin/git -C "$DEV" rev-parse HEAD)"
    echo "DEVELOPMENT_BRANCH=$(/usr/bin/git -C "$DEV" branch --show-current || true)"
    echo "DEVELOPMENT_DIRTY_COUNT=$(/usr/bin/git -C "$DEV" status --porcelain | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
  else
    echo "DEVELOPMENT_GIT=NO"
  fi
  [[ -x "$DEV/.venv/bin/python" ]] && echo "DEVELOPMENT_VENV=YES" || echo "DEVELOPMENT_VENV=NO"
else
  echo "DEVELOPMENT_PRESENT=NO"
fi

for pidfile in "$RUNTIME_ROOT/ssd-service-supervisor.pid" "$RUNTIME_ROOT/dashboard.pid"; do
  if [[ -f "$pidfile" ]]; then
    pid="$(/bin/cat "$pidfile" 2>/dev/null || true)"
    echo "PID_FILE=$pidfile|pid=$pid"
    if [[ "$pid" =~ ^[0-9]+$ ]] && /bin/kill -0 "$pid" 2>/dev/null; then
      echo "PID_ALIVE=$pid|YES"
    else
      echo "PID_ALIVE=$pid|NO"
    fi
  else
    echo "PID_FILE=$pidfile|MISSING"
  fi
done

echo "=== CANONICAL CONTEXT ==="
for rel in   "READ_FIRST_CRYPTO_SIGNAL.md"   "CURRENT_STATUS.md"   "PROJECT_CHRONICLE.md"   "ENVIRONMENT_REGISTRY.md"   "docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md"   "docs/agent/CURRENT_FRONTIER.md"
do
  p="$SELF_ROOT/$rel"
  echo "--- $rel ---"
  if [[ -f "$p" ]]; then
    case "$rel" in
      "CURRENT_STATUS.md")
        /usr/bin/sed -n '1,170p' "$p"
        ;;
      "docs/CRYPTO_SIGNAL_REALITY_BACKED_EVIDENCE_DATA_PLANE_V1.md")
        /usr/bin/awk '
          /^## RDP9 —/ {show=1}
          /^## RDP11 —/ {if(show){exit}}
          show {print}
        ' "$p"
        ;;
      "docs/agent/CURRENT_FRONTIER.md")
        /bin/cat "$p"
        ;;
      *)
        /usr/bin/head -80 "$p"
        ;;
    esac
  else
    echo "MISSING"
  fi
done

echo "=== RDP9 FILE SURFACE ==="
for rel in   "src/crypto_signal/intelligence/cross_venue_quality.py"   "src/crypto_signal/intelligence/evidence_overlap.py"   "src/crypto_signal/intelligence/confluence_matrix_v2.py"   "src/crypto_signal/unified_decision_runtime.py"   "src/crypto_signal/exact_decision_composition.py"   "tests/test_rdp9_cross_venue_quality.py"   "tests/test_rdp9_evidence_overlap.py"   "tests/test_rdp9_cross_venue_decision.py"
do
  [[ -f "$SELF_ROOT/$rel" ]] && echo "RDP9_FILE=$rel|PRESENT" || echo "RDP9_FILE=$rel|MISSING"
done

echo "=== PROVIDER DIVERGENCE DB READ-ONLY ==="
if [[ -r "$DIV_DB" ]]; then
  echo "DIVERGENCE_DB_READABLE=YES"
  /usr/bin/python3 -B - "$DIV_DB" <<'PY'
import json
import sqlite3
import sys

path=sys.argv[1]
con=sqlite3.connect(f"file:{path}?mode=ro",uri=True,timeout=2.0)
try:
    con.execute("pragma query_only=on")
    con.execute("pragma busy_timeout=2000")
    quick=con.execute("pragma quick_check").fetchone()[0]
    tables=[r[0] for r in con.execute(
        "select name from sqlite_master where type='table' order by name"
    )]
    counts={}
    for name in tables:
        try:
            counts[name]=int(con.execute(f'select count(*) from "{name}"').fetchone()[0])
        except Exception:
            counts[name]="UNREADABLE"
    print("DIVERGENCE_DB_QUICK_CHECK="+str(quick))
    print("DIVERGENCE_DB_TABLE_COUNTS="+json.dumps(counts,sort_keys=True))
finally:
    con.close()
PY
else
  echo "DIVERGENCE_DB_READABLE=NO"
fi

echo "RUNTIME_WRITE=NO"
echo "REAL_CAPITAL=0"
echo "DURDURULMAZ_TOUCHED=NO"
echo "QUANTUM_CAPITAL_TOUCHED=NO"
echo "CRYPTO_AGENT_BOOTSTRAP_COMPLETE=YES"
