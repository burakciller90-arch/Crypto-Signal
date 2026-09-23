"use strict";

const API = Object.freeze({
  health: "/api/health",
  command: "/api/command-center?recent_limit=12",
  radar: "/api/market-radar",
  epoch: "/api/paper/epoch-contract",
  paper: "/api/paper/mission-control",
  epoch2State: "/api/paper/epoch2-state",
  archive: "/api/archive/proof-wall?limit=500&offset=0",
  education: "/api/education",
  intelligence: "/api/intelligence-center",
  performance: "/api/performance",
  decisionStatus: "/api/decision-evidence/status",
  shadowRail: "/api/shadow-decision-rail/status",
  operationalTruth: "/api/r25/operational-truth",
  marketTapeStatus: "/api/market-tape-runtime/status",
  coldArchiveStatus: "/api/cold-archive/status?verify_limit=24",
  liveFeed: "/api/intelligence-feed?limit=100",
  decisionProof: (identity) => `/api/decision-proof/${encodeURIComponent(identity)}`,
  shadowForecastCycle: (identity) =>
    `/api/shadow-decision-rail/forecast/${encodeURIComponent(identity)}`,
  assetCockpit: (symbol, timeframe) =>
    `/api/assets/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}?recent_limit=30`,
  signalDetail: (identity) => `/api/signals/${encodeURIComponent(identity)}`,
});

const ROUTE_LABELS = Object.freeze({
  command: "COMMAND",
  markets: "MARKETS",
  intelligence: "INTELLIGENCE",
  capital: "CAPITAL",
  archive: "ARCHIVE",
  performance: "PERFORMANCE",
  learn: "LEARN",
  system: "SYSTEM",
});

const state = {
  asset: "ALL",
  route: "command",
  explainMode: "simple",
  proofFilter: "all",
  learnQuery: "",
  health: null,
  command: null,
  radar: null,
  epoch: null,
  paper: null,
  epoch2State: null,
  archive: null,
  education: null,
  intelligence: null,
  performance: null,
  decisionStatus: null,
  shadowRail: null,
  operationalTruth: null,
  marketTapeStatus: null,
  coldArchiveStatus: null,
  liveFeed: null,
  marketLayer: "PA",
  marketSelection: null,
  marketCockpit: null,
  marketProviderDetails: [],
  marketSelectedDetail: null,
  marketSelectedProof: null,
  marketRequestSeq: 0,
  evidenceDetail: null,
  lastEvidenceTrigger: null,
  runtimeRefreshInFlight: false,
};

function byId(id) {
  return document.getElementById(id);
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function text(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function upper(value, fallback = "UNKNOWN") {
  return text(value, fallback).toUpperCase();
}

function shortIdentity(value) {
  const raw = text(value, "");
  if (raw.length < 16) return raw || "—";
  return `${raw.slice(0, 8)}…${raw.slice(-6)}`;
}

function formatTime(ms) {
  if (!Number.isFinite(Number(ms))) return "NOT MEASURED";
  try {
    return new Intl.DateTimeFormat("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      day: "2-digit",
      month: "2-digit",
    }).format(new Date(Number(ms)));
  } catch {
    return "NOT MEASURED";
  }
}

function escapeHtml(value) {
  return text(value, "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function setBoot(id, label, kind = "muted") {
  const node = byId(id);
  if (!node) return;
  node.textContent = label;
  node.dataset.state = kind;
}

function setTruthChip(id, label, kind = "muted") {
  const node = byId(id);
  if (!node) return;
  node.textContent = label;
  node.className = "truth-chip";
  node.classList.add(
    kind === "ready"
      ? "truth-chip-ready"
      : kind === "safe"
        ? "truth-chip-safe"
        : kind === "risk"
          ? "truth-chip-risk"
          : "truth-chip-muted"
  );
}

function stateClass(value) {
  const normalized = text(value, "").toLowerCase();
  if (normalized === "active" || normalized.includes("success") || normalized === "bullish") {
    return "state-positive";
  }
  if (
    normalized.includes("invalid") ||
    normalized.includes("fail") ||
    normalized.includes("bearish") ||
    normalized.includes("event_block")
  ) return "state-risk";
  if (normalized === "watch" || normalized.includes("caution")) return "state-watch";
  return "state-neutral";
}

function pairsToObject(pairs) {
  if (!Array.isArray(pairs)) return {};
  return Object.fromEntries(
    pairs
      .filter((item) => Array.isArray(item) && item.length >= 2)
      .map((item) => [String(item[0]), Number(item[1]) || 0])
  );
}

function setMainBusy(isBusy, announcement = "") {
  const main = byId("mainContent");
  if (main) main.setAttribute("aria-busy", String(isBusy));
  if (announcement) {
    const announcer = byId("runtimeAnnouncer");
    if (announcer) announcer.textContent = announcement;
  }
}

function announceRoute(route) {
  const label = ROUTE_LABELS[route] || "COMMAND";
  const announcer = byId("routeAnnouncer");
  if (announcer) announcer.textContent = `${label} bölümü açıldı.`;
  document.title = `GALACTECH // ${label}`;
}

function routeTo(route) {
  const nextRoute = ROUTE_LABELS[route] ? route : "command";
  state.route = nextRoute;
  document.querySelectorAll("[data-route-view]").forEach((view) => {
    const active = view.dataset.routeView === nextRoute;
    view.hidden = !active;
    view.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === nextRoute;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const main = byId("mainContent");
  if (main) {
    main.scrollIntoView({
      block: "start",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  }
  announceRoute(nextRoute);
  if (nextRoute === "markets") {
    void initializeMarketWorkspace({ reload: true });
  }
}
function bindNavigation() {
  const navButtons = [...document.querySelectorAll("#primaryNav [data-route]")];
  navButtons.forEach((button, index) => {
    button.addEventListener("click", () => routeTo(button.dataset.route || "command"));
    button.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (event.key === "ArrowDown" || event.key === "ArrowRight") {
        nextIndex = (index + 1) % navButtons.length;
      } else if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
        nextIndex = (index - 1 + navButtons.length) % navButtons.length;
      } else if (event.key === "Home") {
        nextIndex = 0;
      } else if (event.key === "End") {
        nextIndex = navButtons.length - 1;
      }
      if (nextIndex === null) return;
      event.preventDefault();
      navButtons[nextIndex]?.focus();
    });
  });

  document.querySelectorAll("[data-asset]").forEach((button) => {
    button.addEventListener("click", () => {
      state.asset = button.dataset.asset || "ALL";
      document.querySelectorAll("[data-asset]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderCommand();
      renderRadar();
      renderArchive();
      void initializeMarketWorkspace({ reload: state.route === "markets" });
    });
  });

  document.querySelectorAll("[data-explain-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.explainMode = button.dataset.explainMode || "simple";
      document.querySelectorAll("[data-explain-mode]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderIntelligence();
    });
  });

  document.querySelectorAll("[data-layer]").forEach((button) => {
    button.addEventListener("click", () => {
      state.marketLayer = button.dataset.layer || "PA";
      document.querySelectorAll("[data-layer]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderMarketWorkspace();
    });
  });

  byId("marketSymbolSelect")?.addEventListener("change", () => {
    syncMarketSelectionFromControls(true);
  });
  byId("marketTimeframeSelect")?.addEventListener("change", () => {
    syncMarketSelectionFromControls(true);
  });

  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.proofFilter = button.dataset.filter || "all";
      document.querySelectorAll("[data-filter]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderArchive();
    });
  });

  document.addEventListener("click", (event) => {
    const source = event.target instanceof Element ? event.target : null;
    const marketProvider = source?.closest("[data-market-provider-id]");
    if (marketProvider instanceof HTMLElement) {
      void selectMarketProvider(marketProvider.dataset.marketProviderId || "");
      return;
    }

    const evidenceTrigger = source?.closest("[data-evidence-id]");
    if (evidenceTrigger instanceof HTMLElement) {
      const identity = evidenceTrigger.dataset.evidenceId || "";
      void openEvidenceRoom(identity, evidenceTrigger);
      return;
    }

    const conceptTrigger = source?.closest("[data-learn-concept]");
    if (conceptTrigger instanceof HTMLElement) {
      const concept = conceptTrigger.dataset.learnConcept || "";
      state.learnQuery = concept;
      const input = byId("learnSearchInput");
      if (input) input.value = concept;
      renderEducation();
      routeTo("learn");
      return;
    }

    const learnTrigger = source?.closest("[data-evidence-learn]");
    if (learnTrigger) {
      closeEvidenceRoom();
      routeTo("learn");
    }
  });

  byId("learnSearchInput")?.addEventListener("input", (event) => {
    const input = event.target instanceof HTMLInputElement ? event.target : null;
    state.learnQuery = input?.value || "";
    renderEducation();
  });

  const dialog = byId("evidenceDialog");
  const closeButton = byId("closeEvidenceDialog");
  closeButton?.addEventListener("click", closeEvidenceRoom);
  dialog?.addEventListener("close", () => {
    const trigger = state.lastEvidenceTrigger;
    if (trigger instanceof HTMLElement) {
      trigger.focus({ preventScroll: true });
    }
  });
}

function signalMatchesAsset(item) {
  if (state.asset === "ALL") return true;
  return upper(item?.symbol, "").startsWith(state.asset);
}

function renderCommand() {
  const data = state.command;
  if (!data) return;

  byId("metricForecasts").textContent = text(data.freeze_count, "0");
  byId("metricForecastsNote").textContent = data.latest_frozen_at_ms
    ? `latest · ${formatTime(data.latest_frozen_at_ms)}`
    : "henüz immutable freeze yok";

  const counts = pairsToObject(data.state_counts);
  byId("metricAttention").textContent = String((counts.watch || 0) + (counts.active || 0));

  const recent = Array.isArray(data.recent_signals)
    ? data.recent_signals.filter(signalMatchesAsset)
    : [];
  const feed = byId("commandFeed");
  if (!feed) return;

  if (!recent.length) {
    feed.className = "feed-list empty-state";
    feed.innerHTML =
      "<strong>Seçili odakta immutable forecast yok.</strong>" +
      "<p>Boş liste sıfır başarı ya da sıfır risk anlamına gelmez.</p>";
    return;
  }

  feed.className = "feed-list";
  feed.innerHTML = recent.map((item) => `
    <button class="evidence-trigger" type="button"
      data-evidence-id="${escapeHtml(item.signal_freeze_identity)}"
      aria-label="${escapeHtml(item.symbol)} ${escapeHtml(item.timeframe)} frozen evidence aç">
      <article class="feed-item">
        <div class="feed-item-head">
          <strong>${escapeHtml(item.symbol)} · ${escapeHtml(item.timeframe)}</strong>
          <span class="${stateClass(item.state)}">${escapeHtml(upper(item.state))}</span>
        </div>
        <div class="feed-item-meta">
          <span>${escapeHtml(upper(item.direction))}</span>
          <span>agreement ${escapeHtml(item.confluence_score)}</span>
          <span>${escapeHtml(item.probability_status || "NOT_CALIBRATED")}</span>
          <span>${escapeHtml(formatTime(item.frozen_at_ms))}</span>
          <code>${escapeHtml(shortIdentity(item.signal_freeze_identity))}</code>
          <span class="evidence-open-cue">Evidence Room →</span>
        </div>
      </article>
    </button>`).join("");
}

function renderRadar() {
  const target = byId("criticalRadar");
  if (!target || !state.radar) return;
  const rows = Array.isArray(state.radar.items)
    ? state.radar.items.filter((item) => signalMatchesAsset(item.latest || item))
    : [];
  const material = rows.filter((item) =>
    ["watch", "active"].includes(text((item.latest || {}).state, "").toLowerCase())
  );

  if (!material.length) {
    target.className = "radar-list empty-state";
    target.innerHTML =
      "<strong>Şu anda bu endpointten material radar state gelmiyor.</strong>" +
      "<p>Bu, piyasanın risksiz olduğu anlamına gelmez; yalnız bu evidence yüzeyinde material WATCH/ACTIVE yok.</p>";
    return;
  }

  target.className = "radar-list";
  target.innerHTML = material.map((item) => {
    const latest = item.latest || {};
    return `
      <button class="evidence-trigger" type="button"
        data-evidence-id="${escapeHtml(latest.signal_freeze_identity)}"
        aria-label="${escapeHtml(latest.symbol || item.symbol)} critical radar evidence aç">
        <article class="radar-item">
          <div class="radar-item-head">
            <strong>${escapeHtml(latest.symbol || item.symbol)} · ${escapeHtml(latest.timeframe || item.timeframe)}</strong>
            <span class="${stateClass(latest.state)}">${escapeHtml(upper(latest.state))}</span>
          </div>
          <div class="radar-item-meta">
            <span>${escapeHtml(upper(latest.direction))}</span>
            <span>${escapeHtml(latest.setup_type || "setup unavailable")}</span>
            <code>${escapeHtml(shortIdentity(latest.signal_freeze_identity))}</code>
            <span class="evidence-open-cue">Proof →</span>
          </div>
        </article>
      </button>`;
  }).join("");
}

function marketContextKey(symbol, timeframe) {
  return `${text(symbol, "")}::${text(timeframe, "")}`;
}

function availableMarketContexts() {
  const rows = Array.isArray(state.radar?.items) ? state.radar.items : [];
  const byKey = new Map();
  rows.forEach((item) => {
    const latest = item?.latest || item || {};
    const symbol = text(latest.symbol || item?.symbol, "");
    const timeframe = text(latest.timeframe || item?.timeframe, "");
    if (!symbol || !timeframe) return;
    const key = marketContextKey(symbol, timeframe);
    if (!byKey.has(key)) byKey.set(key, { symbol, timeframe });
  });
  return [...byKey.values()].sort((left, right) =>
    (left.symbol + left.timeframe).localeCompare(right.symbol + right.timeframe)
  );
}

