# PAPER STABLE VENUE RULE REFRESH

This operation is observation-only. It refreshes public Binance Spot venue-rule
metadata for BTCUSDT, ETHUSDT and SOLUSDT into the append-only paper venue-rule
cache. It does not select signals, activate paper trading, simulate fills or
create orders.

Command surface:
- issue title: `[PAPER] RULESREFRESH`
- body: `command: rulesrefresh`

The stable worktree runs `ops/refresh_paper_venue_rules.py` using its own
frozen Python environment. The script acquires a non-blocking local lock,
asserts the existing 100 USDT paper fund still has zero decisions/fills/
mutations/NAV records, fetches public Binance exchangeInfo metadata, appends
immutable snapshots, and asserts the no-trade invariant again.

A successful workflow requires:
- one successful snapshot for BTCUSDT;
- one successful snapshot for ETHUSDT;
- one successful snapshot for SOLUSDT;
- cached rows for all three symbols;
- paper fund creation count remains 1;
- decision/fill/mutation/NAV counts remain 0;
- replay index remains 1;
- `trade_policy=NOT_ACTIVATED`;
- `REAL_CAPITAL=0`.

This operation has no credential or account endpoint and does not change the
PAPER/STABLE trade-policy authority boundary.
