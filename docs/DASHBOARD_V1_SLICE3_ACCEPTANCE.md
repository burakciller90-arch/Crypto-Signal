# Dashboard V1 Slice 3 Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## PRODUCT/STABLE isolation
A dedicated product worktree now exists:

/Users/crypto-signal-agent/Crypto-Signal-Product

Pinned accepted commit:

b1cd19fdecb80e8793d8b3db584f21de726c460c

The product runtime does not import the mutable development working tree.

## Product-local environment
PRODUCT/STABLE owns its own .venv created from the accepted uv.lock.

Verified runtime:
- CPython 3.12.14
- FastAPI 0.141.1
- Uvicorn 0.53.0
- product imports PASS

The product worktree remains detached and clean.

## Persistent local runtime
LaunchAgent:

com.cryptosignal.dashboard

Program:
- PRODUCT/STABLE .venv Python
- PRODUCT/STABLE ops/run_dashboard.py

Binding:
- host 127.0.0.1
- port 48700

Production ledger:
- /Users/crypto-signal-agent/Crypto-Signal/runtime/ledger/live_signal_ledger.sqlite3

The web application opens ledger data read-only through DashboardReader.

No network bind beyond localhost exists.

## LaunchAgent behavior
Configured:
- RunAtLoad=true
- KeepAlive=true
- ThrottleInterval=5

Logs:
- runtime/dashboard/dashboard.out.log
- runtime/dashboard/dashboard.err.log

## Runtime acceptance
Initial launch:
- LaunchAgent state=running
- port 48700 LISTEN on 127.0.0.1 only
- /api/health -> HTTP 200
- ledger_present=true
- read_only=true
- REAL_CAPITAL=0

## KeepAlive acceptance
Original child PID:
58609

The child was intentionally terminated.

Launchd restarted the dashboard:
- runs increased to 2
- replacement PID=59520
- port 48700 returned LISTEN
- /api/health returned HTTP 200 after restart
- Uvicorn logs show clean shutdown of old process and clean startup of new process

This proves the persistent product runtime can recover from a child-process exit.

## Isolation
LIVE/STABLE forward evidence clock remains separate at:

/Users/crypto-signal-agent/Crypto-Signal-Live

PRODUCT/STABLE does not own or mutate:
- evidence clock
- signal freezes
- outcome logic
- exchange ingestion
- Durdurulmaz
- Quantum Capital

## User access
While the crypto-signal-agent GUI session is active, the dashboard is available locally at:

http://127.0.0.1:48700

The current shell is evidence-oriented and read-only.

## Canonical next frontier
Dashboard V1 Slice 4:
- richer Signal Detail from frozen bundle evidence
- Historical Evaluation metric projection into Performance
- explicit retrospective / walk-forward / untouched-forward tabs
- provider / symbol / timeframe navigation
- clearer uncertainty and methodology agreement presentation
- UI polish and responsive behavior
- no mock data masquerading as real
- no execution controls

REAL_CAPITAL remains 0.
