"use strict";

const API = Object.freeze({
  messages: "/api/stream/messages",
  live: "/api/stream/live",
  message: (identity) => `/api/stream/messages/${encodeURIComponent(identity)}`,
  detail: (identity) => `/api/stream/messages/${encodeURIComponent(identity)}/detail`,
  visualProof: (identity) =>
    `/api/stream/messages/${encodeURIComponent(identity)}/visual-proof`,
  exactEvidence: (identity) =>
    `/api/stream/messages/${encodeURIComponent(identity)}/evidence`,
  decisionProofForForecast: (identity) =>
    `/api/decision-proof/forecast/${encodeURIComponent(identity)}`,
  education: (concept) => `/api/education/${encodeURIComponent(concept)}`,
  detachedEvidence: (identity, kind) =>
    `/stream-evidence?narrative=${encodeURIComponent(identity)}&kind=${encodeURIComponent(kind)}`,
});

const ui = {
  viewport: document.getElementById("streamViewport"),
  list: document.getElementById("messageList"),
  empty: document.getElementById("emptyState"),
  emptyTitle: document.getElementById("emptyTitle"),
  emptyCopy: document.getElementById("emptyCopy"),
  loadOlder: document.getElementById("loadOlderButton"),
  newButton: document.getElementById("newMessageButton"),
  newCount: document.getElementById("newMessageCount"),
  connectionDot: document.getElementById("connectionDot"),
  connectionLabel: document.getElementById("connectionLabel"),
  connectionNote: document.getElementById("connectionNote"),
  transportMode: document.getElementById("transportMode"),
  fixtureBanner: document.getElementById("fixtureBanner"),
  discoveryDrawer: document.getElementById("discoveryDrawer"),
  settingsDrawer: document.getElementById("settingsDrawer"),
  backdrop: document.getElementById("drawerBackdrop"),
  searchButton: document.getElementById("searchButton"),
  filterButton: document.getElementById("filterButton"),
  soundButton: document.getElementById("soundButton"),
  settingsButton: document.getElementById("settingsButton"),
  soundEnabled: document.getElementById("soundEnabledToggle"),
  soundMode: document.getElementById("soundModeSelect"),
  soundVolume: document.getElementById("soundVolumeInput"),
  soundVolumeValue: document.getElementById("soundVolumeValue"),
  soundUnlock: document.getElementById("soundUnlockButton"),
  testChime: document.getElementById("testChimeButton"),
  desktopNotification: document.getElementById("desktopNotificationToggle"),
  desktopPermission: document.getElementById("desktopPermissionButton"),
  soundStatusPill: document.getElementById("soundStatusPill"),
  notificationStatusText: document.getElementById("notificationStatusText"),
  searchInput: document.getElementById("searchInput"),
  symbolFilter: document.getElementById("symbolFilter"),
  categoryFilter: document.getElementById("categoryFilter"),
  timeframeFilter: document.getElementById("timeframeFilter"),
  vaultFilter: document.getElementById("vaultFilter"),
  evidenceFilter: document.getElementById("evidenceFilter"),
  stateFilter: document.getElementById("stateFilter"),
  importanceFilter: document.getElementById("importanceFilter"),
  fromDateFilter: document.getElementById("fromDateFilter"),
  toDateFilter: document.getElementById("toDateFilter"),
  clearFilters: document.getElementById("clearFiltersButton"),
  applyFilters: document.getElementById("applyFiltersButton"),
  floatingLayer: document.getElementById("floatingWindowLayer"),
  announcer: document.getElementById("liveAnnouncer"),
};

const state = {
  messages: [],
  ids: new Set(),
  beforeCursor: null,
  newestCursor: null,
  hasOlder: false,
  unread: 0,
  eventSource: null,
  pollingTimer: null,
  pollingLiveArmed: false,
  sseEverOpened: false,
  liveNotificationArmed: false,
  notificationRearmTimer: null,
  loadingHistory: false,
  expanded: new Set(),
  details: new Map(),
  detailRequests: new Set(),
  evidenceWindows: new Map(),
  evidenceWindowZ: 1,
  fixture: new URLSearchParams(window.location.search).get("fixture") || "",
  deepLinkIdentity: new URLSearchParams(window.location.search).get("message") || "",
  filters: {
    text: "",
    symbol: "",
    category: "",
    timeframe: "",
    vault: "",
    evidenceDomain: "",
    state: "",
    importance: "",
    fromMs: "",
    toMs: "",
  },
  virtualStart: 0,
  virtualEnd: 0,
  virtualShiftLocked: false,
  lastRenderDurationMs: 0,
  drawerReturnFocus: null,
};

const VIRTUAL_WINDOW_SIZE = 180;
const VIRTUAL_SHIFT_SIZE = 60;
const DETAIL_CACHE_LIMIT = 80;

const EVIDENCE_WINDOW_SESSION_KEY = "crypto-signal-stream-v1-s9-windows";
const EVIDENCE_WINDOW_KINDS = Object.freeze({
  liquidity: { label: "Likidite", family: "liquidity", concept: "liquidity_sweep" },
  order_flow: { label: "Emir Akışı", family: "order_flow", concept: "cvd" },
  derivatives: { label: "Türevler", family: "derivatives", concept: "liquidation_heatmap" },
  onchain: { label: "On-chain", family: "onchain", concept: null },
  geometry: { label: "Geometri", family: "geometry", concept: "invalidation" },
  decision: { label: "Karar", family: null, concept: "agreement_vs_probability" },
  capital: { label: "Sermaye", family: null, concept: "paper_trading" },
  event_risk: { label: "Event Risk", family: null, concept: "abstain" },
  proof: { label: "Proof", family: null, concept: "calibration" },
});

const DECISION_EVIDENCE_FAMILIES = Object.freeze([
  Object.freeze({
    key: "geometry_pa_elliott_harmonic",
    aliases: Object.freeze(["geometry_pa_elliott_harmonic", "geometry"]),
    label: "Geometri",
    weight: 20,
    evidenceKind: "geometry",
  }),
  Object.freeze({
    key: "liquidity",
    aliases: Object.freeze(["liquidity"]),
    label: "Likidite",
    weight: 25,
    evidenceKind: "liquidity",
  }),
  Object.freeze({
    key: "order_flow_absorption",
    aliases: Object.freeze(["order_flow_absorption", "order_flow"]),
    label: "Emir Akışı",
    weight: 25,
    evidenceKind: "order_flow",
  }),
  Object.freeze({
    key: "derivatives",
    aliases: Object.freeze(["derivatives"]),
    label: "Türevler",
    weight: 15,
    evidenceKind: "derivatives",
  }),
  Object.freeze({
    key: "onchain_smart_money",
    aliases: Object.freeze(["onchain_smart_money", "onchain"]),
    label: "On-chain",
    weight: 15,
    evidenceKind: "onchain",
  }),
]);

