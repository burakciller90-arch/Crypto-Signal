# R25 Slice 3 — Accepted M2–M5 Evidence → Unified Decision Proof

Status: development candidate. `REAL_CAPITAL=0`.

This slice bridges the **already accepted, immutable** engine freezes into four M6 families and six matching R20.5 proof domains. It does not turn research modules into live provider connections or order authority.

## Exact scope

- M2 accepted Liquidity Dynamics → M6 Liquidity and `liquidity_map`; independently frozen, observed order-book snapshots → `order_book`. Neither is an observed liquidation feed. `liquidation_map` remains insufficient until a separate exact accepted liquidation freeze is bound.
- M3 accepted Order Flow Microstructure and window-local Temporal Flow → M6 Order Flow, `order_book` and `order_flow_cvd`. A directional vote is permitted **only when** the book + public taker pressure agree **and** window-local CVD has the same sign. Directional strength is the *minimum* absolute observed imbalance across these three measurements, not a win probability.
- M4 accepted Derivatives Dynamics → M6 Derivatives and `derivatives`. OI/price/funding/basis are **neutral observed context**, not automatic bullish/bearish votes.
- M5 accepted Exchange Flow → M6 On-chain and `onchain`. Provider-labelled netflow is **neutral observed context**, not proof of a whale's intention or future price.
- Missing, unresolved, source-stale or mismatched exact-PIT freezes become NO_EVIDENCE and INSUFFICIENT. No surrogate data.
- Per-family maximum source ages are explicit research adapter policy; the calculated freshness is *policy-relative source age*, not measured provider latency, model accuracy or universal freshness SLA.
- The `evidence_quality_0_1=1` marker records accepted deterministic measured source completeness only; it is not prediction reliability.
- Exact freeze SHA256 identities used by M6 are carried by corresponding proof domains, including the M3 microstructure identity in `order_book`.

## Composition boundary

This slice returns four M6 families and six proof domains. The caller must still supply accepted Geometry/frozen chart/consumed candles, exact Event Risk evidence and R19 probability authorization (if and only if actually calibrated). Then it may pass the full five families and all required proof domains to the merged `issue_unified_decision` runtime.

This slice **does not activate** Market Tape providers, fill unseen source records, persist raw M2–M5 freezes, produce actual 7/24 production decisions, mutate Epoch 2 canonical NAV, deploy the GALACTECH production root or restart paused wake/lease.

## Next gates

After hosted focused + full repo tests pass:

1. Exact composed end-to-end replay through the existing Unified Decision Runtime (all source freeze identities to proof to ledger to GALACTECH).
2. Separate PIT adapters for accepted observed Liquidation Heatmap, Absorption, Derivatives Crowding and on-chain cohorts where reliable accepted freeze contexts exist.
3. Controlled 7/24 shadow/paper writer replay with crash/restart/idempotency acceptance; only then a **separately approved** production activation and local UID504 live acceptance.
