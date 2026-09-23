# M5 Smart Money / On-chain 2.0 — Slice 1: Provider-neutral Exchange Flow

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**. No production collector, probability, sizing or trading authority.

## Purpose

Extend the accepted Bitcoin on-chain/network evidence with a separate exchange-flow
research layer without inventing a live provider or address-attribution truth.

This slice defines a deterministic provider-neutral contract for already-measured
exchange inflow/outflow windows. It supports assets such as BTC, ETH, USDT and USDC
without claiming that a specific provider is connected or production-active.

## Observation contract

Each `ExchangeFlowObservation` freezes:

- asset;
- provider-defined exchange scope;
- exact source window start/end;
- inflow amount;
- outflow amount;
- provider identity;
- address/cluster attribution methodology identity;
- source timestamp;
- ingestion timestamp;
- adapter version;
- deterministic observation identity.

A positive netflow means measured flow **to the declared exchange scope**.
A negative netflow means measured flow **from the declared exchange scope**.
Neither state is automatically bullish, bearish, a sell signal or a buy signal.

## Derived evidence

The Slice 1 engine measures, over one exact source/provider/attribution context:

- latest inflow/outflow/netflow/gross flow;
- duration-normalized inflow/outflow/netflow rate per hour;
- PIT-window inflow rate percentile;
- PIT-window outflow rate percentile;
- PIT-window absolute-netflow rate percentile;
- change in netflow hourly rate per elapsed hour between the final two windows.

Percentiles are ranks only inside the exact consumed PIT history. They are not universal
historical percentiles and not calibrated probabilities.

## Bounded context labels

- `INFLOW_ANOMALY`: latest inflow rate is extreme inside the consumed PIT history and
  measured netflow is toward the exchange scope.
- `OUTFLOW_ANOMALY`: symmetric observed outflow context.
- `BALANCED`: non-extreme flows with bounded netflow relative to gross flow, including
  a measured zero-gross-flow window.
- `MIXED`: measured evidence exists but does not support one stronger bounded label,
  including simultaneous inflow/outflow extremes.
- `UNRESOLVED`: stale, insufficient or unavailable-at-as-of evidence.

## Scientific boundaries

- Provider-labeled exchange clusters are attribution evidence, not proof of actor intent.
- An exchange inflow is not automatically a sell.
- An exchange outflow is not automatically accumulation.
- Stablecoin inflow is not automatically a pump signal.
- No address, wallet owner, institution or "insider" identity is inferred.
- No future price-return or liquidation claim is produced.
- No R19 probability, Smart Capital Allocator weight, Kelly sizing or paper-trade command.
- No live API/credential/collector is activated in this slice.
- Existing `onchain_network.py` remains unchanged and replay-compatible.

## PIT / fail-closed rules

- Window end, provider timestamp and ingestion timestamp must all be <= `as_of_ms`.
- Exact asset, exchange scope, provider and attribution methodology must match.
- Observation identities and window-end identities must be unique.
- Future or late-ingested observations cannot rewrite an earlier freeze.
- Stale or insufficient history resolves to `UNRESOLVED`.
- Missing evidence is never interpreted as zero exchange flow.

## Acceptance checklist

1. Deterministic observation/freeze identity and arithmetic.
2. Inflow and outflow anomaly cases with no price-direction claim.
3. Separate BALANCED and simultaneous-extreme MIXED cases.
4. Duration-normalized rates, PIT percentiles and netflow-rate velocity.
5. Stale/insufficient/no-PIT evidence fails closed.
6. Future/late evidence cannot rewrite a historical freeze.
7. Context mismatch, duplicates, tampering and invalid thresholds fail closed.
8. Focused pytest/Ruff/mypy, then full repository Python/JavaScript/freshness regression.
9. Temporary hosted workflow removed after PASS; final diff limited to data model, engine,
   tests and this scientific contract.

Wallet cohort admission/performance, known-cluster source adapters and production data
collection are separate later M5 slices. Wake/lease remains paused by explicit user
instruction and must not be re-armed by development testing.