function text(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatTime(ms) {
  const n = Number(ms);
  if (!Number.isFinite(n)) return "ZAMAN YOK";
  try {
    return new Intl.DateTimeFormat("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    }).format(new Date(n));
  } catch {
    return "ZAMAN YOK";
  }
}

function shortSource(value) {
  const raw = text(value, "deterministic");
  if (raw === "local_rewrite") return "YEREL ANLATIM";
  if (raw === "deterministic") return "DETERMİNİSTİK";
  return raw.replaceAll("_", " ").toUpperCase();
}

function isNearBottom() {
  if (!ui.viewport) return true;
  return ui.viewport.scrollHeight - ui.viewport.scrollTop - ui.viewport.clientHeight < 120;
}

function setConnection(kind, label, note) {
  if (!ui.connectionDot || !ui.connectionLabel || !ui.connectionNote) return;
  ui.connectionDot.className = "connection-dot";
  ui.connectionDot.classList.add(
    kind === "live"
      ? "is-live"
      : kind === "degraded"
        ? "is-degraded"
        : "is-connecting"
  );
  ui.connectionLabel.textContent = label;
  ui.connectionNote.textContent = note;
}

function queryParams({ after = null, before = null, limit = 50 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("surface", "primary");
  if (after) params.set("after", after);
  if (before) params.set("before", before);
  if (state.filters.text) params.set("text", state.filters.text);
  if (state.filters.symbol) params.set("symbol", state.filters.symbol);
  if (state.filters.category) params.set("category", state.filters.category);
  if (state.filters.timeframe) params.set("timeframe", state.filters.timeframe);
  if (state.filters.vault) params.set("vault", state.filters.vault);
  if (state.filters.evidenceDomain) {
    params.set("evidence_domain", state.filters.evidenceDomain);
  }
  if (state.filters.state) params.set("state", state.filters.state);
  if (state.filters.importance) params.set("importance", state.filters.importance);
  if (state.filters.fromMs) params.set("from_ms", state.filters.fromMs);
  if (state.filters.toMs) params.set("to_ms", state.filters.toMs);
  return params;
}

function dateBoundaryMs(value, endOfDay = false) {
  if (!value) return "";
  const suffix = endOfDay ? "T23:59:59.999" : "T00:00:00.000";
  const parsed = new Date(`${value}${suffix}`).getTime();
  return Number.isFinite(parsed) ? String(parsed) : "";
}

function setMessageDeepLink(identity = "") {
  const url = new URL(window.location.href);
  if (identity && exactSha256(identity)) {
    url.searchParams.set("message", identity);
    state.deepLinkIdentity = identity;
  } else {
    url.searchParams.delete("message");
    state.deepLinkIdentity = "";
  }
  window.history.replaceState({}, "", url);
}

function clearDiscoveryControls() {
  for (const control of [
    ui.searchInput,
    ui.symbolFilter,
    ui.categoryFilter,
    ui.timeframeFilter,
    ui.vaultFilter,
    ui.evidenceFilter,
    ui.stateFilter,
    ui.importanceFilter,
    ui.fromDateFilter,
    ui.toDateFilter,
  ]) {
    if (control instanceof HTMLInputElement || control instanceof HTMLSelectElement) {
      control.value = "";
    }
  }
}

function readDiscoveryControls() {
  return {
    text: ui.searchInput?.value.trim() || "",
    symbol: ui.symbolFilter?.value || "",
    category: ui.categoryFilter?.value || "",
    timeframe: ui.timeframeFilter?.value || "",
    vault: ui.vaultFilter?.value || "",
    evidenceDomain: ui.evidenceFilter?.value || "",
    state: ui.stateFilter?.value || "",
    importance: ui.importanceFilter?.value || "",
    fromMs: dateBoundaryMs(ui.fromDateFilter?.value || ""),
    toMs: dateBoundaryMs(ui.toDateFilter?.value || "", true),
  };
}

function resetDiscoveryState() {
  state.filters = {
    text: "",
    symbol: "",
    category: "",
    timeframe: "",
    vault: "",
    evidenceDomain: "",
    state: "",
    importance: "",
    fromMs: "",
    toMs: "",
  };
  clearDiscoveryControls();
  setMessageDeepLink("");
}

async function fetchJson(url, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

function buildChip(label, safe = false) {
  const chip = document.createElement("span");
  chip.className = "message-chip";
  if (safe) chip.classList.add("is-safe");
  chip.textContent = label;
  return chip;
}

function messageText(record) {
  const bundle = record && typeof record === "object" ? record.text : null;
  if (bundle && typeof bundle === "object" && typeof bundle.collapsed_text === "string") {
    return bundle.collapsed_text;
  }
  return "Bu mesajın kısa anlatımı mevcut değil.";
}

function messageState(record) {
  if (typeof record.__fixture_state === "string") return record.__fixture_state;
  if (text(record?.category, "") === "capital") {
    const subtype = text(record?.subtype, "");
    if (subtype === "capital_executed") return "SERMAYE İŞLENDİ";
    if (subtype === "capital_blocked") return "SERMAYE BLOKE";
    if (subtype === "capital_hold") return "NAKİTTE BEKLE";
    if (subtype === "capital_eligible") return "SERMAYE UYGUN";
    if (subtype === "capital_sized") return "SERMAYE BOYUTLANDI";
    if (subtype === "capital_reduced") return "POZİSYON AZALTILDI";
    if (subtype === "capital_exited") return "POZİSYON KAPANDI";
    if (subtype === "capital_candidate") return "SERMAYE ADAYI";
    if (subtype === "capital_accounting_updated") return "MUHASEBE GÜNCELLENDİ";
    if (subtype === "capital_outcome") return "SONUÇ KAYDEDİLDİ";
    return "SERMAYE";
  }
  return "ANALİZ";
}

function displayNumber(value, fallback = "—") {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(n);
}

function decisionEvidenceFamilyConfig(value) {
  const key = text(value, "").toLowerCase();
  return DECISION_EVIDENCE_FAMILIES.find((item) => item.aliases.includes(key)) || null;
}

function familyLabel(value) {
  return decisionEvidenceFamilyConfig(value)?.label || text(value, "Kanıt");
}

function preserveMessageAnchor(item, mutate) {
  if (!ui.viewport) {
    mutate();
    return;
  }
  const beforeTop = item.getBoundingClientRect().top;
  mutate();
  window.requestAnimationFrame(() => {
    if (!ui.viewport || !item.isConnected) return;
    const afterTop = item.getBoundingClientRect().top;
    ui.viewport.scrollTop += afterTop - beforeTop;
  });
}

function depthSection(label, body, { className = "", content = null } = {}) {
  const section = document.createElement("section");
  section.className = `depth-section ${className}`.trim();

  const heading = document.createElement("div");
  heading.className = "depth-heading";
  const eyebrow = document.createElement("span");
  eyebrow.textContent = label;
  heading.append(eyebrow);
  section.append(heading);

  if (content) {
    section.append(content);
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = text(body, "Bu bölüm için ek anlatım yok.");
    section.append(paragraph);
  }
  return section;
}

function decisionEvidenceContribution(fact, config) {
  const families = Array.isArray(fact?.family_contributions)
    ? fact.family_contributions
    : [];
  return (
    families.find((item) => {
      const family = text(item?.family, "").toLowerCase();
      return config.aliases.includes(family);
    }) || null
  );
}

function hasDecisionEvidenceMatrix(fact) {
  return DECISION_EVIDENCE_FAMILIES.every(
    (config) => decisionEvidenceContribution(fact, config) !== null
  );
}

function familyWeightPoints(contribution, config) {
  const prior = Number(contribution?.prior_weight);
  if (Number.isFinite(prior) && prior > 0) {
    return Math.round(prior * 10000) / 100;
  }
  return config.weight;
}

function familyEvidencePresentation(contribution, config) {
  const maximum = familyWeightPoints(contribution, config);
  const stateValue = text(contribution?.state, "").toLowerCase();
  if (!contribution || ["no_evidence", "not_evaluable"].includes(stateValue)) {
    return {
      score: `— / ${displayNumber(maximum)}`,
      status: "VERİ YOK",
      state: "unavailable",
      covered: false,
    };
  }
  if (stateValue === "abstain") {
    return {
      score: `0 / ${displayNumber(maximum)}`,
      status: "NÖTR / ÇEKİMSER",
      state: "neutral",
      covered: true,
    };
  }

  const support = Number(contribution?.support_points);
  const opposition = Number(contribution?.opposition_points);
  const safeSupport = Number.isFinite(support) ? support : 0;
  const safeOpposition = Number.isFinite(opposition) ? opposition : 0;
  const conflicts = Number(contribution?.material_conflict_count);
  let score = `0 / ${displayNumber(maximum)}`;
  let status = "NÖTR";
  let state = "neutral";

  if (safeSupport > safeOpposition && safeSupport > 0) {
    score = `${displayNumber(safeSupport)} / ${displayNumber(maximum)}`;
    status = "DESTEKLİYOR";
    state = "support";
  } else if (safeOpposition > safeSupport && safeOpposition > 0) {
    score = `${displayNumber(safeOpposition)} / ${displayNumber(maximum)}`;
    status = "KARŞI AĞIRLIK";
    state = "opposition";
  }
  if (Number.isFinite(conflicts) && conflicts > 0) {
    status += " · ÇELİŞKİ";
    state = "conflict";
  }
  return { score, status, state, covered: true };
}

function evidenceCoveragePoints(fact) {
  let total = 0;
  for (const config of DECISION_EVIDENCE_FAMILIES) {
    const contribution = decisionEvidenceContribution(fact, config);
    const presentation = familyEvidencePresentation(contribution, config);
    if (presentation.covered) {
      total += familyWeightPoints(contribution, config);
    }
  }
  return Math.round(total * 100) / 100;
}

function customerStanceLabel(value) {
  const labels = {
    bullish: "YÜKSELİŞ BEKLENTİSİ",
    bearish: "DÜŞÜŞ BEKLENTİSİ",
    watch: "NÖTR / BEKLİYORUM",
    blocked: "RİSK NEDENİYLE BLOKLU",
    resolved: "BEKLENTİ SONUÇLANDI",
  };
  const key = text(value, "").toLowerCase();
  return labels[key] || text(value, "BEKLENTİ YOK").replaceAll("_", " ").toUpperCase();
}

function decisionZoneLabel(zone) {
  if (!zone || typeof zone !== "object") return "—";
  const low = Number(zone.low);
  const high = Number(zone.high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "—";
  return low === high
    ? displayNumber(low)
    : `${displayNumber(low)} – ${displayNumber(high)}`;
}

function decisionMetric(labelText, valueText, { className = "" } = {}) {
  const metric = document.createElement("div");
  metric.className = `decision-summary-metric ${className}`.trim();
  const label = document.createElement("span");
  label.textContent = labelText;
  const value = document.createElement("strong");
  value.textContent = text(valueText);
  metric.append(label, value);
  return metric;
}

function currentViewSummary(analytical, fact) {
  const wrap = document.createElement("div");
  wrap.className = "decision-summary";

  const stance = document.createElement("div");
  stance.className = "decision-summary-stance";
  const stanceLabel = document.createElement("span");
  stanceLabel.textContent = "BEKLENTİ";
  const stanceValue = document.createElement("strong");
  stanceValue.textContent = customerStanceLabel(analytical?.stance?.effective_stance);
  stance.append(stanceLabel, stanceValue);

  const metrics = document.createElement("div");
  metrics.className = "decision-summary-grid";
  const support =
    fact?.confluence_support_score_0_100
    ?? analytical?.stance?.support_score_0_100;
  const contradiction = analytical?.main_contradiction?.family
    ? familyLabel(analytical.main_contradiction.family)
    : "Belirgin karşı ağırlık yok";
  const supportLabel =
    fact?.score_semantic === "weighted_directional_family_vote_not_probability"
      ? "Yön desteği"
      : "Karar desteği";
  metrics.append(
    decisionMetric(supportLabel, `${displayNumber(support)} / 100`),
    decisionMetric("Kanıt kapsamı", `${displayNumber(evidenceCoveragePoints(fact))} / 100`),
    decisionMetric("Tetik", decisionZoneLabel(fact?.trigger_zone)),
    decisionMetric("Hedef", decisionZoneLabel(fact?.target_zone)),
    decisionMetric("Geçersizlik", displayNumber(fact?.invalidation_price)),
    decisionMetric("Ana çekince", contradiction, { className: "decision-summary-reservation" })
  );

  const note = document.createElement("p");
  note.className = "decision-summary-note";
  note.textContent =
    fact?.score_semantic === "weighted_directional_family_vote_not_probability"
      ? "Yön desteği sabit family ağırlıklarının gözlenen yön dengesidir; forecast veya olasılık değildir."
      : "Karar desteği ve kanıt kapsamı puandır; yükseliş/düşüş olasılığı değildir.";

  wrap.append(stance, metrics, note);
  return wrap;
}

function familyEvidenceSummaryTable(record, detail) {
  const fact = detail && typeof detail.fact_bundle === "object"
    ? detail.fact_bundle
    : {};
  const table = document.createElement("div");
  table.className = "family-evidence-table";
  table.setAttribute("role", "table");
  table.setAttribute("aria-label", "Beş kanıt ailesi");

  const header = document.createElement("div");
  header.className = "family-evidence-row family-evidence-header";
  header.setAttribute("role", "row");
  for (const headingText of ["KANIT", "KATKI", "DURUM"]) {
    const heading = document.createElement("span");
    heading.setAttribute("role", "columnheader");
    heading.textContent = headingText;
    header.append(heading);
  }
  table.append(header);

  const narrativeIdentity = text(
    record?.narrative_identity ?? detail?.narrative?.narrative_identity,
    ""
  );
  const interactive = exactSha256(narrativeIdentity);

  for (const config of DECISION_EVIDENCE_FAMILIES) {
    const contribution = decisionEvidenceContribution(fact, config);
    const presentation = familyEvidencePresentation(contribution, config);
    const row = document.createElement(interactive ? "button" : "div");
    if (row instanceof HTMLButtonElement) row.type = "button";
    row.className = interactive
      ? "family-evidence-row family-evidence-action"
      : "family-evidence-row";
    row.dataset.family = config.evidenceKind;
    row.dataset.evidenceKind = config.evidenceKind;
    row.dataset.evidenceState = presentation.state;
    if (interactive) {
      row.setAttribute(
        "aria-label",
        `${config.label} kanıtını aç · ${presentation.score} · ${presentation.status}`
      );
    }

    const label = document.createElement("strong");
    label.textContent = config.label;

    const score = document.createElement("span");
    score.className = "family-evidence-score";
    score.textContent = presentation.score;

    const status = document.createElement("span");
    status.className = "family-evidence-status";
    status.textContent = presentation.status;

    row.append(label, score, status);
    if (interactive) {
      row.addEventListener("click", (event) => {
        event.stopPropagation();
        openEvidenceWindow(record, detail, config.evidenceKind);
      });
    }
    table.append(row);
  }
  return table;
}

function evidenceFamilyGrid(fact) {
  return familyEvidenceSummaryTable(null, { fact_bundle: fact });
}

function geometryGrid(fact) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const rows = [
    ["Tetik bölgesi", fact?.trigger_zone?.low, fact?.trigger_zone?.high],
    ["Hedef bölgesi", fact?.target_zone?.low, fact?.target_zone?.high],
    ["Geçersizleşme", fact?.invalidation_price, null],
  ];
  for (const [labelText, low, high] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent =
      high === null
        ? displayNumber(low)
        : `${displayNumber(low)} – ${displayNumber(high)}`;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function proofPanel(fact) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const proofIdentity = text(fact?.proof_identity, "");
  const forecastIdentity = text(fact?.forecast_identity, "");

  const identity = document.createElement("code");
  identity.textContent = proofIdentity
    ? `${proofIdentity.slice(0, 12)}…${proofIdentity.slice(-8)}`
    : "kanıt kimliği yok";

  const action = document.createElement("button");
  action.type = "button";
  action.className = "proof-action";
  action.textContent = "Değiştirilemez kanıtı doğrula";
  action.disabled = !forecastIdentity;

  const result = document.createElement("span");
  result.className = "proof-result";
  result.textContent = "Exact karar kanıtı doğrulanabilir; frozen görsel proof Kanıt penceresinde açılır.";

  action.addEventListener("click", async () => {
    if (!forecastIdentity) return;
    action.disabled = true;
    result.textContent = "Kanıt okunuyor…";
    try {
      const payload = await fetchJson(API.decisionProofForForecast(forecastIdentity));
      if (payload.status === "ready") {
        result.textContent = "Persisted karar kanıtı doğrulandı.";
        result.dataset.state = "ready";
      } else if (payload.status === "empty") {
        result.textContent = "Bu forecast için persisted karar kanıtı bulunamadı.";
        result.dataset.state = "muted";
      } else {
        result.textContent = "Decision Evidence runtime şu anda bağlı değil.";
        result.dataset.state = "muted";
      }
    } catch {
      result.textContent = "Kanıt doğrulama isteği başarısız; veri uydurulmadı.";
      result.dataset.state = "risk";
    } finally {
      action.disabled = false;
    }
  });

  wrap.append(identity, action, result);
  return wrap;
}

function exactSha256(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function familyContribution(detail, family) {
  const fact = detail && typeof detail.fact_bundle === "object" ? detail.fact_bundle : {};
  const config =
    DECISION_EVIDENCE_FAMILIES.find((item) => item.evidenceKind === family)
    || decisionEvidenceFamilyConfig(family);
  if (!config) return null;
  return decisionEvidenceContribution(fact, config);
}

function familyEvidenceExplanation(kind, detail) {
  const config =
    DECISION_EVIDENCE_FAMILIES.find((item) => item.evidenceKind === kind)
    || null;
  if (!config) {
    return "Bu pencere yalnız exact persisted message detail üzerinden okunur.";
  }
  const contribution = familyContribution(detail, kind);
  const presentation = familyEvidencePresentation(contribution, config);
  if (!contribution || presentation.state === "unavailable") {
    return `${config.label} için bu mesajda kabul edilmiş exact kanıt yok. Yönlü katkı üretilmedi ve current data ile kanıt uydurulmadı.`;
  }
  const maximum = familyWeightPoints(contribution, config);
  const support = Number(contribution?.support_points);
  const opposition = Number(contribution?.opposition_points);
  const safeSupport = Number.isFinite(support) ? support : 0;
  const safeOpposition = Number.isFinite(opposition) ? opposition : 0;
  let sentence;
  if (safeSupport > safeOpposition && safeSupport > 0) {
    sentence = `${config.label}, mevcut karar yönünü ${displayNumber(safeSupport)} / ${displayNumber(maximum)} puanla destekliyor.`;
  } else if (safeOpposition > safeSupport && safeOpposition > 0) {
    sentence = `${config.label}, mevcut karar yönüne ${displayNumber(safeOpposition)} / ${displayNumber(maximum)} puanlık karşı ağırlık taşıyor.`;
  } else {
    sentence = `${config.label} ölçüldü ancak bu mesajda yönlü katkı üretmedi.`;
  }
  if (Number(contribution?.material_conflict_count) > 0) {
    sentence += " Bu ailede ayrıca persisted çelişki kaydı var.";
  }
  return sentence;
}

function evidenceWindowSpecificWhy(kind, detail) {
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  const familyConfig = DECISION_EVIDENCE_FAMILIES.find(
    (item) => item.evidenceKind === kind
  );
  if (familyConfig) return familyEvidenceExplanation(kind, detail);
  if (kind === "decision") {
    return `Beklenti ${customerStanceLabel(
      analytical?.stance?.effective_stance
    )}; sonraki koşul ${text(analytical?.next_condition?.state)}. Bu pencere aynı immutable karar lineage'ına bağlıdır.`;
  }
  if (kind === "capital") {
    return `Sanal sermaye sonucu ${text(
      analytical?.capital_consequence?.state,
      "not_bound"
    )}. REAL_CAPITAL=0; burada gerçek para emri yoktur.`;
  }
  if (kind === "event_risk") {
    return `Event Risk durumu ${text(fact?.event_context_state)}. Bu persisted karar bağlamıdır; yeni haber yorumu üretilmez.`;
  }
  if (kind === "proof") {
    return `Forecast ${text(fact?.forecast_identity, "").slice(0, 12)}… ve proof ${text(
      fact?.proof_identity,
      ""
    ).slice(0, 12)}… aynı exact mesaj lineage'ında doğrulanır.`;
  }
  return "Pencere yalnız exact persisted message detail üzerinden okunur.";
}

function evidenceMetric(label, value) {
  const cell = document.createElement("div");
  cell.className = "window-metric";
  const l = document.createElement("span");
  l.textContent = label;
  const v = document.createElement("strong");
  v.textContent = text(value);
  cell.append(l, v);
  return cell;
}

function evidenceWindowSection(label, body = "") {
  const section = document.createElement("section");
  section.className = "window-section";
  const heading = document.createElement("h4");
  heading.textContent = label;
  const paragraph = document.createElement("p");
  paragraph.textContent = text(body);
  section.append(heading, paragraph);
  return section;
}

function buildEvidenceWindowData(kind, detail) {
  const config = EVIDENCE_WINDOW_KINDS[kind];
  const narrative = detail?.narrative || {};
  const fact = detail?.fact_bundle || {};
  const analytical = detail?.analytical_view || {};
  const fragment = document.createDocumentFragment();

  const context = document.createElement("div");
  context.className = "window-context-grid";
  context.append(
    evidenceMetric("Varlık", narrative.symbol),
    evidenceMetric("TF", narrative.timeframe),
    evidenceMetric("Kaynak", narrative.source_kind)
  );
  fragment.append(context);

  const familyConfig = DECISION_EVIDENCE_FAMILIES.find(
    (item) => item.evidenceKind === kind
  );
  if (familyConfig) {
    const family = familyContribution(detail, kind);
    const presentation = familyEvidencePresentation(family, familyConfig);
    fragment.append(
      evidenceWindowSection(
        "BU MESAJDA NE ANLAMA GELİYOR?",
        familyEvidenceExplanation(kind, detail)
      )
    );

    if (kind === "geometry") {
      const geometry = document.createElement("div");
      geometry.className = "window-context-grid";
      geometry.append(
        evidenceMetric(
          "Tetik",
          `${displayNumber(fact?.trigger_zone?.low)}–${displayNumber(fact?.trigger_zone?.high)}`
        ),
        evidenceMetric(
          "Hedef",
          `${displayNumber(fact?.target_zone?.low)}–${displayNumber(fact?.target_zone?.high)}`
        ),
        evidenceMetric("Geçersiz", displayNumber(fact?.invalidation_price))
      );
      fragment.append(geometry);
    }

    const grid = document.createElement("div");
    grid.className = "window-context-grid";
    grid.append(
      evidenceMetric("Katkı", presentation.score),
      evidenceMetric("Durum", presentation.status),
      evidenceMetric(
        "Kanıt kimliği",
        Array.isArray(family?.source_evidence_identities)
          ? String(family.source_evidence_identities.length)
          : "0"
      )
    );
    fragment.append(grid);

    const refs = Array.isArray(family?.source_evidence_identities)
      ? family.source_evidence_identities
      : [];
    const refsSection = evidenceWindowSection(
      "EXACT SOURCE EVIDENCE",
      refs.length
        ? `${refs.length} persisted source identity bu aileye bağlı.`
        : "Bu aile için exact source identity yok; veri uydurulmadı."
    );
    for (const ref of refs) {
      const code = document.createElement("code");
      code.className = "window-identity";
      code.textContent = ref;
      refsSection.append(code);
    }
    fragment.append(refsSection);
  } else if (kind === "decision") {
    fragment.append(
      evidenceWindowSection(
        "Decision state",
        `Stance ${text(analytical?.stance?.effective_stance)} · strength ${text(
          analytical?.stance?.strength
        )} · support ${displayNumber(analytical?.stance?.support_score_0_100)} · opposition ${displayNumber(
          analytical?.stance?.opposition_score_0_100
        )}`
      ),
      evidenceWindowSection(
        "Next / invalidation",
        `${text(analytical?.next_condition?.state)} · ${displayNumber(
          analytical?.invalidation_condition?.price ?? fact?.invalidation_price
        )}`
      )
    );
  } else if (kind === "capital") {
    const capital = analytical?.capital_consequence || {};
    fragment.append(
      evidenceWindowSection(
        "Capital consequence",
        `${text(capital.state, "not_bound")} · current refs ${Array.isArray(
          capital.current_reference_identities
        ) ? capital.current_reference_identities.length : 0} · REAL_CAPITAL=0`
      )
    );
  } else if (kind === "event_risk") {
    fragment.append(
      evidenceWindowSection(
        "Event Risk",
        `Event context ${text(fact?.event_context_state)} · uncertainty ${(
          Array.isArray(fact?.uncertainty_flags) ? fact.uncertainty_flags : []
        ).join(", ") || "yok"}`
      )
    );
  } else if (kind === "proof") {
    const proof = evidenceWindowSection(
      "Exact proof lineage",
      "S9 exact identity penceresini sağlar. Frozen visual coordinates ve çizimler S10 kapsamıdır."
    );
    for (const [label, value] of [
      ["forecast", fact?.forecast_identity],
      ["proof", fact?.proof_identity],
    ]) {
      const code = document.createElement("code");
      code.className = "window-identity";
      code.textContent = `${label}: ${text(value)}`;
      proof.append(code);
    }
    const verify = document.createElement("button");
    verify.type = "button";
    verify.className = "window-primary-action";
    verify.textContent = "Persisted Decision Proof’u doğrula";
    const result = document.createElement("span");
    result.className = "window-action-result";
    verify.addEventListener("click", async () => {
      const forecastIdentity = text(fact?.forecast_identity, "");
      if (!exactSha256(forecastIdentity)) return;
      verify.disabled = true;
      result.textContent = "Doğrulanıyor…";
      try {
        const payload = await fetchJson(API.decisionProofForForecast(forecastIdentity));
        result.textContent =
          payload.status === "ready"
            ? "Persisted Decision Proof doğrulandı."
            : "Persisted Decision Proof bu runtime’da mevcut değil.";
      } catch {
        result.textContent = "Proof isteği başarısız; veri uydurulmadı.";
      } finally {
        verify.disabled = false;
      }
    });
    proof.append(verify, result);
    fragment.append(proof);
  }

  fragment.append(
    evidenceWindowSection(
      "Bu mesajda neden önemli?",
      evidenceWindowSpecificWhy(kind, detail)
    )
  );

  if (config?.concept) {
    const education = evidenceWindowSection(
      "Bu nedir?",
      "Deterministik eğitim açıklaması yalnız istek üzerine yüklenir."
    );
    const button = document.createElement("button");
    button.type = "button";
    button.className = "window-secondary-action";
    button.textContent = "Açıklamayı getir";
    const target = education.querySelector("p");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const payload = await fetchJson(API.education(config.concept));
        if (target) {
          target.textContent = `${text(payload?.lesson?.beginner_tr)} ${text(
            payload?.lesson?.why_it_matters_tr,
            ""
          )}`.trim();
        }
      } catch {
        if (target) target.textContent = "Eğitim içeriği şu anda okunamadı.";
      } finally {
        button.disabled = false;
      }
    });
    education.append(button);
    fragment.append(education);
  }

  return fragment;
}

function evidenceWindowId(narrativeIdentity, kind) {
  return `${narrativeIdentity}:${kind}`;
}

function defaultEvidenceWindowGeometry(index) {
  const layer = ui.floatingLayer?.getBoundingClientRect();
  const layerWidth = layer?.width || window.innerWidth;
  const width = Math.min(470, Math.max(340, layerWidth - 32));
  return {
    x: Math.max(12, layerWidth - width - 26 - (index % 3) * 28),
    y: 18 + (index % 5) * 34,
    width,
    height: 520,
  };
}

function evidenceWindowSnapshot() {
  return [...state.evidenceWindows.values()].map((model) => ({
    id: model.id,
    narrativeIdentity: model.narrativeIdentity,
    kind: model.kind,
    x: Math.round(model.x),
    y: Math.round(model.y),
    width: Math.round(model.width),
    height: Math.round(model.height),
    minimized: Boolean(model.minimized),
    pinned: Boolean(model.pinned),
    z: Number(model.z) || 1,
  }));
}

function persistEvidenceWindows() {
  try {
    localStorage.setItem(
      EVIDENCE_WINDOW_SESSION_KEY,
      JSON.stringify(evidenceWindowSnapshot())
    );
  } catch {
    // Session persistence is best-effort; evidence truth remains server-side.
  }
}

function applyEvidenceWindowGeometry(model) {
  const node = model.element;
  if (!(node instanceof HTMLElement)) return;
  const layer = ui.floatingLayer?.getBoundingClientRect();
  if (layer) {
    const effectiveHeight = model.minimized ? 56 : model.height;
    model.width = Math.min(Math.max(320, model.width), Math.max(320, layer.width - 16));
    model.height = Math.min(Math.max(260, model.height), Math.max(260, layer.height - 16));
    model.x = Math.min(Math.max(8, model.x), Math.max(8, layer.width - model.width - 8));
    model.y = Math.min(Math.max(8, model.y), Math.max(8, layer.height - effectiveHeight - 8));
  }
  node.style.left = `${Math.round(model.x)}px`;
  node.style.top = `${Math.round(model.y)}px`;
  node.style.width = `${Math.round(model.width)}px`;
  node.style.height = `${Math.round(model.height)}px`;
  node.style.zIndex = String((model.pinned ? 5000 : 2000) + model.z);
  node.classList.toggle("is-minimized", Boolean(model.minimized));
  node.classList.toggle("is-pinned", Boolean(model.pinned));
  const pin = node.querySelector('[data-window-action="pin"]');
  if (pin instanceof HTMLButtonElement) {
    pin.setAttribute("aria-pressed", String(Boolean(model.pinned)));
    pin.title = model.pinned ? "Sabitlemeyi kaldır" : "Pencereyi sabitle";
  }
  const minimize = node.querySelector('[data-window-action="minimize"]');
  if (minimize instanceof HTMLButtonElement) {
    minimize.textContent = model.minimized ? "□" : "—";
    minimize.title = model.minimized ? "Geri aç" : "Küçült";
  }
}

function focusEvidenceWindow(id) {
  const model = state.evidenceWindows.get(id);
  if (!model) return;
  state.evidenceWindowZ += 1;
  model.z = state.evidenceWindowZ;
  applyEvidenceWindowGeometry(model);
  persistEvidenceWindows();
}

function closeEvidenceWindow(id, { persist = true } = {}) {
  const model = state.evidenceWindows.get(id);
  if (!model) return;
  model.element?.remove();
  state.evidenceWindows.delete(id);
  if (persist) persistEvidenceWindows();
}

function closeAllEvidenceWindows({ persist = true } = {}) {
  for (const id of [...state.evidenceWindows.keys()]) {
    closeEvidenceWindow(id, { persist: false });
  }
  if (persist) persistEvidenceWindows();
}

function startEvidenceWindowDrag(event, model) {
  if (!(event instanceof PointerEvent) || event.button !== 0) return;
  if (event.target instanceof Element && event.target.closest("button")) return;
  focusEvidenceWindow(model.id);
  const startX = event.clientX;
  const startY = event.clientY;
  const originX = model.x;
  const originY = model.y;

  const move = (moveEvent) => {
    model.x = originX + (moveEvent.clientX - startX);
    model.y = originY + (moveEvent.clientY - startY);
    applyEvidenceWindowGeometry(model);
  };
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    persistEvidenceWindows();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end, { once: true });
  window.addEventListener("pointercancel", end, { once: true });
  event.preventDefault();
}

function startEvidenceWindowResize(event, model) {
  if (!(event instanceof PointerEvent) || event.button !== 0 || model.minimized) return;
  focusEvidenceWindow(model.id);
  const startX = event.clientX;
  const startY = event.clientY;
  const originWidth = model.width;
  const originHeight = model.height;

  const move = (moveEvent) => {
    model.width = originWidth + (moveEvent.clientX - startX);
    model.height = originHeight + (moveEvent.clientY - startY);
    applyEvidenceWindowGeometry(model);
  };
  const end = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
    persistEvidenceWindows();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end, { once: true });
  window.addEventListener("pointercancel", end, { once: true });
  event.preventDefault();
}

async function hydrateFrozenVisualProof(model) {
  const familyKind = DECISION_EVIDENCE_FAMILIES.some(
    (item) => item.evidenceKind === model.kind
  );
  if (!familyKind && model.kind !== "proof") return;
  const body = model.element?.querySelector(".evidence-window-body");
  if (!(body instanceof HTMLElement)) return;

  const fullRenderer = window.CryptoSignalVisualProof?.renderFrozenVisualProof;
  const familyExactRenderer =
    window.CryptoSignalVisualProof?.renderFamilyExactEvidence;
  if (model.kind === "proof" && typeof fullRenderer !== "function") return;
  if (familyKind && typeof familyExactRenderer !== "function") return;

  const record = state.messages.find(
    (item) => item?.narrative_identity === model.narrativeIdentity
  );

  if (familyKind) {
    let exactEvidence =
      record?.__fixture_exact_evidence &&
      typeof record.__fixture_exact_evidence === "object"
        ? record.__fixture_exact_evidence
        : null;
    if (!exactEvidence) {
      try {
        const payload = await fetchJson(API.exactEvidence(model.narrativeIdentity));
        exactEvidence =
          payload?.evidence && typeof payload.evidence === "object"
            ? payload.evidence
            : {
                status: payload?.status || "unavailable",
                reason: payload?.reason || "exact_family_evidence_unavailable",
                narrative_identity: model.narrativeIdentity,
                current_data_substitution: false,
              };
      } catch {
        exactEvidence = {
          status: "unavailable",
          reason: "exact_family_evidence_request_failed",
          narrative_identity: model.narrativeIdentity,
          current_data_substitution: false,
        };
      }
    }
    if (!model.element?.isConnected) return;
    const currentBody = model.element.querySelector(".evidence-window-body");
    if (!(currentBody instanceof HTMLElement)) return;
    currentBody.querySelector(".frozen-visual-proof")?.remove();
    const contribution = familyContribution(model.detail, model.kind);
    currentBody.prepend(
      familyExactRenderer(exactEvidence, {
        kind: model.kind,
        contribution,
      })
    );
    return;
  }

  let visualProof =
    record?.__fixture_visual_proof &&
    typeof record.__fixture_visual_proof === "object"
      ? record.__fixture_visual_proof
      : null;
  if (!visualProof) {
    try {
      const payload = await fetchJson(API.visualProof(model.narrativeIdentity));
      visualProof =
        payload?.visual_proof && typeof payload.visual_proof === "object"
          ? payload.visual_proof
          : {
              status: payload?.status || "unavailable",
              reason: payload?.reason || "exact_visual_proof_unavailable",
              narrative_identity: model.narrativeIdentity,
            };
    } catch {
      visualProof = {
        status: "unavailable",
        reason: "visual_proof_request_failed",
        narrative_identity: model.narrativeIdentity,
      };
    }
  }

  if (!model.element?.isConnected) return;
  const currentBody = model.element.querySelector(".evidence-window-body");
  if (!(currentBody instanceof HTMLElement)) return;
  currentBody.querySelector(".frozen-visual-proof")?.remove();
  currentBody.prepend(fullRenderer(visualProof));
}

function renderEvidenceWindowBody(model, detail) {
  const body = model.element?.querySelector(".evidence-window-body");
  if (!(body instanceof HTMLElement)) return;
  body.replaceChildren(buildEvidenceWindowData(model.kind, detail));
  model.detail = detail;
  const narrative = detail?.narrative || {};
  const subtitle = model.element?.querySelector(".evidence-window-subtitle");
  if (subtitle) {
    subtitle.textContent = `${text(narrative.symbol, "PİYASA")} · ${text(
      narrative.timeframe
    )} · ${model.narrativeIdentity.slice(0, 8)}…`;
  }
  if (
    model.kind === "proof"
    || DECISION_EVIDENCE_FAMILIES.some((item) => item.evidenceKind === model.kind)
  ) {
    void hydrateFrozenVisualProof(model);
  }
}

async function hydrateEvidenceWindow(model, detail = null) {
  if (detail && typeof detail === "object") {
    renderEvidenceWindowBody(model, detail);
    return;
  }
  try {
    const payload = await fetchJson(API.detail(model.narrativeIdentity));
    if (payload.status === "ready" && payload.detail) {
      renderEvidenceWindowBody(model, payload.detail);
      return;
    }
    throw new Error("detail unavailable");
  } catch {
    const body = model.element?.querySelector(".evidence-window-body");
    if (body instanceof HTMLElement) {
      body.replaceChildren(
        detailPlaceholder("Exact persisted evidence detail okunamadı; veri uydurulmadı.")
      );
    }
  }
}

function createEvidenceWindowShell(model) {
  if (!ui.floatingLayer) return null;
  const config = EVIDENCE_WINDOW_KINDS[model.kind];
  if (!config) return null;

  const node = document.createElement("article");
  node.className = "evidence-window";
  node.dataset.windowId = model.id;
  node.dataset.kind = model.kind;
  node.dataset.narrativeIdentity = model.narrativeIdentity;
  node.setAttribute("role", "dialog");
  node.setAttribute("aria-label", `${config.label} kanıt penceresi`);

  const bar = document.createElement("header");
  bar.className = "evidence-window-bar evidence-window-drag";

  const heading = document.createElement("div");
  heading.className = "evidence-window-heading";
  const title = document.createElement("strong");
  title.textContent = config.label;
  const subtitle = document.createElement("span");
  subtitle.className = "evidence-window-subtitle";
  subtitle.textContent = `${model.narrativeIdentity.slice(0, 8)}…`;
  heading.append(title, subtitle);

  const controls = document.createElement("div");
  controls.className = "evidence-window-controls";
  const controlSpecs = [
    ["minimize", "—", "Küçült"],
    ["pin", "⌖", "Sabitle"],
    ["detach", "↗", "Ayrı pencereye al"],
    ["close", "×", "Kapat"],
  ];
  for (const [action, glyph, label] of controlSpecs) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.windowAction = action;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.textContent = glyph;
    if (action === "pin") button.setAttribute("aria-pressed", "false");
    controls.append(button);
  }
  bar.append(heading, controls);

  const body = document.createElement("div");
  body.className = "evidence-window-body";
  body.append(detailPlaceholder("Exact persisted evidence yükleniyor…"));

  const resize = document.createElement("button");
  resize.type = "button";
  resize.className = "evidence-window-resize";
  resize.setAttribute("aria-label", "Pencereyi yeniden boyutlandır");
  resize.title = "Yeniden boyutlandır";

  node.append(bar, body, resize);
  ui.floatingLayer.append(node);
  model.element = node;

  node.addEventListener("pointerdown", () => focusEvidenceWindow(model.id));
  bar.addEventListener("pointerdown", (event) => startEvidenceWindowDrag(event, model));
  resize.addEventListener("pointerdown", (event) => startEvidenceWindowResize(event, model));

  controls.addEventListener("click", (event) => {
    const button = event.target instanceof Element
      ? event.target.closest("button[data-window-action]")
      : null;
    if (!(button instanceof HTMLButtonElement)) return;
    const action = button.dataset.windowAction;
    if (action === "close") {
      closeEvidenceWindow(model.id);
    } else if (action === "minimize") {
      model.minimized = !model.minimized;
      button.textContent = model.minimized ? "□" : "—";
      applyEvidenceWindowGeometry(model);
      persistEvidenceWindows();
    } else if (action === "pin") {
      model.pinned = !model.pinned;
      focusEvidenceWindow(model.id);
    } else if (action === "detach") {
      const url = API.detachedEvidence(model.narrativeIdentity, model.kind);
      button.dataset.detachUrl = url;
      window.open(
        url,
        "_blank",
        "popup=yes,resizable=yes,scrollbars=yes,width=900,height=760"
      );
    }
    event.stopPropagation();
  });

  const detach = controls.querySelector('[data-window-action="detach"]');
  if (detach instanceof HTMLButtonElement) {
    detach.dataset.detachUrl = API.detachedEvidence(model.narrativeIdentity, model.kind);
  }

  applyEvidenceWindowGeometry(model);
  return node;
}

