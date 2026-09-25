# Crypto Signal — Intelligence Stream V1 Master Roadmap

Status: **CANONICAL CURRENT FRONTEND / PRODUCT EXECUTION AUTHORITY**  
Company: GALACTECH  
Product: Crypto Signal  
Current frontend scope: **ONE PANEL / ONE LIVE INTELLIGENCE STREAM**  
Safety: REAL_CAPITAL=0  
Supersession date: 2026-09-25

---

## 0. Authority and scope

This document supersedes the prior multi-screen frontend execution program.

For current frontend/product work, the target is intentionally narrow:

> Build one world-class Intelligence Stream that makes the entire accepted backend understandable through live, persistent, evidence-bound messages.

No separate Markets, Capital, Performance, Archive, Learn or System screen is part of the current product frontier.

Those capabilities may be exposed **inside the stream** through expandable messages, floating evidence windows, detached proof windows and contextual drill-downs.

The product is not considered ready to broaden into more screens until Intelligence Stream V1 passes all acceptance gates in this roadmap.

Repository-wide scientific, point-in-time, evidence, persistence, paper-capital and REAL_CAPITAL safety boundaries remain binding.

## 0.1 Locked user product decisions

These decisions are already made and must not be re-opened during ordinary implementation:

- V1 has **one primary panel only**;
- the primary surface is a Telegram/WhatsApp-like live Intelligence Stream;
- no other main tabs/screens are built before Stream V1 is accepted;
- normal feed messages are short and show primarily the first analytical paragraph;
- clicking a message expands deeper SIMPLE / PRO / INTELLIGENCE / DECISION / geometry / CAPITAL / PROOF content;
- technical evidence and score components are clickable;
- evidence opens in movable/resizable Mac-like windows without leaving the stream;
- supported proof windows can detach to another browser window/monitor;
- the system writes original Turkish in a consistent trader/analyst voice from canonical facts and story history;
- the system can explain its current view, what changed, what it is waiting for, what would change its view and what virtual capital did;
- new real messages arrive automatically;
- a configurable original short notification chime accompanies eligible new messages;
- messages are backend-persistent, append-only and never silently deleted/revised;
- older history is reached by scrolling upward;
- the default experience is one mixed chronological stream;
- search/filter is a temporary discovery tool, not separate navigation;
- BTC / ETH / SOL, message category, timeframe, vault, evidence domain, state, importance, date and full-text filtering are supported targets;
- five-family intelligence and three-vault paper-capital behavior are surfaced through the stream;
- future standalone screens are a later decision after Stream V1 is finished.

## 0.2 Current execution frontier

- **S0 Authority Freeze: PASS**.
- **S1 Stream-only Backend Capability Audit: PASS**.
- **S2 Canonical Stream Event & Message Model: PASS**.
- **S3 Story Engine and Change Detection: PASS**.
- **S4 Analytical Composer: PASS**.
- **S5 Narrative Engine: PASS**.
- **S6 Real-time Stream Backend: PASS**.
- **S7 One-Panel UI Shell: PASS**.
- **S8 Expandable Message Experience: PASS**.
- **S9 Evidence Window Manager: ACTIVE FRONTIER**.
- Do not begin S10 as the active implementation frontier until S9 reusable evidence-window behavior is browser-rendered and accepted with exact identity preservation.
- The deployed GALACTECH V2 surface remains production fallback until S16 controlled cutover.

---

# 1. Product thesis

Crypto Signal should feel as if a highly capable market analyst is sending the user live Telegram/WhatsApp-style messages.

The user opens one page.

The system continuously observes the market, explains what changed, states its current view, links every important statement to evidence, and explains what the virtual capital system did in response.

The surface is simple.

The depth is underneath every message.

Core experience:

**LIVE MARKET → SYSTEM VIEW → MESSAGE → EXPAND → EVIDENCE → CAPITAL CONSEQUENCE → FROZEN PROOF**

The product voice should feel:

- calm;
- professional;
- Turkish-first;
- analytical;
- concise in the collapsed feed;
- deep when opened;
- consistent in tone;
- capable of saying “bekliyorum”, “görüşümü güçlendiriyorum”, “önceki görüşümü zayıflatıyorum”, “Tactical giriş için tetik bekliyorum” when canonical facts support those statements.

---

# 2. The one-screen rule

Intelligence Stream V1 has one primary application surface.

No sidebar with product sections.

No multi-tab dashboard architecture.

No separate Capital page.

No separate Markets page.

No separate Evidence page.

No separate Archive page.

No separate Performance page.

The top chrome may contain only compact global controls such as:

- Crypto Signal identity;
- live/connection indicator;
- search;
- filter;
- notification sound;
- settings;
- optional advanced/debug toggle.

