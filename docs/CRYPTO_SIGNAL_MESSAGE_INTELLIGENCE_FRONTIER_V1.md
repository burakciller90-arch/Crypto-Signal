# Crypto Signal — Message Intelligence & Family Evidence UX Frontier V1

Status: **ACTIVE USER-APPROVED FRONTIER**
Date opened: 2026-09-27
Company: GALACTECH
Product: Crypto Signal
Repository: `burakciller90-arch/Crypto-Signal`
Safety: **REAL_CAPITAL=0**
Supersedes for this scoped frontend/message work: no prior completion status; this is a new, explicit post-F10 refinement authority.

---

## 0. Why this frontier exists

Intelligence Stream V1 and its F0-F10 deficiency-closure program remain mechanically accepted and must not be reopened or replayed.

The user has now explicitly opened a new, narrow frontend/message-intelligence refinement scope because the deployed Stream is functionally live but the visible message language and evidence hierarchy are not yet at the intended product quality.

The current defect is not "messages do not arrive". Live Stream delivery is working.

The defect is that low-level family state transitions such as:

- `mixed -> sell_pressure`;
- `measured:bid_side_liquidity_take_candidate`;
- raw component/state-label names;
- implementation-oriented family transition prose;

can leak into the primary user-facing Stream.

This makes the system feel like telemetry instead of a disciplined market analyst.

This frontier fixes that presentation and composition problem without weakening scientific truth, changing Decision policy, fabricating evidence, adding real-money authority, or rebuilding the accepted backend.

---

## 1. Locked product outcome

The primary Stream must answer three questions within a few seconds:

1. **Sistem ne düşünüyor?**
2. **Neden böyle düşünüyor?**
3. **Ne olursa görüş değişir?**

The default visible message is one concise, natural Turkish system statement.

Example shape, only when exact canonical facts support every claim:

> Bitcoin aşağıdaki kısa vadeli likiditeyi temizledi ve satış baskısı zayıflıyor. 81.800 üzerindeki 15 dakikalık kapanış gerçekleşirse 82.500 bölgesine doğru yükseliş senaryosunu daha güçlü görüyorum.

The UI must not expose raw internal state-machine vocabulary in the normal feed.

No user-facing sentence may invent:

- a price;
- a target;
- a trigger;
- an invalidation;
- a probability;
- a time horizon;
- a causal explanation;
- an actor attribution;
- an evidence family result;
- a score contribution.

Everything must come from canonical persisted facts.

---

## 2. Five-family decision evidence remains canonical

The five accepted evidence families and locked weights remain:

- **Geometry / Market Structure — 20**
- **Liquidity — 25**
- **Order Flow / Absorption — 25**
- **Derivatives — 15**
- **On-chain / Smart Money — 15**

Total: **100 points**.

Event Risk remains outside the 100-point family matrix as a separate gate/context layer.

The total support score is **not a calibrated probability** and must never be presented as "% chance of going up/down".

The product may present a value such as `78/100` as decision/evidence support, not as win probability.

If a family is unavailable, unsupported or not currently live, the UI must show an explicit unavailable state such as:

**— / 15 · VERİ YOK**

It must not silently convert missing evidence into zero directional support.

---

## 3. New collapsed-message contract

The normal Stream bubble must remain visually light.

Required default structure:

**timestamp · symbol · timeframe · stance badge**

Then exactly one short natural-language system paragraph.

Preferred stance vocabulary:

- 🟢 **YÜKSELİŞ BEKLENTİSİ**
- 🔴 **DÜŞÜŞ BEKLENTİSİ**
- 🟡 **NÖTR / BEKLİYORUM**
- ⚠️ **RİSK NEDENİYLE BLOKLU**
- ✅ **BEKLENTİ SONUÇLANDI**

Alternative state wording is allowed only when it is simpler and equally clear.

The default bubble must not contain raw implementation vocabulary such as:

- `mixed`;
- `sell_pressure`;
- `state changed`;
- `candidate`;
- `state_label`;
- raw JSON/component names;
- arrow-heavy transitions;
- internal reason-code strings.

Those may remain available in developer/debug evidence views but not in the normal customer message.

---

## 4. New expanded-message contract

Clicking a message expands a compact decision/evidence summary.

The expanded message should show only decision-relevant information.

Recommended order:

### 4.1 Current view

- direction / stance;
- decision-support score;
- evidence coverage;
- main trigger;
- target if exact;
- invalidation if exact;
- one concise main reservation/contradiction.

### 4.2 Five-family evidence table

Every family row is individually clickable.

Example layout:

| Family | Contribution | State |
| --- | ---: | --- |
| Geometry | 16 / 20 | supports bullish |
| Liquidity | 21 / 25 | supports bullish |
| Order Flow | 22 / 25 | supports bullish |
| Derivatives | 10 / 15 | partial support |
| On-chain | — / 15 | live evidence unavailable |

