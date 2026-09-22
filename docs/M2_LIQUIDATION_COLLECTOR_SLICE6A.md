# M2 Liquidation Collector Slice 6A — Disabled-by-Default Wire Collection

Status: development-only / NOT production activated  
REAL_CAPITAL: 0  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`

## Purpose

Wire the already accepted observed-liquidation normalizer and Market Tape persistence
contract to the public Bybit linear WebSocket **without activating production
collection**.

This slice is deliberately separate from the already accepted Hot/Cold runtime branch.
Those branches diverged after the raw-journal common ancestor and are integrated only
through a later cross-stack Slice 6B.

## Provider contract

Current Bybit public-linear contract used by this slice:

- endpoint: `wss://stream.bybit.com/v5/public/linear`;
- topic: `allLiquidation.{symbol}`;
- message type: `snapshot`;
- provider push frequency: 500 ms;
- `S=Buy` means a **long position was liquidated**;
- `S=Sell` means a **short position was liquidated**;
- `v` is executed size;
- `p` is bankruptcy price.

The provider side is never reinterpreted as public-trade aggressor side.

## Coverage boundary

This slice does **not** infer:

`WebSocket connected + no message => zero liquidations`.

A coverage record is emitted only for a provider liquidation message that actually
arrived. Its bounded window begins at the earliest liquidation event timestamp in that
provider snapshot and ends at the provider-generated message timestamp.

An empty provider data array fails closed instead of fabricating zero-event coverage.

Future work may add a separately proven continuous coverage protocol, but that is not
claimed here.

## Raw-first transaction boundary

For each provider message:

1. canonical raw payload is appended to the raw wire journal;
2. normalized liquidation observations are persisted;
3. feed coverage is appended last.

If normalized persistence fails after raw append, raw evidence remains available and a
retry is idempotent.

## Development-only runner

`ops/run_liquidation_market_tape_stream.py` is intentionally fail-closed:

- default: disabled;
- requires `--enable-development-collector`;
- requires a positive `--max-messages`;
- supports only canonical SSD DB paths;
- no continuous/unbounded mode;
- no launchd/supervisor integration;
- no production enable latch;
- REAL_CAPITAL=0.

## Explicitly not done

- no live production subscription;
- no SSD production Market Tape mutation;
- no launchd/runtime supervisor change;
- no production deployment;
- no cold archive integration yet;
- no estimated leverage or future liquidation zone.

## Acceptance

- official public-linear endpoint/topic contract frozen in tests;
- provider position-side semantics preserved;
- raw wire payload retained before normalized persistence;
- retry idempotence;
- bounded message count;
- empty message cannot fabricate zero-event coverage;
- SQLite quick checks pass;
- full repository regression passes.