Everything else begins from the chronological message stream.

---

# 3. Stream behavior

The stream behaves like a messaging application.

## 3.1 Ordering

- newest messages appear at the bottom;
- older messages are reached by scrolling upward;
- scrolling upward loads older history;
- day/time separators are allowed;
- the user may navigate arbitrarily far back through persisted history.

## 3.2 New-message behavior

If the user is already near the bottom:
- a new real message appends automatically;
- the feed remains anchored near the newest event.

If the user is reading older history:
- do not yank the viewport downward;
- show a compact “↓ N yeni mesaj” control;
- tapping it returns to the newest message.

## 3.3 Immutability

Once a message is published to the canonical stream, it is never silently edited to match later outcomes.

If the system changes its view, it sends a new message.

Examples:

- GÖRÜŞ GÜÇLENİYOR
- GÖRÜŞ ZAYIFLIYOR
- TETİK GERÇEKLEŞTİ
- TACTICAL ELIGIBLE
- TACTICAL EXECUTED
- GÖRÜŞ İPTAL
- OUTCOME RECORDED

Old messages remain visible.

---

# 4. Collapsed message contract

The feed must remain visually light.

A normal message in the timeline shows only the first layer.

Recommended collapsed structure:

**timestamp · symbol · timeframe · state badge**

Then one short system paragraph.

Then a small row of semantic chips.

Example:

**14:32 · BTC/USDT · 5m · GÖRÜŞ GÜÇLENİYOR**

> Bitcoin aşağıdaki kısa vadeli likiditeyi temizledikten sonra satış baskısını absorbe etmeye başladı. CVD toparlanırken açık pozisyon miktarının artması yukarı yönlü senaryoyu güçlendiriyor. 81.800 üzerindeki kapanış Tactical giriş koşullarını tamamlayabilir.

Chips:

`Liquidity` `Order Flow` `Derivatives` `Score 82` `Tactical`

Collapsed message acceptance:

- concise enough to scan rapidly;
- not a giant dashboard card;
- readable in seconds;
- visually closer to a premium messaging bubble than a BI card;
- no hidden invented facts;
- the paragraph is generated from canonical message context.

---

# 5. Expanded message contract

Clicking/tapping the message expands it inline without navigating away from the stream.

Expanded sections may include:

## 5.1 SIMPLE — Sade Anlatım

A short explanation for a non-specialist.

## 5.2 PRO — Teknik Kanıt

Clickable evidence items such as:

- Liquidity Sweep
- CVD Divergence
- Absorption
- OI Rising
- Funding State
- Basis
- Liquidation Context
- Exchange Flow
- Wallet Cohort
- Event Risk
- Market Structure

## 5.3 INTELLIGENCE

The five-family contribution model:

- Geometry / 20
- Liquidity / 25
- Order Flow / 25
- Derivatives / 15
- On-chain / 15

Also expose:
- total Decision Score;
- opposition;
- evidence coverage;
- freshness/quality;
- material conflicts.

## 5.4 DECISION

Natural-language current system view.

Questions it should answer:
- What does the system currently think?
- Why?
- What changed since the previous relevant message?
- What is the main supporting evidence?
- What is the main reservation/contradiction?
- What would change the view?

## 5.5 TRADE GEOMETRY

When canonical evidence exists:
- trigger;
- entry zone;
- target;
- invalidation.

## 5.6 CAPITAL

When exact lineage exists:
- vault;
- HOLD / BLOCK / ELIGIBLE / SIZED / EXECUTED / REDUCED / EXITED;
- sizing;
- reason;
- capital consequence.

## 5.7 PROOF ACTION

Primary action:

**KANIT GRAFİĞİNİ & DONDURULMUŞ KANITI GÖR**

Expanded detail remains attached to the original message identity.

---

# 6. Clickable evidence model

Every important technical term in PRO and INTELLIGENCE should be clickable when a canonical evidence reference exists.

Examples:

- Liquidity Sweep
- CVD Divergence
- Bid Absorption
- Geometry 16/20
- Liquidity 24/25
- Derivatives 11/15
- Decision 82
- Tactical
- Event Risk

A click opens a context window rather than forcing a route change.

---

# 7. Evidence Window System

Evidence windows are a signature interaction.

They should feel closer to lightweight Mac desktop windows than classic blocking website modals.

Required capabilities:

- draggable;
- resizable;
- movable around the workspace;
- z-index/focus behavior;
- minimizable;
- closable;
- optionally pinnable;
- multiple windows may coexist;
- stream remains usable behind them;
- window position/size can persist for the current session;
- supported windows may be detached into a real browser window/tab for second-monitor use.

## 7.1 Common evidence-window anatomy