function populateMarketSelectors() {
  const symbolSelect = byId("marketSymbolSelect");
  const timeframeSelect = byId("marketTimeframeSelect");
  if (!symbolSelect || !timeframeSelect) return [];

  const contexts = availableMarketContexts();
  const symbols = [...new Set(contexts.map((item) => item.symbol))];
  const selectedSymbol = state.marketSelection?.symbol || symbolSelect.value || "";
  const nextSymbol = symbols.includes(selectedSymbol)
    ? selectedSymbol
    : (symbols[0] || "");

  symbolSelect.innerHTML = symbols.length
    ? symbols.map((symbol) =>
        `<option value="${escapeHtml(symbol)}">${escapeHtml(symbol)}</option>`
      ).join("")
    : '<option value="">No observed symbol</option>';
  symbolSelect.value = nextSymbol;

  const timeframes = contexts
    .filter((item) => item.symbol === nextSymbol)
    .map((item) => item.timeframe);
  const selectedTimeframe = state.marketSelection?.timeframe || timeframeSelect.value || "";
  const nextTimeframe = timeframes.includes(selectedTimeframe)
    ? selectedTimeframe
    : (timeframes[0] || "");

  timeframeSelect.innerHTML = timeframes.length
    ? timeframes.map((timeframe) =>
        `<option value="${escapeHtml(timeframe)}">${escapeHtml(timeframe)}</option>`
      ).join("")
    : '<option value="">No observed timeframe</option>';
  timeframeSelect.value = nextTimeframe;

  return contexts;
}

function preferredMarketContext(contexts) {
  if (!contexts.length) return null;
  const current = state.marketSelection;
  if (
    current &&
    contexts.some((item) =>
      item.symbol === current.symbol && item.timeframe === current.timeframe
    )
  ) {
    if (state.asset === "ALL" || upper(current.symbol, "").startsWith(state.asset)) {
      return current;
    }
  }
  if (state.asset !== "ALL") {
    const assetMatch = contexts.find((item) =>
      upper(item.symbol, "").startsWith(state.asset)
    );
    if (assetMatch) return assetMatch;
  }
  return contexts[0];
}

async function initializeMarketWorkspace({ reload = true } = {}) {
  const contexts = populateMarketSelectors();
  const selection = preferredMarketContext(contexts);
  if (!selection) {
    state.marketSelection = null;
    state.marketCockpit = null;
    state.marketProviderDetails = [];
    state.marketSelectedDetail = null;
    state.marketSelectedProof = null;
    renderMarketWorkspace();
    renderMarketTruth();
    return;
  }

  const symbolSelect = byId("marketSymbolSelect");
  const timeframeSelect = byId("marketTimeframeSelect");
  if (symbolSelect) symbolSelect.value = selection.symbol;
  const availableTimeframes = contexts
    .filter((item) => item.symbol === selection.symbol)
    .map((item) => item.timeframe);
  if (timeframeSelect) {
    timeframeSelect.innerHTML = availableTimeframes.map((timeframe) =>
      `<option value="${escapeHtml(timeframe)}">${escapeHtml(timeframe)}</option>`
    ).join("");
    timeframeSelect.value = selection.timeframe;
  }

  const changed =
    !state.marketSelection ||
    state.marketSelection.symbol !== selection.symbol ||
    state.marketSelection.timeframe !== selection.timeframe;
  state.marketSelection = { ...selection };
  if (reload || changed || !state.marketCockpit) {
    await loadMarketSelection();
  } else {
    renderMarketWorkspace();
    renderMarketTruth();
  }
}

function syncMarketSelectionFromControls(reload) {
  const symbol = byId("marketSymbolSelect")?.value || "";
  const contexts = availableMarketContexts();
  const timeframeSelect = byId("marketTimeframeSelect");
  if (!symbol || !timeframeSelect) return;

  const timeframes = contexts
    .filter((item) => item.symbol === symbol)
    .map((item) => item.timeframe);
  if (!timeframes.includes(timeframeSelect.value)) {
    timeframeSelect.innerHTML = timeframes.map((timeframe) =>
      `<option value="${escapeHtml(timeframe)}">${escapeHtml(timeframe)}</option>`
    ).join("");
    timeframeSelect.value = timeframes[0] || "";
  }
  const timeframe = timeframeSelect.value;
  if (!timeframe) return;

  state.marketSelection = { symbol, timeframe };
  if (reload) void loadMarketSelection();
  else renderMarketWorkspace();
}

async function loadMarketSelection() {
  const selection = state.marketSelection;
  if (!selection) return;
  const requestSeq = ++state.marketRequestSeq;
  state.marketCockpit = null;
  state.marketProviderDetails = [];
  state.marketSelectedDetail = null;
  state.marketSelectedProof = null;
  renderMarketWorkspace();

  let cockpit;
  try {
    cockpit = await fetchJson(API.assetCockpit(selection.symbol, selection.timeframe));
  } catch (error) {
    console.warn("[GALACTECH] market cockpit unavailable", error);
    if (requestSeq !== state.marketRequestSeq) return;
    state.marketCockpit = {
      status: "unavailable",
      symbol: selection.symbol,
      timeframe: selection.timeframe,
      latest_by_provider: [],
      recent_signals: [],
    };
    renderMarketWorkspace();
    renderMarketTruth();
    return;
  }
  if (requestSeq !== state.marketRequestSeq) return;
  state.marketCockpit = cockpit;

  const providers = Array.isArray(cockpit.latest_by_provider)
    ? cockpit.latest_by_provider
    : [];
  const details = await Promise.all(
    providers.map(async (card) => {
      try {
        const detail = await fetchJson(API.signalDetail(card.signal_freeze_identity));
        return { card, detail, ok: true };
      } catch (error) {
        console.warn("[GALACTECH] provider signal detail unavailable", error);
        return { card, detail: null, ok: false };
      }
    })
  );
  if (requestSeq !== state.marketRequestSeq) return;

  state.marketProviderDetails = details;
  const currentId = state.marketSelectedDetail?.signal?.signal_freeze_identity;
  const selected =
    details.find((item) => item.detail?.signal?.signal_freeze_identity === currentId) ||
    details.find((item) => item.ok && item.detail?.status === "ready") ||
    details[0] ||
    null;
  state.marketSelectedDetail = selected?.detail || null;
  await loadSelectedDecisionProof(requestSeq);
  renderMarketWorkspace();
  renderMarketTruth();
}

async function loadSelectedDecisionProof(requestSeq = state.marketRequestSeq) {
  const identity = state.marketSelectedDetail?.signal?.signal_freeze_identity || "";
  state.marketSelectedProof = null;
  if (!identity) return;
  try {
    const payload = await fetchJson(API.decisionProof(identity));
    const currentIdentity =
      state.marketSelectedDetail?.signal?.signal_freeze_identity || "";
    if (requestSeq !== state.marketRequestSeq || currentIdentity !== identity) return;
    state.marketSelectedProof = payload;
  } catch (error) {
    console.warn("[GALACTECH] decision proof unavailable", error);
    const currentIdentity =
      state.marketSelectedDetail?.signal?.signal_freeze_identity || "";
    if (requestSeq !== state.marketRequestSeq || currentIdentity !== identity) return;
    state.marketSelectedProof = {
      status: "unavailable",
      reason: "decision_proof_endpoint_error",
      read_only: true,
      real_capital: 0,
    };
  }
}

async function selectMarketProvider(identity) {
  const item = state.marketProviderDetails.find(
    (entry) => entry.card?.signal_freeze_identity === identity
  );
  if (!item) return;
  state.marketSelectedDetail = item.detail || null;
  await loadSelectedDecisionProof(state.marketRequestSeq);
  renderMarketWorkspace();
  renderMarketTruth();
}

function renderMarketProviderList() {
  const target = byId("marketProviderList");
  if (!target) return;
  const rows = state.marketProviderDetails;
  if (!rows.length) {
    target.className = "market-provider-list empty-state";
    target.innerHTML =
      "<strong>No provider freeze is available for this context.</strong>" +
      "<p>Binance/Bybit state is never invented from another provider.</p>";
    return;
  }

  const selectedId = state.marketSelectedDetail?.signal?.signal_freeze_identity || "";
  target.className = "market-provider-list";
  target.innerHTML = rows.map(({ card, detail, ok }) => {
    const signal = detail?.signal || card || {};
    const identity = card?.signal_freeze_identity || "";
    const active = identity === selectedId;
    return `
      <button type="button"
        class="market-provider-card${active ? " is-active" : ""}"
        data-market-provider-id="${escapeHtml(identity)}"
        aria-pressed="${active ? "true" : "false"}">
        <div class="market-provider-head">
          <strong>${escapeHtml(upper(signal.exchange, "UNKNOWN PROVIDER"))}</strong>
          <span class="${stateClass(signal.state)}">${escapeHtml(upper(signal.state))}</span>
        </div>
        <div class="market-provider-meta">
          <span>${escapeHtml(upper(signal.direction))}</span>
          <span>${escapeHtml(signal.setup_type || "setup unavailable")}</span>
          <span>frozen ${escapeHtml(formatTime(signal.frozen_at_ms))}</span>
          <code>${escapeHtml(shortIdentity(identity))}</code>
          <span>${ok ? "exact detail ready" : "detail unavailable"}</span>
        </div>
      </button>`;
  }).join("");
}

function renderMarketRecentTape() {
  const target = byId("marketRecentTape");
  const count = byId("marketRecentCount");
  if (!target) return;
  const rows = Array.isArray(state.marketCockpit?.recent_signals)
    ? state.marketCockpit.recent_signals
    : [];
  if (count) count.textContent = `${rows.length} freezes`;
  if (!rows.length) {
    target.className = "feed-list empty-state";
    target.innerHTML =
      "<strong>No recent immutable decisions for this context.</strong>" +
      "<p>Empty tape is not interpreted as low risk or inactivity failure.</p>";
    return;
  }

  target.className = "feed-list";
  target.innerHTML = rows.map((signal) => `
    <button class="evidence-trigger" type="button"
      data-evidence-id="${escapeHtml(signal.signal_freeze_identity)}"
      aria-label="${escapeHtml(signal.symbol)} ${escapeHtml(signal.timeframe)} recent evidence aç">
      <article class="feed-item">
        <div class="feed-item-head">
          <strong>${escapeHtml(upper(signal.exchange))}</strong>
          <span class="${stateClass(signal.state)}">${escapeHtml(upper(signal.state))}</span>
        </div>
        <div class="feed-item-meta">
          <span>${escapeHtml(upper(signal.direction))}</span>
          <span>${escapeHtml(signal.setup_type)}</span>
          <span>agreement ${escapeHtml(signal.confluence_score)}</span>
          <span>${escapeHtml(formatTime(signal.frozen_at_ms))}</span>
          <code>${escapeHtml(shortIdentity(signal.signal_freeze_identity))}</code>
          <span class="evidence-open-cue">Evidence Room →</span>
        </div>
      </article>
    </button>`).join("");
}