function systemViewFamilyProofIdentity(detail, kind) {
  if (!detail?.system_view) return "";
  const contribution = familyContribution(detail, kind);
  const identity = text(contribution?.source_narrative_identity, "");
  return exactSha256(identity) ? identity : "";
}

function openEvidenceWindow(record, detail, kind) {
  const config = EVIDENCE_WINDOW_KINDS[kind];
  const ownerIdentity = text(
    record?.narrative_identity ?? detail?.narrative?.narrative_identity,
    ""
  );
  const sourceIdentity = systemViewFamilyProofIdentity(detail, kind);
  const narrativeIdentity = sourceIdentity || ownerIdentity;
  if (!config || !exactSha256(ownerIdentity) || !exactSha256(narrativeIdentity)) {
    return null;
  }

  const id = evidenceWindowId(ownerIdentity, kind);
  const existing = state.evidenceWindows.get(id);
  if (existing) {
    focusEvidenceWindow(id);
    if (detail) renderEvidenceWindowBody(existing, detail);
    return existing;
  }

  const geometry = defaultEvidenceWindowGeometry(state.evidenceWindows.size);
  const model = {
    id,
    narrativeIdentity,
    kind,
    ...geometry,
    minimized: false,
    pinned: false,
    z: ++state.evidenceWindowZ,
    element: null,
    detail: null,
  };
  state.evidenceWindows.set(id, model);
  createEvidenceWindowShell(model);
  persistEvidenceWindows();
  void hydrateEvidenceWindow(model, detail);
  return model;
}

