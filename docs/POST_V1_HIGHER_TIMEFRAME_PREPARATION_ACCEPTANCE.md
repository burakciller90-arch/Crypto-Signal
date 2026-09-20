# Post-V1 Canonical Higher-Timeframe Preparation Acceptance

Date: 2026-09-20
Status: ACCEPTED
REAL_CAPITAL: 0

## Purpose
Prepare higher-timeframe live evidence only from canonical closed 15m truth,
without enabling production coverage yet.

## Accepted planning semantics
A higher-timeframe history plan is derived from:
- explicit LiveCoverageContext
- latest canonical 15m source cutoff
- target timeframe
- requested target candle count

The planner selects only fully completed target buckets.

If the latest 15m cutoff is inside an incomplete target bucket, that bucket is
not eligible.

## Canonical acquisition
Higher-timeframe preparation:
1. computes the exact required 15m open-time range
2. reads the local CandleStore cache
3. identifies missing canonical 15m opens
4. groups missing opens into contiguous ranges
5. calls accepted backfill_range() only for missing ranges
6. uses bounded page_limit <= 1000
7. reloads closed canonical 15m from cache
8. aggregates with aggregate_closed_15m()

No native 1h/4h/1D/1W exchange candles are used as truth.

## Cache behavior
A complete cached window performs zero new adapter requests.

A partially cached window fetches only missing contiguous ranges.

This prevents repeated full-history REST downloads on every live-clock cycle.

## Missing-data behavior
Missing base candles remain explicit.

Preparation exposes:
- missing_base_open_times_ms
- aggregation.incomplete

complete is true only when:
- no base opens are missing
- no target bucket is incomplete
- exact requested target candle count was produced

No missing candle or target bucket is synthesized.

## PIT/provenance
aggregate_closed_15m() preserves deterministic provenance:
- source=AGGREGATED
- source_timestamp_ms=max constituent source timestamp
- ingested_at_ms=max constituent ingest timestamp
- target candle is_closed=true only from closed canonical inputs

## Mechanical acceptance
Focused preparation / aggregation / recovery gate:
- 11 tests PASS
- Ruff PASS
- mypy PASS

Full repository:
- 267 tests PASS
- Ruff PASS
- mypy PASS
- uv lock PASS
- git diff check PASS

Coverage includes:
- latest fully completed target bucket selection
- paginated missing-base acquisition
- exact canonical 15m-only adapter requests
- deterministic higher-timeframe aggregation
- second-run zero API calls from complete cache
- explicit incomplete result when one base candle is missing
- partial-cache acquisition only for the missing contiguous tail

## Production deployment
NOT DEPLOYED.

All higher-timeframe coverage contexts remain disabled.

LIVE/STABLE continues the accepted BTCUSDT 15m Spot pilot.

## Canonical next frontier
Decouple immutable freeze analysis from adapter acquisition:
1. extract a freeze_live_candles() path that accepts already-canonical candles
2. preserve exact existing 15m semantics
3. have freeze_live_provider() delegate to it
4. allow future aggregated higher-timeframe preparation to use the same
   confluence/signal/bundle/lifecycle path
5. prove exact regression equivalence for the current 15m pilot
6. do not activate higher-timeframe production yet

REAL_CAPITAL remains 0.