function renderMarketLayerSurface() {
  const target = byId("marketLayerSurface");
  if (!target) return;
  const detail = state.marketSelectedDetail;
  const layer = state.marketLayer;

  if (!detail || detail.status !== "ready" || !detail.signal) {
    target.className = "market-layer-surface empty-state";
    target.innerHTML =
      `<strong>${escapeHtml(layer)} layer has no exact selected provider proof.</strong>` +
      "<p>No synthetic overlay is rendered.</p>";
    return;
  }

  if (layer !== "PA") {
    const labels = {
      LIQ: "Liquidity / liquidation",
      FLOW: "Order flow / CVD",
      DERIV: "Derivatives / OI / funding / basis",
      ONCHAIN: "On-chain",
    };
    const domains = {
      LIQ: ["liquidity_map", "liquidation_map"],
      FLOW: ["order_book", "order_flow_cvd"],
      DERIV: ["derivatives"],
      ONCHAIN: ["onchain"],
    };
    const proofPayload = state.marketSelectedProof || {};
    const proof = proofPayload.status === "ready" ? proofPayload.proof : null;
    const slices = Array.isArray(proof?.evidence_slices)
      ? proof.evidence_slices.filter((item) =>
          (domains[layer] || []).includes(text(item?.domain, ""))
        )
      : [];

    if (!proof || !slices.length) {
      target.className = "market-layer-surface market-layer-unavailable";
      target.innerHTML = `
        <span class="proof-section-label">${escapeHtml(layer)} / DECISION PROOF</span>
        <strong>${escapeHtml(labels[layer] || layer)} · NOT PERSISTED</strong>
        <p>
          No exact R20.5 Decision Proof is persisted for this immutable signal.
          GALACTECH does not synthesize a layer from unrelated evidence.
        </p>`;
      return;
    }

    target.className = "market-layer-surface";
    target.innerHTML = `
      <div class="market-layer-head">
        <div>
          <span class="proof-section-label">${escapeHtml(layer)} / R20.5 DECISION PROOF</span>
          <strong>${escapeHtml(labels[layer] || layer)}</strong>
        </div>
        <code>${escapeHtml(shortIdentity(proof.proof_identity))}</code>
      </div>
      <div class="truth-table">
        ${slices.map((slice) => {
          const availability = upper(slice?.availability, "INSUFFICIENT");
          const verdict = upper(slice?.verdict, "INSUFFICIENT");
          const freshness = Number(slice?.freshness_0_1);
          const freshnessText = Number.isFinite(freshness)
            ? `${(freshness * 100).toFixed(1)}%`
            : "NOT MEASURED";
          const ids = Array.isArray(slice?.evidence_identities)
            ? slice.evidence_identities
            : [];
          const summaries = Array.isArray(slice?.summary_codes)
            ? slice.summary_codes
            : [];
          return `
            <div class="truth-row">
              <span>${escapeHtml(upper(slice?.domain, "UNKNOWN"))}</span>
              <strong class="${stateClass(verdict)}">${escapeHtml(availability)} · ${escapeHtml(verdict)}</strong>
            </div>
            <div class="proof-footnote">
              source ${escapeHtml(slice?.source_quality || "NOT AVAILABLE")} ·
              freshness ${escapeHtml(freshnessText)} ·
              evidence ${escapeHtml(ids.length)}
            </div>
            ${summaries.length
              ? `<ul class="market-evidence-summary">${summaries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
              : ""}
            ${ids.length
              ? `<div class="feed-item-meta">${ids.map((identity) => `<code>${escapeHtml(shortIdentity(identity))}</code>`).join("")}</div>`
              : ""}
          `;
        }).join("")}
      </div>`;
    return;
  }

  const methods = Array.isArray(detail.methodologies) ? detail.methodologies : [];
  const priceAction = methods.find(
    (item) => text(item?.methodology, "").toLowerCase() === "price_action"
  );
  const summaries = Array.isArray(detail.evidence_summary) ? detail.evidence_summary : [];
  const geometry = detail.geometry;
  target.className = "market-layer-surface market-layer-pa";
  target.innerHTML = `
    <div class="market-layer-head">
      <div>
        <span class="proof-section-label">PA / FROZEN SIGNAL EVIDENCE</span>
        <strong>${escapeHtml(detail.signal.setup_type)}</strong>
      </div>
      <span class="${stateClass(detail.signal.direction)}">${escapeHtml(upper(detail.signal.direction))}</span>
    </div>
    <div class="market-pa-grid">
      <div>
        <span>METHOD STATE</span>
        <strong>${escapeHtml(upper(priceAction?.resolved_direction, "UNRESOLVED"))}</strong>
        <small>${escapeHtml(priceAction?.selected_count ?? 0)} selected / ${escapeHtml(priceAction?.source_count ?? 0)} source</small>
      </div>
      <div>
        <span>ENTRY REFERENCE</span>
        <strong>${geometry ? `${escapeHtml(geometry.entry_zone_low)} → ${escapeHtml(geometry.entry_zone_high)}` : "NOT FROZEN"}</strong>
        <small>${geometry ? escapeHtml(geometry.entry_reference_model) : "no synthetic zone"}</small>
      </div>
      <div>
        <span>INVALIDATION</span>
        <strong>${geometry ? escapeHtml(geometry.invalidation_price) : "NOT FROZEN"}</strong>
        <small>${geometry ? escapeHtml(geometry.invalidation_trigger) : "no synthetic invalidation"}</small>
      </div>
    </div>
    <ul class="market-evidence-summary">
      ${summaries.length
        ? summaries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
        : "<li>No concise PA summary was frozen.</li>"}
    </ul>`;
}

function renderMarketWorkspace() {
  const selection = state.marketSelection;
  const cockpit = state.marketCockpit;
  const detail = state.marketSelectedDetail;
  const title = byId("marketWorkspaceTitle");
  const contextTag = byId("marketContextTag");
  const providerTag = byId("marketProviderTag");
  const chart = byId("marketFrozenChart");

  if (title) {
    title.textContent = selection
      ? `${selection.symbol} · ${selection.timeframe}`
      : "Select a market context";
  }
  if (contextTag) {
    contextTag.textContent = selection
      ? `CONTEXT · ${selection.symbol} / ${selection.timeframe}`
      : "CONTEXT · UNAVAILABLE";
  }
  if (providerTag) {
    providerTag.textContent = detail?.signal
      ? `PROVIDER · ${upper(detail.signal.exchange)}`
      : "PROVIDER · —";
  }

  if (chart) {
    if (!selection) {
      chart.className = "empty-state";
      chart.innerHTML =
        "<strong>No observed market context.</strong><p>Chart evidence is not invented.</p>";
    } else if (!cockpit) {
      chart.className = "empty-state";
      chart.innerHTML =
        "<strong>Frozen market context loading…</strong><p>Waiting for exact cockpit evidence.</p>";
    } else if (!detail || detail.status !== "ready") {
      chart.className = "empty-state";
      chart.innerHTML =
        "<strong>Selected provider detail unavailable.</strong><p>No synthetic candle chart is rendered.</p>";
    } else {
      chart.className = "market-frozen-chart";
      chart.innerHTML = frozenChartMarkup(detail);
    }
  }

  renderMarketProviderList();
  renderMarketRecentTape();
  renderMarketLayerSurface();
}

function renderMarketTruth() {
  const target = byId("marketTruth");
  if (!target) return;
  const detail = state.marketSelectedDetail;
  const cockpitStatus = upper(state.marketCockpit?.status, "UNAVAILABLE");
  const paReady = detail?.status === "ready";
  const proof = state.marketSelectedProof?.status === "ready"
    ? state.marketSelectedProof.proof
    : null;
  const evidenceSlices = Array.isArray(proof?.evidence_slices)
    ? proof.evidence_slices
    : [];
  const domainStatus = (names) => {
    const matches = evidenceSlices.filter((item) => names.includes(text(item?.domain, "")));
    if (!matches.length) return "NOT PERSISTED";
    if (matches.some((item) => item.availability === "available")) return "AVAILABLE · R20.5";
    if (matches.some((item) => item.availability === "unsupported")) return "UNSUPPORTED";
    return "INSUFFICIENT";
  };
  const rows = [
    ["Radar API", state.radar ? upper(state.radar.status, "READY") : "UNAVAILABLE"],
    ["Asset cockpit", cockpitStatus],
    ["Provider freezes", String(state.marketProviderDetails.length)],
    ["Decision Proof", proof ? "PERSISTED · IMMUTABLE" : "NOT PERSISTED"],
    ["PA", paReady ? "AVAILABLE · FROZEN SIGNAL DETAIL" : "INSUFFICIENT"],
    ["LIQ", domainStatus(["liquidity_map", "liquidation_map"])],
    ["FLOW", domainStatus(["order_book", "order_flow_cvd"])],
    ["DERIV", domainStatus(["derivatives"])],
    ["ONCHAIN", domainStatus(["onchain"])],
  ];
  target.innerHTML = rows.map(([label, value]) =>
    `<div class="truth-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  ).join("");
}

function moneyText(value) {
  const raw = text(value, "");
  return raw ? `${raw} USDT` : "NOT MEASURED";
}

function capitalStatusText(value) {
  return upper(value, "NOT_YET_MEASURED").replaceAll("_", " ");
}

function renderVaultCard(vault) {
  const positions = Array.isArray(vault?.positions) ? vault.positions : [];
  const costs = [
    ["fee", vault?.fee_usdt],
    ["spread", vault?.spread_usdt],
    ["slippage", vault?.slippage_usdt],
  ];
  return `
    <article class="capital-vault-card">
      <div class="capital-vault-head">
        <div>
          <span class="eyebrow">VAULT</span>
          <h3>${escapeHtml(vault?.vault_id || "UNKNOWN")}</h3>
        </div>
        <span class="tag">${escapeHtml(capitalStatusText(vault?.metrics_status))}</span>
      </div>
      <div class="capital-vault-metrics">
        <div><span>NAV</span><strong>${escapeHtml(moneyText(vault?.nav_usdt))}</strong></div>
        <div><span>CASH</span><strong>${escapeHtml(moneyText(vault?.cash_usdt))}</strong></div>
        <div><span>EXPOSURE</span><strong>${escapeHtml(moneyText(vault?.marked_exposure_usdt))}</strong></div>
        <div><span>DRAWDOWN</span><strong>${escapeHtml(text(vault?.drawdown_fraction, "NOT MEASURED"))}</strong></div>
      </div>
      <div class="capital-vault-detail">
        <span>start ${escapeHtml(moneyText(vault?.starting_cash_usdt))}</span>
        <span>realized ${escapeHtml(moneyText(vault?.realized_pnl_usdt))}</span>
        <span>unrealized ${escapeHtml(moneyText(vault?.unrealized_pnl_usdt))}</span>
        <span>turnover ${escapeHtml(text(vault?.turnover_fraction, "NOT MEASURED"))}</span>
        <span>closed trades ${escapeHtml(vault?.closed_trade_count ?? 0)}</span>
        <span>expectancy ${escapeHtml(
          vault?.expectancy_usdt_per_closed_trade === null ||
          vault?.expectancy_usdt_per_closed_trade === undefined
            ? "NOT YET MEASURED"
            : moneyText(vault.expectancy_usdt_per_closed_trade)
        )}</span>
      </div>
      <div class="capital-cost-row" aria-label="Execution costs">
        ${costs.map(([label, value]) =>
          `<span><small>${escapeHtml(label)}</small><strong>${escapeHtml(moneyText(value))}</strong></span>`
        ).join("")}
      </div>
      <div class="capital-position-list">
        ${positions.length
          ? positions.map((position) =>
              `<span><strong>${escapeHtml(position.symbol)}</strong> · qty ${escapeHtml(position.quantity)}</span>`
            ).join("")
          : "<span>Cash only · no open virtual position</span>"}
      </div>
      <code class="capital-identity">${escapeHtml(vault?.snapshot_identity || "NO SNAPSHOT ID")}</code>
    </article>`;
}

function renderEpoch() {
  const target = byId("capitalOverview");
  if (!target || !state.epoch) return;

  const program = state.epoch.current_program || {};
  const canonical = state.epoch2State || {};
  const activation = canonical.activation || {};
  const consolidated = canonical.consolidated || {};
  const vaults = Array.isArray(canonical.vaults) ? canonical.vaults : [];
  const order = ["CORE", "TACTICAL", "OPPORTUNITY_RESERVE"];
  const orderedVaults = [...vaults].sort(
    (left, right) => order.indexOf(left.vault_id) - order.indexOf(right.vault_id)
  );

  if (canonical.status !== "ready") {
    target.innerHTML = `
      <article class="panel capital-unavailable">
        <span class="eyebrow">CANONICAL EPOCH 2</span>
        <h2>Runtime accounting evidence unavailable</h2>
        <p>${escapeHtml(text(canonical.reason, "epoch2 state not available"))}</p>
        <div class="truth-table">
          <div class="truth-row"><span>Program</span><strong>${escapeHtml(program.epoch_id || "Epoch 2")}</strong></div>
          <div class="truth-row"><span>Constitution start</span><strong>${escapeHtml(moneyText(program.starting_cash_usdt))}</strong></div>
          <div class="truth-row"><span>Runtime NAV</span><strong>NOT MEASURED</strong></div>
          <div class="truth-row"><span>REAL CAPITAL</span><strong class="safe-text">DISABLED</strong></div>
        </div>
        <p>No NAV, PnL, allocation or performance is inferred from the constitution alone.</p>
      </article>
      <article class="panel">
        <span class="eyebrow">VAULT CONSTITUTION</span>
        <div class="truth-table">
          ${(Array.isArray(program.vault_allocations) ? program.vault_allocations : [])
            .map((item) =>
              `<div class="truth-row"><span>${escapeHtml(item.vault_id)}</span><strong>${escapeHtml(moneyText(item.starting_cash_usdt))}</strong></div>`
            ).join("") ||
            '<div class="truth-row"><span>Allocation evidence</span><strong>UNAVAILABLE</strong></div>'}
        </div>
        <p>Accepted Epoch 2 constitution · not a model recommendation.</p>
      </article>`;
    return;
  }

  const totalCosts = [
    ["fee", consolidated.fee_usdt],
    ["spread", consolidated.spread_usdt],
    ["slippage", consolidated.slippage_usdt],
  ];

  target.innerHTML = `
    <article class="capital-hero-card">
      <div class="capital-hero-head">
        <div>
          <span class="eyebrow">CANONICAL EPOCH 2 / CONSOLIDATED</span>
          <h2>${escapeHtml(moneyText(consolidated.nav_usdt))}</h2>
          <p>NAV from immutable R21 accounting · snapshot ${escapeHtml(formatTime(consolidated.snapshot_at_ms))}</p>
        </div>
        <span class="truth-chip truth-chip-safe">REAL CAPITAL · DISABLED</span>
      </div>
      <div class="capital-hero-metrics">
        <div><span>CASH</span><strong>${escapeHtml(moneyText(consolidated.cash_usdt))}</strong></div>
        <div><span>MARKED EXPOSURE</span><strong>${escapeHtml(moneyText(consolidated.marked_exposure_usdt))}</strong></div>
        <div><span>REALIZED PNL</span><strong>${escapeHtml(moneyText(consolidated.realized_pnl_usdt))}</strong></div>
        <div><span>UNREALIZED PNL</span><strong>${escapeHtml(moneyText(consolidated.unrealized_pnl_usdt))}</strong></div>
        <div><span>DRAWDOWN</span><strong>${escapeHtml(text(consolidated.drawdown_fraction, "NOT MEASURED"))}</strong></div>
        <div><span>TURNOVER</span><strong>${escapeHtml(text(consolidated.turnover_fraction, "NOT MEASURED"))}</strong></div>
      </div>
      <div class="capital-cost-row">
        ${totalCosts.map(([label, value]) =>
          `<span><small>${escapeHtml(label)}</small><strong>${escapeHtml(moneyText(value))}</strong></span>`
        ).join("")}
      </div>
      <code class="capital-identity">${escapeHtml(consolidated.snapshot_identity || "NO SNAPSHOT ID")}</code>
    </article>

    <article class="panel capital-constitution">
      <span class="eyebrow">WHY THIS ALLOCATION?</span>
      <h2>Accepted Epoch 2 constitution</h2>
      <p>Core 600 / Tactical 300 / Opportunity Reserve 100 USDT is frozen program policy, not an AI inference or live recommendation.</p>
      <div class="truth-table">
        <div class="truth-row"><span>Activation</span><strong>${escapeHtml(shortIdentity(activation.activation_identity))}</strong></div>
        <div class="truth-row"><span>Starting cash</span><strong>${escapeHtml(moneyText(activation.starting_cash_usdt))}</strong></div>
        <div class="truth-row"><span>Leverage</span><strong>${activation.leverage_allowed === false ? "DISABLED" : "UNVERIFIED"}</strong></div>
        <div class="truth-row"><span>Borrowing</span><strong>${activation.borrowing_allowed === false ? "DISABLED" : "UNVERIFIED"}</strong></div>
        <div class="truth-row"><span>Martingale</span><strong>${activation.martingale_allowed === false ? "DISABLED" : "UNVERIFIED"}</strong></div>
      </div>
    </article>

    <section class="capital-vault-section">
      <div class="capital-section-head">
        <div><span class="eyebrow">VAULT ARCHITECTURE</span><h2>Core / Tactical / Opportunity Reserve</h2></div>
        <span class="tag">${escapeHtml(capitalStatusText(consolidated.metrics_status))}</span>
      </div>
      <div class="capital-vault-grid">
        ${orderedVaults.map(renderVaultCard).join("")}
      </div>
    </section>

    <article class="panel capital-track-record">
      <span class="eyebrow">TRACK RECORD TRUTH</span>
      <h2>${escapeHtml(capitalStatusText(consolidated.metrics_status))}</h2>
      <div class="truth-table">
        <div class="truth-row"><span>Closed trades</span><strong>${escapeHtml(consolidated.closed_trade_count ?? 0)}</strong></div>
        <div class="truth-row"><span>Wins / Losses / Breakeven</span><strong>${escapeHtml(consolidated.win_count ?? 0)} / ${escapeHtml(consolidated.loss_count ?? 0)} / ${escapeHtml(consolidated.breakeven_count ?? 0)}</strong></div>
        <div class="truth-row"><span>Expectancy</span><strong>${escapeHtml(
          consolidated.expectancy_usdt_per_closed_trade === null ||
          consolidated.expectancy_usdt_per_closed_trade === undefined
            ? "NOT YET MEASURED"
            : moneyText(consolidated.expectancy_usdt_per_closed_trade)
        )}</strong></div>
      </div>
      <p>Empty history is not 0% win rate. Metrics remain NOT YET MEASURED until accepted closed-trade evidence exists.</p>
    </article>`;
}

