# R20 Immutable Forecast Stream — Slice 1

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Implement the locked Phase 13 immutable forecast stream without crossing into Phase 14
Decision Proof UI or Phase 15 canonical paper-capital mutation.

A forecast is a pre-outcome evidence artifact. Later outcome information is appended as a
separate resolution artifact. The original forecast is never edited after issuance.

## Forecast truth

Each `ImmutableForecast` freezes:

- forecast identity;
- authority (research/shadow in Slice 1);
- asset and symbol;
- timeframe;
- issuance timestamp;
- exact source as-of timestamp;
- exact signal freeze identity and state;
- direction and condition/setup code;
- trigger kind and trigger zone;
- target label and target zone;
- invalidation price and trigger;
- horizon in bars;
- exact M6 confluence identity;
- support and opposition scores;
- confluence resolution and score semantic;
- R19 calibrated probability only when authorized;
- otherwise `NOT_CALIBRATED`;
- exact Event Risk circuit-breaker identity/state/triggers;
- exact evidence identities;
- model/policy/engine version references;
- freshness;
- uncertainty flags.

No forecast carries production/order authority.

## Exact context alignment

Signal, M6 Confluence and Event Risk evidence must share the same point-in-time source
context.

- Signal symbol must match the Confluence asset.
- Base asset must match the Event Risk asset.
- Direction must agree between signal and Confluence.
- Forecast issuance cannot predate source evidence.

Context mismatch fails closed.

## R19 probability boundary

Confluence is not probability.

If no accepted R19 probability is supplied:

`Probability: NOT CALIBRATED`

If calibrated probability is supplied, Slice 1 requires both:

1. an accepted immutable `CalibratedProbabilityEvidence`; and
2. the exact immutable R19 `CalibrationScope`.

The scope must match the forecast's:

- symbol;
- timeframe;
- Confluence regime;
- fixed-duration horizon.

For fixed-duration forecast timeframes, R20 converts horizon bars to milliseconds and
requires exact equality with the R19 scope horizon.

The R19 authorization scope identity must match the supplied immutable scope identity.

Probability lineage retains:

- authorization identity;
- calibration evidence identity;
- source forecast identity;
- frozen prediction identity;
- walk-forward fit identity;
- model version;
- calibrator version.

Therefore a calibrated percentage from another asset, timeframe, regime or horizon cannot
be attached to this forecast.

## Append-only resolution

A later `ForecastResolution` references the immutable forecast and accepted outcome
evidence.

Accepted mapped states include:

- `HIT_TARGET`;
- `INVALIDATED`;
- `EXPIRED`;
- `AMBIGUOUS`;
- `NOT_EVALUABLE`;
- `CANCELLED`.

Pending outcome evidence cannot be appended as a final resolution.

Resolution must match:

- forecast signal lineage;
- forecast horizon;
- chronological order.

The resolution records `original_forecast_unchanged = true`.

## Stream semantics

`ForecastStreamSnapshot` is a functional append-only snapshot.

- Forecast identities are unique.
- Forecasts are append-ordered by issuance.
- Resolution identities are unique.
- One forecast may receive at most one final resolution.
- Resolutions may reference only existing forecasts.
- Resolutions are append-ordered by evaluation time.
- Appending a resolution does not mutate forecast content or identity.

## Scientific boundaries

- Forecast != trade.
- Forecast != position size.
- Confluence score != probability.
- Historical hit rate != probability.
- R19 probability is shown only with exact accepted scope evidence.
- Event Risk state is preserved, not hidden.
- Uncertainty/freshness remain visible.
- Outcome truth is appended, never used to rewrite issuance-time truth.
- No private chain-of-thought is stored or exposed.
- No ledger write, network/exchange call, sizing or execution surface.
- REAL_CAPITAL=0.

## Relationship to historical prototype

Historical branch `v1.1-forecast-decision-proof-v1` is a diverged prototype on an older
base and is not current merge authority.

Useful product ideas from that work belong to the next locked Phase 14 Decision Proof /
Live Intelligence Feed. Slice 1 uses only the current-main-compatible immutable evidence
contract.

## Acceptance checklist

1. Required forecast fields are immutable and deterministic.
2. Signal / Confluence / Event Risk context mismatch fails closed.
3. Direction mismatch fails closed.
4. Missing probability remains NOT_CALIBRATED.
5. Calibrated probability requires exact R19 authorization + immutable CalibrationScope.
6. Probability asset/timeframe/regime/horizon mismatch fails closed.
7. R19 forecast/prediction/walk-forward/calibration lineage is retained.
8. Later outcome maps to a separate resolution artifact.
9. Pending outcome cannot become a final resolution.
10. Resolution horizon and signal lineage must match.
11. Forecast append order is deterministic.
12. One forecast receives at most one final resolution.
13. Original forecast remains byte/identity stable after resolution append.
14. Identity tampering fails closed.
15. No chain-of-thought, network, ledger, sizing, execution or production authority.
16. REAL_CAPITAL=0.
17. Focused pytest/Ruff/mypy and full repository Python/JavaScript/freshness regression.
18. Temporary hosted workflow removed after PASS.

After acceptance, Phase 13 R20 infrastructure exit is satisfied. The next locked frontier is
Phase 14 — R20.5 Decision Proof / Live Intelligence Feed, which must render structured
evidence rather than private reasoning.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