Every evidence window should answer:

### Bu nedir?

Short contextual education.

### Bu mesajda neden önemli?

Message-specific explanation generated from the exact evidence and current story.

### Sistem bunu nasıl yorumladı?

The structured analytical consequence.

### Kanıt

Frozen visual/numeric evidence.

### Kaynak / zaman

Advanced disclosure:
- evidence identity;
- snapshot identity;
- provider/exchange;
- event time;
- observed/ingested/frozen time;
- schema/version where relevant.

---

# 8. Example: Liquidity Sweep evidence window

The user clicks **Liquidity Sweep**.

Window content:

### Bu nedir?

Plain-language explanation of a liquidity sweep.

### Bu mesajda neden önemli?

Example style:

> BTC 81.120–81.190 arasındaki aşağı likidite bölgesini test etti. Fiyat bölgenin altına geçmesine rağmen sonraki mumlarda tekrar bölgenin üzerine döndü. Aynı zaman aralığında satış akışının yeni düşük üretememesi nedeniyle bu sweep mevcut bullish tezi destekleyen evidence olarak sınıflandırıldı.

The actual text must come from canonical facts, not this example.

### Frozen evidence

A large issuance-time/frozen chart when exact evidence exists.

Potential overlays:
- liquidity zone;
- sweep point;
- relevant candle;
- trigger;
- invalidation;
- evidence timestamp.

If exact visual coordinates are not available, the window must not invent them.

---

# 9. Example: Intelligence score component window

The user clicks **Geometry 16/20**.

Window should show:

### Geometry nedir?

Simple explanation.

### Neden 16/20?

Message-specific natural-language summary.

### Destekleyen evidence

Exact supporting evidence.

### Karşı evidence

Exact contradiction/opposition.

### Dondurulmuş grafik

Where exact chart geometry exists.

The same interaction model applies to:
- Liquidity;
- Order Flow;
- Derivatives;
- On-chain.

---

# 10. Example: Decision window

Clicking the total Decision Score opens a system-view window.

It should answer in original Turkish prose:

### Sistem şu anda ne düşünüyor?

### Neden?

### Ne değişti?

Compare current story state with the previous relevant state.

### Ana destek ne?

### Ana çekince ne?

### Ne olursa görüş değişir?

### Sermaye açısından sonucu ne?

This window should make the system feel like a coherent analyst rather than a score calculator.

---

# 11. Example: Capital window

Clicking a capital chip opens the exact virtual-capital consequence.

Examples:

- CORE · HOLD
- TACTICAL · WAITING_FOR_TRIGGER
- TACTICAL · EXECUTED
- OPPORTUNITY · BLOCKED
- OPPORTUNITY · EXECUTED

The window may show:

- canonical Epoch 2 context;
- vault;
- available cash;
- exposure;
- current state;
- sizing result;
- fee/spread/slippage assumptions;
- exact reason codes translated into Turkish;
- forecast/proof identity;
- transaction/fill identity when present;
- outcome when later available.

No separate Capital page is required for V1.

---

# 12. Narrative Intelligence Architecture

The system must be able to speak in its own consistent words while remaining bound to backend truth.

The target is not a random LLM prompt.

The target is a layered narrative architecture.

## 12.1 Fact Bundle

Canonical facts only.

Examples:
- asset;
- timeframe;
- current price context;
- evidence-family states;
- exact metrics;
- Decision Score;
- opposition;
- trigger;
- target;
- invalidation;
- Event Risk;
- capital state;
- evidence identities;
- timestamps.

## 12.2 Change Set

What changed since the previous relevant story state?

Examples:
- Order Flow neutral -> support;
- score 69 -> 82;
- Event Risk CLEAR -> CAUTION;
- Tactical HOLD -> ELIGIBLE;
- trigger not met -> met;
- CVD support lost;
- invalidation crossed.

## 12.3 Analytical View

Structured interpretation produced by deterministic product policy.

Fields may include:
- stance;
- stance_strength;
- dominant_support;
- main_contradiction;
- what_changed;
- next_condition;
- invalidation_condition;
- capital_consequence;
- materiality.

## 12.4 Narrative Plan

Before prose generation, create a bounded plan:

- opening statement;
- main reason;
- secondary reason;
- reservation;
- next condition;
- capital implication.

## 12.5 Natural-language renderer

The renderer writes concise Turkish in the Crypto Signal voice.

It may be:
- deterministic template;
- optional local model rewrite;
- or a hybrid.

## 12.6 Fact Validator

The final text is checked against the Fact Bundle.

It must reject:
- invented prices;
- invented metrics;
- unsupported causal claims;
- unsupported actor attribution;
- invented target/invalidation;
- wrong vault state;
- wrong timestamps.

