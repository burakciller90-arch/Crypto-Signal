const $ = (selector) => document.querySelector(selector);

let navigationContexts = [];
let selectedEvidenceClass = null;
let performanceData = null;

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
  recent.innerHTML = data.recent_signals?.length
    ? data.recent_signals.map(signalRow).join("")
    : '<div class="performance-empty">No frozen signals are available.</div>';
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

function optionMarkup(values, selected) {
  return values
    .map((value) => `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(value)}</option>`)
    .join("");
}

function configureNavigation(data) {
  navigationContexts = data.status === "ready" ? data.contexts : [];
  const symbolSelect = $("#symbolSelect");
  const timeframeSelect = $("#timeframeSelect");
  const providerSelect = $("#providerSelect");

  if (!navigationContexts.length) {
    symbolSelect.innerHTML = "<option>No symbols</option>";
    timeframeSelect.innerHTML = "<option>No timeframes</option>";
    providerSelect.innerHTML = '<option value="all">All providers</option>';
    return;
  }

  const symbols = [...new Set(navigationContexts.map((item) => item.symbol))];
  const symbol = symbols.includes(symbolSelect.value) ? symbolSelect.value : symbols[0];
  symbolSelect.innerHTML = optionMarkup(symbols, symbol);

  const timeframes = [...new Set(
    navigationContexts.filter((item) => item.symbol === symbol).map((item) => item.timeframe)
  )];
  const timeframe = timeframes.includes(timeframeSelect.value)
    ? timeframeSelect.value
    : timeframes[0];
  timeframeSelect.innerHTML = optionMarkup(timeframes, timeframe);

  const providers = [...new Set(
    navigationContexts
      .filter((item) => item.symbol === symbol && item.timeframe === timeframe)
      .map((item) => item.exchange)
  )];
  const provider = providers.includes(providerSelect.value) ? providerSelect.value : "all";
  providerSelect.innerHTML =
    '<option value="all">All providers</option>' + optionMarkup(providers, provider);
  providerSelect.value = provider;
}

async function loadSelectedAsset() {
  if (!navigationContexts.length) {
    $("#assetCockpit").innerHTML =
      '<div class="performance-empty">No navigation context available.</div>';
    return;
  }
  const symbol = $("#symbolSelect").value;
  const timeframe = $("#timeframeSelect").value;
  const provider = $("#providerSelect").value;
  const asset = await fetchJSON(
    `/api/assets/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}?recent_limit=24`
  );
  renderAsset(asset, provider);
}

function renderAsset(data, provider = "all") {
  $("#assetTitle").textContent = `${data.symbol} · ${data.timeframe}`;
  const root = $("#assetCockpit");
  if (data.status !== "ready" || !data.latest_by_provider?.length) {
    root.innerHTML = `<div class="performance-empty">Asset Cockpit: ${esc(human(data.status))}.</div>`;
    return;
  }
  const cards = provider === "all"
    ? data.latest_by_provider
    : data.latest_by_provider.filter((card) => card.exchange === provider);

  root.innerHTML = cards.length
    ? cards.map((card) => `
      <div class="asset-row" data-signal-id="${esc(card.signal_freeze_identity)}">
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
    `).join("")
    : '<div class="performance-empty">No frozen signal for the selected provider.</div>';
}