Labels should be natural Turkish in the UI.

The table is not a developer log. Each row may include at most one short human-readable summary.

---

## 5. Critical user decision: family rows own their proof

This rule is **LOCKED** by explicit user instruction.

There is **no generic bottom CTA** such as:

- "KANIT GRAFİĞİNİ GÖR";
- "DONDURULMUŞ KANITI GÖR";
- one global proof button for the entire message.

Instead:

> **Each of the five family rows is itself the proof entry point.**

When the user clicks a family row, open a family-specific evidence window for that exact message/family.

Examples:

- click **Geometry 16/20** -> Geometry evidence window;
- click **Liquidity 21/25** -> Liquidity evidence window;
- click **Order Flow 22/25** -> Order Flow evidence window;
- click **Derivatives 10/15** -> Derivatives evidence window;
- click **On-chain —/15** -> explicit unavailable/external-dependency evidence window.

No separate global proof action is required below the table.

---

## 6. Family-specific evidence window contract

Every family evidence window must contain two layers.

### 6.1 Short explanation

A small, plain-Turkish explanation specific to that family and this exact message.

Examples of style:

**Likidite**
> Fiyat aşağıdaki kısa vadeli likidite bölgesini temizledi. Bu olay yükseliş senaryosunu destekleyen kanıtlardan biri olarak kaydedildi.

**Emir Akışı**
> Satış tarafındaki agresif akış zayıflarken alıcıların gelen satışları karşılaması yukarı yönlü görüşe destek veriyor.

The explanation must remain fact-bound.

### 6.2 Exact/frozen proof

Show the strongest exact proof available for that family and message.

Possible evidence types include, only when canonically bound:

**Geometry**
- frozen candles;
- market-structure levels;
- trigger;
- target;
- invalidation;
- structure break;
- Harmonic/Elliott/PA evidence where applicable.

**Liquidity**
- liquidity zone;
- sweep point;
- liquidation cluster/heatmap where exact;
- relevant frozen candle;
- source timestamp.

**Order Flow**
- frozen order-book snapshot;
- CVD;
- absorption region;
- measured imbalance;
- taker-flow relation;
- exact market-tape identity.

**Derivatives**
- OI;
- funding;
- basis;
- crowding;
- liquidation context;
- exact persisted derivatives evidence.

**On-chain**
- only accepted live/persisted source evidence.
- if no accepted live source exists, show explicit unavailable state and no invented chart.

Exact evidence states remain fail-closed:

- `READY_EXACT`;
- `IDENTITY_ONLY_EXACT`;
- `UNAVAILABLE_EXPLICIT`.

A current chart/order book must never be substituted for a historical/frozen message proof.

---

## 7. Message composition architecture

The desired user-facing pipeline is:

**Raw market/family evidence**
-> **Five-family confluence**
-> **Deterministic analytical view**
-> **Fact-locked message brief**
-> **Optional guarded local Ollama Turkish polish**
-> **One user-facing system message**
-> **Clickable family evidence windows**

Raw family state transitions remain persisted and auditable.

They should not automatically become separate user-facing feed bubbles merely because one low-level family state changed.

A user-facing message should be emitted when the accepted materiality/story/decision policy says the change is worth telling the user.

This preserves the backend's detailed truth while keeping the customer Stream coherent.

---

## 8. Ollama / local LLM role

The accepted local Ollama path remains presentation-only.

The model may:

- make Turkish more natural;
- remove robotic wording;
- improve sentence flow;
- vary phrasing within the accepted Crypto Signal voice.

The model may not:

- choose market direction;
- calculate the five-family score;
- invent a target;
- invent a trigger;
- invent invalidation;
- invent time horizon;
- invent probability;
- invent a causal explanation;
- reinterpret unavailable evidence as negative evidence;
- create execution/capital authority.

The preferred future input to Ollama is a deterministic, fact-locked analyst brief rather than a raw state-machine sentence.

The deterministic fallback remains mandatory.

---

## 9. Detail reduction rule

The expanded message must not be filled with redundant SIMPLE / PRO / INTELLIGENCE / DECISION / CAPITAL prose merely because those legacy sections exist.

The default expanded experience should prioritize:

- current expectation;
- support score;
- evidence coverage;
- trigger/target/invalidation when exact;
- main contradiction;
- five clickable family rows.

Legacy deep technical data may remain available inside family-specific evidence windows or advanced/developer surfaces.

Capital/Portfolio remains outside this frontier except for already accepted contextual references. Do not reopen or expand the dedicated Capital/Portfolio workstream here.

---

## 10. No historical rewrite

Existing published messages remain immutable.

Do not rewrite historical Stream rows to make them look nicer.

This frontier applies forward from its own activation boundary.

Historical raw/technical messages remain evidence of what was actually published.

No fabricated backfill.

---

## 11. Implementation phases