## 12.7 Deterministic fallback

If the natural-language model is unavailable or validation fails, a deterministic Turkish message is still published.

The stream must not depend on an LLM being healthy.

---

# 13. Crypto Signal voice

The product should have one stable personality.

Voice traits:

- sakin;
- profesyonel;
- trader gibi doğal;
- kısa ama anlamsız derecede kuru değil;
- gerektiğinde birinci tekil şahıs kullanabilir;
- değişen görüşü açıkça kabul eder;
- hata/iptal durumunu gizlemez;
- kullanıcıyı heyecanlandırmak için abartılı dil kullanmaz.

Allowed style examples when facts support them:

- “Şimdilik bekliyorum.”
- “Bullish görüşümü güçlendiriyorum.”
- “Önceki çekincem azaldı.”
- “Order Flow teyidi geldi.”
- “Tactical giriş için tetik bekliyorum.”
- “Önceki bullish görüşümü geri çekiyorum.”
- “Bu setup Core için yeterince temiz değil.”

Avoid repetitive template feel.

The system should vary phrasing while preserving the same meaning.

---

# 14. Story memory

The stream needs memory at the story level.

A message should not act as if it has never seen the previous state.

Required story concepts:

- story_identity;
- asset/context;
- current stance;
- previous stance;
- current score;
- previous score;
- unresolved trigger;
- current capital state;
- relevant prior messages;
- supersedes/relation metadata.

Example sequence:

14:20  
> Order-flow teyidi olmadığı için bekliyorum.

14:31  
> 11 dakika önce eksik olan order-flow teyidi geldi.

14:34  
> Beklediğim 81.800 tetik koşulu gerçekleşti.

14:35  
> Tactical sizing tamamlandı ve sanal pozisyon açıldı.

15:12  
> CVD desteği zayıflıyor; görüşümü düşürüyorum.

The story relation must be explicit; time proximity alone is not sufficient.

---

# 15. Message trigger policy

Do not send a message for every tick.

A message is emitted for a material product event.

Core categories:

## MARKET

Meaningful market observation.

## INTELLIGENCE

Evidence-family state changed materially.

## DECISION

Decision Score band, stance or actionability changed.

## CAPITAL

Vault state, sizing, simulated execution, reduce or exit changed.

## RISK

Event Risk, data quality or major contradiction changed.

## OUTCOME

Forecast/trade outcome became available.

## SYSTEM

Provider/data/system quality event relevant to decision trust.

Optional lower-priority class:

## ROUTINE

Periodic concise summary only when it adds value.

Each message stores:
- category;
- subtype;
- importance;
- asset;
- timeframe;
- vault when relevant;
- evidence domains;
- story identity.

---

# 16. Canonical Message Ledger

The product needs an append-only Intelligence Stream projection.

Each published message should have at minimum:

- message_identity;
- source_event_identity;
- story_identity;
- category;
- subtype;
- importance;
- asset;
- symbol;
- market;
- timeframe;
- event_at;
- source_as_of;
- published_at;
- canonical fact bundle identity;
- analytical-view identity/version;
- narrative schema version;
- renderer version;
- collapsed text;
- SIMPLE content;
- PRO evidence references;
- intelligence breakdown;
- decision state;
- trigger/target/invalidation refs;
- capital consequence refs;
- proof/evidence refs;
- relation/supersession metadata;
- search/filter metadata.

The ledger is append-only.

Later renderer improvements do not rewrite old canonical message text silently.

If future re-rendering is allowed for display experiments, original published text/version remains preserved.

---

# 17. Real-time delivery

Target transport:

**canonical stream ledger -> event delivery -> browser**

Preferred:
- SSE or WebSocket for push;
- reconnect cursor;
- at-least-once-safe delivery with message-identity de-duplication;
- polling fallback.

Required behavior:
- no duplicate bubble after reconnect;
- no lost cursor;
- reconnect catches missed messages;
- history and live stream converge on one canonical ordering;
- connection status is visible but visually quiet.

---

# 18. Message notification sound

A real new message should be able to produce a short premium notification chime.

Do not copy a proprietary WhatsApp/iPhone audio asset.

Create/use an original Crypto Signal chime with a similar lightweight messaging function.

Settings:

- sound ON/OFF;
- volume;
- notification mode:
  - all messages;
  - important only;
  - Decision + Capital only;
  - silent;
- optional browser/desktop notification permission.

Sound behavior:
- one real new published message -> one eligible chime;
- history load -> no chime;
- reconnect replay -> no duplicate chime;
- user-controlled;
- browser autoplay restrictions handled through explicit initial user interaction.

Future optional:
- different subtle sounds for Decision, Capital and Critical Risk.