function restoreEvidenceWindows() {
  let raw;
  try {
    raw = JSON.parse(localStorage.getItem(EVIDENCE_WINDOW_SESSION_KEY) || "[]");
  } catch {
    return;
  }
  if (!Array.isArray(raw)) return;
  for (const saved of raw.slice(0, 10)) {
    if (!saved || !exactSha256(saved.narrativeIdentity) || !EVIDENCE_WINDOW_KINDS[saved.kind]) {
      continue;
    }
    const id = evidenceWindowId(saved.narrativeIdentity, saved.kind);
    const defaults = defaultEvidenceWindowGeometry(state.evidenceWindows.size);
    const model = {
      id,
      narrativeIdentity: saved.narrativeIdentity,
      kind: saved.kind,
      x: Number.isFinite(Number(saved.x)) ? Number(saved.x) : defaults.x,
      y: Number.isFinite(Number(saved.y)) ? Number(saved.y) : defaults.y,
      width: Number.isFinite(Number(saved.width)) ? Number(saved.width) : defaults.width,
      height: Number.isFinite(Number(saved.height)) ? Number(saved.height) : defaults.height,
      minimized: Boolean(saved.minimized),
      pinned: Boolean(saved.pinned),
      z: Number.isFinite(Number(saved.z)) ? Number(saved.z) : ++state.evidenceWindowZ,
      element: null,
      detail: null,
    };
    state.evidenceWindowZ = Math.max(state.evidenceWindowZ, model.z);
    state.evidenceWindows.set(id, model);
    createEvidenceWindowShell(model);
    void hydrateEvidenceWindow(model);
  }
}

function evidenceWindowLauncher(record, detail) {
  const launcher = document.createElement("section");
  launcher.className = "evidence-launcher depth-wide";
  const heading = document.createElement("div");
  heading.className = "evidence-launcher-head";
  const title = document.createElement("strong");
  title.textContent = "KANIT PENCERELERİ";
  const note = document.createElement("span");
  note.textContent = "Akıştan ayrılmadan derinleş";
  heading.append(title, note);

  const actions = document.createElement("div");
  actions.className = "evidence-launcher-actions";
  for (const [kind, config] of Object.entries(EVIDENCE_WINDOW_KINDS)) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.evidenceKind = kind;
    button.textContent = config.label;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openEvidenceWindow(record, detail, kind);
    });
    actions.append(button);
  }
  launcher.append(heading, actions);
  return launcher;
}

function compactIdentity(value, fallback = "kanıt kimliği yok") {
  const raw = text(value, "");
  if (!exactSha256(raw)) return fallback;
  return `${raw.slice(0, 12)}…${raw.slice(-8)}`;
}

function capitalMetricGrid(capital) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const rows = [
    ["Vault", text(capital?.vault_id, "—")],
    ["Aksiyon", text(capital?.action, "—")],
    ["Miktar", displayNumber(capital?.quantity)],
    ["Referans", `${displayNumber(capital?.reference_price)} USDT`],
    ["Simüle fill", `${displayNumber(capital?.simulated_fill_price)} USDT`],
    ["Notional", `${displayNumber(capital?.notional_usdt)} USDT`],
    [
      "Nakit",
      `${displayNumber(capital?.cash_before_usdt)} → ${displayNumber(
        capital?.cash_after_usdt
      )} USDT`,
    ],
    [
      "Vault NAV",
      `${displayNumber(capital?.vault_nav_before_usdt)} → ${displayNumber(
        capital?.vault_nav_after_usdt
      )} USDT`,
    ],
    [
      "Epoch 2 NAV",
      `${displayNumber(capital?.consolidated_nav_before_usdt)} → ${displayNumber(
        capital?.consolidated_nav_after_usdt
      )} USDT`,
    ],
    [
      "Maliyet",
      `fee ${displayNumber(capital?.fee_usdt)} · spread ${displayNumber(
        capital?.spread_usdt
      )} · slippage ${displayNumber(capital?.slippage_usdt)} USDT`,
    ],
  ];
  if (capital?.outcome_identity) {
    rows.push(
      ["Finansal sonuç", text(capital?.financial_outcome, "—")],
      ["Gerçekleşen PnL", `${displayNumber(capital?.realized_pnl_delta_usdt)} USDT`],
      [
        "Pozisyon miktarı",
        `${displayNumber(capital?.position_quantity_before)} → ${displayNumber(
          capital?.position_quantity_after
        )}`,
      ]
    );
  }
  for (const [labelText, valueText] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function capitalLineagePanel(capital) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const rows = [
    ["R22 bundle", capital?.bundle_identity],
    ["R22 intent", capital?.intent_identity],
    ["R22 fill", capital?.fill_identity],
    ...(capital?.outcome_identity ? [["Outcome", capital.outcome_identity]] : []),
    ["Vault önce", capital?.before_vault_snapshot_identity],
    ["Vault sonra", capital?.after_vault_snapshot_identity],
    ["Epoch 2 önce", capital?.before_consolidated_snapshot_identity],
    ["Epoch 2 sonra", capital?.after_consolidated_snapshot_identity],
  ];
  for (const [labelText, identity] of rows) {
    const line = document.createElement("div");
    line.className = "condition-row";
    const label = document.createElement("span");
    label.textContent = labelText;
    const code = document.createElement("code");
    code.textContent = compactIdentity(identity);
    line.append(label, code);
    wrap.append(line);
  }
  const authority = document.createElement("small");
  authority.textContent = "Immutable paper-capital kanıtı · REAL_CAPITAL=0 · borsa emri yok";
  wrap.append(authority);
  return wrap;
}

function capitalDecisionMetricGrid(capital) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const reasons = Array.isArray(capital?.reason_codes)
    ? capital.reason_codes.join(" · ")
    : "—";
  const rows = [
    ["Vault", text(capital?.vault_id, "—")],
    ["Durum", text(capital?.disposition, "—").toUpperCase()],
    ["Event Risk", text(capital?.event_risk_state, "—").toUpperCase()],
    ["Zaman ufku", text(capital?.timeframe, "—")],
    ["Başlangıç bütçesi", `${displayNumber(capital?.starting_budget_usdt)} USDT`],
    ["Nedenler", reasons],
  ];
  for (const [labelText, valueText] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function capitalDecisionLineagePanel(capital) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const rows = [
    ["Vault decision", capital?.decision_identity],
    ["Allocator assessment", capital?.allocator_assessment_identity],
    ["Allocator candidate", capital?.allocator_candidate_identity],
  ];
  for (const [labelText, identity] of rows) {
    const line = document.createElement("div");
    line.className = "condition-row";
    const label = document.createElement("span");
    label.textContent = labelText;
    const code = document.createElement("code");
    code.textContent = compactIdentity(identity);
    line.append(label, code);
    wrap.append(line);
  }
  const refs = Array.isArray(capital?.capital_reference_identities)
    ? capital.capital_reference_identities
    : [];
  const evidence = document.createElement("small");
  evidence.textContent = `Exact kanıt zinciri: ${refs.length} kimlik · REAL_CAPITAL=0 · borsa emri yok`;
  wrap.append(evidence);
  return wrap;
}

function capitalSizingMetricGrid(capital) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const fraction = Number(capital?.fraction_of_vault);
  const rows = [
    ["Vault", text(capital?.vault_id, "—")],
    [
      "Vault payı",
      Number.isFinite(fraction) ? `%${displayNumber(fraction * 100)}` : "—",
    ],
    ["Paper notional", `${displayNumber(capital?.canonical_notional_usdt)} USDT`],
    ["Mevcut nakit", `${displayNumber(capital?.current_cash_usdt)} USDT`],
    ["Mevcut NAV", `${displayNumber(capital?.current_nav_usdt)} USDT`],
    ["Zaman ufku", text(capital?.timeframe, "—")],
  ];
  for (const [labelText, valueText] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function capitalSizingLineagePanel(capital) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const rows = [
    ["Sizing event", capital?.sizing_event_identity],
    ["Sizing selection", capital?.selection_identity],
    ["Eligibility proof", capital?.eligibility_proof_identity],
    ["Allocator candidate", capital?.allocator_candidate_identity],
  ];
  for (const [labelText, identity] of rows) {
    const line = document.createElement("div");
    line.className = "condition-row";
    const label = document.createElement("span");
    label.textContent = labelText;
    const code = document.createElement("code");
    code.textContent = compactIdentity(identity);
    line.append(label, code);
    wrap.append(line);
  }
  const note = document.createElement("small");
  note.textContent =
    "Boyut seçimi execution değildir · fill/PnL yok · REAL_CAPITAL=0 · borsa emri yok";
  wrap.append(note);
  return wrap;
}

function buildCapitalSizingExpandedContent(record, detail) {
  const capital =
    detail && typeof detail.capital_sizing === "object" && detail.capital_sizing
      ? detail.capital_sizing
      : record;
  const textBundle =
    capital && typeof capital.text === "object" && capital.text ? capital.text : {};
  const grid = document.createElement("div");
  grid.className = "message-depth-grid";

  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, {
      className: "depth-simple depth-wide",
    }),
    depthSection("PRO", textBundle.technical_text, {
      className: "depth-pro",
    })
  );

  const sizingTruth = document.createElement("div");
  sizingTruth.className = "depth-composite";
  const copy = document.createElement("p");
  copy.textContent = text(
    textBundle.intelligence_text,
    "Bu kayıt yalnız paper sizing kararını açıklar; henüz execution veya fill yoktur."
  );
  sizingTruth.append(copy, capitalSizingMetricGrid(capital));
  grid.append(
    depthSection("CAPITAL SIZING", "", {
      className: "depth-intelligence depth-wide",
      content: sizingTruth,
    })
  );

  grid.append(
    depthSection("DECISION", textBundle.decision_text, {
      className: "depth-decision",
    }),
    depthSection("CAPITAL", textBundle.capital_text, {
      className: "depth-capital",
    }),
    depthSection("IMMUTABLE LINEAGE", "", {
      className: "depth-proof depth-wide",
      content: capitalSizingLineagePanel(capital),
    })
  );
  return grid;
}

function buildCapitalDecisionExpandedContent(record, detail) {
  const capital =
    detail && typeof detail.capital_decision === "object" && detail.capital_decision
      ? detail.capital_decision
      : record;
  const textBundle =
    capital && typeof capital.text === "object" && capital.text ? capital.text : {};
  const grid = document.createElement("div");
  grid.className = "message-depth-grid";

  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, {
      className: "depth-simple depth-wide",
    }),
    depthSection("PRO", textBundle.technical_text, {
      className: "depth-pro",
    })
  );

  const truth = document.createElement("div");
  truth.className = "depth-composite";
  const copy = document.createElement("p");
  copy.textContent = text(
    textBundle.intelligence_text,
    "Bu kayıt yalnız allocator sermaye kararını açıklar; fill veya PnL üretmez."
  );
  truth.append(copy, capitalDecisionMetricGrid(capital));
  grid.append(
    depthSection("CAPITAL DECISION", "", {
      className: "depth-intelligence depth-wide",
      content: truth,
    })
  );

  grid.append(
    depthSection("DECISION", textBundle.decision_text, {
      className: "depth-decision",
    }),
    depthSection("CAPITAL", textBundle.capital_text, {
      className: "depth-capital",
    })
  );
  grid.append(
    depthSection("IMMUTABLE LINEAGE", "", {
      className: "depth-proof depth-wide",
      content: capitalDecisionLineagePanel(capital),
    })
  );
  return grid;
}

function buildCapitalExpandedContent(record, detail) {
  const capital =
    detail && typeof detail.capital_story === "object" && detail.capital_story
      ? detail.capital_story
      : record;
  const textBundle =
    capital && typeof capital.text === "object" && capital.text ? capital.text : {};

  const grid = document.createElement("div");
  grid.className = "message-depth-grid";
  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, {
      className: "depth-simple depth-wide",
    }),
    depthSection("PRO", textBundle.technical_text, {
      className: "depth-pro",
    })
  );

  const intelligence = document.createElement("div");
  intelligence.className = "depth-composite";
  const intelligenceCopy = document.createElement("p");
  intelligenceCopy.textContent = text(
    textBundle.intelligence_text,
    "Bu kayıt için ek sermaye yorumu mevcut değil."
  );
  intelligence.append(intelligenceCopy, capitalMetricGrid(capital));
  grid.append(
    depthSection("CAPITAL TRUTH", "", {
      className: "depth-intelligence depth-wide",
      content: intelligence,
    })
  );

  grid.append(
    depthSection("DECISION", textBundle.decision_text, {
      className: "depth-decision",
    }),
    depthSection("CAPITAL", textBundle.capital_text, {
      className: "depth-capital",
    })
  );

  grid.append(
    depthSection("IMMUTABLE LINEAGE", "", {
      className: "depth-proof depth-wide",
      content: capitalLineagePanel(capital),
    })
  );
  return grid;
}

function capitalLifecycleGrid(capital) {
  const grid = document.createElement("div");
  grid.className = "geometry-grid";
  const subtype = text(capital?.subtype, "");
  const rows = [];

  if (subtype === "capital_candidate") {
    rows.push(
      ["Aday", compactIdentity(capital?.allocator_candidate_identity)],
      ["Değerlendirme", compactIdentity(capital?.allocator_assessment_identity)],
      ["Durum", "3 vault değerlendirmesi başladı"],
      ["Otorite", "Paper-only · REAL_CAPITAL=0"]
    );
  } else if (subtype === "capital_accounting_updated") {
    rows.push(
      ["Vault", text(capital?.vault_id, "—").replaceAll("_", " ")],
      ["Aksiyon", text(capital?.action, "—")],
      [
        "Nakit",
        `${displayNumber(capital?.cash_before_usdt)} → ${displayNumber(
          capital?.cash_after_usdt
        )} USDT`,
      ],
      [
        "Vault NAV",
        `${displayNumber(capital?.vault_nav_before_usdt)} → ${displayNumber(
          capital?.vault_nav_after_usdt
        )} USDT`,
      ],
      [
        "Epoch 2 NAV",
        `${displayNumber(capital?.consolidated_nav_before_usdt)} → ${displayNumber(
          capital?.consolidated_nav_after_usdt
        )} USDT`,
      ],
      ["R22 bundle", compactIdentity(capital?.bundle_identity)]
    );
  } else if (subtype === "capital_outcome") {
    rows.push(
      ["Vault", text(capital?.vault_id, "—").replaceAll("_", " ")],
      ["Aksiyon", text(capital?.action, "—")],
      ["Finansal sonuç", text(capital?.financial_outcome, "—")],
      ["Gerçekleşen PnL", `${displayNumber(capital?.realized_pnl_delta_usdt)} USDT`],
      [
        "Pozisyon",
        `${displayNumber(capital?.position_quantity_before)} → ${displayNumber(
          capital?.position_quantity_after
        )}`,
      ],
      ["Outcome", compactIdentity(capital?.outcome_identity)]
    );
  }

  for (const [labelText, valueText] of rows) {
    const cell = document.createElement("div");
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    cell.append(label, value);
    grid.append(cell);
  }
  return grid;
}

function capitalLifecycleLineage(capital) {
  const wrap = document.createElement("div");
  wrap.className = "proof-panel";
  const rows = [
    ["Lifecycle", capital?.lifecycle_identity],
    ["Candidate", capital?.allocator_candidate_identity],
    ["Assessment", capital?.allocator_assessment_identity],
    ["Forecast", capital?.forecast_identity],
    ["Proof", capital?.proof_identity],
    ["Decision context", capital?.decision_context_identity],
    ["R22 bundle", capital?.bundle_identity],
    ["Outcome", capital?.outcome_identity],
  ];
  for (const [labelText, identity] of rows) {
    if (!exactSha256(identity)) continue;
    const line = document.createElement("div");
    line.className = "condition-row";
    const label = document.createElement("span");
    label.textContent = labelText;
    const code = document.createElement("code");
    code.textContent = compactIdentity(identity);
    line.append(label, code);
    wrap.append(line);
  }
  const authority = document.createElement("small");
  authority.textContent = "Deterministic immutable lifecycle · REAL_CAPITAL=0 · gerçek borsa emri yok";
  wrap.append(authority);
  return wrap;
}