function renderShadowDecisionRail() {
  const target = byId("shadowRailOverview");
  if (!target) return;
  const data = state.shadowRail || {};
  const snapshot = data.snapshot || {};
  const ready = data.status === "ready";
  const replayVerified =
    snapshot.quick_check_ok === true && snapshot.read_only_verified === true;
  const lastRecords = Array.isArray(snapshot.last_record_identities)
    ? snapshot.last_record_identities
    : [];

  if (!ready) {
    target.innerHTML = `
      <article class="panel capital-unavailable">
        <span class="eyebrow">SHADOW DECISION RAIL</span>
        <h2>Runtime shadow evidence unavailable</h2>
        <p>${escapeHtml(text(data.reason, "shadow decision rail not exposed"))}</p>
        <div class="truth-table">
          <div class="truth-row"><span>Semantic</span><strong>SHADOW / RESEARCH ONLY</strong></div>
          <div class="truth-row"><span>Canonical Epoch 2 mutation</span><strong>DISABLED</strong></div>
          <div class="truth-row"><span>Production authority</span><strong>DISABLED</strong></div>
        </div>
        <p>Unavailable shadow evidence is not interpreted as a trade, fill, or canonical paper mutation.</p>
      </article>`;
    return;
  }

  target.innerHTML = `
    <article class="panel">
      <div class="panel-head">
        <div>
          <span class="eyebrow">SHADOW DECISION RAIL / READ ONLY</span>
          <h2>${escapeHtml(snapshot.record_count ?? 0)} journaled previews</h2>
        </div>
        <span class="truth-chip ${replayVerified ? "truth-chip-ready" : "truth-chip-muted"}">
          ${replayVerified ? "REPLAY · VERIFIED" : "REPLAY · UNVERIFIED"}
        </span>
      </div>
      <div class="truth-table">
        <div class="truth-row"><span>Journal</span><strong>${escapeHtml(data.journal_filename || "configured")}</strong></div>
        <div class="truth-row"><span>SQLite quick_check</span><strong>${snapshot.quick_check_ok === true ? "PASS" : "UNVERIFIED"}</strong></div>
        <div class="truth-row"><span>Read-only replay</span><strong>${snapshot.read_only_verified === true ? "VERIFIED" : "UNVERIFIED"}</strong></div>
        <div class="truth-row"><span>Canonical Epoch 2 mutation</span><strong class="safe-text">DISABLED</strong></div>
        <div class="truth-row"><span>Production authority</span><strong class="safe-text">DISABLED</strong></div>
        <div class="truth-row"><span>REAL CAPITAL</span><strong class="safe-text">DISABLED</strong></div>
      </div>
      <div class="feed-item-meta">
        ${lastRecords.length
          ? lastRecords.map((item) =>
              `<span>${escapeHtml(item?.[0] || "UNKNOWN")} <code>${escapeHtml(shortIdentity(item?.[1]))}</code></span>`
            ).join("")
          : "<span>No shadow preview has been journaled.</span>"}
      </div>
      <p>Reviewed preview evidence only · not a fill, not canonical NAV mutation, not live trading.</p>
    </article>`;
}

function renderPaper() {
  const data = state.epoch2State || {};
  const navNode = byId("metricPaperNav");
  const noteNode = byId("metricPaperNavNote");
  if (!navNode || !noteNode) return;

  if (data.status !== "ready" || !data.consolidated) {
    navNode.textContent = "UNAVAILABLE";
    noteNode.textContent = text(data.reason, "canonical Epoch2 evidence unavailable");
    return;
  }

  navNode.textContent = moneyText(data.consolidated.nav_usdt);
  noteNode.textContent = "canonical Epoch2 · immutable R21 accounting";
}
function proofCategory(item) {
  const outcome = item?.latest_outcome;
  if (!outcome) {
    const signalState = text(item?.signal?.state, "").toLowerCase();
    if (["no_signal", "neutral"].includes(signalState)) return "not_evaluable";
    return "unresolved";
  }

  const outcomeState = text(outcome.outcome_state, "").toLowerCase();
  const resolution = text(outcome.resolution_status, "").toLowerCase();
  if (outcomeState.startsWith("success_tp")) return "winner";
  if (outcomeState === "fail_sl") return "loser";
  if (outcomeState === "timeout") return "expired";
  if (outcomeState === "invalidated") return "invalidated";
  if (outcomeState === "ambiguous") return "ambiguous";
  if (
    outcomeState === "not_evaluable" ||
    outcomeState === "cancelled" ||
    resolution === "not_evaluable"
  ) {
    return "not_evaluable";
  }
  return "unresolved";
}

function archiveCategoryLabel(category) {
  const labels = {
    winner: "WINNER",
    loser: "LOSER",
    expired: "EXPIRED",
    invalidated: "INVALIDATED",
    ambiguous: "AMBIGUOUS",
    not_evaluable: "ABSTAIN / N-E",
    unresolved: "UNRESOLVED",
  };
  return labels[category] || upper(category);
}

function archiveCategoryClass(category) {
  if (category === "winner") return "archive-status archive-status-winner";
  if (["loser", "invalidated"].includes(category)) {
    return "archive-status archive-status-risk";
  }
  if (["expired", "ambiguous", "not_evaluable"].includes(category)) {
    return "archive-status archive-status-caution";
  }
  return "archive-status archive-status-neutral";
}

function archiveReason(outcome) {
  if (!outcome) return "No later outcome snapshot yet.";
  if (outcome.ambiguity_reason) return `ambiguity · ${outcome.ambiguity_reason}`;
  if (outcome.not_evaluable_reason) return `not evaluable · ${outcome.not_evaluable_reason}`;
  if (outcome.outcome_state === "cancelled") return "cancelled";
  return "";
}

function updateArchiveSummary(allRows, visibleRows) {
  const total = Number(state.archive?.total_count ?? allRows.length);
  const resolved = allRows.filter((item) => item.latest_outcome).length;
  const unresolved = allRows.length - resolved;

  if (byId("archiveTotal")) byId("archiveTotal").textContent = String(total);
  if (byId("archiveResolved")) byId("archiveResolved").textContent = String(resolved);
  if (byId("archiveUnresolved")) byId("archiveUnresolved").textContent = String(unresolved);
  if (byId("archiveVisible")) byId("archiveVisible").textContent = String(visibleRows.length);

  const schemaTag = byId("archiveSchemaTag");
  if (schemaTag) {
    schemaTag.textContent = state.archive?.outcome_schema_available
      ? "OUTCOME SCHEMA · AVAILABLE"
      : "OUTCOME SCHEMA · NOT AVAILABLE";
  }

  const counts = {
    all: allRows.length,
    winner: 0,
    loser: 0,
    expired: 0,
    invalidated: 0,
    ambiguous: 0,
    not_evaluable: 0,
    unresolved: 0,
  };
  allRows.forEach((item) => {
    const category = proofCategory(item);
    counts[category] = (counts[category] || 0) + 1;
  });
  Object.entries(counts).forEach(([category, count]) => {
    const node = document.querySelector(`[data-filter-count="${category}"]`);
    if (node) node.textContent = String(count);
  });
}

function archiveItemMarkup(item) {
  const signal = item?.signal || {};
  const outcome = item?.latest_outcome || null;
  const category = proofCategory(item);
  const reason = archiveReason(outcome);
  const probability = upper(signal.probability_status, "NOT_CALIBRATED");
  const confluenceSemantic =
    signal.confluence_score_semantic || "agreement_index_not_probability";

  return `
    <button class="archive-proof-trigger" type="button"
      data-evidence-id="${escapeHtml(signal.signal_freeze_identity)}"
      aria-label="${escapeHtml(signal.symbol || "UNKNOWN")} ${escapeHtml(signal.timeframe || "")}
        issuance snapshot ve Evidence Room aç">
      <article class="archive-proof-card">
        <header class="archive-proof-head">
          <div>
            <span class="eyebrow">IMMUTABLE PROOF</span>
            <h2>${escapeHtml(signal.symbol || "UNKNOWN")} · ${escapeHtml(signal.timeframe || "—")}</h2>
          </div>
          <span class="${archiveCategoryClass(category)}">${escapeHtml(archiveCategoryLabel(category))}</span>
        </header>

        <div class="archive-snapshot-pair">
          <section class="archive-snapshot archive-snapshot-issuance">
            <div class="archive-snapshot-title">
              <span>01</span>
              <strong>ISSUANCE SNAPSHOT</strong>
            </div>
            <div class="archive-signal-line">
              <strong class="${stateClass(signal.state)}">${escapeHtml(upper(signal.state))}</strong>
              <span class="${stateClass(signal.direction)}">${escapeHtml(upper(signal.direction))}</span>
            </div>
            <dl class="archive-kv">
              <div><dt>provider</dt><dd>${escapeHtml(upper(signal.exchange))} · ${escapeHtml(upper(signal.market_type))}</dd></div>
              <div><dt>setup</dt><dd>${escapeHtml(signal.setup_type || "UNAVAILABLE")}</dd></div>
              <div><dt>agreement</dt><dd>${escapeHtml(signal.confluence_score)} · not probability</dd></div>
              <div><dt>probability</dt><dd>${escapeHtml(probability)}</dd></div>
              <div><dt>issued</dt><dd>${escapeHtml(formatTime(signal.frozen_at_ms))}</dd></div>
              <div><dt>source cutoff</dt><dd>${escapeHtml(formatTime(signal.source_cutoff_open_time_ms))}</dd></div>
            </dl>
            <p class="archive-semantic-note">${escapeHtml(confluenceSemantic)}</p>
            <code>${escapeHtml(signal.signal_freeze_identity || "NO FREEZE ID")}</code>
          </section>

          <div class="archive-link-line" aria-hidden="true">
            <span>→</span>
            <small>append only</small>
          </div>

          <section class="archive-snapshot archive-snapshot-outcome">
            <div class="archive-snapshot-title">
              <span>02</span>
              <strong>LATER · OUTCOME SNAPSHOT</strong>
            </div>
            ${outcome ? `
              <div class="archive-outcome-line">
                <strong class="${archiveCategoryClass(category)}">${escapeHtml(upper(outcome.outcome_state || outcome.resolution_status))}</strong>
                <span>${escapeHtml(upper(outcome.evidence_class, "UNLABELLED"))}</span>
              </div>
              <dl class="archive-kv">
                <div><dt>resolution</dt><dd>${escapeHtml(upper(outcome.resolution_status))}</dd></div>
                <div><dt>coverage</dt><dd>${escapeHtml(upper(outcome.coverage_status))}</dd></div>
                <div><dt>evaluated</dt><dd>${escapeHtml(formatTime(outcome.evaluated_as_of_ms))}</dd></div>
                <div><dt>horizon</dt><dd>${escapeHtml(outcome.max_holding_bars)} bars</dd></div>
                <div><dt>entry observed</dt><dd>${outcome.entry_observed ? "YES" : "NO"}</dd></div>
                <div><dt>highest target</dt><dd>${escapeHtml(outcome.highest_target_index ?? 0)}</dd></div>
              </dl>
              ${reason ? `<p class="archive-outcome-reason">${escapeHtml(reason)}</p>` : ""}
              <code>${escapeHtml(outcome.outcome_identity || "NO OUTCOME ID")}</code>
            ` : `
              <div class="archive-unresolved">
                <strong>NO LATER OUTCOME YET</strong>
                <p>Issuance remains visible. Missing outcome is not rewritten as failure, success or 0% performance.</p>
              </div>
            `}
          </section>
        </div>

        <footer class="archive-proof-foot">
          <span>Freeze stays immutable after outcome.</span>
          <span class="evidence-open-cue">Open frozen Evidence Room →</span>
        </footer>
      </article>
    </button>`;
}

