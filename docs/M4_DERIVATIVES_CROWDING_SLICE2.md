# M4 Derivatives Intelligence 2.0 — Slice 2: Bounded Crowding Context

Status: development candidate; hosted acceptance required before main merge.
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`
REAL_CAPITAL: **0**. No production deployment, probability, position sizing or trading authority.

## Existing accepted evidence, reused without rewriting

- M4 Slice 1 `DerivativesDynamicsEvidenceFreeze`: chronological OI x mark-price state, PIT funding rank/acceleration and observed mark/index basis. Original `derivatives_context.py` stays unchanged for backward replay.
- M2 observed `LiquidationHeatmapEvidenceFreeze`: witnessed liquidated position side, bankruptcy notional, bounded observed clusters and independently verified complete feed coverage. Observed liquidations are **not** estimates of future liquidation zones.

This slice consumes both upstream immutable freezes with exactly matching exchange, instrument, symbol and `as_of_ms`. Upstream unresolved quality propagates to `UNRESOLVED`; partial data is not silently upgraded into a directional assessment. Frozen input identities and output identity use deterministic SHA256.

## Candidate contextual labels

- `LONG_CROWDING`: OI expands while **observed** funding rank/rate and mark/index basis jointly exceed explicit research thresholds on the long side.
- `SHORT_CROWDING`: symmetric observed short-side context.
- `SQUEEZE_RISK`: a conditional **context flag** requiring the same candidate crowding state plus sufficiently dominant **already-observed** liquidation side and elevated measured mark-price movement. The flag does not predict the next liquidation, its price, or any probability.
- `DELEVERAGING`: observed OI contraction together with measured liquidation activity; no actor/direction inference.
- `BALANCED`: low observed funding/OI/basis pressure **and verified complete liquidation coverage with no observed events**.
- `MIXED`: insufficient agreement for a stronger label even though upstream measured evidence was available.
- `UNRESOLVED`: upstream incomplete/stale/mismatched evidence, never interpreted as balanced or zero risk.

All numeric thresholds are **versioned research defaults**, not statistically fitted win probabilities or canonical policy weights. The observed funding percentile is only relative to the consumed PIT window. The mean and maximum absolute consecutive **mark returns** are proxies for movement, not a validated volatility model. The liquidity collector remains disabled by default.

## Non-negotiable scientific boundaries

- No guessed future liquidation clusters or private actor attribution.
- Neither crowding nor squeeze-risk is a BUY/SELL instruction.
- Complete event coverage is required to infer “none observed”; no feed is not a zero-event feed.
- No mixing symbols, venues, instrument types or issuance cutoffs.
- Late or future ingestion never changes a historical evidence freeze.
- No R19-calibrated probability or Kelly sizing is produced.
- No production collector, fund or customer-facing weighting is switched on.

## Acceptance checklist

1. Long and short crowded/observed-liquidation contextual cases with deterministic replay.
2. Explicit no-liquidation complete-coverage case and separate `DELEVERAGING` and `BALANCED` cases.
3. Upstream stale/insufficient/partial coverage fails closed.
4. Reversed source order, future observations, late ingestion and tampered evidence identities do not rewrite accepted historical evidence.
5. Strict same-context and `as_of_ms` alignment; invalid threshold parameters rejected.
6. Focused pytest, Ruff and mypy, then full repository Python/JavaScript/freshness regression on the exact branch HEAD.
7. Remove any temporary hosted-gate workflow after PASS; compare the final intended code/test/doc tree against `main`, then run exact-main acceptance after merge.

Do not call this production accepted before a separately authorized live runtime check. The user-requested wake/lease **pause remains dominant** and must not be re-armed by testing or development.