---

# 19. Search and filter

Normal mode always shows one mixed chronological stream.

Search is opened from a magnifying-glass control.

Search/filter must not fragment the core product into sections.

Filters:

## Asset
- BTC
- ETH
- SOL
- All

## Message category
- Market
- Intelligence
- Decision
- Capital
- Risk
- Outcome
- System
- Routine

## Timeframe
- 1m
- 5m
- 15m
- 1h
- 4h
- others when canonical

## Vault
- Core
- Tactical
- Opportunity

## Evidence domain
- Geometry
- Liquidity
- Order Flow
- Derivatives
- On-chain
- Event Risk

## State
Examples:
- Watch
- Actionable
- Hold
- Blocked
- Eligible
- Executed
- Resolved

## Importance
- Routine
- Important
- Critical

## Date range

## Full-text search

Search results preserve original message identity and can reopen the exact message/evidence context.

---

# 20. History and persistence

Messages must not disappear after refresh.

Requirements:
- backend persistence;
- stable ordering;
- older-history pagination/cursor;
- reload returns to a meaningful position where practical;
- deep-link to exact message;
- exact story history;
- no browser-only archive as canonical source.

Historical import rule:
- existing canonical forecast/feed events may be imported only from exact persisted source truth;
- do not retroactively synthesize rich historical messages using information that was not available at the time;
- newly activated rich stream becomes canonical from its activation boundary.

---

# 21. Five-layer intelligence in the stream

The five evidence families remain first-class:

- Geometry / 20;
- Liquidity / 25;
- Order Flow / 25;
- Derivatives / 15;
- On-chain / 15.

Event Risk remains a separate gate/context layer.

The score is used as part of the paper decision policy.

The stream should explain:
- current score;
- contribution by family;
- opposition;
- missing/degraded evidence;
- material change since the previous state.

The UI should focus on usefulness rather than repeatedly lecturing the user about score semantics.

---

# 22. Decision -> virtual capital integration

The stream must narrate capital consequences.

Required target pipeline:

**Market Evidence**  
-> **Five-Layer Decision / Score**  
-> **Event Risk**  
-> **Vault Eligibility**  
-> **Sizing**  
-> **Simulated Execution**  
-> **R22 Transaction Tape**  
-> **R21 Epoch 2 Accounting**  
-> **Capital Stream Event**

Three vaults:

- Core 600 USDT;
- Tactical 300 USDT;
- Opportunity Reserve 100 USDT.

All three are active parts of the forward paper experiment.

When preregistered conditions pass, simulated policy should execute without an extra discretionary fear veto.

Conditions are not weakened merely to create activity.

The stream must make prolonged inactivity diagnosable:
- candidates scanned;
- strongest current candidate;
- blockers;
- last eligible setup;
- last execution;
- data-quality state.

---

# 23. Evidence source audit for Stream V1

Before UI completion, every user-relevant backend engine used by the stream is audited through:

1. ENGINE
2. LIVE_SOURCE
3. PERSISTED_EVIDENCE
4. PRODUCT_PROJECTION
5. MESSAGE_PROJECTION
6. UI_SURFACE

A missing Product/Message projection does not mean the backend capability does not exist.

Stream V1 audit includes at minimum:

- price/geometry;
- liquidity;
- liquidation context;
- order-book;
- spoofing candidate;
- hidden-liquidity candidate;
- CVD;
- divergence;
- absorption;
- derivatives OI/funding/basis/crowding;
- exchange flows;
- large transfers;
- wallet cohorts;
- on-chain/network;
- Event Risk/news/calendar;
- Decision Score;
- forecast/actionability;
- three-vault capital state;
- sizing;
- simulated fills;
- outcomes;
- provider/data quality.

---

# 24. Visual evidence contract

Any chart annotation shown as proof must have exact source coordinates/identity.

Potential evidence overlays:

- trigger;
- entry zone;
- target;
- invalidation;
- liquidity zone;
- sweep point;
- liquidation cluster;
- structure level;
- CVD relation;
- absorption region;
- event marker.

A visual overlay without canonical coordinates is not drawn as fact.

---

# 25. Frozen order-book / microstructure proof

Market Tape contains order-book history, but proof-bound rendering requires exact identity mapping.

Stream V1 must complete the contract where possible.

Target proof fields:
- exchange/provider;
- market type;
- symbol;
- snapshot identity;
- event/source/ingestion timestamps;
- bids/asks;
- quantities;
- measured imbalance;
- adapter/schema version.

If an exact historical order-book snapshot cannot be bound to a message/proof, the product must not show a current book as if it were historical.

---

# 26. Phase S0 — Supersession and authority freeze

