"use strict";

const API = Object.freeze({
  messages: "/api/stream/messages",
  live: "/api/stream/live",
  detail: (identity) => `/api/stream/messages/${encodeURIComponent(identity)}/detail`,
  decisionProofForForecast: (identity) =>
    `/api/decision-proof/forecast/${encodeURIComponent(identity)}`,
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
  searchInput: document.getElementById("searchInput"),
  symbolFilter: document.getElementById("symbolFilter"),
  timeframeFilter: document.getElementById("timeframeFilter"),
  clearFilters: document.getElementById("clearFiltersButton"),
  applyFilters: document.getElementById("applyFiltersButton"),
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
  loadingHistory: false,
  expanded: new Set(),
  details: new Map(),
  detailRequests: new Set(),
  fixture: new URLSearchParams(window.location.search).get("fixture") || "",
  filters: {
    text: "",
    symbol: "",
    timeframe: "",
  },
};

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
  if (after) params.set("after", after);
  if (before) params.set("before", before);
  if (state.filters.text) params.set("text", state.filters.text);
  if (state.filters.symbol) params.set("symbol", state.filters.symbol);
  if (state.filters.timeframe) params.set("timeframe", state.filters.timeframe);
  return params;
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
  return "ANALİZ";
}

function displayNumber(value, fallback = "—") {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 }).format(n);
}

function familyLabel(value) {
  const labels = {
    geometry: "Geometri",
    liquidity: "Likidite",
    order_flow: "Emir akışı",
    derivatives: "Türevler",
    onchain: "On-chain",
  };
  const key = text(value, "").toLowerCase();
  return labels[key] || text(value, "Kanıt");
}