function buildCapitalLifecycleExpandedContent(record, detail) {
  const capital =
    detail && typeof detail.capital_lifecycle === "object" && detail.capital_lifecycle
      ? detail.capital_lifecycle
      : record;
  const textBundle =
    capital && typeof capital.text === "object" && capital.text ? capital.text : {};
  const grid = document.createElement("div");
  grid.className = "message-depth-grid";

  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, {
      className: "depth-simple depth-wide",
    }),
    depthSection("PRO", textBundle.technical_text, {
      className: "depth-pro",
    })
  );

  const truth = document.createElement("div");
  truth.className = "depth-composite";
  const copy = document.createElement("p");
  copy.textContent = text(
    textBundle.intelligence_text,
    "Bu lifecycle olayı için ek yorum mevcut değil."
  );
  truth.append(copy, capitalLifecycleGrid(capital));
  grid.append(
    depthSection("CAPITAL LIFECYCLE", "", {
      className: "depth-intelligence depth-wide",
      content: truth,
    }),
    depthSection("DECISION", textBundle.decision_text, {
      className: "depth-decision",
    }),
    depthSection("CAPITAL", textBundle.capital_text, {
      className: "depth-capital",
    }),
    depthSection("IMMUTABLE LINEAGE", "", {
      className: "depth-proof depth-wide",
      content: capitalLifecycleLineage(capital),
    })
  );
  return grid;
}

function buildExpandedContent(record, detail) {
  const subtype = text(record?.subtype, "");
  if (
    subtype === "capital_candidate"
    || subtype === "capital_accounting_updated"
    || subtype === "capital_outcome"
    || (detail && typeof detail.capital_lifecycle === "object" && detail.capital_lifecycle)
  ) {
    return buildCapitalLifecycleExpandedContent(record, detail);
  }
  if (
    subtype === "capital_sized"
    || (detail && typeof detail.capital_sizing === "object" && detail.capital_sizing)
  ) {
    return buildCapitalSizingExpandedContent(record, detail);
  }
  if (
    subtype !== "capital_executed"
    && (
      subtype === "capital_eligible"
      || subtype === "capital_hold"
      || subtype === "capital_blocked"
      || (detail && typeof detail.capital_decision === "object" && detail.capital_decision)
    )
  ) {
    return buildCapitalDecisionExpandedContent(record, detail);
  }
  if (
    subtype === "capital_executed"
    || subtype === "capital_reduced"
    || subtype === "capital_exited"
    || (detail && typeof detail.capital_story === "object" && detail.capital_story)
  ) {
    return buildCapitalExpandedContent(record, detail);
  }
  const textBundle =
    record && typeof record.text === "object" && record.text ? record.text : {};
  const fact = detail && typeof detail.fact_bundle === "object"
    ? detail.fact_bundle
    : {};
  const analytical = detail && typeof detail.analytical_view === "object"
    ? detail.analytical_view
    : {};

  if (hasDecisionEvidenceMatrix(fact)) {
    const decisionGrid = document.createElement("div");
    decisionGrid.className = "message-depth-grid message-decision-evidence-grid";
    decisionGrid.append(
      depthSection("KARAR ÖZETİ", "", {
        className: "depth-decision depth-wide",
        content: currentViewSummary(analytical, fact),
      }),
      depthSection("5 KANIT AİLESİ", "", {
        className: "depth-intelligence depth-wide",
        content: familyEvidenceSummaryTable(record, detail),
      })
    );
    return decisionGrid;
  }

  const grid = document.createElement("div");
  grid.className = "message-depth-grid";

  grid.append(
    depthSection("SIMPLE", textBundle.simple_text, { className: "depth-simple depth-wide" }),
    depthSection("PRO", textBundle.technical_text, { className: "depth-pro" })
  );

  const intelligence = document.createElement("div");
  intelligence.className = "depth-composite";
  const intelligenceCopy = document.createElement("p");
  intelligenceCopy.textContent = text(
    textBundle.intelligence_text,
    "Structured intelligence anlatımı mevcut değil."
  );
  intelligence.append(intelligenceCopy, evidenceFamilyGrid(fact));
  grid.append(
    depthSection("INTELLIGENCE", "", {
      className: "depth-intelligence depth-wide",
      content: intelligence,
    })
  );

  const decision = document.createElement("div");
  decision.className = "depth-composite";
  const decisionCopy = document.createElement("p");
  decisionCopy.textContent = text(
    textBundle.decision_text,
    "Karar anlatımı mevcut değil."
  );
  const conditions = document.createElement("div");
  conditions.className = "condition-row";
  const next = document.createElement("span");
  next.textContent = `Sonraki koşul · ${text(analytical?.next_condition?.state, "ölçülmedi")}`;
  const invalidation = document.createElement("span");
  invalidation.textContent = `Geçersizleşme · ${displayNumber(
    analytical?.invalidation_condition?.price ?? fact?.invalidation_price
  )}`;
  conditions.append(next, invalidation);
  decision.append(decisionCopy, conditions);
  grid.append(
    depthSection("DECISION", "", {
      className: "depth-decision",
      content: decision,
    }),
    depthSection("TRADE GEOMETRY", "", {
      className: "depth-geometry",
      content: geometryGrid(fact),
    })
  );

  const capital = document.createElement("div");
  capital.className = "depth-composite";
  const capitalCopy = document.createElement("p");
  capitalCopy.textContent = text(
    textBundle.capital_text,
    "Bu mesajda sermaye anlatımı mevcut değil."
  );
  const capitalState = document.createElement("span");
  capitalState.className = "capital-state";
  capitalState.textContent = `Sanal sermaye sonucu · ${text(
    analytical?.capital_consequence?.state,
    "not_bound"
  ).replaceAll("_", " ")} · REAL_CAPITAL=0`;
  capital.append(capitalCopy, capitalState);
  grid.append(
    depthSection("CAPITAL", "", {
      className: "depth-capital",
      content: capital,
    }),
    depthSection("PROOF", "", {
      className: "depth-proof",
      content: proofPanel(fact),
    })
  );

  grid.append(evidenceWindowLauncher(record, detail));
  return grid;
}

function detailPlaceholder(label) {
  const box = document.createElement("div");
  box.className = "message-depth-placeholder";
  box.textContent = label;
  return box;
}

function renderExpandedPanel(item, record, detail) {
  const panel = item.querySelector(".message-detail");
  if (!(panel instanceof HTMLElement)) return;
  preserveMessageAnchor(item, () => {
    panel.replaceChildren(buildExpandedContent(record, detail));
    panel.hidden = false;
  });
}

function currentRenderedMessage(identity, fallback = null) {
  if (!identity || !ui.list) return fallback;
  const current = ui.list.querySelector(
    `.message[data-identity="${CSS.escape(identity)}"]`
  );
  return current instanceof HTMLElement ? current : fallback;
}

async function loadMessageDetail(item, record) {
  const identity = text(record?.narrative_identity, "");
  if (!identity || state.detailRequests.has(identity)) return;

  if (record.__fixture_detail && typeof record.__fixture_detail === "object") {
    rememberDetail(identity, record.__fixture_detail);
    renderExpandedPanel(item, record, record.__fixture_detail);
    return;
  }

  state.detailRequests.add(identity);
  try {
    const payload = await fetchJson(API.detail(identity));
    if (payload.status === "ready" && payload.detail) {
      rememberDetail(identity, payload.detail);
      const target = currentRenderedMessage(identity, item);
      if (target instanceof HTMLElement && state.expanded.has(identity)) {
        renderExpandedPanel(target, record, payload.detail);
      }
    } else {
      const target = currentRenderedMessage(identity, item);
      const panel = target?.querySelector(".message-detail");
      if (
        target instanceof HTMLElement
        && panel instanceof HTMLElement
        && state.expanded.has(identity)
      ) {
        preserveMessageAnchor(target, () => {
          panel.replaceChildren(
            detailPlaceholder(
              payload.status === "unavailable"
                ? "Structured detail runtime şu anda bağlı değil."
                : "Bu mesaj için structured detail bulunamadı."
            )
          );
        });
      }
    }
  } catch {
    const target = currentRenderedMessage(identity, item);
    const panel = target?.querySelector(".message-detail");
    if (
      target instanceof HTMLElement
      && panel instanceof HTMLElement
      && state.expanded.has(identity)
    ) {
      preserveMessageAnchor(target, () => {
        panel.replaceChildren(
          detailPlaceholder("Structured detail okunamadı; içerik uydurulmadı.")
        );
      });
    }
  } finally {
    state.detailRequests.delete(identity);
  }
}

function toggleMessageExpansion(item, record) {
  const identity = text(record?.narrative_identity, "");
  if (!identity) return;
  const summary = item.querySelector(".message-summary");
  const panel = item.querySelector(".message-detail");
  if (!(summary instanceof HTMLButtonElement) || !(panel instanceof HTMLElement)) return;

  const willOpen = !state.expanded.has(identity);
  if (
    willOpen
    && !state.details.has(identity)
    && record.__fixture_detail
    && typeof record.__fixture_detail === "object"
  ) {
    rememberDetail(identity, record.__fixture_detail);
  }
  preserveMessageAnchor(item, () => {
    if (willOpen) {
      state.expanded.add(identity);
      setMessageDeepLink(identity);
      item.classList.add("is-expanded");
      summary.setAttribute("aria-expanded", "true");
      const cue = summary.querySelector(".message-expand-cue");
      if (cue) cue.textContent = "Detayı kapat ↑";
      panel.hidden = false;
      const cached = state.details.get(identity);
      panel.replaceChildren(
        cached
          ? buildExpandedContent(record, cached)
          : detailPlaceholder("Exact persisted message depth okunuyor…")
      );
    } else {
      state.expanded.delete(identity);
      if (state.deepLinkIdentity === identity) setMessageDeepLink("");
      item.classList.remove("is-expanded");
      summary.setAttribute("aria-expanded", "false");
      const cue = summary.querySelector(".message-expand-cue");
      if (cue) cue.textContent = "Detayı aç ↓";
      panel.hidden = true;
    }
  });

  if (willOpen && !state.details.has(identity)) {
    void loadMessageDetail(item, record);
  }
}

function renderMessage(
  record,
  { isNew = false, absoluteIndex = 0, totalMessages = 1 } = {}
) {
  const item = document.createElement("li");
  item.className = "message";
  item.setAttribute("role", "article");
  item.setAttribute("aria-posinset", String(absoluteIndex + 1));
  item.setAttribute("aria-setsize", String(totalMessages));
  if (isNew) item.classList.add("is-new");
  const identity = text(record.narrative_identity, "");
  item.dataset.identity = identity;
  item.dataset.category = text(record?.category, "");
  item.dataset.subtype = text(record?.subtype, "");
  item.dataset.vaultId = text(record?.vault_id, "");

  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "message-summary";
  const detailId = `message-detail-${identity}`;
  summary.setAttribute("aria-expanded", String(state.expanded.has(identity)));
  summary.setAttribute("aria-controls", detailId);
  summary.setAttribute(
    "aria-label",
    `${text(record.symbol, "Piyasa")} ${text(record.timeframe, "")} · ${messageState(
      record
    )} · detayı ${state.expanded.has(identity) ? "kapat" : "aç"}`
  );

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const time = document.createElement("span");
  time.textContent = formatTime(record.event_at_ms);
  const symbol = document.createElement("strong");
  symbol.textContent = text(record.symbol, "PİYASA");
  const timeframe = document.createElement("span");
  timeframe.textContent = text(record.timeframe, "—");
  const stateBadge = document.createElement("span");
  stateBadge.className = "message-state";
  stateBadge.textContent = messageState(record);
  meta.append(time, symbol, timeframe, stateBadge);

  const copy = document.createElement("p");
  copy.className = "message-copy";
  copy.textContent = messageText(record);

  const footer = document.createElement("div");
  footer.className = "message-summary-foot";
  const chips = document.createElement("div");
  chips.className = "message-chips";
  chips.append(buildChip(shortSource(record.source_kind)));
  if (text(record?.category, "") === "capital") {
    chips.append(buildChip("CAPITAL"));
    const vault = text(record?.vault_id, "");
    if (vault) chips.append(buildChip(vault.replaceAll("_", " ")));
  }
  if (record.original_text_preserved === true) chips.append(buildChip("ORİJİNAL METİN"));
  if (record.real_capital === 0) chips.append(buildChip("GERÇEK PARA KAPALI", true));
  const cue = document.createElement("span");
  cue.className = "message-expand-cue";
  cue.textContent = state.expanded.has(identity) ? "Detayı kapat ↑" : "Detayı aç ↓";
  footer.append(chips, cue);
  summary.append(meta, copy, footer);

  const detailPanel = document.createElement("div");
  detailPanel.className = "message-detail";
  detailPanel.id = detailId;
  detailPanel.hidden = !state.expanded.has(identity);
  const cached = state.details.get(identity);
  if (state.expanded.has(identity)) {
    detailPanel.append(
      cached
        ? buildExpandedContent(record, cached)
        : detailPlaceholder("Exact persisted message depth okunuyor…")
    );
    item.classList.add("is-expanded");
  }

  summary.addEventListener("click", () => toggleMessageExpansion(item, record));
  item.append(summary, detailPanel);
  if (state.expanded.has(identity) && !cached) void loadMessageDetail(item, record);
  return item;
}
function captureViewportAnchor() {
  if (!ui.viewport || !ui.list) return null;
  const viewportTop = ui.viewport.getBoundingClientRect().top;
  const rendered = [...ui.list.querySelectorAll(".message")];
  const item =
    rendered.find((node) => node.getBoundingClientRect().bottom > viewportTop + 1)
    || rendered[0];
  if (!(item instanceof HTMLElement)) return null;
  const identity = item.dataset.identity || "";
  if (!identity) return null;
  return {
    identity,
    top: item.getBoundingClientRect().top,
  };
}

function restoreViewportAnchor(anchor) {
  if (!anchor || !ui.viewport || !ui.list) {
    state.virtualShiftLocked = false;
    return;
  }
  window.requestAnimationFrame(() => {
    try {
      if (!ui.viewport || !ui.list) return;
      const item = ui.list.querySelector(
        `.message[data-identity="${CSS.escape(anchor.identity)}"]`
      );
      if (!(item instanceof HTMLElement)) return;
      ui.viewport.scrollTop += item.getBoundingClientRect().top - anchor.top;
    } finally {
      state.virtualShiftLocked = false;
    }
  });
}

function resetVirtualWindow({ pinToBottom = false } = {}) {
  const total = state.messages.length;
  if (!total) {
    state.virtualStart = 0;
    state.virtualEnd = 0;
    return;
  }
  if (total <= VIRTUAL_WINDOW_SIZE) {
    state.virtualStart = 0;
    state.virtualEnd = total;
    return;
  }
  if (pinToBottom) {
    state.virtualEnd = total;
    state.virtualStart = Math.max(0, total - VIRTUAL_WINDOW_SIZE);
    return;
  }
  const start = Math.min(
    Math.max(0, state.virtualStart),
    Math.max(0, total - VIRTUAL_WINDOW_SIZE)
  );
  state.virtualStart = start;
  state.virtualEnd = Math.min(total, start + VIRTUAL_WINDOW_SIZE);
}

function centerVirtualWindow(index) {
  const total = state.messages.length;
  if (!total) return;
  const half = Math.floor(VIRTUAL_WINDOW_SIZE / 2);
  state.virtualStart = Math.max(
    0,
    Math.min(index - half, Math.max(0, total - VIRTUAL_WINDOW_SIZE))
  );
  state.virtualEnd = Math.min(total, state.virtualStart + VIRTUAL_WINDOW_SIZE);
}

