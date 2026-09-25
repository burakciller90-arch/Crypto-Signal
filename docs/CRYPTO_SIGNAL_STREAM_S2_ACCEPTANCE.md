# Crypto Signal — Stream S2 Canonical Event & Message Model Acceptance

Status: **PASS**  
Authority: `docs/CRYPTO_SIGNAL_INTELLIGENCE_STREAM_V1_MASTER_ROADMAP.md`  
REAL_CAPITAL: **0**

S2 closes the canonical append-only event/message backbone required before Story Engine work.

## Accepted slices

### Slice 1 — immutable source truth and decision context
Merged PR #1261 / main commit `4bc42f00582f47f91b3fcbc17f1f5a6057a4c8bb`.

Accepted:
- forward-only Stream activation boundary;
- immutable Stream source-event model;
- full issuance-time M6 five-family snapshot persistence;
- exact Forecast / Proof / Signal Freeze / Event Risk lineage;
- append-only chronology;
- physical SQLite UPDATE/DELETE rejection;
- no rich historical backfill before activation.

Exact-head UID504 acceptance:
- run `36150140616`;
- focused PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

### Slice 2 — canonical Fact Bundle and Message Input ledger
Merged PR #1262 / main commit `5516c285ce4e174efed3646a89681ba49e1850da`.

Accepted:
- canonical Fact Bundle identity;
- forecast-root Story Identity;
- canonical Message Input identity;
- category/subtype/importance/materiality fields;
- evidence/proof/capital reference slots;
- search/filter metadata;
- relation/supersession metadata;
- renderer/analytical/narrative version slots explicitly unset until later phases;
- append-only Fact Bundle + Message Input persistence;
- deterministic `FORECAST_RESOLVED` continuation in the same story;
- outcome never rewrites issuance truth.

Exact-head UID504 acceptance:
- run `36152613405`;
- focused PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

### Slice 3 — versioned publication policy and source-projector contract
Merged PR #1263 / main commit `d4991438c92df61450cd2c051de6f0e480ca3c47`.

Accepted:
- versioned materiality/publication policy;
- materiality decision identity bound into message identity;
- explicit PUBLISH vs SILENT contract;
- accepted source-projector registry;
- exact decision issuance/resolution projectors marked IMPLEMENTED;
- Event Risk / provider / market-family projectors remain gated on S3-S4 change detection;
- Bitcoin network projector remains deferred until accepted always-on Stream persistence exists;
- provider-neutral M5 smart-money research is not presented as live customer chatter;
- paper-capital projector remains reserved for S11;
- pure deterministic forecast issuance/resolution projection wrappers;
- replay of identical canonical source truth produces the same projection.

Exact-head UID504 acceptance:
- run `36153483021`;
- focused PASS;
- whole-repository regression PASS;
- Development checkout non-mutation PASS.

## S2 PASS criteria

Roadmap criterion: deterministic source event -> canonical Stream message input.  
**PASS** — pure source-event/fact/message projectors are deterministic and exact-identity bound.

Roadmap criterion: idempotent append.  
**PASS** — source ledger and message ledger return unchanged for exact replay and reject conflicting identity reuse.

Roadmap criterion: no duplicate message identity.  
**PASS** — source-event/message uniqueness is enforced by model identity and SQLite uniqueness constraints.

Roadmap criterion: chronological integrity.  
**PASS** — backfill/fork attempts are rejected; event/message append order is immutable.

Roadmap criterion: replay produces the same canonical projection.  
**PASS** — exact replay tests produce identical source event, Fact Bundle and Message Input identities.

## S2 boundaries that remain for later phases

S2 PASS does **not** claim:
- Story Engine change detection — S3;
- analytical stance/opinion composition — S4;
- published Turkish narrative text — S5;
- SSE/WebSocket realtime delivery — S6;
- Stream UI — S7+;
- rich evidence-object lookup/visual proof — S9-S10;
- three-vault capital story/runtime — S11;
- live M5 smart-money provider evidence;
- continuous production liquidation collection;
- trading edge/profitability evidence.

The message input remains deliberately `ready_for_analysis=true` and `ready_for_publication=false`.

## Active frontier

**S2 = PASS. S3 Story Engine and Change Detection is the sole active Stream implementation frontier.**