function renderPerformanceGroup(group) {
  if (!group.segments?.length) {
    return '<div class="performance-empty">No evaluated segments for this horizon.</div>';
  }
  return group.segments.map((segment) => {
    const key = segment.key;
    const frequency = segment.historical_success_fraction === null
      ? "—"
      : segment.historical_success_fraction;
    return `
      <div class="performance-segment">
        <div class="row-title">${esc(key.symbol)} · ${esc(key.timeframe)} · ${esc(human(key.setup_type))}</div>
        <div class="row-sub">${esc(human(key.signal_direction))} · ${esc(human(key.confluence_score_bucket))} · horizon ${esc(group.max_holding_bars)} bars</div>
        <div class="performance-grid">
          <div class="performance-stat"><div class="value-label">Decisive N</div><strong>${esc(segment.decisive_n)}</strong></div>
          <div class="performance-stat"><div class="value-label">Historical success fraction</div><strong>${esc(frequency)}</strong><div class="row-sub">descriptive frequency, not probability</div></div>
          <div class="performance-stat"><div class="value-label">R-evaluable N</div><strong>${esc(segment.r_evaluable_n)}</strong></div>
          <div class="performance-stat"><div class="value-label">Average shadow R</div><strong>${esc(segment.average_r ?? "—")}</strong></div>
          <div class="performance-stat"><div class="value-label">Cumulative shadow R</div><strong>${esc(segment.cumulative_r ?? "—")}</strong></div>
          <div class="performance-stat"><div class="value-label">Max drawdown R</div><strong>${esc(segment.max_drawdown_r ?? "—")}</strong></div>
        </div>
        <div class="truth-note">
          Stored snapshots: ${esc(group.stored_snapshot_count)} · latest-per-signal used: ${esc(group.selected_latest_signal_count)} · promotion policy eligible: ${esc(segment.promotion_eligible)}
        </div>
      </div>`;
  }).join("");
}

