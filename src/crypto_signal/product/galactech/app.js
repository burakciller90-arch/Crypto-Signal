"use strict";

const API = Object.freeze({
  health: "/api/health",
  command: "/api/command-center?recent_limit=12",
  radar: "/api/market-radar",
  epoch: "/api/paper/epoch-contract",
  paper: "/api/paper/mission-control",
  epoch2State: "/api/paper/epoch2-state",
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
  epoch2State: null,
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

  document.addEventListener("click", (event) => {
    const source = event.target instanceof Element ? event.target : null;
    const evidenceTrigger = source?.closest("[data-evidence-id]");
    if (evidenceTrigger instanceof HTMLElement) {
      const identity = evidenceTrigger.dataset.evidenceId || "";
      void openEvidenceRoom(identity, evidenceTrigger);
      return;
    }

    const learnTrigger = source?.closest("[data-evidence-learn]");
    if (learnTrigger) {
      closeEvidenceRoom();
      routeTo("learn");
    }
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
      <button class="evidence-trigger" type="button"
        data-evidence-id="${escapeHtml(signal.signal_freeze_identity)}"
        aria-label="${escapeHtml(signal.symbol || "UNKNOWN")} archive evidence aç">
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
            <span class="evidence-open-cue">Frozen proof →</span>
          </div>
        </article>
      </button>`;
  }).join("");
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
          <button type="button" data-evidence-learn="true">OPEN LEARN CENTER →</button>
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
    const detail = await fetchJson(API.signalDetail(identity));
    state.evidenceDetail = detail;
    renderEvidenceRoom(detail);
  } catch (error) {
    console.warn("[GALACTECH] signal detail unavailable", error);
    renderEvidenceRoom({ status: "unavailable", signal: null });
  }
}

function closeEvidenceRoom() {
  const dialog = byId("evidenceDialog");
  if (!dialog) return;
  if (typeof dialog.close === "function" && dialog.open) dialog.close();
  else dialog.removeAttribute("open");
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
