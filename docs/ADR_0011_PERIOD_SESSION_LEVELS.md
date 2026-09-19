# ADR 0011 — Prior-Period and Session High/Low Levels

Status: Accepted for PA Slice 4A implementation
Date: 2026-09-20

## Canonical source
Period/session ranges use closed canonical 15m candles.

## Previous calendar ranges
V1 computes:
- Previous Day High / Low
- Previous Week High / Low
- Previous Month High / Low

Calendar boundaries are UTC:
- day: 00:00 UTC
- week: Monday 00:00 UTC
- month: first day 00:00 UTC

A range result includes expected candle count, observed candle count and completeness.
If any expected 15m candle is missing or was not locally observed by the requested as-of time,
the range is INCOMPLETE and no high/low numeric truth is emitted.

## Session ranges
The core engine does not silently declare universal Asia/London/New York hours.

A SessionSpec explicitly provides:
- name
- IANA timezone
- local start time
- local end time

The engine resolves the latest completed session at the requested as-of time using zoneinfo.
Sessions may cross midnight and actual UTC duration follows timezone/DST rules.

Session boundaries must resolve to the canonical 15m grid.
A session high/low is emitted only when every expected 15m candle in the resolved window
was closed and locally observed by as-of.

## Point-in-time rule
Historical market candles fetched later do not become available at an earlier as-of.
Local ingest timestamps remain part of completeness.

## Scope
This layer provides deterministic reference levels only.
It does not label them support/resistance or turn them into signals.

REAL_CAPITAL remains 0.
