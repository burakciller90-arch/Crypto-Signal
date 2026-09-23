# Event Risk + NLP — Slice 2: Source-bounded News/NLP Evidence

Status: development candidate; hosted acceptance required before main merge.  
Parent: `docs/V1_1_LOCKED_MASTER_ROADMAP_20260922.md`  
REAL_CAPITAL: **0**.

## Purpose

Add a provider-neutral news/NLP evidence layer after the accepted structured Event Risk
calendar.

This slice freezes source and extraction provenance. It does not ask an LLM to invent
market truth, does not infer price direction, and does not activate a live news provider.

## Observation contract

Each `NewsEventObservation` freezes:

- provider article identity;
- upstream event-cluster key;
- headline;
- event category;
- affected assets, or empty for global scope;
- publication timestamp;
- source provider and source quality;
- source timestamp;
- ingestion timestamp;
- extraction method and extraction/model version;
- relevance confidence in [0,1];
- adapter version;
- deterministic news identity.

The event-cluster key is an upstream extraction key. It is not actor identity, legal
identity, or proof that two reports are objectively the same real-world event.

## Bounded evidence states

For the latest PIT-eligible relevant event cluster:

- `MULTI_SOURCE_CONFIRMED`: at least the configured number of distinct providers agree
  on one category and selected evidence is not low-confidence/unverified.
- `SINGLE_SOURCE_CONTEXT`: one provider supplies bounded, sufficiently confident
  context.
- `PROVIDER_DISAGREEMENT`: selected reports for the same event-cluster key disagree on
  category.
- `DEGRADED_DATA`: selected evidence includes unverified source quality or relevance
  confidence below the versioned threshold.
- `UNRESOLVED`: no relevant PIT-safe news evidence exists in the lookback.

No state is bullish, bearish, a forecast, or a trading command.

## PIT / causal boundaries

- Publication, source and ingestion timestamps must all be available by `as_of_ms`.
- Only the configured recent lookback is eligible.
- Only global news or news explicitly affecting the requested asset is eligible.
- Future, late-ingested and other-asset evidence cannot rewrite a historical freeze.
- Distinct event clusters are not silently pooled; the latest eligible cluster is selected
  deterministically.
- Duplicate news identity or duplicate provider/article identity fails closed.
- One provider article ID may only appear once per source provider in one eligible set.

## Source / confidence boundaries

- `OFFICIAL` and `PRIMARY_PROVIDER` are counted separately from lower-quality sources.
- `UNVERIFIED` selected evidence degrades rather than becoming confirmed context.
- Relevance confidence is provider/NLP extraction metadata, not a calibrated probability
  of market movement or event truth.
- Category disagreement is surfaced explicitly instead of averaged away.
- Secondary-only evidence remains context and carries an explicit quality flag.

## Scientific boundaries

- Headline/category extraction is not market direction.
- Multi-source agreement does not prove an event is true in every factual detail.
- Provider disagreement does not prove either provider is wrong.
- No actor motive, insider/institution identity or future-return claim.
- No sentiment-to-price shortcut.
- No probability, confluence production weight, capital sizing or order authority.
- No live news/NLP provider, credential or collector activated.
- REAL_CAPITAL=0.

## Acceptance checklist

1. Deterministic news observation / analysis / freeze identity.
2. Multi-source confirmation distinct from single-source context.
3. Category disagreement remains explicit.
4. Low-confidence or unverified selected evidence degrades.
5. No relevant evidence resolves UNRESOLVED rather than fabricating CLEAR.
6. Future/late/other-asset evidence cannot rewrite history.
7. Distinct event clusters are not silently aggregated.
8. Duplicate provider/article identity and tampering fail closed.
9. Focused pytest/Ruff/mypy and full repository Python/JavaScript/freshness regression.
10. Remove temporary hosted workflow after PASS.

Next Event Risk frontier: compose structured calendar + News/NLP + market-data quality
signals into versioned circuit-breaker semantics including `DEGRADED_DATA`,
`EVENT_BLOCK` and downstream `ABSTAIN`, without creating trade authority.

The user-requested wake/lease pause remains authoritative and must not be re-armed.