function preserveMessageAnchor(item, mutate) {
  if (!ui.viewport) {
    mutate();
    return;
  }
  const beforeTop = item.getBoundingClientRect().top;
  const beforeScroll = ui.viewport.scrollTop;
  mutate();
  window.requestAnimationFrame(() => {
    if (!ui.viewport || !item.isConnected) return;
    const afterTop = item.getBoundingClientRect().top;
    ui.viewport.scrollTop = beforeScroll + (afterTop - beforeTop);
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

function evidenceFamilyGrid(fact) {
  const grid = document.createElement("div");
  grid.className = "family-grid";
  const families = Array.isArray(fact?.family_contributions)
    ? fact.family_contributions
    : [];
  for (const family of families) {
    const card = document.createElement("div");
    card.className = "family-card";
    const label = document.createElement("span");
    label.textContent = familyLabel(family?.family);
    const score = document.createElement("strong");
    score.textContent = `+${displayNumber(family?.support_points, "0")} / -${displayNumber(
      family?.opposition_points,
      "0"
    )}`;
    const note = document.createElement("small");
    const quality = Number(family?.evidence_quality_0_1);
    note.textContent = Number.isFinite(quality)
      ? `kanıt kalitesi %${Math.round(quality * 100)}`
      : text(family?.state, "ölçülmedi");
    card.append(label, score, note);
    grid.append(card);
  }
  if (!families.length) {
    const note = document.createElement("p");
    note.className = "depth-muted";
    note.textContent = "Beş-aile katkısı bu kayıtta mevcut değil.";
    grid.append(note);
  }
  return grid;
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
  result.textContent = "S10 görsel proof değil; exact persisted karar kanıtı kontrolü.";

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

function buildExpandedContent(record, detail) {
  const textBundle =
    record && typeof record.text === "object" && record.text ? record.text : {};
  const fact = detail && typeof detail.fact_bundle === "object"
    ? detail.fact_bundle
    : {};
  const analytical = detail && typeof detail.analytical_view === "object"
    ? detail.analytical_view
    : {};

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

async function loadMessageDetail(item, record) {
  const identity = text(record?.narrative_identity, "");
  if (!identity || state.detailRequests.has(identity)) return;

  if (record.__fixture_detail && typeof record.__fixture_detail === "object") {
    state.details.set(identity, record.__fixture_detail);
    renderExpandedPanel(item, record, record.__fixture_detail);
    return;
  }

  state.detailRequests.add(identity);
  try {
    const payload = await fetchJson(API.detail(identity));
    if (payload.status === "ready" && payload.detail) {
      state.details.set(identity, payload.detail);
      if (state.expanded.has(identity)) {
        renderExpandedPanel(item, record, payload.detail);
      }
    } else {
      const panel = item.querySelector(".message-detail");
      if (panel instanceof HTMLElement && state.expanded.has(identity)) {
        preserveMessageAnchor(item, () => {
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
    const panel = item.querySelector(".message-detail");
    if (panel instanceof HTMLElement && state.expanded.has(identity)) {
      preserveMessageAnchor(item, () => {
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
  preserveMessageAnchor(item, () => {
    if (willOpen) {
      state.expanded.add(identity);
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

function renderMessage(record, { isNew = false } = {}) {
  const item = document.createElement("li");
  item.className = "message";
  if (isNew) item.classList.add("is-new");
  const identity = text(record.narrative_identity, "");
  item.dataset.identity = identity;

  const summary = document.createElement("button");
  summary.type = "button";
  summary.className = "message-summary";
  summary.setAttribute("aria-expanded", String(state.expanded.has(identity)));

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
  if (record.original_text_preserved === true) chips.append(buildChip("ORİJİNAL METİN"));
  if (record.real_capital === 0) chips.append(buildChip("GERÇEK PARA KAPALI", true));
  const cue = document.createElement("span");
  cue.className = "message-expand-cue";
  cue.textContent = state.expanded.has(identity) ? "Detayı kapat ↑" : "Detayı aç ↓";
  footer.append(chips, cue);
  summary.append(meta, copy, footer);

  const detailPanel = document.createElement("div");
  detailPanel.className = "message-detail";
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
function renderAll() {
  if (!ui.list || !ui.empty) return;
  ui.list.replaceChildren();
  for (const record of state.messages) {
    ui.list.append(renderMessage(record));
  }
  const isEmpty = state.messages.length === 0;
  ui.empty.hidden = !isEmpty;
  ui.list.hidden = isEmpty;
  if (ui.loadOlder) ui.loadOlder.hidden = !state.hasOlder || isEmpty;
  updateUnread();
}

function updateUnread() {
  if (!ui.newButton || !ui.newCount) return;
  ui.newCount.textContent = String(state.unread);
  ui.newButton.hidden = state.unread <= 0;
}

function scrollToBottom({ smooth = true } = {}) {
  if (!ui.viewport) return;
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
}

function appendRecord(record, cursor = null, { fixtureNew = false } = {}) {
  const id = text(record && record.narrative_identity, "");
  if (!id || state.ids.has(id)) return false;
  const stayAtBottom = isNearBottom();
  state.ids.add(id);
  state.messages.push(record);

  if (ui.list && !ui.list.hidden) {
    ui.list.append(renderMessage(record, { isNew: fixtureNew || stayAtBottom }));
  } else {
    renderAll();
  }

  if (cursor) state.newestCursor = cursor;
  if (stayAtBottom) {
    window.requestAnimationFrame(() => scrollToBottom({ smooth: !state.fixture }));
  } else {
    state.unread += 1;
    updateUnread();
    if (ui.announcer) ui.announcer.textContent = `${state.unread} yeni mesaj`;
  }
  return true;
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
  const oldHeight = ui.viewport ? ui.viewport.scrollHeight : 0;
  const oldTop = ui.viewport ? ui.viewport.scrollTop : 0;

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
    state.beforeCursor = page && typeof page.oldest_cursor === "string" ? page.oldest_cursor : state.beforeCursor;
    state.hasOlder = Boolean(page && page.has_more);
    renderAll();
    window.requestAnimationFrame(() => {
      if (!ui.viewport) return;
      const delta = ui.viewport.scrollHeight - oldHeight;
      ui.viewport.scrollTop = oldTop + delta;
    });
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
    if (ui.transportMode) ui.transportMode.textContent = "SSE CANLI";
  });

  source.addEventListener("message", (event) => {
    try {
      const record = JSON.parse(event.data);
      appendRecord(record, event.lastEventId || null);
    } catch {
      setConnection("degraded", "AKIŞ HATASI", "geçersiz mesaj güvenle reddedildi");
    }
  });

  source.addEventListener("error", () => {
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
    for (const record of items) appendRecord(record);
    if (page && typeof page.newest_cursor === "string" && items.length) {
      state.newestCursor = page.newest_cursor;
    }
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

function openDrawer(drawer) {
  if (!drawer || !ui.backdrop) return;
  for (const item of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (item && item !== drawer) item.hidden = true;
  }
  drawer.hidden = false;
  ui.backdrop.hidden = false;
  if (ui.searchButton) ui.searchButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.filterButton) ui.filterButton.setAttribute("aria-expanded", String(drawer === ui.discoveryDrawer));
  if (ui.soundButton) ui.soundButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
  if (ui.settingsButton) ui.settingsButton.setAttribute("aria-expanded", String(drawer === ui.settingsDrawer));
}

function closeDrawers() {
  for (const drawer of [ui.discoveryDrawer, ui.settingsDrawer]) {
    if (drawer) drawer.hidden = true;
  }
  if (ui.backdrop) ui.backdrop.hidden = true;
  for (const button of [ui.searchButton, ui.filterButton, ui.soundButton, ui.settingsButton]) {
    if (button) button.setAttribute("aria-expanded", "false");
  }
}

function fixtureIdentity(index) {
  return index.toString(16).padStart(64, "0");
}

function fixtureRecord(index, symbol, timeframe, stateLabel, copy, minutesAgo, source = "deterministic") {
  const narrativeIdentity = fixtureIdentity(index + 1);
  const forecastIdentity = fixtureIdentity(700 + index);
  const proofIdentity = fixtureIdentity(800 + index);
  const familyNames = ["geometry", "liquidity", "order_flow", "derivatives", "onchain"];
  const familyContributions = familyNames.map((family, offset) => ({
    family,
    state: "observed",
    direction: offset === 3 ? "mixed" : "support",
    support_points: 74 - offset * 8,
    opposition_points: 8 + offset * 4,
    evidence_quality_0_1: 0.94 - offset * 0.07,
    freshness_0_1: 0.97 - offset * 0.06,
    material_conflict_count: offset === 3 ? 1 : 0,
  }));
  return {
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
          support_score_0_100: 74,
          opposition_score_0_100: 19,
          net_support_points: 55,
        },
        next_condition: { state: "entry_zone_watch" },
        invalidation_condition: { price: 60750 },
        capital_consequence: { state: "not_bound" },
      },
      fact_bundle: {
        forecast_identity: forecastIdentity,
        proof_identity: proofIdentity,
        confluence_support_score_0_100: 74,
        confluence_opposition_score_0_100: 19,
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
  const base = fixtureMessages();

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

  const fixtureCount = name === "long" ? 36 : name === "history" ? 14 : 0;
  const records = fixtureCount
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
  renderAll();
  setConnection("live", "CANLI", "fixture · S7 görsel kabul");
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

  if (name === "expanded") {
    window.requestAnimationFrame(() => {
      const target = ui.list?.children?.[2];
      const summary = target?.querySelector?.(".message-summary");
      if (summary instanceof HTMLButtonElement) summary.click();
    });
  }

  if (name === "filters") {
    openDrawer(ui.discoveryDrawer);
    if (ui.searchInput) ui.searchInput.value = "likidite";
    if (ui.symbolFilter) ui.symbolFilter.value = "BTCUSDT";
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
    if (isNearBottom() && state.unread > 0) {
      state.unread = 0;
      updateUnread();
    }
    if (ui.viewport && ui.viewport.scrollTop < 70 && state.hasOlder && !state.fixture) {
      void loadOlder();
    }
  });

  ui.clearFilters?.addEventListener("click", () => {
    if (ui.searchInput) ui.searchInput.value = "";
    if (ui.symbolFilter) ui.symbolFilter.value = "";
    if (ui.timeframeFilter) ui.timeframeFilter.value = "";
  });

  ui.applyFilters?.addEventListener("click", () => {
    state.filters.text = ui.searchInput?.value.trim() || "";
    state.filters.symbol = ui.symbolFilter?.value || "";
    state.filters.timeframe = ui.timeframeFilter?.value || "";
    closeDrawers();
    if (!state.fixture) void loadInitial();
  });

  document.querySelectorAll('input[name="density"]').forEach((radio) => {
    radio.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLInputElement && target.checked) {
        document.body.dataset.density = target.value;
      }
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDrawers();
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openDrawer(ui.discoveryDrawer);
      ui.searchInput?.focus();
    }
  });
}

function init() {
  wireUi();
  if (state.fixture) {
    applyFixture(state.fixture);
    return;
  }
  void loadInitial();
}

window.addEventListener("beforeunload", () => {
  state.eventSource?.close();
  stopPolling();
});

init();
