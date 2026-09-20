# PAPER AUTONOMY POLICY V1

Status: candidate policy for Stage 6C. It is pure decision logic only and does not activate PAPER/STABLE trading.

Policy version: `paper_autonomy_policy.v1`.

## Purpose

Convert a bounded set of already-frozen signal decisions into a non-executable paper action candidate while remaining fail-closed. This policy sits above immutable signal truth and below the still-separate frozen execution-input/planning gate.

## V1 decision cadence and consensus

- decision timeframe: 4h only;
- required providers: Binance spot and Bybit spot, exactly one frozen decision from each;
- providers must refer to the same symbol, timeframe and exact as-of timestamp;
- permitted symbols remain BTCUSDT, ETHUSDT and SOLUSDT;
- both providers must be ACTIVE and agree on direction;
- each ACTIVE signal must still prove at least two supporting methodologies, zero opposing methodologies and one complete geometry;
- `partial_methodology_coverage` is the only uncertainty flag accepted by V1; any other uncertainty flag means no trade.

## Freshness and activation

- signal as-of must be at or after an explicit runtime activation watermark;
- therefore historical freezes that existed before activation cannot be backfilled into virtual trades;
- maximum signal age is 4 hours;
- future-dated signal truth fails closed.

## Risk and turnover

This autonomy layer complements the already-frozen `paper_risk_policy.v1`, which retains the 25% maximum position concentration, 20 USDT minimum cash reserve and 50% maximum gross exposure planning gates.

Autonomy V1 adds:
- maximum per-position loss budget: 1% of current marked paper NAV;
- per-symbol post-action cooldown: 4 hours;
- no pyramiding;
- no shorting;
- no automatic REDUCE action;
- missing mark prices needed to reconstruct NAV mean HOLD_CASH.

The 1% figure is a conservative V1 simulation policy, not a claim of statistical optimality. It must be evaluated empirically and changed only through an explicit policy-version change.

## Candidate semantics

- fresh bullish consensus while flat -> BUY candidate;
- fresh bearish consensus while a long position exists -> EXIT candidate;
- bullish consensus while already long -> HOLD_CASH/no new action;
- bearish consensus while flat -> HOLD_CASH because shorting is forbidden;
- WATCH, NEUTRAL, NO_SIGNAL, provider disagreement, stale evidence, cooldown, unsupported context or unsafe uncertainty -> HOLD_CASH.

A BUY/EXIT result is still only a candidate. It always declares that a frozen execution input is required. V1 does not choose a venue price, simulate a fill, append to the paper ledger or contact an exchange.

## Remaining gate before trading activation

Before PAPER/STABLE may persist any BUY/EXIT:
1. define and freeze the execution-input source and exact provider/venue rule;
2. convert the 1% loss budget plus frozen entry/invalidation inputs into a quantity;
3. pass that quantity through the existing paper_risk_policy.v1 concentration/cash/gross-exposure planner;
4. simulate explicit fee/spread/slippage with paper_execution_policy.v1;
5. commit through the accepted atomic orchestration-bundle boundary;
6. persist an activation watermark so historical signals remain permanently non-tradable.

REAL_CAPITAL remains 0.