function renderArchive() {
  const target = byId("archiveWall");
  if (!target || !state.archive) return;

  const loaded = Array.isArray(state.archive.items) ? state.archive.items : [];
  const assetRows = loaded.filter((item) => signalMatchesAsset(item.signal || {}));
  const visibleRows = state.proofFilter === "all"
    ? assetRows
    : assetRows.filter((item) => proofCategory(item) === state.proofFilter);

  updateArchiveSummary(assetRows, visibleRows);

  if (!visibleRows.length) {
    target.className = "archive-proof-wall empty-state";
    target.innerHTML =
      "<strong>Bu filtre için immutable proof kaydı yok.</strong>" +
      "<p>Boş filtre sonucu başarı, başarısızlık veya risksizlik iddiası değildir.</p>";
    return;
  }

  target.className = "archive-proof-wall";
  target.innerHTML = visibleRows.map(archiveItemMarkup).join("");
}


function proofBadgeClass(value) {
  const normalized = text(value, "").toLowerCase();
  if (["agree", "bullish", "valid", "valid_so_far"].includes(normalized)) {
    return "proof-badge proof-badge-support";
  }
  if (["contradict", "bearish"].includes(normalized) || normalized.includes("conflict")) {
    return "proof-badge proof-badge-risk";
  }
  if (
    normalized.includes("ambigu") ||
    normalized.includes("insufficient") ||
    normalized.includes("unresolved")
  ) {
    return "proof-badge proof-badge-caution";
  }
  return "proof-badge proof-badge-neutral";
}

