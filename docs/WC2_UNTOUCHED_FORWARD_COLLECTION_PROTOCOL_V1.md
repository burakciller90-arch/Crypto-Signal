# WC2 Untouched-Forward Collection Protocol v1

Status: **PREREGISTRATION CANDIDATE — collection must remain disabled until runtime registration is accepted**  
Evidence class: `LIVE_UNTOUCHED_FORWARD` only  
Review policy: `docs/WC2_UNTOUCHED_FORWARD_EVIDENCE_POLICY_V1.md`  
REAL_CAPITAL: **0**

## Purpose

The existing WC2 review-sufficiency policy answers a different question:

> When is the accumulated untouched-forward cohort large and diverse enough for WC3 review?

This collection protocol freezes the operational rules used to create that cohort **before**
live WC2 collection starts. It exists so issuance timing and forecast horizon cannot be
changed after observing results.

A later protocol change starts a new collection boundary. It cannot be applied
retroactively to earlier forecasts.

## Bound identities

Every accepted protocol binds:

- the exact WC2 review-policy identity;
- the exact canonical Epoch2 activation identity;
- review-policy collection start;
- Epoch2 activation time;
- exact `LiveCoveragePlan.current_pilot()` version;
- every enabled coverage context;
- collection protocol preregistration time;
- collection start time;
- issuance-delay ceiling;
- horizon bars by timeframe;
- paper-action mode;
- probability mode.

The current pilot is exactly:

- exchanges: Binance Spot and Bybit Spot;
- symbols: BTCUSDT, ETHUSDT, SOLUSDT;
- timeframes: 15m, 1h, 4h;
- total enabled contexts: 18;
- 15m uses direct canonical 15m evidence;
- 1h/4h use deterministic aggregation from canonical 15m evidence.

## Locked v1 operational choices

### Same-cycle issuance delay

Maximum source-freeze-to-R20 issuance delay:

**120,000 ms (120 seconds)**

Rationale:

- the accepted live-evidence clock contract has historically used a 120-second scheduler
  interval;
- WC2 issuance happens inside the same in-process freeze cycle;
- 120 seconds is a conservative fail-closed freshness ceiling, not a latency claim;
- a forecast outside this ceiling is not silently admitted into the untouched-forward
  cohort.

This number is selected before collection and is not based on observed forecast outcomes.

### Forecast horizon

The frozen v1 horizon is **4 bars of the forecast's own source timeframe**:

| Timeframe | Horizon bars | Wall-clock horizon |
| --- | ---: | ---: |
| 15m | 4 | 1 hour |
| 1h | 4 | 4 hours |
| 4h | 4 | 16 hours |

Rationale:

- the horizon is simple and interpretable;
- it preserves timeframe-relative semantics rather than forcing one wall-clock duration
  onto structurally different source timeframes;
- it is fixed before untouched-forward outcomes exist;
- it creates one deterministic outcome horizon per supported timeframe.

These horizons are research protocol choices, not claims that four bars are optimal.
Changing them later requires a new protocol identity and new cohort boundary.

## Paper-action boundary

Collection mode is:

`hold_cash_no_reviewed_sizing`

Every accepted forecast still receives a paper decision/intent, but v1 collection does
not invent risk measurements, does not invent a numeric Position Sizing policy, does not
select a sizing winner, and does not create a simulated fill for HOLD_CASH.

A future paper TRADE path must satisfy the separately accepted review, sizing, execution
and explicit-cost evidence gates. It cannot be activated by this protocol.

## Probability boundary

Collection mode is:

`not_calibrated_unless_exact_r19`

The protocol never converts confluence into probability. R20 may carry calibrated
probability only if exact accepted R19 scope/evidence authorizes the same
asset/timeframe/regime/horizon. Otherwise the forecast remains `NOT_CALIBRATED`.

## Time boundary

A protocol is valid only when:

- preregistration occurs before its collection start;
- its collection start is not earlier than the bound review-policy collection start;
- its collection start is not earlier than canonical Epoch2 activation.

No historical forecast backfill authority exists.

## Authority boundary

The protocol grants none of the following:

- real-money authority;
- exchange-order authority;
- canonical Epoch2 mutation authority;
- leverage;
- borrowing;
- martingale;
- automatic model/policy promotion;
- historical backfill authority.

`REAL_CAPITAL=0` remains mandatory.

## Acceptance before collection

Before any WC2 network cycle can use this protocol:

1. hosted focused tests, Ruff and mypy pass;
2. whole-repository regression passes;
3. the protocol is registered on UID504 from exact accepted workflow source;
4. read-only state proves the persisted identity and byte stability;
5. live clock reads the protocol before network access;
6. raw caller-supplied horizon/delay values no longer have independent authority;
7. prepared receipt and R20 lineage bind the exact protocol identity;
8. a bounded one-shot UID504 cycle is accepted before periodic service activation.