function shiftVirtualWindow(direction) {
  if (
    state.virtualShiftLocked
    || state.messages.length <= VIRTUAL_WINDOW_SIZE
    || !ui.viewport
  ) {
    return false;
  }
  const anchor = captureViewportAnchor();
  const total = state.messages.length;
  const currentStart = state.virtualStart;
  const maxStart = Math.max(0, total - VIRTUAL_WINDOW_SIZE);
  const nextStart =
    direction === "older"
      ? Math.max(0, currentStart - VIRTUAL_SHIFT_SIZE)
      : Math.min(maxStart, currentStart + VIRTUAL_SHIFT_SIZE);
  if (nextStart === currentStart) return false;
  state.virtualShiftLocked = true;
  state.virtualStart = nextStart;
  state.virtualEnd = Math.min(total, nextStart + VIRTUAL_WINDOW_SIZE);
  renderAll({ anchor });
  return true;
}

function rememberDetail(identity, detail) {
  if (!identity) return;
  if (state.details.has(identity)) state.details.delete(identity);
  state.details.set(identity, detail);
  while (state.details.size > DETAIL_CACHE_LIMIT) {
    const oldest = state.details.keys().next().value;
    if (!oldest) break;
    state.details.delete(oldest);
  }
}

function renderAll({ anchor = null, pinToBottom = false } = {}) {
  if (!ui.list || !ui.empty) return;
  const started = performance.now();
  if (pinToBottom) resetVirtualWindow({ pinToBottom: true });
  else resetVirtualWindow();

  ui.list.setAttribute("aria-busy", "true");
  ui.list.replaceChildren();
  const total = state.messages.length;
  const start = state.virtualStart;
  const end = state.virtualEnd;
  for (let index = start; index < end; index += 1) {
    ui.list.append(
      renderMessage(state.messages[index], {
        absoluteIndex: index,
        totalMessages: total,
      })
    );
  }
  ui.list.dataset.totalMessages = String(total);
  ui.list.dataset.renderStart = String(start);
  ui.list.dataset.renderEnd = String(end);
  ui.list.dataset.renderedMessages = String(Math.max(0, end - start));
  ui.list.setAttribute("aria-busy", "false");

  const isEmpty = total === 0;
  ui.empty.hidden = !isEmpty;
  ui.list.hidden = isEmpty;
  if (ui.loadOlder) ui.loadOlder.hidden = !state.hasOlder || isEmpty;
  state.lastRenderDurationMs = performance.now() - started;
  updateUnread();
  if (anchor) restoreViewportAnchor(anchor);
}

function notificationApi() {
  return window.CryptoSignalNotifications || null;
}

function notificationSnapshot() {
  return notificationApi()?.snapshot?.() || {
    settings: { enabled: false, volume: 0.55, mode: "important", desktopEnabled: false },
    unlocked: false,
    audioState: "unavailable",
    notificationPermission: "unsupported",
    audit: {},
  };
}

function syncNotificationUi(note = "") {
  const snapshot = notificationSnapshot();
  const settings = snapshot.settings || {};
  if (ui.soundEnabled instanceof HTMLInputElement) {
    ui.soundEnabled.checked = settings.enabled === true;
  }
  if (ui.soundMode instanceof HTMLSelectElement) {
    ui.soundMode.value = text(settings.mode, "important");
  }
  if (ui.soundVolume instanceof HTMLInputElement) {
    ui.soundVolume.value = String(Math.round(Number(settings.volume || 0) * 100));
  }
  if (ui.soundVolumeValue) {
    ui.soundVolumeValue.textContent = `${Math.round(Number(settings.volume || 0) * 100)}%`;
  }
  if (ui.desktopNotification instanceof HTMLInputElement) {
    ui.desktopNotification.checked = settings.desktopEnabled === true;
  }
  if (ui.soundButton) {
    ui.soundButton.dataset.soundEnabled = String(
      settings.enabled === true && settings.mode !== "silent"
    );
  }
  if (ui.soundStatusPill) {
    ui.soundStatusPill.classList.remove("is-ready", "is-locked");
    if (!settings.enabled || settings.mode === "silent") {
      ui.soundStatusPill.textContent = "KAPALI";
    } else if (snapshot.unlocked) {
      ui.soundStatusPill.textContent = "HAZIR";
      ui.soundStatusPill.classList.add("is-ready");
    } else {
      ui.soundStatusPill.textContent = "KİLİTLİ";
      ui.soundStatusPill.classList.add("is-locked");
    }
  }
  if (ui.notificationStatusText) {
    const permission = text(snapshot.notificationPermission, "unsupported");
    ui.notificationStatusText.textContent =
      note
      || `Ses ${snapshot.unlocked ? "hazır" : "kullanıcı jesti bekliyor"} · masaüstü izni ${permission} · geçmiş/replay sessiz.`;
  }
}

function updateNotificationSettings(patch) {
  const api = notificationApi();
  if (!api?.updateSettings) return notificationSnapshot();
  const snapshot = api.updateSettings(patch);
  syncNotificationUi();
  return snapshot;
}

function routeNotification(record, delivery = "silent") {
  const result = notificationApi()?.route?.(record, delivery) || null;
  if (delivery === "live_new") syncNotificationUi();
  return result;
}

function clearNotificationRearmTimer() {
  if (!state.notificationRearmTimer) return;
  window.clearTimeout(state.notificationRearmTimer);
  state.notificationRearmTimer = null;
}

function armAfterReconnectGrace() {
  clearNotificationRearmTimer();
  state.liveNotificationArmed = false;
  state.notificationRearmTimer = window.setTimeout(() => {
    state.liveNotificationArmed = true;
    state.notificationRearmTimer = null;
  }, 1600);
}

function updateUnread() {
  if (!ui.newButton || !ui.newCount) return;
  ui.newCount.textContent = String(state.unread);
  ui.newButton.hidden = state.unread <= 0;
}

function scrollToBottom({ smooth = true } = {}) {
  if (!ui.viewport) return;
  if (state.messages.length > VIRTUAL_WINDOW_SIZE) {
    const needsTail = state.virtualEnd !== state.messages.length;
    resetVirtualWindow({ pinToBottom: true });
    if (needsTail) renderAll();
  }
  ui.viewport.scrollTo({
    top: ui.viewport.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
  state.unread = 0;
  updateUnread();
}

function resetMessages() {
  state.messages = [];
  state.ids = new Set();
  state.beforeCursor = null;
  state.newestCursor = null;
  state.hasOlder = false;
  state.unread = 0;
  state.expanded = new Set();
  state.details = new Map();
  state.detailRequests = new Set();
  state.virtualStart = 0;
  state.virtualEnd = 0;
  state.virtualShiftLocked = false;
  renderAll();
}

function mergeInitial(records) {
  const chronological = [...records].reverse();
  state.messages = [];
  state.ids = new Set();
  for (const record of chronological) {
    const id = text(record.narrative_identity, "");
    if (!id || state.ids.has(id)) continue;
    state.ids.add(id);
    state.messages.push(record);
  }
  resetVirtualWindow({ pinToBottom: true });
}

function appendRecord(
  record,
  cursor = null,
  { fixtureNew = false, delivery = "silent" } = {}
) {
  const id = text(record && record.narrative_identity, "");
  if (!id || state.ids.has(id)) return false;
  const stayAtBottom = isNearBottom();
  const anchor = stayAtBottom ? null : captureViewportAnchor();
  state.ids.add(id);
  state.messages.push(record);

  if (stayAtBottom) {
    resetVirtualWindow({ pinToBottom: true });
    renderAll();
    const newest = ui.list?.lastElementChild;
    if (fixtureNew && newest instanceof HTMLElement) newest.classList.add("is-new");
  } else {
    renderAll({ anchor });
  }

  if (cursor) state.newestCursor = cursor;
  routeNotification(record, delivery);
  if (stayAtBottom) {
    window.requestAnimationFrame(() => scrollToBottom({ smooth: !state.fixture }));
  } else {
    state.unread += 1;
    updateUnread();
    if (ui.announcer) ui.announcer.textContent = `${state.unread} yeni mesaj`;
  }
  return true;
}

function focusRenderedMessage(identity) {
  if (!exactSha256(identity)) return false;
  const index = state.messages.findIndex(
    (item) => item?.narrative_identity === identity
  );
  if (index < 0) return false;
  const record = state.messages[index];
  state.expanded.add(identity);
  centerVirtualWindow(index);
  renderAll();
  const item = ui.list?.querySelector(
    `.message[data-identity="${CSS.escape(identity)}"]`
  );
  if (!(item instanceof HTMLElement)) return false;
  item.classList.add("is-deep-linked");
  if (!state.details.has(identity)) void loadMessageDetail(item, record);
  window.requestAnimationFrame(() => {
    item.scrollIntoView({ block: "center", behavior: "auto" });
  });
  return true;
}

async function loadExactMessage(identity) {
  if (!exactSha256(identity)) {
    setMessageDeepLink("");
    await loadInitial();
    return;
  }
  resetMessages();
  setConnection("connecting", "MESAJ AÇILIYOR", "exact immutable kayıt okunuyor");
  try {
    const payload = await fetchJson(API.message(identity));
    const record =
      payload?.status === "ready" && payload?.message
        ? payload.message
        : null;
    if (!record || record.narrative_identity !== identity) {
      setConnection("degraded", "MESAJ BULUNAMADI", "kimlik için kayıt uydurulmadı");
      if (ui.emptyTitle) ui.emptyTitle.textContent = "Exact mesaj bulunamadı";
      if (ui.emptyCopy) {
        ui.emptyCopy.textContent =
          "Bu immutable kimlik mevcut Stream deposunda bulunmuyor.";
      }
      renderAll();
      return;
    }
    mergeInitial([record]);
    state.hasOlder = false;
    state.beforeCursor = null;
    state.newestCursor = null;
    state.expanded.add(identity);
    renderAll();
    focusRenderedMessage(identity);
    setConnection("live", "EXACT MESAJ", "orijinal kayıt ve kanıt lineage'ı");
    if (ui.transportMode) ui.transportMode.textContent = "EXACT MESSAGE";
  } catch {
    setConnection("degraded", "MESAJ OKUNAMADI", "exact lookup başarısız; veri uydurulmadı");
    renderAll();
  }
}

async function loadInitial() {
  resetMessages();
  setConnection("connecting", "BAĞLANIYOR", "kalıcı mesajlar okunuyor");

  const params = queryParams({ limit: 50 });
  let payload;
  try {
    payload = await fetchJson(`${API.messages}?${params.toString()}`);
  } catch (error) {
    setConnection("degraded", "BAĞLANTI SINIRLI", "polling yanıtı alınamadı");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Akış şu anda okunamıyor";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Backend gerçeği uydurulmadı. Bağlantı yeniden denenecek.";
    renderAll();
    startPolling();
    return;
  }

  const page = payload && typeof payload.page === "object" ? payload.page : null;
  if (payload.status === "unavailable" || !page) {
    setConnection("degraded", "RUNTIME HAZIR DEĞİL", "mesaj deposu yapılandırılmamış");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Stream runtime hazır değil";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Eksik runtime, boş piyasa sinyali gibi gösterilmez.";
    renderAll();
    return;
  }

  const items = Array.isArray(page.items) ? page.items : [];
  mergeInitial(items);
  state.beforeCursor = typeof page.oldest_cursor === "string" ? page.oldest_cursor : null;
  state.newestCursor = typeof page.newest_cursor === "string" ? page.newest_cursor : null;
  state.hasOlder = Boolean(page.has_more);
  renderAll();
  window.requestAnimationFrame(() => scrollToBottom({ smooth: false }));
  connectLive();
}

async function loadOlder() {
  if (state.loadingHistory || !state.beforeCursor || !state.hasOlder) return;
  state.loadingHistory = true;
  if (ui.loadOlder) ui.loadOlder.textContent = "Yükleniyor…";
  const before = state.beforeCursor;
  const anchor = captureViewportAnchor();

  try {
    const params = queryParams({ before, limit: 50 });
    const payload = await fetchJson(`${API.messages}?${params.toString()}`);
    const page = payload && typeof payload.page === "object" ? payload.page : null;
    const items = page && Array.isArray(page.items) ? [...page.items].reverse() : [];
    const additions = [];
    for (const record of items) {
      const id = text(record.narrative_identity, "");
      if (!id || state.ids.has(id)) continue;
      state.ids.add(id);
      additions.push(record);
    }
    state.messages = [...additions, ...state.messages];
    state.virtualStart += additions.length;
    state.virtualEnd += additions.length;
    state.beforeCursor = page && typeof page.oldest_cursor === "string" ? page.oldest_cursor : state.beforeCursor;
    state.hasOlder = Boolean(page && page.has_more);
    renderAll({ anchor });
  } catch {
    setConnection("degraded", "GEÇMİŞ SINIRLI", "eski mesajlar yüklenemedi");
  } finally {
    state.loadingHistory = false;
    if (ui.loadOlder) ui.loadOlder.textContent = "↑ Daha eski mesajları yükle";
  }
}

function liveUrl() {
  const params = queryParams({ after: state.newestCursor, limit: 200 });
  params.delete("before");
  return `${API.live}?${params.toString()}`;
}

function connectLive() {
  if (state.fixture) return;
  if (state.eventSource) state.eventSource.close();
  if (!("EventSource" in window)) {
    setConnection("degraded", "POLLING", "EventSource yok; güvenli fallback");
    startPolling();
    return;
  }

  setConnection("connecting", "CANLI AKIŞ", "SSE bağlantısı kuruluyor");
  const source = new EventSource(liveUrl());
  state.eventSource = source;

  source.addEventListener("open", () => {
    setConnection("live", "CANLI", "SSE bağlı · yeni mesajlar otomatik");
    stopPolling();
    if (!state.sseEverOpened) {
      state.sseEverOpened = true;
      state.liveNotificationArmed = true;
    } else {
      armAfterReconnectGrace();
    }
    if (ui.transportMode) ui.transportMode.textContent = "SSE CANLI";
  });

  source.addEventListener("message", (event) => {
    try {
      const record = JSON.parse(event.data);
      appendRecord(record, event.lastEventId || null, {
        delivery: state.liveNotificationArmed ? "live_new" : "replay",
      });
    } catch {
      setConnection("degraded", "AKIŞ HATASI", "geçersiz mesaj güvenle reddedildi");
    }
  });

  source.addEventListener("error", () => {
    clearNotificationRearmTimer();
    state.liveNotificationArmed = false;
    state.pollingLiveArmed = false;
    setConnection("degraded", "YENİDEN BAĞLANIYOR", "SSE kesildi · polling fallback aktif");
    if (ui.transportMode) ui.transportMode.textContent = "POLLING FALLBACK";
    startPolling();
  });
}

async function pollCatchUp() {
  if (state.fixture) return;
  try {
    const params = queryParams({ after: state.newestCursor, limit: 100 });
    const payload = await fetchJson(`${API.messages}?${params.toString()}`);
    const page = payload && typeof payload.page === "object" ? payload.page : null;
    const items = page && Array.isArray(page.items) ? page.items : [];
    const delivery = state.pollingLiveArmed ? "live_new" : "replay";
    for (const record of items) appendRecord(record, null, { delivery });
    if (page && typeof page.newest_cursor === "string" && items.length) {
      state.newestCursor = page.newest_cursor;
    }
    state.pollingLiveArmed = true;
  } catch {
    setConnection("degraded", "BAĞLANTI SINIRLI", "SSE ve polling yeniden denenecek");
  }
}

function startPolling() {
  if (state.pollingTimer) return;
  void pollCatchUp();
  state.pollingTimer = window.setInterval(() => void pollCatchUp(), 5000);
}

function stopPolling() {
  if (!state.pollingTimer) return;
  window.clearInterval(state.pollingTimer);
  state.pollingTimer = null;
}

function activeDrawer() {
  return [ui.discoveryDrawer, ui.settingsDrawer].find(
    (drawer) => drawer instanceof HTMLElement && !drawer.hidden
  ) || null;
}

function drawerFocusable(drawer) {
  if (!(drawer instanceof HTMLElement)) return [];
  return [...drawer.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), '
      + 'textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
  )].filter((item) => item instanceof HTMLElement && !item.hidden);
}