### MI0 — Authority + exact UI/message contract

Goal:
- make this document the active post-F10 frontend/message frontier;
- update READ_FIRST, CURRENT_STATUS and Chronicle;
- identify exact existing code paths to reuse.

PASS:
- a new agent cannot reasonably mistake F0-F10 for active work;
- no other repository/project is touched.

### MI1 — User-facing message composer

Status: **PASS — accepted on main at `28fa1c208e9e66173214a8bdfaa33cea4bbfe935`; UID504 acceptance run `36330349505`.**

Goal:
- stop low-level family telemetry from being the default customer sentence;
- compose one deterministic system-view message from canonical analytical/confluence facts.

PASS:
- raw `mixed -> sell_pressure` style prose is absent from normal new user-facing messages;
- direction/trigger/target/invalidation only appear when exact;
- missing evidence remains explicit.

### MI2 — Guarded natural Turkish layer

Status: **PASS — accepted on main at `20c1c18c3253254555708e0cbcc0c52cc04ae784`; UID504 acceptance run `36331471395`.**

Goal:
- feed the local rewriter a fact-locked analyst brief;
- improve customer prose without granting factual authority.

PASS:
- local rewrite materially improves language;
- all factual/numeric guardrails remain;
- deterministic fallback still publishes safely.

### MI3 — Five-family evidence summary UI

Status: **PASS — accepted on main at `4dc3c2a4ebdda513f2150313f74f0f06a3a47ec6`; UID504 acceptance run `36332071137`.**

Goal:
- expanded message shows the decision view plus the five weighted family rows.

PASS:
- Geometry 20, Liquidity 25, Order Flow 25, Derivatives 15, On-chain 15 are visible;
- unavailable family is represented as unavailable, not directional zero;
- support score is not labeled probability.

### MI4 — Family-specific clickable proof windows

Status: **ACTIVE FRONTIER**

Goal:
- each family row opens its own proof/explanation window;
- remove the generic global proof CTA from the normal expanded message.

PASS:
- all five rows are individually clickable;
- each click opens the correct family context for the exact message;
- available frozen proof renders exactly;
- unavailable evidence fails closed;
- no global bottom proof button remains.

### MI5 — Real desktop/mobile acceptance

Goal:
- verify live Product behavior with real new Stream messages.

PASS:
- desktop and mobile screenshots prove the new hierarchy;
- live SSE messages arrive in the new presentation;
- evidence row clicks open correct proof;
- no raw state-machine vocabulary leaks into normal presentation;
- search/history/reconnect/sound remain intact;
- REAL_CAPITAL=0.

### MI6 — Authority freeze

Goal:
- record exact accepted behavior and close this refinement frontier.

PASS:
- final acceptance document;
- exact source-to-message/proof ledger update where needed;
- README/READ_FIRST/CURRENT_STATUS/Chronicle state consistent;
- no stale active frontier wording remains.

---

## 12. Out of scope

This frontier does not authorize:

- new main product screens;
- Portfolio/Capital completion work;
- real capital;
- exchange credentials/orders;
- new trading policy;
- looser Decision thresholds;
- fabricated signals;
- historical narrative backfill;
- scientific claims unsupported by evidence;
- Durdurulmaz project changes;
- Quantum Capital project changes;
- shared cross-project runtime/state.

---

## 13. Project isolation — explicit user instruction

This authority applies only to:

**`burakciller90-arch/Crypto-Signal`**

The user explicitly instructed that the separate **Durdurulmaz** project must not be touched.

Do not:

- edit its repository;
- reuse its branch/state;
- change its runtime;
- alter its docs;
- share ports/databases/credentials;
- infer authority over it from this document.

The same project-isolation rules continue to apply to all other repositories.

---

## 14. Immediate frontier

MI1 is accepted. Its exact accepted behavior is:
- the normal Product feed is a primary customer surface;
- five market-family telemetry narratives remain persisted/auditable but are not default customer bubbles;
- Event Risk/provider-quality trust alerts remain visible;
- deterministic collapsed decision copy is one fact-bound Turkish system view;
- historical rows were not rewritten;
- `REAL_CAPITAL=0`.

MI2 is accepted. The local model remains presentation-only and is now constrained by a deterministic fact-locked analyst brief plus deterministic post-rewrite guards.

MI3 is accepted. Canonical five-family decision messages now use the compact evidence-first expanded hierarchy with exact 20/25/25/15/15 weights and fail-closed unavailable states.

The exact next implementation frontier is:

**MI4 — Family-specific clickable proof windows**

Before coding MI4, mechanically re-check current `main`, open PRs, runtime state and any newer authority update.

Reuse the existing:

- five-family confluence matrix;
- analytical view/story system;
- exact evidence contracts;
- visual proof framework;
- local guarded Ollama adapter;
- Stream transport and UI.

Do not create a parallel intelligence engine.

**REAL_CAPITAL=0**