Goal:
- retire the prior multi-screen frontend execution roadmap;
- make this roadmap the sole current frontend/product execution authority;
- preserve old documents as historical evidence only;
- update READ_FIRST/CURRENT_STATUS/Chronicle/README authority chain.

PASS:
- no current read-order document points to the old frontend roadmap as active authority;
- old roadmap is visibly SUPERSEDED;
- current status says Intelligence Stream V1 is the active frontend frontier.

---

# 27. Phase S1 — Stream-only backend capability audit

Goal:
know exactly what the stream can say, show and prove.

Work:
- full six-stage capability matrix:
  ENGINE -> LIVE_SOURCE -> PERSISTED_EVIDENCE -> PRODUCT_PROJECTION -> MESSAGE_PROJECTION -> UI_SURFACE;
- exact identity graph;
- temporal map;
- event-source inventory;
- capital lineage inventory;
- proof/visual coordinate inventory;
- existing feed/history storage audit.

Deliverables:
- Stream Capability Matrix;
- Stream Gap Ledger;
- exact source-to-message mapping.

PASS:
- no major user-relevant backend capability is unclassified;
- every message/evidence idea has a canonical source or an explicit gap.

---

# 28. Phase S2 — Canonical Stream Event & Message Model

Goal:
create the append-only backbone.

Build:
- message schema;
- message identity;
- story identity;
- categories/subtypes;
- materiality;
- importance;
- evidence references;
- capital references;
- search metadata;
- renderer/version metadata;
- relation/supersession metadata.

Define event projectors from accepted source systems.

PASS:
- deterministic source event -> canonical stream message input;
- idempotent append;
- no duplicate message identity;
- chronological integrity;
- replay produces the same canonical projection.

---

# 29. Phase S3 — Story Engine and Change Detection

Goal:
make the system understand continuity.

Build:
- current story state;
- previous relevant state;
- stance change;
- score change;
- evidence-family change;
- trigger transition;
- risk transition;
- capital transition;
- relation metadata.

PASS:
- the system can answer “what changed?” deterministically;
- a message can reference previous story state without heuristic time-only joins;
- unrelated events are not falsely grouped.

---

# 30. Phase S4 — Analytical Composer

Goal:
produce a structured system opinion before prose.

Output contract:
- current stance;
- stance strength;
- dominant support;
- secondary support;
- main contradiction;
- uncertainty;
- what changed;
- next trigger;
- invalidation/change condition;
- capital consequence;
- message materiality.

PASS:
- same canonical facts -> same analytical result;
- result can explain why the message deserves publication;
- decision and capital state are identity-bound.

---

# 31. Phase S5 — Narrative Engine

Goal:
produce original, natural Turkish.

Build:
- Crypto Signal voice profile;
- narrative plan;
- deterministic Turkish renderer;
- optional local LLM rewrite path;
- fact validator;
- similarity/repetition guard;
- length budget for collapsed/expanded text;
- deterministic fallback.

Collapsed target:
approximately one concise paragraph.

Expanded target:
richer explanation without turning into an essay.

PASS:
- no invented numeric fact in narrative fixtures;
- same facts may be expressed naturally without robotic repetition;
- messages remain stylistically consistent;
- LLM failure does not stop the stream;
- story-aware phrases such as “önceki eksik teyit geldi” work when exact history supports them.

---

# 32. Phase S6 — Real-time Stream Backend

Goal:
make messages arrive by themselves.

Build:
- append-only stream read model;
- cursor;
- live delivery via SSE/WebSocket;
- polling fallback;
- reconnect/catch-up;
- de-duplication;
- history pagination;
- exact message lookup;
- search/filter query model.

PASS:
- live message arrives without refresh;
- reconnect loses no messages;
- replay produces no duplicates;
- old history loads upward;
- message remains after browser refresh.

---

# 33. Phase S7 — One-Panel UI Shell

Goal:
build the final V1 application shell.

Only:
- top bar;
- live stream;
- search/filter overlay/drawer;
- sound/settings control;
- floating-window layer.

Build collapsed message bubble first.

PASS:
- desktop feels like a premium messaging application;
- no unnecessary dashboard chrome;
- no separate product sections;
- new message behavior matches messaging UX;
- old-message scrolling remains stable.

---

# 34. Phase S8 — Expandable Message Experience

Goal:
put the entire product inside each message.

Build:
- inline expand/collapse;
- SIMPLE;
- PRO;
- INTELLIGENCE;
- DECISION;
- trade geometry;
- CAPITAL;
- proof action.

Interaction rule:
collapsed feed remains clean.

PASS:
- user can understand first paragraph without expanding;
- user can reach all supported depth from the same message;
- expansion does not destroy scroll position.

---