function openDrawer(drawer, opener = document.activeElement) {
  if (!(drawer instanceof HTMLElement) || !ui.backdrop) return;
  if (opener instanceof HTMLElement && !drawer.contains(opener)) {
    state.drawerReturnFocus = opener;
  }
  for (const item of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (item && item !== drawer) item.hidden = true;
  }
  drawer.hidden = false;
  ui.backdrop.hidden = false;
  if (ui.searchButton) ui.searchButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.filterButton) ui.filterButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.soundButton) ui.soundButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
  if (ui.settingsButton) ui.settingsButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
  window.requestAnimationFrame(() => {
    const first = drawerFocusable(drawer)[0];
    (first || drawer).focus({ preventScroll: true });
  });
}

function closeDrawers({ restoreFocus = true } = {}) {
  const wasOpen = activeDrawer();
  for (const drawer of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (drawer) drawer.hidden = true;
  }
  if (ui.backdrop) ui.backdrop.hidden = true;
  for (const button of [ui.searchButton, ui.filterButton, ui.soundButton, ui.settingsButton]) {
    if (button) button.setAttribute("aria-expanded", "false");
  }
  if (
    wasOpen
    && restoreFocus
    && state.drawerReturnFocus instanceof HTMLElement
    && state.drawerReturnFocus.isConnected
  ) {
    state.drawerReturnFocus.focus({ preventScroll: true });
  }
  state.drawerReturnFocus = null;
}

function handleDrawerKeyboard(event) {
  const drawer = activeDrawer();
  if (!drawer) return false;
  if (event.key === "Escape") {
    event.preventDefault();
    closeDrawers();
    return true;
  }
  if (event.key !== "Tab") return false;
  const focusable = drawerFocusable(drawer);
  if (!focusable.length) {
    event.preventDefault();
    drawer.focus({ preventScroll: true });
    return true;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus({ preventScroll: true });
    return true;
  }
  if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus({ preventScroll: true });
    return true;
  }
  return false;
}

function fixtureIdentity(index) {
  return index.toString(16).padStart(64, "0");
}

function fixtureRecord(index, symbol, timeframe, stateLabel, copy, minutesAgo, source = "deterministic") {
  const narrativeIdentity = fixtureIdentity(index + 1);
  const forecastIdentity = fixtureIdentity(700 + index);
  const proofIdentity = fixtureIdentity(800 + index);
  const familyContributions = [
    {
      family: "geometry_pa_elliott_harmonic",
      state: "observed",
      direction: "bullish",
      prior_weight: 0.20,
      support_points: 16,
      opposition_points: 0,
      evidence_quality_0_1: 0.92,
      freshness_0_1: 0.95,
      material_conflict_count: 0,
    },
    {
      family: "liquidity",
      state: "observed",
      direction: "bullish",
      prior_weight: 0.25,
      support_points: 21,
      opposition_points: 0,
      evidence_quality_0_1: 0.91,
      freshness_0_1: 0.93,
      material_conflict_count: 0,
    },
    {
      family: "order_flow_absorption",
      state: "observed",
      direction: "bullish",
      prior_weight: 0.25,
      support_points: 22,
      opposition_points: 0,
      evidence_quality_0_1: 0.90,
      freshness_0_1: 0.92,
      material_conflict_count: 0,
    },
    {
      family: "derivatives",
      state: "observed",
      direction: "bearish",
      prior_weight: 0.15,
      support_points: 0,
      opposition_points: 10,
      evidence_quality_0_1: 0.82,
      freshness_0_1: 0.88,
      material_conflict_count: 1,
    },
    {
      family: "onchain_smart_money",
      state: "no_evidence",
      direction: null,
      prior_weight: 0.15,
      support_points: 0,
      opposition_points: 0,
      evidence_quality_0_1: null,
      freshness_0_1: null,
      material_conflict_count: 0,
    },
  ];
  const record = {
    narrative_identity: narrativeIdentity,
    event_at_ms: Date.now() - minutesAgo * 60_000,
    symbol,
    timeframe,
    source_kind: source,
    original_text_preserved: true,
    real_capital: 0,
    __fixture_state: stateLabel,
    text: {
      collapsed_text: copy,
      simple_text: `${copy} Kısaca sistem yeni kanıt gelene kadar görüşünü kontrollü tutuyor.`,
      technical_text: "Trend yapısı, likidite davranışı ve emir akışı birlikte değerlendirildi; teyit eşiği henüz tam kapanmadı.",
      intelligence_text: "Beş-aile kanıtı aynı yönde değil. Geometri ve likidite destek verirken türev tarafı ana çelişkiyi taşıyor.",
      decision_text: "Yeni karar için tetik bölgesinin korunması ve emir akışının teyidi gerekiyor. Geçersizleşme seviyesi aşılırsa görüş bırakılır.",
      capital_text: "Bu mesaj yeni sanal sermaye hareketi üretmedi. Üç-vault davranışı S11’de canonical runtime ile tamamlanacak.",
    },
    __fixture_detail: {
      analytical_view: {
        stance: {
          effective_stance: stateLabel.toLowerCase(),
          strength: "moderate",
          support_score_0_100: 59,
          opposition_score_0_100: 10,
          net_support_points: 49,
        },
        next_condition: { state: "entry_zone_watch" },
        invalidation_condition: { price: 60750 },
        capital_consequence: { state: "not_bound" },
      },
      fact_bundle: {
        forecast_identity: forecastIdentity,
        proof_identity: proofIdentity,
        confluence_support_score_0_100: 59,
        confluence_opposition_score_0_100: 10,
        family_contributions: familyContributions,
        trigger_zone: { low: 62000, high: 62500 },
        target_zone: { low: 65000, high: 66000 },
        invalidation_price: 60750,
      },
      message_input: { importance: "important", category: "decision" },
      read_only: true,
      production_authority: false,
      real_capital: 0,
    },
  };
  const fixtureBuilder = window.CryptoSignalVisualProof?.fixtureVisualProof;
  if (typeof fixtureBuilder === "function") {
    record.__fixture_visual_proof = fixtureBuilder({
      narrativeIdentity,
      symbol,
      timeframe,
      forecastIdentity,
      proofIdentity,
    });
  }
  return record;
}

function longSessionFixtureRecord(index, total) {
  const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
  const timeframes = ["5m", "15m", "1h", "4h"];
  const symbol = symbols[index % symbols.length];
  const timeframe = timeframes[index % timeframes.length];
  const identity = fixtureIdentity(50_000 + index);
  const record = {
    narrative_identity: identity,
    event_at_ms: 1_790_000_000_000 + index * 60_000,
    category: index % 11 === 0 ? "capital" : "decision",
    subtype: index % 11 === 0 ? "capital_hold" : "forecast_updated",
    importance: index % 17 === 0 ? "critical" : "important",
    symbol,
    timeframe,
    vault_id: index % 11 === 0 ? "TACTICAL" : null,
    source_kind: "deterministic",
    original_text_preserved: true,
    read_only: true,
    production_authority: false,
    real_capital: 0,
    __fixture_state: index % 11 === 0 ? "NAKİTTE BEKLE" : "UZUN OTURUM",
    text: {
      collapsed_text:
        `Uzun oturum fixture mesajı ${index + 1}/${total}. `
        + "Kalıcı mesaj kimliği korunur; bu kayıt canlı piyasa gerçeği değildir.",
      simple_text: "S14 uzun oturum kabulü için hafif deterministik fixture.",
      technical_text: "Windowed feed DOM sınırı ve scroll anchor davranışı ölçülür.",
      intelligence_text: "Bu fixture yeni piyasa kanıtı veya karar otoritesi üretmez.",
      decision_text: "Yalnız UI performans ve erişilebilirlik kabulü içindir.",
      capital_text: "REAL_CAPITAL=0.",
    },
  };
  if (index === total - 40) {
    const detailSeed = fixtureRecord(
      40_000,
      symbol,
      timeframe,
      "UZUN OTURUM",
      "S14 expansion anchor fixture.",
      1
    );
    record.__fixture_detail = detailSeed.__fixture_detail;
  }
  return record;
}

function capitalFixtureRecord(
  index,
  subtype,
  vaultId,
  copy,
  minutesAgo,
  extra = {}
) {
  const identity = (offset) => fixtureIdentity(3000 + index * 20 + offset);
  const textBundle = {
    collapsed_text: `${copy} REAL_CAPITAL=0.`,
    simple_text: `${copy} Bu yalnız sanal sermaye akışıdır; gerçek borsa emri yoktur.`,
    technical_text:
      "Exact allocator / sizing / R22 / R21 lineage korunur; fixture yalnız görsel kabul içindir.",
    intelligence_text:
      "Bu kayıt yeni piyasa kanıtı uydurmaz; yalnız canonical paper-capital lifecycle durumunu gösterir.",
    decision_text: `Lifecycle durumu: ${subtype.replaceAll("_", " ")}.`,
    capital_text: "Paper capital only · REAL_CAPITAL=0 · production authority yok.",
  };
  const base = {
    narrative_identity: identity(1),
    event_at_ms: Date.now() - minutesAgo * 60_000,
    category: "capital",
    subtype,
    asset: "BTCUSDT",
    symbol: "BTCUSDT",
    timeframe: vaultId === "TACTICAL" ? "5m" : "4h",
    source_kind: "deterministic",
    original_text_preserved: true,
    read_only: true,
    production_authority: false,
    real_capital: 0,
    vault_id: vaultId || null,
    lifecycle_identity: identity(2),
    allocator_candidate_identity: identity(3),
    allocator_assessment_identity: identity(4),
    forecast_identity: identity(5),
    proof_identity: identity(6),
    decision_context_identity: identity(7),
    bundle_identity: identity(8),
    intent_identity: identity(9),
    fill_identity: identity(10),
    outcome_identity: null,
    before_vault_snapshot_identity: identity(11),
    after_vault_snapshot_identity: identity(12),
    before_consolidated_snapshot_identity: identity(13),
    after_consolidated_snapshot_identity: identity(14),
    action: null,
    quantity: null,
    reference_price: null,
    simulated_fill_price: null,
    notional_usdt: null,
    cash_before_usdt: null,
    cash_after_usdt: null,
    vault_nav_before_usdt: null,
    vault_nav_after_usdt: null,
    consolidated_nav_before_usdt: null,
    consolidated_nav_after_usdt: null,
    fee_usdt: null,
    spread_usdt: null,
    slippage_usdt: null,
    financial_outcome: null,
    realized_pnl_delta_usdt: null,
    position_quantity_before: null,
    position_quantity_after: null,
    text: textBundle,
    ...extra,
  };

  let detailKey = "capital_lifecycle";
  if (["capital_eligible", "capital_hold", "capital_blocked"].includes(subtype)) {
    detailKey = "capital_decision";
  } else if (subtype === "capital_sized") {
    detailKey = "capital_sizing";
  } else if (
    ["capital_executed", "capital_reduced", "capital_exited"].includes(subtype)
  ) {
    detailKey = "capital_story";
  }
  base.__fixture_detail = {
    [detailKey]: { ...base },
    read_only: true,
    production_authority: false,
    real_capital: 0,
  };
  delete base.__fixture_detail[detailKey].__fixture_detail;
  return base;
}

function capitalFixtureMessages() {
  return [
    capitalFixtureRecord(
      1,
      "capital_candidate",
      null,
      "BTC Smart Capital adayı üç vault değerlendirmesine alındı; henüz sizing veya fill yok.",
      50
    ),
    capitalFixtureRecord(
      2,
      "capital_eligible",
      "CORE",
      "Core vault exact allocator kuralları altında aday için uygun bulundu.",
      45,
      { disposition: "eligible", starting_budget_usdt: 600 }
    ),
    capitalFixtureRecord(
      3,
      "capital_hold",
      "TACTICAL",
      "Tactical vault 5m teyidi tamamlanmadığı için nakitte bekliyor.",
      40,
      { disposition: "hold", tactical_timeframe: "5m", starting_budget_usdt: 300 }
    ),
    capitalFixtureRecord(
      4,
      "capital_blocked",
      "OPPORTUNITY_RESERVE",
      "Opportunity vault Event Risk nedeniyle sermaye kullanmıyor.",
      35,
      { disposition: "blocked", starting_budget_usdt: 100 }
    ),
    capitalFixtureRecord(
      5,
      "capital_sized",
      "CORE",
      "Core için fixed-fractional canonical paper boyutu seçildi; Kelly promote edilmedi.",
      30,
      {
        sizing_selection_identity: fixtureIdentity(3901),
        sizing_decision_identity: fixtureIdentity(3902),
        canonical_notional_usdt: 150,
        fraction_of_vault: 0.25,
        method: "fixed_fractional",
      }
    ),
    capitalFixtureRecord(
      6,
      "capital_executed",
      "CORE",
      "Core BTCUSDT paper BUY simüle edildi ve R21/R22 atomik muhasebeye işlendi.",
      25,
      {
        action: "BUY",
        quantity: 1.45,
        reference_price: 101,
        simulated_fill_price: 101.2,
        notional_usdt: 146.74,
        cash_before_usdt: 600,
        cash_after_usdt: 453.11,
        vault_nav_before_usdt: 600,
        vault_nav_after_usdt: 599.71,
        consolidated_nav_before_usdt: 1000,
        consolidated_nav_after_usdt: 999.71,
        fee_usdt: 0.15,
        spread_usdt: 0.07,
        slippage_usdt: 0.07,
      }
    ),
    capitalFixtureRecord(
      7,
      "capital_reduced",
      "CORE",
      "Core açık BTCUSDT paper pozisyonunun bir kısmını azalttı.",
      20,
      {
        action: "REDUCE",
        quantity: 0.7,
        reference_price: 105,
        simulated_fill_price: 104.8,
        notional_usdt: 73.36,
        cash_before_usdt: 453.11,
        cash_after_usdt: 526.32,
        vault_nav_before_usdt: 605.2,
        vault_nav_after_usdt: 605.02,
        consolidated_nav_before_usdt: 1005.2,
        consolidated_nav_after_usdt: 1005.02,
        outcome_identity: fixtureIdentity(3941),
        financial_outcome: "PARTIAL_REDUCTION",
        realized_pnl_delta_usdt: 2.31,
        position_quantity_before: 1.45,
        position_quantity_after: 0.75,
      }
    ),
    capitalFixtureRecord(
      8,
      "capital_exited",
      "CORE",
      "Core kalan BTCUSDT paper pozisyonunu tamamen kapattı.",
      15,
      {
        action: "EXIT",
        quantity: 0.75,
        reference_price: 110,
        simulated_fill_price: 109.8,
        notional_usdt: 82.35,
        cash_before_usdt: 526.32,
        cash_after_usdt: 608.49,
        vault_nav_before_usdt: 608.7,
        vault_nav_after_usdt: 608.49,
        consolidated_nav_before_usdt: 1008.7,
        consolidated_nav_after_usdt: 1008.49,
        outcome_identity: fixtureIdentity(3961),
        financial_outcome: "CLOSED_WIN",
        realized_pnl_delta_usdt: 6.42,
        position_quantity_before: 0.75,
        position_quantity_after: 0,
      }
    ),
    capitalFixtureRecord(
      9,
      "capital_accounting_updated",
      "CORE",
      "Epoch 2 accounting yeni cash/NAV snapshot'larını immutable şekilde kaydetti.",
      10,
      {
        action: "EXIT",
        cash_before_usdt: 526.32,
        cash_after_usdt: 608.49,
        vault_nav_before_usdt: 608.7,
        vault_nav_after_usdt: 608.49,
        consolidated_nav_before_usdt: 1008.7,
        consolidated_nav_after_usdt: 1008.49,
      }
    ),
    capitalFixtureRecord(
      10,
      "capital_outcome",
      "CORE",
      "Kapanan paper pozisyonun finansal sonucu immutable outcome evidence olarak kaydedildi.",
      5,
      {
        action: "EXIT",
        outcome_identity: fixtureIdentity(3991),
        financial_outcome: "CLOSED_WIN",
        realized_pnl_delta_usdt: 6.42,
        position_quantity_before: 0.75,
        position_quantity_after: 0,
      }
    ),
  ];
}

