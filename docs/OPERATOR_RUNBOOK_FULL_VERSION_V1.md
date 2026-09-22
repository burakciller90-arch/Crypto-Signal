# Crypto Signal Full Version — Operator Runbook v1

This runbook describes the accepted **paper/simulation-only** system.
`REAL_CAPITAL=0` at all times.

## 1. Canonical layout

SSD root:

`/Volumes/Crypto-504/Crypto-Signal`

Expected directories:

- `Development`
- `Product`
- `Live`
- `Alerts`
- `Paper`
- `Runner`
- `ServiceLogs`
- `RunnerLogs`

Do not substitute legacy internal Macintosh project/runtime paths.

## 2. Normal health checks

Dashboard:

`http://127.0.0.1:48700/`

Read-only health:

`curl -fsS http://127.0.0.1:48700/api/health`

Expected accepted properties include:

- `status=ok`;
- `read_only=true`;
- `real_capital=0`;
- `ledger_present=true`;
- `alert_outbox_present=true`.

Research Lab truth:

`curl -fsS http://127.0.0.1:48700/api/intelligence-center`

Expected:

- `status=ready`;
- `read_only=true`;
- `real_capital=0`;
- `production_active_engine_count=0`;
- `probability_status=not_calibrated`.

## 3. Safe GitHub → UID504 diagnostic commands

The allowlisted `Crypto Mac Command` workflow is the preferred remote
diagnostic surface. Useful command bodies include:

- `command: status`
- `command: productstate`
- `command: pausecheck`
- `command: ssdleftover`
- `command: runnerpersistdiag`
- `command: producttest`
- `command: fulltest`

Do not invent a new command when an existing bounded diagnostic already answers
the question.

## 4. Runtime processes

The accepted runtime uses:

- UID504 self-hosted GitHub runner under the SSD `Runner` directory;
- SSD service supervisor at
  `/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.sh`;
- dashboard PID file at
  `/Volumes/Crypto-504/Crypto-Signal/dashboard.pid`;
- supervisor PID file at
  `/Volumes/Crypto-504/Crypto-Signal/ssd-service-supervisor.pid`.

The dashboard must be launched with explicit SSD paths for:

- live signal ledger;
- alert outbox;
- paper ledger;
- candle cache.

A dashboard process that silently falls back to removed internal paths is not
accepted.

## 5. Product updates

Never change `Product` by hand just to make the UI look current.

Accepted sequence:

1. merge to `main`;
2. hosted Stage10 full regression PASS;
3. UID504 `sync`;
4. UID504 `producttest`;
5. UID504 `fulltest`;
6. rollback-safe `productdeploy` to an explicit exact target;
7. post-deploy `productstate` and health checks.

If the Product code is already byte-equivalent to main product/runtime code,
docs/ops-only main commits do not require a Product redeploy.

## 6. Continuity

User pause is authoritative.

When pause is expected, healthy continuity state is:

- local pause YES;
- shared pause YES;
- active leases 0;
- local wake queue 0;
- relay wake queue 0.

Do not resume wakes merely to test continuity.

The accepted 20-minute cadence fallback is GitHub `:00/:20/:40` because
launchd bootstrap from the UID504 self-hosted-runner context proved unavailable.
The detached UID504 continuity bridge is the accepted bridge fallback.

## 7. Scientific truth

Never reinterpret these statements:

- confluence score is not probability;
- historical win rate is not calibrated probability;
- backtest is not untouched-forward evidence;
- missing evidence is not invented;
- losses/failures remain in evidence;
- NO_SIGNAL, AMBIGUOUS, ABSTAIN, NO_EVIDENCE and NOT_EVALUABLE are valid;
- research/shadow evidence does not automatically become production authority.

## 8. Incident priority

If anything looks wrong:

1. protect state; do not delete or rewrite evidence;
2. verify SSD mount and free space;
3. verify UID504 runner/control path;
4. verify supervisor/dashboard PIDs;
5. verify `/api/health`;
6. verify current `Development` and `Product` Git heads;
7. verify database integrity/readability;
8. verify pause/lease queues;
9. use rollback-safe recovery rather than ad-hoc migration or path fallbacks.

See the dedicated dashboard and SSD recovery guides.
