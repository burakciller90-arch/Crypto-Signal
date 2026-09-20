const $ = (selector) => document.querySelector(selector);

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtTime(ms) {
  if (ms === null || ms === undefined) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(Number(ms)));
}

function human(value) {
  return String(value ?? "—").replaceAll("_", " ");
}

function stateClass(state) {
  return state === "active" ? "state-active" : state === "watch" ? "state-watch" : "";
}

function directionClass(direction) {
  return direction === "bullish"
    ? "direction-bullish"
    : direction === "bearish"
      ? "direction-bearish"
      : "";
}

async function fetchJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${path}: HTTP ${response.status} ${body}`);
  }
  return response.json();
}

function showNotice(message) {
  const notice = $("#dataNotice");
  notice.textContent = message;
  notice.classList.remove("hidden");
}

function clearNotice() {
  $("#dataNotice").classList.add("hidden");
}

function renderMix(items) {
  if (!items?.length) return "No observations";
  return items.map(([name, count]) => `${human(name)} ${count}`).join(" · ");
}

function signalRow(card) {
  return `
    <div class="signal-row" data-signal-id="${esc(card.signal_freeze_identity)}">
      <div>
        <div class="row-title">${esc(card.exchange.toUpperCase())} · ${esc(card.symbol)}</div>
        <div class="row-sub">${esc(card.timeframe)} · ${esc(fmtTime(card.frozen_at_ms))}</div>
      </div>
      <div>
        <div class="value-label">State</div>
        <div class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</div>
      </div>
      <div>
        <div class="value-label">Direction</div>
        <div class="value-main ${directionClass(card.direction)}">${esc(human(card.direction))}</div>
      </div>
      <div>
        <div class="value-label">Confluence</div>
        <div class="value-main">${esc(card.confluence_score)}</div>
        <div class="row-sub">agreement index, not probability</div>
      </div>
    </div>`;
}

function renderCommandCenter(data) {
  if (data.status !== "ready") {
    showNotice(`Command Center data status: ${human(data.status)}.`);
  }
  $("#freezeCount").textContent = String(data.freeze_count ?? 0);
  $("#latestFreeze").textContent = fmtTime(data.latest_frozen_at_ms);
  $("#stateMix").textContent = renderMix(data.state_counts);
  $("#directionMix").textContent = renderMix(data.direction_counts);

  const recent = $("#recentSignals");
  if (!data.recent_signals?.length) {
    recent.innerHTML = '<div class="performance-empty">No frozen signals are available.</div>';
  } else {
    recent.innerHTML = data.recent_signals.map(signalRow).join("");
  }
}

function renderRadar(data) {
  const root = $("#radarList");
  if (data.status !== "ready" || !data.items?.length) {
    root.innerHTML = `<div class="performance-empty">Market Radar: ${esc(human(data.status))}.</div>`;
    return;
  }
  root.innerHTML = data.items.map((item) => `
    <div class="radar-row">
      <div>
        <div class="row-title">${esc(item.exchange.toUpperCase())} · ${esc(item.symbol)}</div>
        <div class="row-sub">${esc(item.market_type)} · ${esc(item.timeframe)}</div>
      </div>
      <div>
        <div class="value-label">State</div>
        <div class="state-pill ${stateClass(item.latest.state)}">${esc(human(item.latest.state))}</div>
      </div>
      <div>
        <div class="value-label">Direction</div>
        <div class="value-main ${directionClass(item.latest.direction)}">${esc(human(item.latest.direction))}</div>
      </div>
      <div>
        <div class="value-label">Confluence</div>
        <div class="value-main">${esc(item.latest.confluence_score)}</div>
        <div class="row-sub">not probability</div>
      </div>
    </div>
  `).join("");
}

function renderAsset(data) {
  $("#assetTitle").textContent = `${data.symbol} · ${data.timeframe}`;
  const root = $("#assetCockpit");
  if (data.status !== "ready" || !data.latest_by_provider?.length) {
    root.innerHTML = `<div class="performance-empty">Asset Cockpit: ${esc(human(data.status))}.</div>`;
    return;
  }
  root.innerHTML = data.latest_by_provider.map((card) => `
    <div class="asset-row">
      <div>
        <div class="value-label">Provider</div>
        <div class="row-title">${esc(card.exchange.toUpperCase())}</div>
      </div>
      <div>
        <div class="value-label">Frozen state</div>
        <div class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</div>
      </div>
      <div>
        <div class="value-label">Agreement index</div>
        <div class="value-main">${esc(card.confluence_score)}</div>
        <div class="row-sub">${esc(card.probability_status)}</div>
      </div>
    </div>
  `).join("");
}

function renderPerformance(data) {
  const root = $("#performance");
  if (data.status === "ready") {
    const counts = data.evidence_class_counts
      .map((item) => `${human(item.evidence_class)}: ${item.count}`)
      .join(" · ");
    root.innerHTML = `
      <div class="small-label">Outcome snapshots</div>
      <div class="performance-count">${esc(data.outcome_snapshot_count)}</div>
      <div class="truth-note">${esc(counts)}</div>
      <div class="truth-note">Evidence classes stay separate. Historical frequency is not calibrated probability.</div>`;
    return;
  }
  if (data.status === "empty") {
    root.innerHTML = `
      <div class="small-label">Outcome evidence</div>
      <div class="performance-count">0</div>
      <div class="performance-empty">
        No explicit outcome snapshots yet. This is an empty evidence set—not a 0% win rate.
      </div>`;
    return;
  }
  root.innerHTML = `
    <div class="performance-empty">
      Performance data status: ${esc(human(data.status))}. No metric is inferred.
    </div>`;
}

function renderArchive(data) {
  $("#archiveCount").textContent = `${data.total_count ?? 0} frozen`;
  const body = $("#archiveBody");
  if (!data.signals?.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty-cell">No immutable signals available.</td></tr>';
    return;
  }
  body.innerHTML = data.signals.map((card) => `
    <tr data-signal-id="${esc(card.signal_freeze_identity)}">
      <td>${esc(fmtTime(card.frozen_at_ms))}</td>
      <td><strong>${esc(card.exchange.toUpperCase())}</strong> · ${esc(card.symbol)} · ${esc(card.timeframe)}</td>
      <td><span class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</span></td>
      <td class="${directionClass(card.direction)}">${esc(human(card.direction))}</td>
      <td>${esc(card.confluence_score)}<div class="row-sub">agreement index</div></td>
      <td>${esc(human(card.probability_status))}</td>
      <td>${esc(human(card.setup_type))}</td>
    </tr>
  `).join("");
}

async function openSignal(signalId) {
  const detail = await fetchJSON(`/api/signals/${encodeURIComponent(signalId)}`);
  if (detail.status !== "ready" || !detail.signal) {
    showNotice(`Signal detail status: ${human(detail.status)}.`);
    return;
  }
  const card = detail.signal;
  $("#dialogTitle").textContent = `${card.exchange.toUpperCase()} · ${card.symbol} · ${card.timeframe}`;
  $("#dialogBody").innerHTML = `
    <div class="detail-grid">
      <div class="detail-item"><div class="value-label">State</div><div class="value-main">${esc(human(card.state))}</div></div>
      <div class="detail-item"><div class="value-label">Direction</div><div class="value-main ${directionClass(card.direction)}">${esc(human(card.direction))}</div></div>
      <div class="detail-item"><div class="value-label">Confluence</div><div class="value-main">${esc(card.confluence_score)}</div><div class="row-sub">${esc(card.confluence_score_semantic)}</div></div>
      <div class="detail-item"><div class="value-label">Probability</div><div class="value-main">${esc(human(card.probability_status))}</div></div>
      <div class="detail-item"><div class="value-label">Decision as-of</div><div class="value-main">${esc(fmtTime(card.as_of_ms))}</div></div>
      <div class="detail-item"><div class="value-label">Frozen at</div><div class="value-main">${esc(fmtTime(card.frozen_at_ms))}</div></div>
    </div>
    <div class="detail-item">
      <div class="value-label">Evidence-class status</div>
      <div class="value-main">${esc(human(card.evidence_class_status))}</div>
    </div>
    <div class="detail-item">
      <div class="value-label">Signal freeze identity</div>
      <div class="mono">${esc(card.signal_freeze_identity)}</div>
    </div>
    <div class="detail-item">
      <div class="value-label">Bundle identity</div>
      <div class="mono">${esc(card.bundle_identity)}</div>
    </div>
    <div class="detail-item">
      <div class="value-label">Uncertainty flags</div>
      <div class="truth-note">${esc(card.uncertainty_flags?.length ? card.uncertainty_flags.join(" · ") : "none")}</div>
    </div>`;
  $("#signalDialog").showModal();
}

function bindSignalClicks() {
  document.querySelectorAll("[data-signal-id]").forEach((node) => {
    node.addEventListener("click", () => openSignal(node.dataset.signalId).catch(showError));
  });
}

function showError(error) {
  console.error(error);
  showNotice(`Read-only dashboard error: ${error.message}`);
  $("#healthChip").textContent = "Read error";
}

async function loadAll() {
  clearNotice();
  const [health, command, radar, archive, performance] = await Promise.all([
    fetchJSON("/api/health"),
    fetchJSON("/api/command-center?recent_limit=8"),
    fetchJSON("/api/market-radar"),
    fetchJSON("/api/signals?limit=50&offset=0"),
    fetchJSON("/api/performance"),
  ]);

  $("#healthChip").textContent = health.ledger_present ? "Ledger connected" : "Ledger absent";
  renderCommandCenter(command);
  renderRadar(radar);
  renderArchive(archive);
  renderPerformance(performance);

  if (radar.items?.length) {
    const first = radar.items[0];
    const asset = await fetchJSON(
      `/api/assets/${encodeURIComponent(first.symbol)}/${encodeURIComponent(first.timeframe)}?recent_limit=12`
    );
    renderAsset(asset);
  } else {
    $("#assetCockpit").innerHTML = '<div class="performance-empty">No radar context available.</div>';
  }

  bindSignalClicks();
}

$("#refreshButton").addEventListener("click", () => loadAll().catch(showError));
$("#closeDialog").addEventListener("click", () => $("#signalDialog").close());

loadAll().catch(showError);