function fixtureMessages() {
  return [
    fixtureRecord(1, "BTCUSDT", "4h", "GÖRÜŞ KORUNUYOR", "Bitcoin tarafında ana yapı korunuyor. Likidite temizliği sonrası alıcı tepkisi var; sistem yeni teyit gelmeden pozisyon görüşünü büyütmüyor.", 48),
    fixtureRecord(2, "ETHUSDT", "1h", "BEKLİYORUM", "Ethereum kısa vadeli yapıda kararsız. Emir akışı toparlansa da türev tarafındaki teyit henüz yeterli değil; yeni karar üretmek için bekliyorum.", 31),
    fixtureRecord(3, "BTCUSDT", "15m", "GÖRÜŞ GÜÇLENİYOR", "Satış baskısının devam etmemesi ve emir akışındaki toparlanma önceki BTC görüşünü güçlendiriyor. Bir sonraki koşul henüz tamamlanmadı.", 18, "local_rewrite"),
    fixtureRecord(4, "SOLUSDT", "5m", "RİSK ARTTI", "SOL tarafında kısa vadeli hareket hızlandı ancak kanıt kalitesi aynı ölçüde artmadı. Sistem bu değişikliği fırsat değil, izlenmesi gereken risk olarak işaretliyor.", 11),
    fixtureRecord(5, "ETHUSDT", "4h", "SONUÇ KAYDI", "Önceki ETH beklentisinin sonucu değiştirilemez kayda eklendi. Eski mesaj korunuyor; yeni sonuç ayrı bir mesaj olarak tutuluyor.", 6),
    fixtureRecord(6, "BTCUSDT", "5m", "YENİ TEYİT", "Önce eksik olan teyitlerden biri geldi. Kısa vadeli emir akışı mevcut görüşü destekliyor, fakat sistem hâlâ tetik koşulunun tamamlanmasını bekliyor.", 1, "local_rewrite"),
  ];
}

function applyFixture(name) {
  state.fixture = name;
  if (ui.fixtureBanner) ui.fixtureBanner.hidden = false;
  resetMessages();
  const base = name === "capital" ? capitalFixtureMessages() : fixtureMessages();

  if (name === "empty") {
    setConnection("live", "HAZIR", "fixture · mesaj bekleniyor");
    if (ui.emptyTitle) ui.emptyTitle.textContent = "Henüz anlamlı değişiklik yok";
    if (ui.emptyCopy) ui.emptyCopy.textContent = "Sistem sessiz kalabiliyor. NO_SIGNAL ve bekleme geçerli durumlardır.";
    renderAll();
    return;
  }

  if (name === "degraded") {
    mergeInitial(base.slice(0, 3).reverse());
    renderAll();
    setConnection("degraded", "VERİ SINIRLI", "fixture · bağlantı bozulması");
    if (ui.transportMode) ui.transportMode.textContent = "POLLING FALLBACK";
    window.requestAnimationFrame(() => scrollToBottom({ smooth: false }));
    return;
  }

  const longSessionCount =
    name === "long10k" ? 10_000 : name === "long1k" ? 1_000 : 0;
  const fixtureCount = name === "long" ? 36 : name === "history" ? 14 : 0;
  const records = longSessionCount
    ? Array.from(
        { length: longSessionCount },
        (_, i) => longSessionFixtureRecord(i, longSessionCount)
      )
    : fixtureCount
      ? Array.from({ length: fixtureCount }, (_, i) => {
          const seed = base[i % base.length];
          return {
            ...seed,
            narrative_identity: fixtureIdentity(100 + i),
            event_at_ms: Date.now() - (fixtureCount - i) * 4 * 60_000,
          };
        })
      : base;

  for (const record of records) {
    state.ids.add(record.narrative_identity);
    state.messages.push(record);
  }
  state.hasOlder = name === "history" || name === "long";
  if (name === "history") state.unread = 3;
  resetVirtualWindow({ pinToBottom: true });
  renderAll();
  setConnection("live", "CANLI", "fixture · Stream görsel kabul");
  if (ui.transportMode) ui.transportMode.textContent = "SSE CANLI · FIXTURE";

  window.requestAnimationFrame(() => {
    if (!ui.viewport) return;
    if (name === "history") {
      ui.viewport.scrollTop = Math.max(0, ui.viewport.scrollHeight * 0.18);
    } else {
      scrollToBottom({ smooth: false });
    }

    if (name === "incoming" && state.messages.length) {
      const last = ui.list ? ui.list.lastElementChild : null;
      if (last) last.classList.add("is-new");
    }
  });

  if (name === "capital") {
    window.requestAnimationFrame(() => {
      const target = ui.list?.lastElementChild;
      const summary = target?.querySelector?.(".message-summary");
      if (summary instanceof HTMLButtonElement) summary.click();
      scrollToBottom({ smooth: false });
    });
  }

  if (name === "expanded" || name === "windows" || name === "proof") {
    window.requestAnimationFrame(() => {
      const target = ui.list?.children?.[2];
      const summary = target?.querySelector?.(".message-summary");
      if (summary instanceof HTMLButtonElement) summary.click();

      if (name === "windows" || name === "proof") {
        closeAllEvidenceWindows({ persist: false });
        try {
          localStorage.removeItem(EVIDENCE_WINDOW_SESSION_KEY);
        } catch {
          // Deterministic fixture remains usable without storage.
        }
        const record = state.messages[2];
        const detail = record?.__fixture_detail;
        if (record && detail && name === "windows") {
          openEvidenceWindow(record, detail, "liquidity");
          openEvidenceWindow(record, detail, "geometry");
          const decisionWindow = openEvidenceWindow(record, detail, "decision");
          if (decisionWindow) {
            decisionWindow.pinned = true;
            decisionWindow.x = 44;
            decisionWindow.y = 70;
            applyEvidenceWindowGeometry(decisionWindow);
          }
          persistEvidenceWindows();
        } else if (record && detail && name === "proof") {
          const proofWindow = openEvidenceWindow(record, detail, "proof");
          if (proofWindow) {
            proofWindow.pinned = true;
            proofWindow.x = 70;
            proofWindow.y = 18;
            proofWindow.width = 940;
            proofWindow.height = 860;
            applyEvidenceWindowGeometry(proofWindow);
          }
          persistEvidenceWindows();
        }
      }
    });
  }

  if (name === "sound") {
    const api = notificationApi();
    api?.resetSessionAudit?.();
    api?.updateSettings?.({
      enabled: true,
      volume: 0.42,
      mode: "important",
      desktopEnabled: false,
    });
    syncNotificationUi("Fixture · canlı yeni mesaj sesi açık; history/replay sessiz.");
    openDrawer(ui.settingsDrawer);
  }

  if (name === "filters") {
    openDrawer(ui.discoveryDrawer);
    if (ui.searchInput) ui.searchInput.value = "likidite";
    if (ui.symbolFilter) ui.symbolFilter.value = "BTCUSDT";
    if (ui.categoryFilter) ui.categoryFilter.value = "decision";
    if (ui.timeframeFilter) ui.timeframeFilter.value = "4h";
    if (ui.vaultFilter) ui.vaultFilter.value = "";
    if (ui.evidenceFilter) ui.evidenceFilter.value = "order_flow_cvd";
    if (ui.stateFilter) ui.stateFilter.value = "watch";
    if (ui.importanceFilter) ui.importanceFilter.value = "important";
    if (ui.fromDateFilter) ui.fromDateFilter.value = "2026-09-20";
    if (ui.toDateFilter) ui.toDateFilter.value = "2026-09-25";
  }
}

function wireUi() {
  ui.searchButton?.addEventListener("click", () => openDrawer(ui.discoveryDrawer));
  ui.filterButton?.addEventListener("click", () => openDrawer(ui.discoveryDrawer));
  ui.soundButton?.addEventListener("click", () => openDrawer(ui.settingsDrawer));
  ui.settingsButton?.addEventListener("click", () => openDrawer(ui.settingsDrawer));
  ui.backdrop?.addEventListener("click", closeDrawers);
  document.querySelectorAll("[data-close-drawer]").forEach((button) => {
    button.addEventListener("click", closeDrawers);
  });

  ui.loadOlder?.addEventListener("click", () => void loadOlder());
  ui.newButton?.addEventListener("click", () => scrollToBottom());

  ui.viewport?.addEventListener("scroll", () => {
    if (!ui.viewport) return;
    if (
      ui.viewport.scrollTop < 110
      && state.virtualStart > 0
      && !state.virtualShiftLocked
    ) {
      shiftVirtualWindow("older");
      return;
    }
    if (
      ui.viewport.scrollTop + ui.viewport.clientHeight
        > ui.viewport.scrollHeight - 110
      && state.virtualEnd < state.messages.length
      && !state.virtualShiftLocked
    ) {
      shiftVirtualWindow("newer");
      return;
    }
    if (isNearBottom() && state.unread > 0) {
      state.unread = 0;
      updateUnread();
    }
    if (ui.viewport.scrollTop < 70 && state.hasOlder && !state.fixture) {
      void loadOlder();
    }
  });

  ui.clearFilters?.addEventListener("click", () => {
    resetDiscoveryState();
    closeDrawers();
    if (!state.fixture) void loadInitial();
  });

  ui.applyFilters?.addEventListener("click", () => {
    state.filters = readDiscoveryControls();
    setMessageDeepLink("");
    closeDrawers();
    if (!state.fixture) void loadInitial();
  });

  ui.soundEnabled?.addEventListener("change", () => {
    if (!(ui.soundEnabled instanceof HTMLInputElement)) return;
    updateNotificationSettings({ enabled: ui.soundEnabled.checked });
  });

  ui.soundMode?.addEventListener("change", () => {
    if (!(ui.soundMode instanceof HTMLSelectElement)) return;
    updateNotificationSettings({ mode: ui.soundMode.value });
  });

  ui.soundVolume?.addEventListener("input", () => {
    if (!(ui.soundVolume instanceof HTMLInputElement)) return;
    updateNotificationSettings({ volume: Number(ui.soundVolume.value) / 100 });
  });

  ui.soundUnlock?.addEventListener("click", async () => {
    const ok = await notificationApi()?.unlock?.({ preview: true });
    syncNotificationUi(ok ? "Ses açıldı · özgün Crypto Signal chime test edildi." : "Ses açılamadı; tarayıcı audio iznini kontrol et.");
  });

  ui.testChime?.addEventListener("click", async () => {
    let snapshot = notificationSnapshot();
    if (!snapshot.unlocked) {
      await notificationApi()?.unlock?.();
      snapshot = notificationSnapshot();
    }
    const played = snapshot.unlocked
      ? notificationApi()?.playPreview?.() === true
      : false;
    syncNotificationUi(played ? "Chime test edildi." : "Chime için önce sesi aç.");
  });

  ui.desktopNotification?.addEventListener("change", () => {
    if (!(ui.desktopNotification instanceof HTMLInputElement)) return;
    const snapshot = notificationSnapshot();
    if (
      ui.desktopNotification.checked
      && snapshot.notificationPermission !== "granted"
    ) {
      ui.desktopNotification.checked = false;
      updateNotificationSettings({ desktopEnabled: false });
      syncNotificationUi("Masaüstü bildirimi için önce açıkça izin iste.");
      return;
    }
    updateNotificationSettings({
      desktopEnabled: ui.desktopNotification.checked,
    });
  });

  ui.desktopPermission?.addEventListener("click", async () => {
    const permission = await notificationApi()?.requestDesktopPermission?.();
    if (permission === "granted") {
      updateNotificationSettings({ desktopEnabled: true });
      syncNotificationUi("Masaüstü bildirimi izni verildi.");
    } else {
      updateNotificationSettings({ desktopEnabled: false });
      syncNotificationUi(`Masaüstü izni: ${text(permission, "desteklenmiyor")}.`);
    }
  });

  document.querySelectorAll('input[name="density"]').forEach((radio) => {
    radio.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement && target.checked) {
        document.body.dataset.density = target.value;
      }
    });
  });

  window.addEventListener("resize", () => {
    for (const model of state.evidenceWindows.values()) {
      applyEvidenceWindowGeometry(model);
    }
    persistEvidenceWindows();
  });

  document.addEventListener("keydown", (event) => {
    if (handleDrawerKeyboard(event)) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openDrawer(ui.discoveryDrawer);
      ui.searchInput?.focus();
    }
  });
}

function init() {
  wireUi();
  syncNotificationUi();
  if (state.fixture) {
    applyFixture(state.fixture);
    if (exactSha256(state.deepLinkIdentity)) {
      window.requestAnimationFrame(() => focusRenderedMessage(state.deepLinkIdentity));
    }
    return;
  }
  restoreEvidenceWindows();
  if (exactSha256(state.deepLinkIdentity)) {
    void loadExactMessage(state.deepLinkIdentity);
  } else {
    if (state.deepLinkIdentity) setMessageDeepLink("");
    void loadInitial();
  }
}

window.__cryptoSignalStreamS9 = Object.freeze({
  openEvidenceWindow,
  closeAllEvidenceWindows,
  evidenceWindowSnapshot,
  persistEvidenceWindows,
});

window.__cryptoSignalStreamS12 = Object.freeze({
  queryParams,
  readDiscoveryControls,
  resetDiscoveryState,
  focusRenderedMessage,
  discoverySnapshot: () => ({
    filters: { ...state.filters },
    deepLinkIdentity: state.deepLinkIdentity,
    messageCount: state.messages.length,
    expanded: [...state.expanded],
  }),
});

window.__cryptoSignalStreamS13 = Object.freeze({
  notificationSnapshot,
  setNotificationSettings: (patch) => updateNotificationSettings(patch),
  resetNotificationAudit: () => notificationApi()?.resetSessionAudit?.(),
  simulateFixtureDelivery: ({
    identity = fixtureIdentity(9000),
    category = "decision",
    importance = "important",
    delivery = "live_new",
  } = {}) => {
    if (!state.fixture) return { ok: false, reason: "fixture_only" };
    const record = {
      narrative_identity: identity,
      symbol: "BTCUSDT",
      category,
      importance,
      text: { collapsed_text: "S13 notification acceptance fixture." },
    };
    return notificationApi()?.route?.(record, delivery) || null;
  },
});

window.__cryptoSignalStreamS14 = Object.freeze({
  snapshot: () => ({
    totalMessages: state.messages.length,
    renderedMessages: ui.list?.querySelectorAll(".message").length || 0,
    renderStart: state.virtualStart,
    renderEnd: state.virtualEnd,
    detailCacheSize: state.details.size,
    expandedCount: state.expanded.size,
    evidenceWindowCount: state.evidenceWindows.size,
    lastRenderDurationMs: state.lastRenderDurationMs,
    activeIdentity:
      document.activeElement?.closest?.(".message")?.dataset?.identity || "",
    activeDrawer: activeDrawer()?.id || "",
    realCapital: 0,
  }),
  shiftOlder: () => shiftVirtualWindow("older"),
  shiftNewer: () => shiftVirtualWindow("newer"),
  focusMessage: (identity) => focusRenderedMessage(identity),
  prependFixturePage: (count = 50) => {
    if (!state.fixture || !Number.isInteger(count) || count < 1 || count > 200) {
      return { ok: false, reason: "fixture_only_or_invalid_count" };
    }
    const anchor = captureViewportAnchor();
    const existing = state.messages.length;
    const additions = Array.from(
      { length: count },
      (_, i) => longSessionFixtureRecord(20_000 + existing + i, existing + count)
    );
    for (const record of additions) state.ids.add(record.narrative_identity);
    state.messages = [...additions, ...state.messages];
    state.virtualStart += additions.length;
    state.virtualEnd += additions.length;
    renderAll({ anchor });
    return { ok: true, count: additions.length };
  },
  openDiscovery: () => openDrawer(ui.discoveryDrawer, ui.searchButton),
  closeDrawers,
});

window.addEventListener("beforeunload", () => {
  persistEvidenceWindows();
  clearNotificationRearmTimer();
  state.eventSource?.close();
  stopPolling();
});

init();
