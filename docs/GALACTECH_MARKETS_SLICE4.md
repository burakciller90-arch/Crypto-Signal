# GALACTECH Product Rail — Markets Workspace Slice 4

Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`, Product rail.
Predecessor: accepted GALACTECH Capital Center PR #926.
REAL_CAPITAL=0.

## Scope

This slice implements the locked professional Markets workspace without pretending that
every accepted intelligence family already has a point-in-time customer API.

The workspace uses existing immutable product evidence:

- `/api/market-radar` to discover observed symbol/timeframe contexts;
- `/api/assets/{symbol}/{timeframe}` for provider-separated latest/recent freezes;
- `/api/signals/{signal_freeze_identity}` for exact frozen provider detail.

## Provider truth

Provider state stays separate.

- Binance/Bybit or any other provider freeze is not merged into an invented consensus.
- The selected provider is explicit.
- Provider cards retain exact SHA256 freeze identity, direction, state, setup and freeze time.
- Switching provider changes only the selected exact detail; it does not mutate evidence.
- Recent decision tape opens the same immutable Evidence Room used elsewhere.

## Frozen chart

The central chart reuses the accepted deterministic frozen OHLC renderer from the exact
selected signal detail.

- No live candle is invented.
- No later candle rewrites issuance-time evidence.
- Missing/unparseable exact candle detail produces an explicit unavailable state.
- Market workspace rendering has no trading/execution authority.

## Layer discipline

The locked layer controls are:

- PA
- LIQ
- FLOW
- DERIV
- ONCHAIN

Only one is selected at a time by default.

### PA

PA is currently bound to accepted frozen signal evidence:

- exact Price Action methodology state if present;
- setup type;
- frozen entry reference / invalidation geometry when present;
- concise frozen evidence summary.

Missing geometry remains NOT FROZEN.

### LIQ / FLOW / DERIV / ONCHAIN

These intelligence families exist elsewhere in the accepted architecture, but this
Markets slice does not have a point-in-time customer adapter for them.

Therefore they render explicitly as **NOT EXPOSED**, rather than:

- synthesizing an overlay from unrelated signal fields;
- reusing stale historical M1/M2 PR code;
- presenting research/architecture presence as live product data;
- inventing order book, CVD, OI, funding, liquidation or on-chain measurements.

A later adapter may populate a layer only when exact PIT evidence/source/freshness
contracts are available.

## Asset focus and context selection

- Observed contexts are derived from current immutable radar evidence.
- Symbol/timeframe controls expose only observed contexts.
- Global ALL/BTC/ETH/SOL focus prefers an observed matching context when available.
- Missing contexts remain explicit; no default signal is fabricated.
- Async provider-detail requests are sequence-guarded so a slower stale response cannot
  overwrite a newer selection.

## Authority

Read-only customer projection only:

- no order submission;
- no exchange credentials;
- no ledger mutation;
- no leverage/borrowing/martingale;
- REAL_CAPITAL=0.

Status: CANDIDATE until exact-head hosted focused + full-repository acceptance passes.