# 35. Phase S9 — Evidence Window Manager

Goal:
make deep analysis possible without leaving the stream.

Build:
- draggable/resizable windows;
- minimize/close/pin;
- multi-window support;
- focus/z-order;
- session persistence;
- detach/pop-out;
- second-monitor usability.

Build reusable evidence-window framework.

Then implement:
- Liquidity;
- Order Flow;
- Derivatives;
- On-chain;
- Geometry;
- Decision;
- Capital;
- Event Risk;
- frozen Proof.

PASS:
- user can open several evidence windows and continue scrolling;
- detached chart remains tied to exact message identity;
- closing/reopening does not alter underlying evidence.

---

# 36. Phase S10 — Frozen Visual Proof

Goal:
make “show me” stronger than “trust me”.

Build:
- large frozen OHLC;
- supported annotations;
- evidence timestamp/provenance;
- frozen order book where exact binding exists;
- CVD/absorption/liquidity evidence;
- score-component explanation.

PASS:
- every drawn evidence mark is backed by canonical coordinates/identity;
- message -> proof lineage is exact;
- no current-data substitution inside historical proof.

---

# 37. Phase S11 — Capital Story Integration

Goal:
make virtual capital feel alive inside the same conversation.

Complete necessary backend closure:
- canonical three-vault forward paper runtime;
- Core integration into canonical Epoch 2 accounting;
- Tactical 1m/5m execution adapter;
- Opportunity recovery execution adapter;
- sizing;
- R22/R21 atomic accounting;
- capital event projection.

Feed messages:
- candidate;
- eligible;
- hold;
- blocked;
- sizing;
- executed;
- reduced;
- exited;
- accounting updated;
- outcome.

PASS:
- all three vaults can participate under their own rules;
- stream explains why capital acted or did not act;
- no separate Capital screen required;
- every simulated fill links to exact decision/proof.

---

# 38. Phase S12 — Search, Filters and History UX

Goal:
make the one stream usable at scale.

Build:
- magnifying-glass search;
- full-text;
- asset filter;
- category;
- timeframe;
- vault;
- evidence domain;
- state;
- importance;
- date;
- clear filters;
- exact message deep-link.

PASS:
- normal state remains one mixed stream;
- filters never create separate permanent navigation sections;
- search result opens exact original message and evidence.

---

# 39. Phase S13 — Sound and Notifications

Goal:
complete the “someone sent me a message” feeling.

Build:
- original Crypto Signal chime;
- sound permission/unlock;
- on/off;
- volume;
- all / important / Decision+Capital / silent;
- optional desktop/browser notifications;
- unread/new-message indicator.

PASS:
- one new eligible message produces one sound;
- history loading is silent;
- reconnect replay is silent;
- user settings persist;
- sound remains optional.

---

# 40. Phase S14 — Performance, Accessibility and Long-Session Stability

Goal:
make a messaging product that can stay open all day.

Build/test:
- feed virtualization;
- 1,000+ and 10,000+ message fixtures;
- reverse pagination;
- window performance;
- memory growth;
- reconnect;
- keyboard navigation;
- focus handling;
- screen reader;
- reduced motion;
- responsive layout;
- browser zoom/font scaling.

PASS:
- long-running feed remains responsive;
- expanding messages/windows does not corrupt scroll;
- accessibility basics are complete.

---

# 40.1 Rendered Visual Acceptance Contract

Beginning with S7, frontend acceptance must include **actual browser-rendered screenshots**, not source-code inspection alone.

**Reuse existing infrastructure; do not rebuild it from scratch.** The repository already contains the accepted `visualsnapshot` path in `.github/workflows/crypto-mac-command.yml`:
- physical capture runs on the UID504 self-hosted Crypto runner against `http://127.0.0.1:48700`;
- it prefers installed Google Chrome / Chromium / Edge / Chrome Canary with `--headless=new`;
- it currently captures desktop `1440x950` and mobile `430x860` PNGs;
- it uploads `galactech-visual-snapshot-<run_id>` through `actions/upload-artifact@v4`;
- it records exact Product HEAD / read-only / REAL_CAPITAL metadata;
- browser execution is bounded by a 30-second hard timeout, process-group kill, `--renderer-process-limit=2` and exit cleanup after an earlier headless-browser resource incident;
- Safari/AppleScript remains a fallback;
- UID501 already provides the narrow maintenance/cleanup bridge for UID504 headless-process cleanup through `visualcleanup504`.

Stream V1 work must **adapt and extend this existing capture path** to deterministic Stream fixture/preview states instead of introducing a second screenshot stack.