function parseFrozenBundle(detail) {
  if (!detail?.bundle_json) return null;
  try {
    const parsed = JSON.parse(detail.bundle_json);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function frozenChartMarkup(detail) {
  const bundle = parseFrozenBundle(detail);
  const rawCandles = Array.isArray(bundle?.candles) ? bundle.candles : [];
  const candles = rawCandles
    .map((item) => ({
      open: Number(item?.open),
      high: Number(item?.high),
      low: Number(item?.low),
      close: Number(item?.close),
      openTime: Number(item?.open_time_ms),
    }))
    .filter((item) =>
      [item.open, item.high, item.low, item.close].every(Number.isFinite)
    )
    .slice(-40);

  if (!candles.length) {
    return `
      <div class="frozen-chart-empty">
        <strong>Frozen OHLC chart not available in this proof payload.</strong>
        <p>Candle count/range is still shown from accepted freeze metadata; no synthetic candles are drawn.</p>
      </div>`;
  }

  const low = Math.min(...candles.map((item) => item.low));
  const high = Math.max(...candles.map((item) => item.high));
  const span = Math.max(high - low, Number.EPSILON);
  const width = 760;
  const height = 210;
  const paddingX = 18;
  const paddingY = 16;
  const plotWidth = width - paddingX * 2;
  const plotHeight = height - paddingY * 2;
  const slot = plotWidth / candles.length;
  const bodyWidth = Math.max(2, Math.min(10, slot * 0.52));
  const y = (price) => paddingY + ((high - price) / span) * plotHeight;

  const candleSvg = candles.map((item, index) => {
    const x = paddingX + slot * index + slot / 2;
    const openY = y(item.open);
    const closeY = y(item.close);
    const highY = y(item.high);
    const lowY = y(item.low);
    const bodyY = Math.min(openY, closeY);
    const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
    const klass = item.close >= item.open ? "candle-up" : "candle-down";
    return `
      <g class="${klass}">
        <line x1="${x.toFixed(2)}" y1="${highY.toFixed(2)}"
          x2="${x.toFixed(2)}" y2="${lowY.toFixed(2)}"></line>
        <rect x="${(x - bodyWidth / 2).toFixed(2)}" y="${bodyY.toFixed(2)}"
          width="${bodyWidth.toFixed(2)}" height="${bodyHeight.toFixed(2)}"></rect>
      </g>`;
  }).join("");

  const first = candles[0];
  const last = candles[candles.length - 1];
  return `
    <div class="frozen-chart-wrap">
      <svg class="frozen-chart" viewBox="0 0 ${width} ${height}"
        role="img" aria-label="Frozen issuance-time candle chart">
        <line class="chart-grid-line" x1="${paddingX}" y1="${paddingY}"
          x2="${width - paddingX}" y2="${paddingY}"></line>
        <line class="chart-grid-line" x1="${paddingX}" y1="${height / 2}"
          x2="${width - paddingX}" y2="${height / 2}"></line>
        <line class="chart-grid-line" x1="${paddingX}" y1="${height - paddingY}"
          x2="${width - paddingX}" y2="${height - paddingY}"></line>
        ${candleSvg}
      </svg>
      <div class="frozen-chart-caption">
        <span>${escapeHtml(String(candles.length))} frozen candles rendered</span>
        <span>low ${escapeHtml(String(low))} · high ${escapeHtml(String(high))}</span>
        <span>${escapeHtml(formatTime(first.openTime))} → ${escapeHtml(formatTime(last.openTime))}</span>
      </div>
    </div>`;
}

function selectedEvidenceMarkup(item) {
  const summaries = Array.isArray(item?.evidence_summary) ? item.evidence_summary : [];
  const metrics = Array.isArray(item?.metrics) ? item.metrics : [];
  const levels = Array.isArray(item?.key_levels) ? item.key_levels : [];
  const ambiguity = Array.isArray(item?.ambiguity_flags) ? item.ambiguity_flags : [];
  const contradiction = Array.isArray(item?.contradiction_flags)
    ? item.contradiction_flags
    : [];
  const extra = [
    ...metrics.map((metric) =>
      `${text(metric.name)}=${text(metric.value)} ${text(metric.unit, "")}`.trim()
    ),
    ...levels.map((level) => `${text(level.label)}=${text(level.price)}`),
  ];

  return `
    <li class="selected-evidence">
      <div class="selected-evidence-head">
        <strong>${escapeHtml(item?.setup_type || "evidence")}</strong>
        <code>${escapeHtml(shortIdentity(item?.evidence_id))}</code>
      </div>
      <div class="selected-evidence-meta">
        <span>${escapeHtml(upper(item?.direction))}</span>
        <span>${escapeHtml(upper(item?.validity))}</span>
        <span>market ${escapeHtml(formatTime(item?.market_available_at_ms))}</span>
        <span>observed ${escapeHtml(formatTime(item?.observed_at_ms))}</span>
      </div>
      ${summaries.length
        ? `<p class="selected-evidence-summary">${summaries.map(escapeHtml).join(" · ")}</p>`
        : ""}
      ${extra.length
        ? `<p class="selected-evidence-summary">${extra.map(escapeHtml).join(" · ")}</p>`
        : ""}
      ${ambiguity.length
        ? `<p class="selected-evidence-summary state-watch">ambiguity · ${ambiguity.map(escapeHtml).join(" · ")}</p>`
        : ""}
      ${contradiction.length
        ? `<p class="selected-evidence-summary state-risk">contradiction · ${contradiction.map(escapeHtml).join(" · ")}</p>`
        : ""}
      ${item?.invalidation_price !== null && item?.invalidation_price !== undefined
        ? `<p class="selected-evidence-summary">invalidation ${escapeHtml(item.invalidation_price)}
          · ${escapeHtml(item.invalidation_trigger || "trigger unspecified")}</p>`
        : ""}
    </li>`;
}

function methodEngineMarkup(method) {
  const selected = Array.isArray(method?.selected) ? method.selected : [];
  return `
    <li class="method-engine">
      <div class="method-engine-head">
        <strong>${escapeHtml(upper(method?.methodology))}</strong>
        <span class="${proofBadgeClass(method?.resolved_direction)}">
          ${escapeHtml(upper(method?.resolved_direction))}
        </span>
      </div>
      <div class="method-engine-meta">
        <span>source ${escapeHtml(method?.source_count ?? 0)}</span>
        <span>selected ${escapeHtml(method?.selected_count ?? selected.length)}</span>
        <span>latest ${escapeHtml(formatTime(method?.latest_market_available_at_ms))}</span>
        <span>${method?.has_internal_direction_conflict ? "INTERNAL CONFLICT" : "no internal conflict"}</span>
      </div>
      ${selected.length
        ? `<ul class="selected-evidence-list">${selected.map(selectedEvidenceMarkup).join("")}</ul>`
        : `<p class="proof-footnote">No selected accepted evidence for this methodology slot.</p>`}
    </li>`;
}

function pairwiseMarkup(item) {
  return `
    <li class="pairwise-item">
      <span>${escapeHtml(upper(item?.left))} ↔ ${escapeHtml(upper(item?.right))}</span>
      <span class="${proofBadgeClass(item?.relation)}">${escapeHtml(upper(item?.relation))}</span>
      <span>${escapeHtml(upper(item?.left_direction))} / ${escapeHtml(upper(item?.right_direction))}</span>
    </li>`;
}

function geometryMarkup(geometry) {
  if (!geometry) {
    return `
      <div class="frozen-chart-empty">
        <strong>No frozen geometry.</strong>
        <p>The accepted signal did not freeze entry/target/invalidation geometry. Nothing is inferred.</p>
      </div>`;
  }
  const targets = Array.isArray(geometry.targets) ? geometry.targets : [];
  return `
    <ul class="geometry-list">
      <li class="geometry-item">
        <strong>Entry zone</strong>
        <span>${escapeHtml(geometry.entry_zone_low)} → ${escapeHtml(geometry.entry_zone_high)}</span>
      </li>
      <li class="geometry-item">
        <strong>Reference</strong>
        <span>${escapeHtml(geometry.entry_reference_price)} · ${escapeHtml(geometry.entry_reference_model)}</span>
      </li>
      <li class="geometry-item">
        <strong>Invalidation</strong>
        <span>${escapeHtml(geometry.invalidation_price)} · ${escapeHtml(geometry.invalidation_trigger)}</span>
      </li>
      ${targets.map((target) => `
        <li class="geometry-item">
          <strong>${escapeHtml(target.label)}</strong>
          <span>${escapeHtml(target.target_price)} · R/R ${escapeHtml(target.reference_rr)}</span>
        </li>`).join("")}
    </ul>
    <p class="proof-footnote">Reference geometry is evidence, not an order instruction.</p>`;
}

function contextualLessonIds(detail) {
  const signal = detail?.signal || {};
  const methods = Array.isArray(detail?.methodologies) ? detail.methodologies : [];
  const summaries = Array.isArray(detail?.evidence_summary) ? detail.evidence_summary : [];
  const haystack = [
    signal.setup_type,
    ...summaries,
    ...methods.flatMap((method) =>
      Array.isArray(method?.selected)
        ? method.selected.flatMap((item) => [
            item?.setup_type,
            ...(Array.isArray(item?.evidence_summary) ? item.evidence_summary : []),
          ])
        : []
    ),
  ].map((item) => text(item, "").toLowerCase()).join(" ");

  const ids = new Set(["agreement_vs_probability"]);
  if (["no_signal", "neutral"].includes(text(signal.state, "").toLowerCase())) {
    ids.add("abstain");
  }
  if (detail?.geometry || text(signal.state, "").toLowerCase() === "invalidated") {
    ids.add("invalidation");
    ids.add("risk_reward");
  }
  if (haystack.includes("cvd") || haystack.includes("delta")) ids.add("cvd");
  if (haystack.includes("absorption")) ids.add("absorption");
  if (haystack.includes("liquidity") || haystack.includes("sweep")) ids.add("liquidity_sweep");
  if (haystack.includes("harmonic") || haystack.includes("gartley") || haystack.includes("bat")) {
    ids.add("harmonic_prz");
  }
  if (haystack.includes("elliott") || haystack.includes("wave")) ids.add("elliott_wave");
  return [...ids];
}

function renderEvidenceRoom(detail) {
  const body = byId("evidenceDialogBody");
  const subtitle = byId("evidenceDialogSubtitle");
  if (!body) return;

  if (!detail || detail.status !== "ready" || !detail.signal) {
    if (subtitle) subtitle.textContent = `Evidence status · ${upper(detail?.status, "UNAVAILABLE")}`;
    body.innerHTML = `
      <div class="empty-state">
        <strong>Frozen evidence unavailable.</strong>
        <p>The product does not fabricate a proof when the signal ledger or exact identity is unavailable.</p>
      </div>`;
    return;
  }

  const signal = detail.signal;
  const methods = Array.isArray(detail.methodologies) ? detail.methodologies : [];
  const pairwise = Array.isArray(detail.pairwise_relations) ? detail.pairwise_relations : [];
  const summaries = Array.isArray(detail.evidence_summary) ? detail.evidence_summary : [];
  const uncertainty = Array.isArray(signal.uncertainty_flags) ? signal.uncertainty_flags : [];

  if (subtitle) {
    subtitle.textContent =
      `${signal.symbol} · ${signal.timeframe} · frozen ${formatTime(signal.frozen_at_ms)}`;
  }

  body.innerHTML = `
    <div class="proof-hero">
      <article class="proof-state-card">
        <span class="proof-section-label">DECISION STATE</span>
        <div class="proof-state-line">
          <strong class="${stateClass(signal.state)}">${escapeHtml(upper(signal.state))}</strong>
          <span class="${stateClass(signal.direction)}">${escapeHtml(upper(signal.direction))}</span>
        </div>
        <p class="proof-footnote">
          ${escapeHtml(signal.setup_type)} · methodology agreement is not probability.
        </p>
        <div class="proof-metric-strip">
          <div class="proof-metric">
            <span>CONFLUENCE</span>
            <strong>${escapeHtml(signal.confluence_score)}</strong>
          </div>
          <div class="proof-metric">
            <span>PROBABILITY</span>
            <strong>${escapeHtml(upper(signal.probability_status, "NOT_CALIBRATED"))}</strong>
          </div>
          <div class="proof-metric">
            <span>CANDLES</span>
            <strong>${escapeHtml(detail.candle_count ?? 0)}</strong>
          </div>
        </div>
      </article>
      <article class="proof-identity-card">
        <span>IMMUTABLE SNAPSHOT</span>
        <code>${escapeHtml(signal.signal_freeze_identity)}</code>
        <p>
          as-of ${escapeHtml(formatTime(signal.as_of_ms))}<br>
          source cutoff ${escapeHtml(formatTime(signal.source_cutoff_open_time_ms))}<br>
          frozen ${escapeHtml(formatTime(signal.frozen_at_ms))}
        </p>
      </article>
    </div>

    <div class="proof-grid">
      <section class="proof-section proof-section-wide">
        <span class="proof-section-label">FROZEN MARKET PROOF</span>
        <h3>Issuance-time chart evidence</h3>
        ${frozenChartMarkup(detail)}
        <p class="proof-footnote">
          Freeze range ${escapeHtml(formatTime(detail.first_candle_open_time_ms))}
          → ${escapeHtml(formatTime(detail.last_candle_open_time_ms))}.
          Later candles cannot rewrite this snapshot.
        </p>
      </section>

      <section class="proof-section">
        <span class="proof-section-label">WHY THIS STATE?</span>
        <h3>Evidence summary</h3>
        <ul class="proof-list">
          ${summaries.length
            ? summaries.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
            : "<li>No concise evidence summary was frozen.</li>"}
        </ul>
      </section>

      <section class="proof-section">
        <span class="proof-section-label">UNCERTAINTY</span>
        <h3>What remains unresolved?</h3>
        <ul class="proof-list">
          ${uncertainty.length
            ? uncertainty.map((item) => `<li class="state-watch">${escapeHtml(item)}</li>`).join("")
            : "<li>No explicit uncertainty flag was frozen at signal level.</li>"}
        </ul>
      </section>

      <section class="proof-section proof-section-wide">
        <span class="proof-section-label">METHOD ENGINES</span>
        <h3>Accepted methodology evidence</h3>
        <ul class="method-engine-list">
          ${methods.length
            ? methods.map(methodEngineMarkup).join("")
            : "<li class=\"method-engine\">No methodology evidence is available.</li>"}
        </ul>
      </section>

      <section class="proof-section">
        <span class="proof-section-label">AGREEMENT MATRIX</span>
        <h3>Cross-method relation</h3>
        <ul class="pairwise-list">
          ${pairwise.length
            ? pairwise.map(pairwiseMarkup).join("")
            : "<li class=\"pairwise-item\">No pairwise relation was frozen.</li>"}
        </ul>
      </section>

      <section class="proof-section">
        <span class="proof-section-label">FROZEN GEOMETRY</span>
        <h3>Entry / target / invalidation reference</h3>
        ${geometryMarkup(detail.geometry)}
      </section>

      <section class="proof-section proof-section-wide">
        <span class="proof-section-label">LEARN FROM THIS SNAPSHOT</span>
        <h3>Evidence, not private reasoning</h3>
        <div class="evidence-learning">
          <p class="proof-footnote">
            This room exposes structured frozen evidence and concise deterministic context.
            It does not expose or invent private chain-of-thought.
          </p>
          <div class="evidence-learning-links">
            ${contextualLessonIds(detail).map((conceptId) =>
              `<button type="button" data-learn-concept="${escapeHtml(conceptId)}">${escapeHtml(upper(conceptId))} →</button>`
            ).join("")}
            <button type="button" data-evidence-learn="true">ALL LESSONS →</button>
          </div>
        </div>
      </section>
    </div>`;
}

async function openEvidenceRoom(identity, trigger) {
  if (!identity || !/^[0-9a-f]{64}$/.test(identity)) return;
  const dialog = byId("evidenceDialog");
  const body = byId("evidenceDialogBody");
  if (!dialog || !body) return;

  state.lastEvidenceTrigger = trigger || document.activeElement;
  state.evidenceDetail = null;
  body.innerHTML = `
    <div class="empty-state">
      <strong>Frozen evidence yükleniyor…</strong>
      <p>Exact signal identity ${escapeHtml(shortIdentity(identity))}</p>
    </div>`;

  if (!dialog.open) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  try {
    const [detail, decisionProof] = await Promise.all([
      fetchJson(API.signalDetail(identity)),
      fetchJson(API.decisionProof(identity)).catch(() => ({
        status: "unavailable",
        read_only: true,
        real_capital: 0,
      })),
    ]);
    state.evidenceDetail = detail;
    renderEvidenceRoom(detail);
    renderDecisionProofExtension(decisionProof);
    const forecastIdentity = decisionProof?.proof?.forecast_identity;
    if (/^[0-9a-f]{64}$/.test(text(forecastIdentity, ""))) {
      const shadowCycle = await fetchJson(
        API.shadowForecastCycle(forecastIdentity)
      ).catch(() => ({
        status: "unavailable",
        reason: "exact_shadow_cycle_lookup_failed",
        forecast_identity: forecastIdentity,
        read_only: true,
        real_capital: 0,
      }));
      renderShadowCycleExtension(shadowCycle);
    }
  } catch (error) {
    console.warn("[GALACTECH] signal detail unavailable", error);
    renderEvidenceRoom({ status: "unavailable", signal: null });
  }
}


function renderDecisionProofExtension(payload) {
  const body = byId("evidenceDialogBody");
  if (!body || payload?.status !== "ready" || !payload.proof) return;
  const proof = payload.proof;
  const slices = Array.isArray(proof.evidence_slices) ? proof.evidence_slices : [];
  const section = document.createElement("section");
  section.className = "proof-section proof-section-wide";
  section.innerHTML = `
    <span class="proof-section-label">R20.5 DECISION PROOF</span>
    <h3>Immutable cross-domain evidence</h3>
    <div class="proof-metric-strip">
      <div class="proof-metric"><span>SUPPORT</span><strong>${escapeHtml(proof.evidence_summary?.support_count ?? 0)}</strong></div>
      <div class="proof-metric"><span>CONTRADICT</span><strong>${escapeHtml(proof.evidence_summary?.contradict_count ?? 0)}</strong></div>
      <div class="proof-metric"><span>AVAILABLE</span><strong>${escapeHtml(proof.evidence_summary?.available_count ?? 0)}/${escapeHtml(proof.evidence_summary?.total_domain_count ?? slices.length)}</strong></div>
    </div>
    <div class="truth-table">
      ${slices.map((slice) => `
        <div class="truth-row">
          <span>${escapeHtml(upper(slice?.domain, "UNKNOWN"))}</span>
          <strong class="${stateClass(slice?.verdict)}">${escapeHtml(upper(slice?.availability, "INSUFFICIENT"))} · ${escapeHtml(upper(slice?.verdict, "INSUFFICIENT"))}</strong>
        </div>
      `).join("")}
    </div>
    <p class="proof-footnote">
      proof ${escapeHtml(proof.proof_identity)} · forecast ${escapeHtml(proof.forecast_identity)} ·
      probability ${escapeHtml(upper(proof.probability_status, "NOT_CALIBRATED"))}.
      This is structured evidence, not private reasoning.
    </p>`;
  const grid = body.querySelector(".proof-grid");
  if (grid) grid.prepend(section);
  else body.appendChild(section);
}

function renderShadowCycleExtension(payload) {
  const body = byId("evidenceDialogBody");
  if (!body) return;

  const section = document.createElement("section");
  section.className = "proof-section proof-section-wide";
  const ready = payload?.status === "ready" && payload?.cycle;
  if (!ready) {
    section.innerHTML = `
      <span class="proof-section-label">R25 CAPITAL DECISION LINEAGE</span>
      <h3>Exact shadow cycle not persisted</h3>
      <p class="proof-footnote">
        ${escapeHtml(text(payload?.reason, "no exact persisted cycle for this forecast"))}.
        The product does not match by symbol, timestamp proximity, direction, or heuristic similarity.
      </p>`;
  } else {
    const cycle = payload.cycle;
    const review = cycle.review_selection_identity
      ? `EXPLICIT · ${shortIdentity(cycle.review_selection_identity)}`
      : "NO EXPLICIT REVIEW";
    const method = cycle.reviewed_method
      ? upper(cycle.reviewed_method)
      : "NONE";
    const replayStatus = upper(
      payload.restart_replay_runtime_status,
      "NOT MEASURED"
    );
    const replay = payload.runtime_replay_observation || null;
    const replayDetail = replay
      ? `runtime ${shortIdentity(replay.runtime_instance_identity)} · first ${formatTime(replay.first_observed_at_ms)} · replay ${formatTime(replay.replay_observed_at_ms)}`
      : text(
          payload.restart_replay_runtime_reason,
          "runtime replay observation not persisted"
        );
    section.innerHTML = `
      <span class="proof-section-label">R25 CAPITAL DECISION LINEAGE</span>
      <h3>Exact forecast → capital → sizing → review → preview</h3>
      <div class="truth-table">
        <div class="truth-row"><span>FORECAST</span><strong>${escapeHtml(shortIdentity(cycle.forecast_identity))}</strong></div>
        <div class="truth-row"><span>DECISION PROOF</span><strong>${escapeHtml(shortIdentity(cycle.proof_identity))}</strong></div>
        <div class="truth-row"><span>CAPITAL SCIENCE</span><strong>${escapeHtml(shortIdentity(cycle.capital_bridge_identity))}</strong></div>
        <div class="truth-row"><span>POSITION SIZING</span><strong>${escapeHtml(shortIdentity(cycle.sizing_bridge_identity))}</strong></div>
        <div class="truth-row"><span>REVIEW</span><strong>${escapeHtml(review)}</strong></div>
        <div class="truth-row"><span>REVIEWED METHOD</span><strong>${escapeHtml(method)}</strong></div>
        <div class="truth-row"><span>R22 PREVIEW</span><strong>${escapeHtml(shortIdentity(cycle.preview_identity))}</strong></div>
        <div class="truth-row"><span>SHADOW JOURNAL REF</span><strong>${escapeHtml(shortIdentity(cycle.journal_record_identity))}</strong></div>
        <div class="truth-row"><span>CYCLE MANIFEST</span><strong>${escapeHtml(shortIdentity(cycle.manifest_identity))}</strong></div>
        <div class="truth-row"><span>RESTART / REPLAY</span><strong class="${replayStatus === "VERIFIED" ? "state-positive" : "state-watch"}">${escapeHtml(replayStatus)}</strong></div>
      </div>
      <p class="proof-footnote">
        Exact persisted forecast_identity match only. This lineage is shadow/research evidence:
        it is not a fill, not a canonical Epoch 2 NAV mutation, not an exchange order, and not a live trade.
        The manifest references a journal record identity; journal runtime presence is verified separately.
        Restart/replay: ${escapeHtml(replayDetail)}.
      </p>`;
  }

  const grid = body.querySelector(".proof-grid");
  if (grid) grid.prepend(section);
  else body.appendChild(section);
}

function closeEvidenceRoom() {
  const dialog = byId("evidenceDialog");
  if (!dialog) return;
  if (typeof dialog.close === "function" && dialog.open) dialog.close();
  else dialog.removeAttribute("open");
}

function lessonMatchesQuery(lesson, query) {
  const needle = text(query, "").trim().toLocaleLowerCase("tr-TR");
  if (!needle) return true;
  const haystack = [
    lesson?.concept_id,
    lesson?.title_tr,
    lesson?.beginner_tr,
    lesson?.why_it_matters_tr,
    lesson?.advanced_tr,
  ]
    .map((item) => text(item, "").toLocaleLowerCase("tr-TR"))
    .join(" ");
  return haystack.includes(needle);
}

function lessonMarkup(lesson) {
  return `
    <article class="learn-card learn-card-rich" data-lesson-id="${escapeHtml(lesson.concept_id)}">
      <header class="learn-card-head">
        <div>
          <span class="eyebrow">${escapeHtml(upper(lesson.concept_id))}</span>
          <h2>${escapeHtml(lesson.title_tr)}</h2>
        </div>
        <span class="tag">EDUCATION</span>
      </header>
      <p class="learn-beginner">${escapeHtml(lesson.beginner_tr)}</p>
      <section class="learn-why">
        <span class="proof-section-label">NEDEN ÖNEMLİ?</span>
        <p>${escapeHtml(lesson.why_it_matters_tr)}</p>
      </section>
      ${lesson.advanced_tr ? `
        <details class="learn-advanced">
          <summary>PRO / teknik açıklamayı aç</summary>
          <p>${escapeHtml(lesson.advanced_tr)}</p>
        </details>` : ""}
      <footer class="learn-card-foot">
        <span>Deterministic catalog · no generated market claim</span>
        <code>REAL_CAPITAL=0</code>
      </footer>
    </article>`;
}

function renderEducation() {
  const target = byId("learnGrid");
  const tag = byId("learnCatalogTag");
  if (!target || !state.education) return;
  const lessons = Array.isArray(state.education.lessons) ? state.education.lessons : [];
  const filtered = lessons.filter((lesson) => lessonMatchesQuery(lesson, state.learnQuery));

  if (tag) {
    tag.textContent = state.education.status === "ready"
      ? `CATALOG · ${lessons.length} VERIFIED LESSONS`
      : `CATALOG · ${upper(state.education.status, "UNAVAILABLE")}`;
  }

  if (!lessons.length) {
    target.className = "learn-grid learn-grid-rich empty-state";
    target.innerHTML =
      "<strong>Eğitim kanıtı yok.</strong><p>Eksik katalog yerine yeni içerik uydurulmaz.</p>";
    return;
  }

  if (!filtered.length) {
    target.className = "learn-grid learn-grid-rich empty-state";
    target.innerHTML =
      `<strong>“${escapeHtml(state.learnQuery)}” için eşleşme yok.</strong>` +
      "<p>Arama sonucu boşsa içerik uydurulmaz; farklı bir kavram ara.</p>";
    return;
  }

  target.className = "learn-grid learn-grid-rich";
  target.innerHTML = filtered.map(lessonMarkup).join("");
}

function setSystemValue(id, value, kind = "neutral") {
  const node = byId(id);
  if (!node) return;
  node.textContent = value;
  node.classList.remove("state-positive", "state-risk", "state-watch", "state-neutral", "safe-text");
  node.classList.add(
    kind === "positive"
      ? "state-positive"
      : kind === "risk"
        ? "state-risk"
        : kind === "watch"
          ? "state-watch"
          : kind === "safe"
            ? "safe-text"
            : "state-neutral"
  );
}

function operationalComponentMarkup(label, component) {
  const status = upper(component?.status, "UNAVAILABLE");
  const ready = status === "READY" || status === "EXPOSED";
  const reason = text(component?.reason, "");
  const detail = reason
    ? ` · ${reason}`
    : "";
  return `
    <div class="truth-row">
      <span>${escapeHtml(label)}</span>
      <strong class="${ready ? "state-positive" : "state-watch"}">
        ${escapeHtml(status)}${escapeHtml(detail)}
      </strong>
    </div>`;
}

function renderOperationalTruth() {
  const target = byId("r25OperationalTruthGrid");
  const tag = byId("r25OperationalTruthTag");
  const note = byId("r25OperationalTruthNote");
  const data = state.operationalTruth;
  if (!target || !tag || !note) return;

  if (!data || data.status !== "ready") {
    tag.textContent = "RUNTIME EVIDENCE · UNAVAILABLE";
    tag.className = "tag state-watch";
    target.innerHTML = `
      <div class="truth-row"><span>R25 OPERATIONAL TRUTH</span><strong class="state-watch">UNAVAILABLE</strong></div>`;
    note.textContent =
      "Operational Truth endpoint unavailable. Missing evidence is not promoted to READY.";
    return;
  }

  const components = data.components || {};
  target.innerHTML = [
    ["DECISION EVIDENCE", components.decision_evidence],
    ["SHADOW INTENT JOURNAL", components.shadow_intent_journal],
    ["SHADOW CYCLE MANIFEST", components.shadow_cycle_manifest],
    ["RUNTIME REPLAY OBSERVATION", components.runtime_replay_observation],
    ["CANONICAL EPOCH 2", components.canonical_epoch2],
    ["MARKET TAPE", components.market_tape_runtime],
    ["COLD ARCHIVE", components.cold_archive],
    ["GALACTECH PRODUCT", components.galactech_product],
  ].map(([label, component]) =>
    operationalComponentMarkup(label, component)
  ).join("");

  const allPresent = data.all_required_runtime_evidence_present === true;
  tag.textContent = allPresent
    ? "ALL REQUIRED RUNTIME EVIDENCE PRESENT"
    : "PARTIAL RUNTIME EVIDENCE";
  tag.className = `tag ${allPresent ? "state-positive" : "state-watch"}`;
  note.textContent = allPresent
    ? "All required R25 runtime evidence sources are independently readable. This is not production or capital-mutation authority."
    : "At least one required R25 runtime source is unavailable. Partial evidence is shown explicitly; production readiness is not inferred.";
}

function renderSystem() {
  const health = state.health || {};
  const radar = state.radar || {};
  const epoch2 = state.epoch2State || {};
  const archive = state.archive || {};
  const intelligence = state.intelligence || {};
  const performance = state.performance || {};
  const education = state.education || {};
  const decisionStatus = state.decisionStatus || {};
  const shadowRail = state.shadowRail || {};
  const marketTape = state.marketTapeStatus || {};
  const coldArchive = state.coldArchiveStatus || {};
  const liveFeed = state.liveFeed || {};

  const apiReady = health.status === "ok";
  const ledgerPresent = health.ledger_present === true;
  const epochReady = epoch2.status === "ready";
  const archiveReady = archive.status === "ready" || archive.status === "empty";
  const radarReady = radar.status === "ready" || radar.status === "empty";
  const intelligenceReady = intelligence.status === "ready";
  const performanceReady = performance.status === "ready" || performance.status === "empty";
  const educationReady = education.status === "ready";
  const radarItems = Array.isArray(radar.items) ? radar.items.length : 0;
  const lessonCount = Array.isArray(education.lessons) ? education.lessons.length : 0;
  const decisionReady = decisionStatus.status === "ready";
  const decisionSnapshot = decisionStatus.snapshot || {};
  const feedReady = liveFeed.status === "ready" || liveFeed.status === "empty";
  const feedCount = Array.isArray(liveFeed.events) ? liveFeed.events.length : 0;
  const shadowRailReady = shadowRail.status === "ready";
  const shadowRailSnapshot = shadowRail.snapshot || {};

  setSystemValue("systemApi", apiReady ? "READY" : "UNAVAILABLE", apiReady ? "positive" : "risk");
  setSystemValue("systemLedger", ledgerPresent ? "PRESENT" : "NOT PRESENT", ledgerPresent ? "positive" : "watch");
  setSystemValue("systemEpoch2", epochReady ? "READY" : "UNAVAILABLE", epochReady ? "positive" : "watch");
  setSystemValue("systemArchive", archiveReady
    ? (archive.outcome_schema_available ? "AVAILABLE" : "SIGNALS ONLY")
    : "UNAVAILABLE", archiveReady && archive.outcome_schema_available ? "positive" : "watch");
  setSystemValue("systemMarketEvidence", radarReady ? "AVAILABLE" : "UNAVAILABLE", radarReady ? "positive" : "watch");
  setSystemValue("systemIntelligence", intelligenceReady ? "READY" : "UNAVAILABLE", intelligenceReady ? "positive" : "watch");
  setSystemValue("systemPerformance", performanceReady ? "READY" : "UNAVAILABLE", performanceReady ? "positive" : "watch");
  setSystemValue("systemEducation", educationReady ? `${lessonCount} LESSONS` : "UNAVAILABLE", educationReady ? "positive" : "watch");
  setSystemValue("systemAlerts", health.alert_outbox_present ? "PRESENT" : "NOT PRESENT", health.alert_outbox_present ? "positive" : "neutral");
  setSystemValue(
    "systemDecisionLedger",
    decisionReady ? `${decisionSnapshot.proof_count ?? 0} PROOFS` : "NOT EXPOSED",
    decisionReady ? "positive" : "watch"
  );
  setSystemValue(
    "systemLiveFeed",
    feedReady ? `${feedCount} LOADED` : "NOT EXPOSED",
    feedReady ? "positive" : "watch"
  );
  setSystemValue(
    "systemShadowRail",
    shadowRailReady
      ? `${shadowRailSnapshot.record_count ?? 0} PREVIEWS`
      : "NOT EXPOSED",
    shadowRailReady ? "positive" : "watch"
  );
  const marketTapeReady = marketTape.status === "ready";
  const marketTapeSnapshot = marketTape.snapshot || {};
  const collectorRuntime = marketTape.collector_runtime || {};
  const collectionProcessStatus = text(
    marketTape.collection_process_status,
    "NOT_MEASURED"
  );
  const collectionFresh = collectionProcessStatus === "HEARTBEAT_FRESH";
  setSystemValue(
    "systemMarketTape",
    marketTapeReady
      ? `${marketTapeSnapshot.total_rows ?? 0} ROWS · PERSISTED`
      : "NOT EXPOSED",
    marketTapeReady && collectionFresh ? "positive" : "watch"
  );
  const marketTapeNote = byId("systemMarketTapeNote");
  if (marketTapeNote) {
    marketTapeNote.textContent = marketTapeReady
      ? `latest persisted age ${marketTapeSnapshot.latest_event_age_ms ?? "NOT MEASURED"} ms · process ${collectionProcessStatus} · heartbeat age ${collectorRuntime.heartbeat_age_ms ?? "NOT MEASURED"} ms · ingestion age ${collectorRuntime.ingestion_age_ms ?? "NOT MEASURED"} ms · ONLINE NOT ASSERTED`
      : text(marketTape.reason, "runtime evidence unavailable");
  }

  const coldReady =
    coldArchive.status === "ready" || coldArchive.status === "empty";
  const coldSnapshot = coldArchive.snapshot || {};
  setSystemValue(
    "systemColdArchive",
    coldReady
      ? (coldArchive.status === "empty"
          ? "0 PARTITIONS"
          : `${coldSnapshot.verified_partition_count ?? 0}/${coldSnapshot.partition_count ?? 0} VERIFIED`)
      : "NOT EXPOSED",
    coldArchive.status === "ready" ? "positive" : "watch"
  );
  const coldNote = byId("systemColdArchiveNote");
  if (coldNote) {
    coldNote.textContent = coldReady
      ? `${text(coldSnapshot.integrity_scope, "NO PARTITIONS")} · process NOT MEASURED · canonical-row replay NOT MEASURED`
      : text(coldArchive.reason, "archive runtime evidence unavailable");
  }

  const shadowRailNote = byId("systemShadowRailNote");
  if (shadowRailNote) {
    shadowRailNote.textContent = shadowRailReady
      ? (shadowRailSnapshot.read_only_verified === true
          ? "read-only replay verified · no canonical writes"
          : "runtime journal present · replay unverified")
      : text(shadowRail.reason, "shadow journal runtime evidence unavailable");
  }

  const epochNote = byId("systemEpoch2Note");
  if (epochNote) {
    epochNote.textContent = epochReady
      ? `snapshot ${shortIdentity(epoch2.consolidated?.snapshot_identity)}`
      : text(epoch2.reason, "canonical R21 runtime evidence unavailable");
  }
  const marketNote = byId("systemMarketEvidenceNote");
  if (marketNote) {
    marketNote.textContent = radarReady
      ? `${radarItems} observed provider/context freezes`
      : `radar ${upper(radar.status, "UNAVAILABLE")}`;
  }

  const truthTag = byId("systemTruthTag");
  if (truthTag) {
    truthTag.textContent = apiReady
      ? "TRUTH · PRODUCT EVIDENCE READY"
      : "TRUTH · DEGRADED";
  }
}


function performanceEvidenceClassLabel(value) {
  const labels = {
    retrospective: "RETROSPECTIVE",
    walk_forward: "WALK-FORWARD",
    live_untouched_forward: "LIVE UNTOUCHED-FORWARD",
  };
  return labels[text(value, "").toLowerCase()] || upper(value, "UNLABELLED");
}

function fractionPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "NOT MEASURED";
  return `${(number * 100).toFixed(1)}%`;
}

function decimalMetric(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "NOT MEASURED";
  return `${value}${suffix}`;
}

function performanceSegmentMarkup(segment) {
  const key = segment?.key || {};
  const decisive = Number(segment?.decisive_n ?? 0);
  const historical = segment?.historical_success_fraction;
  const historyLabel = decisive > 0
    ? fractionPercent(historical)
    : "NOT MEASURED";
  const rStatus = Number(segment?.r_evaluable_n ?? 0) > 0
    ? decimalMetric(segment?.average_r, " R")
    : "NOT MEASURED";

  return `
    <article class="performance-segment">
      <div class="performance-segment-head">
        <div>
          <strong>${escapeHtml(key.symbol || "UNKNOWN")} · ${escapeHtml(key.timeframe || "—")}</strong>
          <span>${escapeHtml(key.setup_type || "setup unavailable")}</span>
        </div>
        <span class="proof-badge proof-badge-neutral">${escapeHtml(upper(key.signal_direction, "NONE"))}</span>
      </div>
      <div class="performance-segment-meta">
        <span>${escapeHtml(upper(key.exchange, "UNKNOWN"))} · ${escapeHtml(upper(key.market_type, "UNKNOWN"))}</span>
        <span>${escapeHtml(key.source_methodology || "multi-method")}</span>
        <span>${escapeHtml(key.confluence_score_bucket || "agreement bucket unavailable")}</span>
        <span>regime ${escapeHtml(key.regime_label || "UNLABELLED")}</span>
      </div>
      <div class="performance-segment-metrics">
        <div><span>TOTAL</span><strong>${escapeHtml(segment?.total_n ?? 0)}</strong></div>
        <div><span>WIN</span><strong>${escapeHtml(segment?.success_n ?? 0)}</strong></div>
        <div><span>LOSS</span><strong>${escapeHtml(segment?.fail_sl_n ?? 0)}</strong></div>
        <div><span>AMBIG</span><strong>${escapeHtml(segment?.ambiguous_n ?? 0)}</strong></div>
        <div><span>TIMEOUT</span><strong>${escapeHtml(segment?.timeout_n ?? 0)}</strong></div>
        <div><span>INVALID</span><strong>${escapeHtml(segment?.invalidated_n ?? 0)}</strong></div>
      </div>
      <div class="performance-descriptive-row">
        <span>
          <small>DECISIVE HISTORICAL FRACTION</small>
          <strong>${escapeHtml(historyLabel)}</strong>
          <em>descriptive frequency · not probability</em>
        </span>
        <span>
          <small>AVERAGE R</small>
          <strong>${escapeHtml(rStatus)}</strong>
          <em>${escapeHtml(segment?.r_evaluable_n ?? 0)} R-evaluable</em>
        </span>
        <span>
          <small>DRAWDOWN R</small>
          <strong>${escapeHtml(decimalMetric(segment?.max_drawdown_r, " R"))}</strong>
          <em>segment path only</em>
        </span>
      </div>
    </article>`;
}

function performanceGroupMarkup(group) {
  const segments = Array.isArray(group?.segments) ? group.segments : [];
  const evidenceClass = performanceEvidenceClassLabel(group?.evidence_class);
  return `
    <section class="performance-cohort">
      <header class="performance-cohort-head">
        <div>
          <span class="eyebrow">EVIDENCE CLASS</span>
          <h3>${escapeHtml(evidenceClass)}</h3>
        </div>
        <div class="performance-cohort-meta">
          <span>horizon ${escapeHtml(group?.max_holding_bars ?? "—")} bars</span>
          <span>stored ${escapeHtml(group?.stored_snapshot_count ?? 0)}</span>
          <span>latest ${escapeHtml(group?.selected_latest_signal_count ?? 0)}</span>
        </div>
      </header>
      <div class="performance-segment-list">
        ${segments.length
          ? segments.map(performanceSegmentMarkup).join("")
          : '<div class="empty-state"><strong>No segment evidence.</strong><p>Empty cohort is not a zero success rate.</p></div>'}
      </div>
    </section>`;
}

function renderPerformanceCohorts() {
  const target = byId("performanceCohorts");
  const data = state.performance;
  if (!target || !data) return;

  const groups = Array.isArray(data.groups) ? data.groups : [];
  const counts = Array.isArray(data.evidence_class_counts)
    ? data.evidence_class_counts
    : [];

  if (byId("performanceOutcomeCount")) {
    byId("performanceOutcomeCount").textContent = String(data.outcome_snapshot_count ?? 0);
  }
  if (byId("performanceEvidenceClassCount")) {
    byId("performanceEvidenceClassCount").textContent = String(counts.length);
  }

  const truthTag = byId("performanceTruthTag");
  if (truthTag) {
    truthTag.textContent =
      data.status === "ready"
        ? "TRUST · COHORT EVIDENCE READY"
        : `TRUST · ${upper(data.status, "UNAVAILABLE")}`;
  }

  if (!groups.length) {
    target.className = "performance-cohorts empty-state";
    target.innerHTML =
      "<strong>Henüz outcome cohort evidence yok.</strong>" +
      "<p>Empty performance history is NOT MEASURED; %0 başarı oranı değildir.</p>";
    return;
  }

  target.className = "performance-cohorts";
  target.innerHTML = groups.map(performanceGroupMarkup).join("");
}

function renderPerformancePaper() {
  const target = byId("performancePaper");
  const canonical = state.epoch2State || {};
  const consolidated = canonical.consolidated || {};
  const vaults = Array.isArray(canonical.vaults) ? canonical.vaults : [];

  if (byId("performancePaperNav")) {
    byId("performancePaperNav").textContent =
      canonical.status === "ready" ? moneyText(consolidated.nav_usdt) : "UNAVAILABLE";
  }
  if (byId("performanceDrawdown")) {
    byId("performanceDrawdown").textContent =
      canonical.status === "ready"
        ? fractionPercent(consolidated.drawdown_fraction)
        : "UNAVAILABLE";
  }

  if (!target) return;
  if (canonical.status !== "ready") {
    target.className = "empty-state";
    target.innerHTML =
      "<strong>Canonical Epoch 2 performance unavailable.</strong>" +
      `<p>${escapeHtml(text(canonical.reason, "runtime evidence unavailable"))}</p>`;
    return;
  }

  const expectancy =
    consolidated.expectancy_usdt_per_closed_trade === null ||
    consolidated.expectancy_usdt_per_closed_trade === undefined
      ? "NOT YET MEASURED"
      : moneyText(consolidated.expectancy_usdt_per_closed_trade);
  const totalCosts =
    Number(consolidated.fee_usdt || 0) +
    Number(consolidated.spread_usdt || 0) +
    Number(consolidated.slippage_usdt || 0);

  target.className = "performance-paper";
  target.innerHTML = `
    <div class="performance-paper-hero">
      <div><span>NAV</span><strong>${escapeHtml(moneyText(consolidated.nav_usdt))}</strong></div>
      <div><span>REALIZED PNL</span><strong>${escapeHtml(moneyText(consolidated.realized_pnl_usdt))}</strong></div>
      <div><span>UNREALIZED PNL</span><strong>${escapeHtml(moneyText(consolidated.unrealized_pnl_usdt))}</strong></div>
      <div><span>CURRENT DRAWDOWN</span><strong>${escapeHtml(fractionPercent(consolidated.drawdown_fraction))}</strong></div>
    </div>
    <div class="truth-table">
      <div class="truth-row"><span>Closed trades</span><strong>${escapeHtml(consolidated.closed_trade_count ?? 0)}</strong></div>
      <div class="truth-row"><span>Wins / Losses / Breakeven</span><strong>${escapeHtml(consolidated.win_count ?? 0)} / ${escapeHtml(consolidated.loss_count ?? 0)} / ${escapeHtml(consolidated.breakeven_count ?? 0)}</strong></div>
      <div class="truth-row"><span>Expectancy</span><strong>${escapeHtml(expectancy)}</strong></div>
      <div class="truth-row"><span>Turnover</span><strong>${escapeHtml(fractionPercent(consolidated.turnover_fraction))}</strong></div>
      <div class="truth-row"><span>Fee + spread + slippage</span><strong>${escapeHtml(Number.isFinite(totalCosts) ? `${totalCosts} USDT` : "NOT MEASURED")}</strong></div>
      <div class="truth-row"><span>Metrics status</span><strong>${escapeHtml(capitalStatusText(consolidated.metrics_status))}</strong></div>
    </div>
    <div class="performance-vault-compare">
      ${vaults.map((vault) => `
        <article>
          <span>${escapeHtml(vault.vault_id)}</span>
          <strong>${escapeHtml(moneyText(vault.nav_usdt))}</strong>
          <small>DD ${escapeHtml(fractionPercent(vault.drawdown_fraction))} · closed ${escapeHtml(vault.closed_trade_count ?? 0)}</small>
        </article>`).join("")}
    </div>
    <p class="proof-footnote">
      Canonical R21 accounting only. Forecast hit-rate is never substituted for paper-fund performance.
    </p>`;
}

function renderPerformance() {
  renderPerformanceCohorts();
  renderPerformancePaper();
}

function renderIntelligence() {
  const target = byId("intelligenceTruth");
  if (!target) return;
  const endpoint = state.intelligence || {};
  const feed = state.liveFeed || {};
  const events = Array.isArray(feed.events) ? feed.events : [];
  const latest = events[0] || null;
  if (state.explainMode === "simple") {
    if (!latest) {
      target.textContent =
        "SIMPLE · Persisted Live Intelligence Feed henüz boş veya runtime’a bağlı değil. " +
        "Sistem eksik Decision Proof yerine sonuç uydurmuyor.";
      return;
    }
    target.textContent =
      `SIMPLE · ${latest.symbol || latest.asset || "Market"} · ${upper(latest.state, "UNKNOWN")}. ` +
      `${latest.conditional_thesis || "Deterministic thesis unavailable."} ` +
      `Probability: ${upper(latest.probability_status, "NOT_CALIBRATED")}.`;
  } else {
    const endpointStatus = upper(endpoint.status, "UNAVAILABLE");
    const feedStatus = upper(feed.status, "UNAVAILABLE");
    target.textContent =
      `PRO · intelligence ${endpointStatus} · persisted R20.5 feed ${feedStatus} · ` +
      `${events.length} loaded event(s). ` +
      (latest
        ? `latest proof ${shortIdentity(latest.proof_identity)} · forecast ${shortIdentity(latest.forecast_identity)}.`
        : "No persisted Decision Proof event is available.");
  }
}

function renderAll() {
  renderCommand();
  renderRadar();
  renderMarketWorkspace();
  renderMarketTruth();
  renderEpoch();
  renderShadowDecisionRail();
  renderPaper();
  renderArchive();
  renderPerformance();
  renderEducation();
  renderIntelligence();
  renderSystem();
  renderOperationalTruth();
}

function applyHealthTruth(data) {
  state.health = data;
  const ready = data?.status === "ok";
  setTruthChip("apiTruth", ready ? "API · READY" : "API · DEGRADED", ready ? "ready" : "risk");
  setBoot("bootApi", ready ? "READY" : "DEGRADED", ready ? "ready" : "muted");

  const ledgerPresent = data?.ledger_present === true;
  setBoot("bootLedger", ledgerPresent ? "PRESENT" : "NOT PRESENT", ledgerPresent ? "ready" : "muted");
  if (byId("systemLedger")) {
    byId("systemLedger").textContent = ledgerPresent ? "PRESENT" : "NOT PRESENT";
  }

  if (Number(data?.real_capital) === 0) {
    setBoot("bootCapital", "DISABLED", "safe");
  } else {
    setBoot("bootCapital", "UNVERIFIED", "muted");
    setTruthChip("apiTruth", "API · AUTHORITY MISMATCH", "risk");
  }
}

async function loadEndpoint(key, url) {
  try {
    const data = await fetchJson(url);
    state[key] = data;
    return { ok: true, key, data };
  } catch (error) {
    console.warn(`[GALACTECH] ${key} unavailable`, error);
    return { ok: false, key, error };
  }
}

async function runBoot() {
  const healthResult = await loadEndpoint("health", API.health);
  if (healthResult.ok) {
    applyHealthTruth(healthResult.data);
  } else {
    setBoot("bootApi", "UNAVAILABLE", "muted");
    setBoot("bootLedger", "NOT VERIFIED", "muted");
    setBoot("bootCapital", "NOT VERIFIED", "muted");
    setTruthChip("apiTruth", "API · UNAVAILABLE", "risk");
  }

  const results = await Promise.all([
    loadEndpoint("command", API.command),
    loadEndpoint("radar", API.radar),
    loadEndpoint("epoch", API.epoch),
    loadEndpoint("epoch2State", API.epoch2State),
    loadEndpoint("archive", API.archive),
    loadEndpoint("education", API.education),
    loadEndpoint("intelligence", API.intelligence),
    loadEndpoint("performance", API.performance),
    loadEndpoint("decisionStatus", API.decisionStatus),
    loadEndpoint("shadowRail", API.shadowRail),
    loadEndpoint("operationalTruth", API.operationalTruth),
    loadEndpoint("marketTapeStatus", API.marketTapeStatus),
    loadEndpoint("coldArchiveStatus", API.coldArchiveStatus),
    loadEndpoint("liveFeed", API.liveFeed),
  ]);

  const marketReady = results.some(
    (result) => result.ok && ["command", "radar"].includes(result.key)
  );
  setBoot(
    "bootMarket",
    marketReady ? "EVIDENCE API READY" : "NOT VERIFIED",
    marketReady ? "ready" : "muted"
  );

  await initializeMarketWorkspace({ reload: true });
  renderAll();
  setMainBusy(false);

  const failed = results.filter((result) => !result.ok).map((result) => result.key);
  byId("bootNote").textContent = failed.length
    ? `Partial evidence surface · unavailable: ${failed.join(", ")}. Eksik veri gizlenmedi.`
    : "Read-only product evidence endpoints responded. REAL_CAPITAL remains disabled.";

  window.setTimeout(() => {
    const boot = byId("coldBoot");
    if (boot) boot.hidden = true;
    byId("mainContent")?.focus({ preventScroll: true });
  }, prefersReducedMotion() ? 0 : 220);
}

async function refreshRuntime(reason = "timer") {
  if (state.runtimeRefreshInFlight || document.visibilityState !== "visible") {
    return false;
  }
  state.runtimeRefreshInFlight = true;
  setMainBusy(true);
  try {
    const results = await Promise.all([
      loadEndpoint("health", API.health),
      loadEndpoint("command", API.command),
      loadEndpoint("radar", API.radar),
      loadEndpoint("epoch2State", API.epoch2State),
      loadEndpoint("archive", API.archive),
      loadEndpoint("performance", API.performance),
      loadEndpoint("decisionStatus", API.decisionStatus),
      loadEndpoint("shadowRail", API.shadowRail),
      loadEndpoint("marketTapeStatus", API.marketTapeStatus),
      loadEndpoint("liveFeed", API.liveFeed),
    ]);
    if (results[0].ok) applyHealthTruth(results[0].data);
    await initializeMarketWorkspace({ reload: state.route === "markets" });
    renderAll();
    if (!results.slice(1).every((item) => item.ok)) {
      setTruthChip("freshnessTruth", "FRESHNESS · PARTIAL EVIDENCE", "muted");
    }
    if (reason === "visibility") {
      setMainBusy(false, "Görünür sekmede runtime kanıtı yenilendi.");
    }
    return true;
  } finally {
    state.runtimeRefreshInFlight = false;
    setMainBusy(false);
  }
}

function startPeriodicRefresh() {
  window.setInterval(() => {
    void refreshRuntime("timer");
  }, 30_000);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      void refreshRuntime("visibility");
    }
  });
}
document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  renderSystem();
  void runBoot().then(startPeriodicRefresh);
});
