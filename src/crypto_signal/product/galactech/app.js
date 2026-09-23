"use strict";

const API = Object.freeze({
  health: "/api/health",
  command: "/api/command-center?recent_limit=12",
  radar: "/api/market-radar",
  epoch: "/api/paper/epoch-contract",
  paper: "/api/paper/mission-control",
  archive: "/api/archive/proof-wall?limit=60&offset=0",
  education: "/api/education",
  intelligence: "/api/intelligence-center",
  signalDetail: (identity) => `/api/signals/${encodeURIComponent(identity)}`,
});

const state = {
  asset: "ALL",
  route: "command",
  explainMode: "simple",
  proofFilter: "all",
  health: null,
  command: null,
  radar: null,
  epoch: null,
  paper: null,
  archive: null,
  education: null,
  intelligence: null,
  evidenceDetail: null,
  lastEvidenceTrigger: null,
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

function routeTo(route) {
  state.route = route;
  document.querySelectorAll("[data-route-view]").forEach((view) => {
    const active = view.dataset.routeView === route;
    view.hidden = !active;
    view.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-route]").forEach((button) => {
    const active = button.dataset.route === route;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const main = byId("mainContent");
  if (main && !prefersReducedMotion()) {
    main.scrollIntoView({ block: "start", behavior: "smooth" });
  }
}

function bindNavigation() {
  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => routeTo(button.dataset.route || "command"));
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
      const active = !button.classList.contains("is-active");
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  });

  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      state.proofFilter = button.dataset.filter || "all";
      document.querySelectorAll("[data-filter]").forEach((item) => {
        item.classList.toggle("is-active", item === button);
      });
      renderArchive();
    });
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
      </div>
    </article>`).join("");
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
      <article class="radar-item">
        <div class="radar-item-head">
          <strong>${escapeHtml(latest.symbol || item.symbol)} · ${escapeHtml(latest.timeframe || item.timeframe)}</strong>
          <span class="${stateClass(latest.state)}">${escapeHtml(upper(latest.state))}</span>
        </div>
        <div class="radar-item-meta">
          <span>${escapeHtml(upper(latest.direction))}</span>
          <span>${escapeHtml(latest.setup_type || "setup unavailable")}</span>
          <code>${escapeHtml(shortIdentity(latest.signal_freeze_identity))}</code>
        </div>
      </article>`;
  }).join("");
}