Required acceptance mechanism:
- deterministic UI fixture states rendered in a real browser;
- screenshots captured by the existing UID504 visual-snapshot/artifact path (extended as needed for Stream fixtures);
- common desktop/laptop viewports plus mobile sanity view;
- capture after fonts/layout/data fixture settle;
- screenshot artifact tied to exact commit/run;
- visual review checks hierarchy, clipping, scroll behavior, bubble density, expanded-message readability, floating-window overlap/z-order, search/filter state and responsive behavior;
- critical visual regressions block the relevant UI phase even when unit/contract tests pass.

Minimum screenshot states:
- empty/initial stream;
- normal mixed stream;
- incoming new message;
- user reading old history with “N yeni mesaj” affordance;
- expanded message;
- SIMPLE/PRO/INTELLIGENCE/DECISION/CAPITAL sections;
- one evidence window;
- multiple overlapping evidence windows;
- large frozen proof;
- search/filter open;
- settings/sound state;
- reconnect/degraded-data state;
- long-history viewport.

User-provided screenshots remain valid direct review inputs. The assistant cannot see a local `127.0.0.1` browser without a supplied image or accessible artifact, so Stream V1 must make render artifacts available during UI acceptance.

---

# 41. Phase S15 — Product Acceptance

The product is not accepted because it looks good.

Acceptance scenario must prove:

A user opens Crypto Signal.

A real backend event occurs.

A message appears automatically.

The message:
- sounds once according to settings;
- shows concise original Turkish;
- can be expanded;
- explains SIMPLE;
- exposes technical evidence;
- explains the five-family score;
- explains the system view;
- shows trigger/target/invalidation when available;
- shows capital consequence;
- opens frozen evidence windows;
- persists forever;
- remains searchable/filterable;
- becomes part of a coherent story.

Then the system changes view.

A new message appears.

The old message remains unchanged.

Then a virtual-capital action occurs.

A new capital message appears and can be traced back to the exact decision and evidence.

PASS only when this end-to-end story works.

---

# 42. Phase S16 — Controlled cutover

Do not replace the current deployed product blindly.

Create a preview deployment for Intelligence Stream V1.

Validate:
- API/runtime parity;
- stream persistence;
- live delivery;
- sound;
- search;
- floating windows;
- proof;
- three-vault capital events;
- long session;
- accessibility;
- rollback.

After explicit acceptance:
- new Intelligence Stream becomes the product root;
- old GALACTECH V2 may remain temporarily available as legacy/fallback if operationally useful.

---

# 43. Explicit out-of-scope until Stream V1 is accepted

Do not build now:

- standalone Markets dashboard;
- standalone Capital Center;
- standalone Performance page;
- standalone Archive page;
- standalone Learn page;
- standalone System Health page;
- multi-tab navigation;
- additional decorative dashboards.

If their information is needed, expose it through:
- messages;
- expanded message details;
- evidence windows;
- search;
- contextual drill-down.

After Stream V1 is accepted, future screens may be considered only if a real user need remains.

---

# 44. Current execution order

Do not jump around.

Execute exactly:

**S0 Authority Freeze**  
-> **S1 Stream Capability Audit**  
-> **S2 Event/Message Model**  
-> **S3 Story Engine**  
-> **S4 Analytical Composer**  
-> **S5 Narrative Engine**  
-> **S6 Realtime Backend**  
-> **S7 One-Panel UI**  
-> **S8 Expanded Messages**  
-> **S9 Evidence Windows**  
-> **S10 Frozen Proof**  
-> **S11 Capital Story**  
-> **S12 Search/History**  
-> **S13 Sound**  
-> **S14 Hardening**  
-> **S15 End-to-End Acceptance**  
-> **S16 Controlled Cutover**

One frontier at a time.

A later stage does not begin as the active implementation frontier until the current stage's acceptance criteria are met, except for explicitly documented dependency work.

---

# 45. Definition of done

Intelligence Stream V1 is done only when:

- there is exactly one primary user surface;
- real messages arrive automatically;
- collapsed messages are short;
- every supported message expands into deep explanation;
- technical evidence is clickable;
- evidence opens in movable/resizable windows;
- large proof can detach to another browser window/monitor;
- system prose is original, context-aware and story-aware;
- messages explain what changed;
- messages explain what the system thinks;
- messages explain what would change the view;
- messages explain virtual-capital consequences;
- the five intelligence families are surfaced;
- three-vault paper actions are narratable and traceable;
- every message is backend-persistent;
- no message is silently deleted or rewritten;
- history scrolls upward;
- search and filters work;
- sound is configurable;
- reconnect/history do not duplicate messages or sounds;
- frozen proof is exact where evidence exists;
- the stream can remain open all day without degrading.

Only after this definition of done is accepted should Crypto Signal discuss adding another main screen.