function renderPerformance(data) {
  performanceData = data;
  const root = $("#performance");
  const tabs = $("#performanceTabs");

  if (data.status === "ready" && data.groups?.length) {
    const classes = [...new Set(data.groups.map((group) => group.evidence_class))];
    if (!selectedEvidenceClass || !classes.includes(selectedEvidenceClass)) {
      selectedEvidenceClass = classes[0];
    }
    tabs.classList.remove("hidden");
    tabs.innerHTML = classes.map((name) => `
      <button class="evidence-tab ${name === selectedEvidenceClass ? "active" : ""}"
              data-evidence-class="${esc(name)}" type="button">
        ${esc(human(name))}
      </button>
    `).join("");

    const groups = data.groups.filter((group) => group.evidence_class === selectedEvidenceClass);
    const count = data.evidence_class_counts.find(
      (item) => item.evidence_class === selectedEvidenceClass
    );
    root.innerHTML = `
      <div class="small-label">Explicit outcome evidence</div>
      <div class="performance-count">${esc(count?.count ?? 0)}</div>
      <div class="truth-note">Evidence class: ${esc(human(selectedEvidenceClass))}. Holding horizons remain separate.</div>
      ${groups.map(renderPerformanceGroup).join("")}
      <div class="truth-note">Historical frequency, confluence score and calibrated probability remain separate concepts.</div>`;

    tabs.querySelectorAll("[data-evidence-class]").forEach((node) => {
      node.addEventListener("click", () => {
        selectedEvidenceClass = node.dataset.evidenceClass;
        renderPerformance(performanceData);
      });
    });
    return;
  }

  tabs.classList.add("hidden");
  tabs.innerHTML = "";
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

function deliveryMarkup(event) {
  if (!event.delivery_states?.length) {
    return '<span class="delivery-pill delivery-pending">pending · no delivery attempt</span>';
  }
  return event.delivery_states.map((item) => `
    <span class="delivery-pill delivery-${esc(item.latest_status)}">
      ${esc(item.sink_id)} · ${esc(human(item.latest_status))} · attempts ${esc(item.attempts)}
    </span>
  `).join("");
}

function renderAlertCenter(data) {
  $("#alertCount").textContent = `${data.total_count ?? 0} events`;
  const root = $("#alertCenter");

  if (data.status === "empty") {
    root.innerHTML = `
      <div class="performance-empty">
        No eligible alert events yet. Under the default policy, WATCH does not notify.
        ACTIVE creation and INVALIDATED lifecycle transitions are eligible.
      </div>`;
    return;
  }
  if (data.status !== "ready") {
    root.innerHTML = `
      <div class="performance-empty">
        Alert outbox status: ${esc(human(data.status))}. No alert is inferred.
      </div>`;
    return;
  }

  root.innerHTML = data.events.map((event) => `
    <div class="alert-row" data-signal-id="${esc(event.signal_freeze_identity)}">
      <div>
        <div class="row-title">${esc(event.exchange.toUpperCase())} · ${esc(event.symbol)}</div>
        <div class="row-sub">${esc(event.timeframe)} · ${esc(human(event.source_kind))} · ${esc(fmtTime(event.appended_at_ms))}</div>
      </div>
      <div>
        <div class="value-label">Signal state</div>
        <div class="state-pill ${stateClass(event.signal_state)}">${esc(human(event.signal_state))}</div>
      </div>
      <div>
        <div class="value-label">Direction / agreement</div>
        <div class="value-main ${directionClass(event.direction)}">${esc(human(event.direction))}</div>
        <div class="row-sub">${esc(event.confluence_score)} · not probability</div>
      </div>
      <div>
        <div class="value-label">Delivery</div>
        <div class="delivery-list">${deliveryMarkup(event)}</div>
      </div>
      <div class="notification-preview">
        <div class="value-label">Canonical notification preview</div>
        <div class="row-title">${esc(event.notification_title)}</div>
        <div class="truth-note">${esc(event.notification_body).replaceAll("\n", "<br>")}</div>
      </div>
    </div>
  `).join("");
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

function renderEvidenceItem(item) {
  const summaries = item.evidence_summary?.length
    ? item.evidence_summary.map((entry) => `<span class="evidence-badge">${esc(entry)}</span>`).join("")
    : '<span class="evidence-badge">no summary</span>';
  const flags = [
    ...(item.ambiguity_flags ?? []).map((flag) => `ambiguity: ${flag}`),
    ...(item.contradiction_flags ?? []).map((flag) => `contradiction: ${flag}`),
  ];
  return `
    <div class="evidence-item">
      <div class="row-title">${esc(human(item.setup_type))} · ${esc(human(item.direction))}</div>
      <div class="row-sub">${esc(human(item.validity))} · observed ${esc(fmtTime(item.observed_at_ms))}</div>
      <div class="evidence-badges">${summaries}</div>
      ${flags.length ? `<div class="truth-note">${esc(flags.join(" · "))}</div>` : ""}
      ${item.key_levels?.length ? `<div class="truth-note">Levels: ${item.key_levels.map((level) => `${esc(level.label)}=${esc(level.price)}`).join(" · ")}</div>` : ""}
      ${item.metrics?.length ? `<div class="truth-note">Metrics: ${item.metrics.map((metric) => `${esc(metric.name)}=${esc(metric.value)} ${esc(metric.unit)}`).join(" · ")}</div>` : ""}
    </div>`;
}

function renderMethodologies(detail) {
  if (!detail.methodologies?.length) {
    return '<div class="performance-empty">No methodology selection snapshot.</div>';
  }
  return `<div class="methodology-grid">${detail.methodologies.map((method) => `
    <div class="methodology-card">
      <div class="methodology-head">
        <div>
          <div class="row-title">${esc(human(method.methodology))}</div>
          <div class="row-sub">source N=${esc(method.source_count)} · selected N=${esc(method.selected_count)}</div>
        </div>
        <div class="state-pill">${esc(human(method.resolved_direction))}</div>
      </div>
      <div class="truth-note">Internal conflict: ${esc(method.has_internal_direction_conflict)}</div>
      ${method.selected?.length
        ? method.selected.map(renderEvidenceItem).join("")
        : '<div class="performance-empty">No selected evidence at the frozen frontier.</div>'}
    </div>
  `).join("")}</div>`;
}

function renderAgreement(detail) {
  if (!detail.pairwise_relations?.length) {
    return '<div class="performance-empty">No pairwise agreement rows.</div>';
  }
  return `<div class="agreement-list">${detail.pairwise_relations.map((item) => `
    <div class="agreement-row">
      <span>${esc(human(item.left))} · ${esc(human(item.left_direction))}</span>
      <span>${esc(human(item.relation))}</span>
      <span>${esc(human(item.right))} · ${esc(human(item.right_direction))}</span>
    </div>
  `).join("")}</div>`;
}

function renderGeometry(geometry) {
  if (!geometry) {
    return '<div class="performance-empty">No complete frozen entry/invalidation/target geometry. Signal cannot be presented as an executable setup.</div>';
  }
  return `
    <div class="detail-grid">
      <div class="detail-item"><div class="value-label">Entry zone</div><div class="value-main">${esc(geometry.entry_zone_low)} — ${esc(geometry.entry_zone_high)}</div></div>
      <div class="detail-item"><div class="value-label">Reference entry</div><div class="value-main">${esc(geometry.entry_reference_price)}</div><div class="row-sub">${esc(human(geometry.entry_reference_model))}</div></div>
      <div class="detail-item"><div class="value-label">Invalidation</div><div class="value-main">${esc(geometry.invalidation_price)}</div><div class="row-sub">${esc(human(geometry.invalidation_trigger))}</div></div>
      <div class="detail-item"><div class="value-label">Source method</div><div class="value-main">${esc(human(geometry.source_methodology))}</div></div>
    </div>
    <div class="truth-note">Targets: ${geometry.targets.map((target) => `${esc(target.label)}=${esc(target.target_price)} (${esc(target.reference_rr)}R reference)`).join(" · ")}</div>`;
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
      <div class="value-label">Evidence / uncertainty</div>
      <div class="truth-note">${esc(detail.evidence_summary?.length ? detail.evidence_summary.join(" · ") : "no evidence summary")}</div>
      <div class="truth-note">${esc(card.uncertainty_flags?.length ? card.uncertainty_flags.join(" · ") : "no uncertainty flags")}</div>
    </div>
    <div class="detail-item">
      <div class="value-label">Frozen candle coverage</div>
      <div class="value-main">${esc(detail.candle_count)} candles</div>
      <div class="row-sub">${esc(fmtTime(detail.first_candle_open_time_ms))} → ${esc(fmtTime(detail.last_candle_open_time_ms))}</div>
    </div>
    <div class="detail-item"><div class="value-label">Methodology evidence</div>${renderMethodologies(detail)}</div>
    <div class="detail-item"><div class="value-label">Agreement matrix</div>${renderAgreement(detail)}</div>
    <div class="detail-item"><div class="value-label">Frozen geometry</div>${renderGeometry(detail.geometry)}</div>
    <div class="detail-item"><div class="value-label">Evidence-class status</div><div class="value-main">${esc(human(card.evidence_class_status))}</div></div>
    <div class="detail-item"><div class="value-label">Signal freeze identity</div><div class="mono">${esc(card.signal_freeze_identity)}</div></div>
    <div class="detail-item"><div class="value-label">Bundle identity</div><div class="mono">${esc(card.bundle_identity)}</div></div>`;
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
  const [health, command, radar, navigation, archive, performance, alerts] = await Promise.all([
    fetchJSON("/api/health"),
    fetchJSON("/api/command-center?recent_limit=8"),
    fetchJSON("/api/market-radar"),
    fetchJSON("/api/navigation"),
    fetchJSON("/api/signals?limit=50&offset=0"),
    fetchJSON("/api/performance"),
    fetchJSON("/api/alerts?limit=50"),
  ]);

  $("#healthChip").textContent = health.ledger_present ? "Ledger connected" : "Ledger absent";
  renderCommandCenter(command);
  renderRadar(radar);
  renderArchive(archive);
  renderPerformance(performance);
  renderAlertCenter(alerts);
  configureNavigation(navigation);
  await loadSelectedAsset();
  bindSignalClicks();
}

$("#symbolSelect").addEventListener("change", () => {
  configureNavigation({ status: navigationContexts.length ? "ready" : "empty", contexts: navigationContexts });
  loadSelectedAsset().then(bindSignalClicks).catch(showError);
});
$("#timeframeSelect").addEventListener("change", () => {
  configureNavigation({ status: navigationContexts.length ? "ready" : "empty", contexts: navigationContexts });
  loadSelectedAsset().then(bindSignalClicks).catch(showError);
});
$("#providerSelect").addEventListener("change", () => {
  loadSelectedAsset().then(bindSignalClicks).catch(showError);
});
$("#refreshButton").addEventListener("click", () => loadAll().catch(showError));
$("#closeDialog").addEventListener("click", () => $("#signalDialog").close());

loadAll().catch(showError);