function renderMarketTruth() {
  const target = byId("marketTruth");
  if (!target) return;
  const rows = Array.isArray(state.radar?.items) ? state.radar.items : [];
  const symbols = [...new Set(rows.map((item) => item?.latest?.symbol || item?.symbol).filter(Boolean))];
  target.innerHTML = [
    ["Radar API", state.radar ? upper(state.radar.status, "READY") : "UNAVAILABLE"],
    ["Observed market contexts", String(rows.length)],
    ["Observed symbols", symbols.length ? symbols.join(" · ") : "NONE IN CURRENT EVIDENCE"],
    ["LIQ / FLOW / DERIV / ONCHAIN overlays", "NOT WIRED IN FOUNDATION"],
  ].map(([label, value]) =>
    `<div class="truth-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  ).join("");
}

function renderEpoch() {
  const target = byId("capitalOverview");
  if (!target || !state.epoch) return;
  const program = state.epoch.current_program || {};
  const binding = state.epoch.runtime_binding || {};
  const allocations = Array.isArray(program.vault_allocations) ? program.vault_allocations : [];

  target.innerHTML = `
    <article class="panel">
      <span class="eyebrow">CURRENT PROGRAM</span>
      <h2>${escapeHtml(program.epoch_id || "Epoch 2 unavailable")}</h2>
      <p>Starting cash · ${escapeHtml(program.starting_cash_usdt || "NOT MEASURED")} USDT</p>
    </article>
    <article class="panel">
      <span class="eyebrow">VAULT ARCHITECTURE</span>
      <div class="truth-table">
        ${allocations.map((item) =>
          `<div class="truth-row"><span>${escapeHtml(item.vault_id)}</span><strong>${escapeHtml(item.starting_cash_usdt)} USDT</strong></div>`
        ).join("") || '<div class="truth-row"><span>Vault evidence</span><strong>UNAVAILABLE</strong></div>'}
      </div>
    </article>
    <article class="panel">
      <span class="eyebrow">RUNTIME BINDING</span>
      <h2>${escapeHtml(binding.activation_status || "NOT VERIFIED")}</h2>
      <p>${binding.ledger_present ? "Epoch ledger file is present." : "Ledger presence is not verified on this runtime."}</p>
    </article>
    <article class="panel">
      <span class="eyebrow">AUTHORITY</span>
      <h2 class="safe-text">REAL_CAPITAL=${escapeHtml(program.real_capital ?? 0)}</h2>
      <p>Leverage · ${program.leverage_allowed === false ? "DISABLED" : "NOT VERIFIED"}</p>
    </article>`;
}

function renderPaper() {
  const data = state.paper;
  if (!data) return;
  const navNode = byId("metricPaperNav");
  const noteNode = byId("metricPaperNavNote");
  if (!navNode || !noteNode) return;

  if (data.status !== "ready" || !data.snapshot) {
    navNode.textContent = "UNAVAILABLE";
    noteNode.textContent = text(data.reason, "runtime evidence unavailable");
    return;
  }

  const snapshot = data.snapshot;
  const nav =
    snapshot.nav_usdt ??
    snapshot.total_nav_usdt ??
    snapshot.portfolio?.nav_usdt ??
    snapshot.performance?.nav_usdt ??
    null;

  if (nav === null) {
    navNode.textContent = "NOT EXPOSED";
    noteNode.textContent = "mission-control payload has no verified NAV field";
  } else {
    navNode.textContent = `${nav} USDT`;
    noteNode.textContent = "read-only paper runtime evidence";
  }
}

function proofCategory(item) {
  const outcome = item?.latest_outcome;
  if (!outcome) return "unresolved";
  const value = text(
    outcome.outcome_state ?? outcome.state ?? outcome.resolution_status,
    ""
  ).toLowerCase();
  if (value.includes("success") || value.includes("hit_target")) return "winner";
  if (value.includes("fail_sl")) return "loser";
  if (value.includes("expired") || value.includes("timeout")) return "expired";
  if (value.includes("invalid")) return "invalidated";
  if (value.includes("ambiguous")) return "ambiguous";
  if (value.includes("not_evaluable") || value.includes("cancel")) return "not_evaluable";
  return "unresolved";
}

function renderArchive() {
  const target = byId("archiveWall");
  if (!target || !state.archive) return;
  let rows = Array.isArray(state.archive.items) ? state.archive.items : [];
  rows = rows.filter((item) => signalMatchesAsset(item.signal || {}));
  if (state.proofFilter !== "all") {
    rows = rows.filter((item) => proofCategory(item) === state.proofFilter);
  }

  if (!rows.length) {
    target.className = "proof-grid empty-state";
    target.innerHTML =
      "<strong>Bu filtre için proof kaydı yok.</strong>" +
      "<p>Boş arşiv sonucu performans iddiası değildir.</p>";
    return;
  }

  target.className = "proof-grid";
  target.innerHTML = rows.map((item) => {
    const signal = item.signal || {};
    const category = proofCategory(item);
    const outcome = item.latest_outcome || {};
    return `
      <article class="proof-card">
        <div class="proof-card-head">
          <strong>${escapeHtml(signal.symbol || "UNKNOWN")} · ${escapeHtml(signal.timeframe || "—")}</strong>
          <span class="${stateClass(category)}">${escapeHtml(upper(category))}</span>
        </div>
        <div class="feed-item-meta">
          <span>issued ${escapeHtml(formatTime(signal.frozen_at_ms || signal.as_of_ms))}</span>
          <span>${escapeHtml(upper(signal.state))}</span>
          <span>outcome ${escapeHtml(outcome.outcome_state || outcome.state || "UNRESOLVED")}</span>
          <code>${escapeHtml(shortIdentity(signal.signal_freeze_identity))}</code>
        </div>
      </article>`;
  }).join("");
}

function renderEducation() {
  const target = byId("learnGrid");
  if (!target || !state.education) return;
  const lessons = Array.isArray(state.education.lessons) ? state.education.lessons : [];
  if (!lessons.length) {
    target.className = "learn-grid empty-state";
    target.innerHTML = "<strong>Eğitim evidence yok.</strong><p>Konsept açıklaması uydurulmaz.</p>";
    return;
  }
  target.className = "learn-grid";
  target.innerHTML = lessons.map((lesson) => `
    <article class="learn-card">
      <span class="eyebrow">${escapeHtml(lesson.concept_id)}</span>
      <strong>${escapeHtml(lesson.title_tr)}</strong>
      <p>${escapeHtml(lesson.beginner_tr)}</p>
    </article>`).join("");
}

function renderIntelligence() {
  const target = byId("intelligenceTruth");
  if (!target) return;
  if (!state.intelligence) {
    target.textContent = "Intelligence endpoint evidence is unavailable.";
    return;
  }
  const statusLabel = upper(state.intelligence.status, "READY");
  if (state.explainMode === "simple") {
    target.textContent =
      `SIMPLE · intelligence endpoint status ${statusLabel}. ` +
      "Bu foundation slice accepted research truth’un varlığını gösterir; daha güçlü bir sonuç uydurmaz.";
  } else {
    const keys = Object.keys(state.intelligence).sort();
    target.textContent =
      `PRO · endpoint fields: ${keys.join(", ") || "none"}. ` +
      "R23 Decision Proof adapter sonraki product slice’ında exact evidence identities ile bağlanacak.";
  }
}

function renderSystem() {
  const api = byId("systemApi");
  const ledger = byId("systemLedger");
  if (api) api.textContent = state.health ? upper(state.health.status, "READY") : "UNAVAILABLE";
  if (ledger) ledger.textContent = state.health?.ledger_present ? "PRESENT" : "NOT PRESENT";
}

function renderAll() {
  renderCommand();
  renderRadar();
  renderMarketTruth();
  renderEpoch();
  renderPaper();
  renderArchive();
  renderEducation();
  renderIntelligence();
  renderSystem();
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
    loadEndpoint("paper", API.paper),
    loadEndpoint("archive", API.archive),
    loadEndpoint("education", API.education),
    loadEndpoint("intelligence", API.intelligence),
  ]);

  const marketReady = results.some(
    (result) => result.ok && ["command", "radar"].includes(result.key)
  );
  setBoot(
    "bootMarket",
    marketReady ? "EVIDENCE API READY" : "NOT VERIFIED",
    marketReady ? "ready" : "muted"
  );

  renderAll();

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

function startPeriodicRefresh() {
  window.setInterval(async () => {
    if (document.visibilityState !== "visible") return;
    const results = await Promise.all([
      loadEndpoint("health", API.health),
      loadEndpoint("command", API.command),
      loadEndpoint("radar", API.radar),
      loadEndpoint("paper", API.paper),
      loadEndpoint("archive", API.archive),
    ]);
    if (results[0].ok) applyHealthTruth(results[0].data);
    renderAll();
    if (!results.slice(1).every((item) => item.ok)) {
      setTruthChip("freshnessTruth", "FRESHNESS · PARTIAL EVIDENCE", "muted");
    }
  }, 30_000);
}

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  renderSystem();
  void runBoot().then(startPeriodicRefresh);
});
