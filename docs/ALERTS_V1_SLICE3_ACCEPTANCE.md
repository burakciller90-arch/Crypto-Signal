# Alerts V1 Slice 3 Acceptance — Stable Materialize Runtime

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## ALERTS/STABLE isolation
A dedicated alerts worktree exists:

/Users/crypto-signal-agent/Crypto-Signal-Alerts

Pinned accepted commit:

f7108384e11af85e07848197f7733ff0a2e29740

The alerts runtime does not import mutable development source.

## Alerts-local environment
ALERTS/STABLE owns its own .venv created from the accepted uv.lock.

Import gate:
- Alert Clock import PASS
- AlertOutbox import PASS

The worktree is detached and clean.

## Persistent materialize-only runtime
LaunchAgent:

com.cryptosignal.alertclock

Program:
- ALERTS/STABLE .venv Python
- ALERTS/STABLE ops/run_alert_clock.py

Source ledger:
- runtime/ledger/live_signal_ledger.sqlite3
- opened read-only by Alert Clock

Production alert outbox:
- runtime/alerts/alert_outbox.sqlite3

Runtime policy:
- RunAtLoad=true
- StartInterval=120 seconds
- one-shot process
- no KeepAlive
- no --dispatch-local-noop
- no external provider

A not-running launchd state between intervals is expected for this one-shot job.

## Logs
- runtime/alerts/alert_clock.out.log
- runtime/alerts/alert_clock.err.log

## Runtime acceptance
First LaunchAgent run:
- runs=1
- last exit code=0
- signals=32
- lifecycle=32
- eligible=0
- inserted=0
- outbox events=0
- attempts=0
- stderr empty

Manual stable rerun:
- signals=32
- lifecycle=32
- eligible=0
- inserted=0
- unchanged=0
- outbox events=0
- attempts=0

Production source state:
- signal freezes=32
- WATCH=32
- lifecycle evaluations=32

The installed plist exactly matches the versioned project plist.

## Isolation
ALERTS/STABLE is independent from:
- LIVE/STABLE evidence clock
- PRODUCT/STABLE dashboard
- mutable development worktree
- Durdurulmaz
- Quantum Capital

No alert runtime modifies the immutable signal ledger.

## Delivery boundary
This stable runtime only materializes eligible alert events.

It does not mark an event delivered.

A future ACTIVE/INVALIDATED event will remain pending in the production alert
outbox until an accepted user-facing delivery adapter processes it.

This prevents a test/no-op sink from consuming real future notifications.

## Canonical next frontier
Alerts V1 Slice 4 — Alert Center and provider-ready presentation:
- add read-only Alert Center projection over production alert outbox
- expose pending/delivered/retryable/permanent state per sink without mutating outbox
- integrate Alert Center into Mission Control
- show explicit empty state while no eligible events exist
- preserve alert source identity and signal semantics
- no synthetic alert data
- no execution controls
- define provider configuration contract without committing secrets

A real external delivery provider remains a later explicit configuration step.

REAL_CAPITAL remains 0.
