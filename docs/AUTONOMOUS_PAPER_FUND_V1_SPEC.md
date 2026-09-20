# AUTONOMOUS PAPER FUND — V1 SPECIFICATION

Status: governing specification for Stage 6C.
REAL_CAPITAL=0.

## Purpose
Create a fully virtual 100 USDT portfolio that lets Crypto Signal prove whether its decisions add value after realistic simulated costs.

## Initial state
- starting cash: 100.00 USDT
- real capital: 0
- initial holdings: none
- permitted initial universe: BTCUSDT, ETHUSDT, SOLUSDT
- no leverage
- no borrowing
- no derivatives execution
- cash is a valid allocation

## Required immutable records
Account creation, decision intent, simulated order, fill, fee, position mutation, NAV snapshot and benchmark snapshot must all be reconstructable and append-only.

## Required realism
Do not assume free fills.
A versioned execution policy must account for venue rules, fee schedule, spread and slippage. If partial fills are not implemented, the limitation must be explicit.

## Risk policy
The first accepted policy must be conservative and versioned. It must define maximum exposure, per-position risk, concentration, cooldown and no-trade conditions. No martingale or loss chasing.

## Benchmarks
Run from identical timestamps:
- cash-only 100 USDT,
- BTC buy-and-hold,
- equal-weight BTC/ETH/SOL.

## UI contract
The user must see current NAV, cash, positions, unrealized/realized PnL, costs, benchmark comparison and each virtual transaction's explanation.

## Acceptance
The ledger must reproduce the account exactly from zero state, survive restart, remain immutable and never create or imply a real order path.
