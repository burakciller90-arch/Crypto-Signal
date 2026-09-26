# Crypto Signal — Stream S12 Search, Filters and History UX Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S12 closes discovery and exact-history navigation on the one mixed Intelligence Stream.

## Accepted implementation

Merged PR #1292 / main `192148e47e83d31fc9153df8cf65fb351c3c81f9`.

Accepted discovery UX:
- full-text search;
- asset/symbol filter;
- category filter;
- timeframe filter;
- vault filter;
- evidence-domain filter;
- decision/capital state filter;
- importance filter;
- from/to date filters;
- clear-filter behavior;
- exact-message deep-link by immutable narrative identity;
- direct URL deep-link loads and expands the exact original message;
- clicked message updates the exact deep-link identity;
- deep-linked detail retains exact proof/evidence actions;
- history/discovery reuses the accepted S6 cursor/query backend;
- the normal state remains one mixed chronological Stream;
- discovery stays a temporary drawer, not permanent navigation.

## Exact-head acceptance

Accepted implementation head:
- `b655eab2a01a1c0e289b74f19909263636a6da2a`.

UID504 run:
- `36217335451` — **PASS**.

The accepted run proved:
- exact source checkout;
- focused S12 read-model/API/UI acceptance;
- Ruff + strict mypy + JS syntax;
- whole-repository regression;
- real Chromium desktop discovery rendering;
- exact 430x860 mobile discovery rendering;
- zero whole-page horizontal overflow;
- full decision discovery query serialization;
- capital vault/state filtering;
- clear filters returns the base mixed-stream query;
- initial direct-message URL opens the exact message;
- click-to-deep-link opens the exact clicked message identity;
- exact expanded detail remains visible;
- proof/evidence action remains available;
- discovery drawer does not replace the Stream;
- Development checkout non-mutation.

Visual artifact:
- `stream-s12-visual-snapshot-36217335451`;
- artifact id `10897559558`;
- digest `sha256:4a6906c30ca7d3c48b6179a75e09d84f178be8878c644d96eb8be543f6e2af15`.

## S12 PASS criteria

Roadmap criterion: normal state remains one mixed stream.  
**PASS** — discovery applies temporary backend query parameters over the same immutable Stream and creates no new main navigation section.

Roadmap criterion: filters never create separate permanent navigation sections.  
**PASS** — search/filter controls live in the temporary “Ara ve daralt” drawer and close back to the same Stream.

Roadmap criterion: search result opens exact original message and evidence.  
**PASS** — immutable narrative identity is carried in the `message` deep-link; direct URL and click navigation expand that exact original message while retaining its persisted detail/proof action.

## Boundaries retained

S12 does not authorize:
- rewritten or synthetic history;
- historical signal/paper backfill;
- a standalone Archive/Markets/Capital screen;
- S13 notification sound/browser notification behavior;
- production-root cutover;
- real exchange orders or credentials.

The active frontier after closeout is S13 Sound and Notifications.
