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

const LABELS = {
  active: "Aktif Sinyal",
  watch: "İzleniyor",
  neutral: "Nötr",
  no_signal: "Sinyal Yok",
  invalidated: "Geçersizleşti",
  bullish: "Yükseliş",
  bearish: "Düşüş",
  none: "Yönsüz",
  unresolved: "Çözümlenmedi",
  not_calibrated: "Kalibre edilmedi",
  agreement_index_not_probability: "uyum endeksi · olasılık değil",
  retrospective: "Geriye dönük",
  walk_forward: "İleri yürüyen",
  live_untouched_forward: "Dokunulmamış canlı ileri",
  delivered: "Teslim edildi",
  retryable_failure: "Yeniden denenecek",
  permanent_failure: "Kalıcı hata",
  insufficient: "Yetersiz kanıt",
  agree: "Uyumlu",
  contradict: "Çelişkili",
  internal_ambiguity: "İç belirsizlik",
  price_action: "Price Action",
  harmonic: "Harmonic",
  elliott: "Elliott",
};

function fmtTime(ms) {
  if (ms === null || ms === undefined) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(Number(ms)));
}

function human(value) {
  const key = String(value ?? "");
  if (!key) return "—";
  return LABELS[key] ?? key.replaceAll("_", " ");
}

function stateClass(state) {
  if (state === "active") return "state-active";
  if (state === "watch") return "state-watch";
  if (state === "neutral") return "state-neutral";
  if (state === "invalidated") return "state-invalidated";
  return "";
}

function directionClass(direction) {
  return direction === "bullish"
    ? "direction-bullish"
    : direction === "bearish"
      ? "direction-bearish"
      : "";
}

function agreementStrength(score) {
  const value = Math.abs(Number(score ?? 0));
  if (value >= 66.67) return "Güçlü uyum";
  if (value >= 33.33) return "Kısmi uyum";
  return "Uyum yok";
}

function providerConsensus(cards) {
  const directions = [...new Set(cards.map((card) => card.latest.direction).filter((x) => x && x !== "none"))];
  if (!directions.length) return "Yön sinyali yok";
  if (directions.length === 1 && cards.length > 1) return "Sağlayıcılar aynı yönde";
  if (directions.length === 1) return "Tek sağlayıcı kanıtı";
  return "Sağlayıcılar ayrışıyor";
}

function attentionRank(item) {
  const state = item.latest.state === "active" ? 300 : item.latest.state === "watch" ? 200 : 100;
  const agreement = Math.abs(Number(item.latest.confluence_score ?? 0));
  const timeframe = item.timeframe === "4h" ? 30 : item.timeframe === "1h" ? 20 : 10;
  return state + agreement + timeframe;
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
  if (!items?.length) return "Gözlem yok";
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
        <div class="value-label">Durum</div>
        <div class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</div>
      </div>
      <div>
        <div class="value-label">Yön</div>
        <div class="value-main ${directionClass(card.direction)}">${esc(human(card.direction))}</div>
      </div>
      <div>
        <div class="value-label">Metodoloji uyumu</div>
        <div class="value-main">${esc(card.confluence_score)}</div>
        <div class="row-sub">uyum endeksi · olasılık değil</div>
      </div>
    </div>`;
}

function renderCommandCenter(data) {
  if (data.status !== "ready") {
    showNotice(`Komuta Merkezi veri durumu: ${human(data.status)}.`);
  }
  $("#freezeCount").textContent = String(data.freeze_count ?? 0);
  $("#latestFreeze").textContent = fmtTime(data.latest_frozen_at_ms);

  const recent = $("#recentSignals");
  recent.innerHTML = data.recent_signals?.length
    ? data.recent_signals.map(signalRow).join("")
    : '<div class="performance-empty">Henüz dondurulmuş sinyal kaydı yok.</div>';
}

function renderRadar(data) {
  const root = $("#radarList");
  const items = data.status === "ready" ? (data.items ?? []) : [];
  $("#contextCount").textContent = String(items.length);
  $("#attentionCount").textContent = String(
    items.filter((item) => ["watch", "active"].includes(item.latest.state)).length
  );
  $("#strongAgreementCount").textContent = String(
    items.filter((item) => Math.abs(Number(item.latest.confluence_score ?? 0)) >= 66.67).length
  );

  if (!items.length) {
    root.innerHTML = `<div class="performance-empty">Piyasa Radarı: ${esc(human(data.status))}.</div>`;
    return;
  }

  const groups = new Map();
  items.forEach((item) => {
    const key = `${item.symbol}|${item.timeframe}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });

  const ordered = [...groups.values()].sort(
    (left, right) => Math.max(...right.map(attentionRank)) - Math.max(...left.map(attentionRank))
  );

  root.innerHTML = ordered.map((cards) => {
    const lead = [...cards].sort((a, b) => attentionRank(b) - attentionRank(a))[0];
    const providers = cards.map((item) => `
      <div class="provider-proof">
        <span>${esc(item.exchange.toUpperCase())}</span>
        <span class="${directionClass(item.latest.direction)}">${esc(human(item.latest.direction))}</span>
        <span class="state-pill ${stateClass(item.latest.state)}">${esc(human(item.latest.state))}</span>
        <strong>${esc(item.latest.confluence_score)}</strong>
      </div>`).join("");
    const uncertainty = [...new Set(cards.flatMap((item) => item.latest.uncertainty_flags ?? []))];
    return `
      <article class="attention-card ${lead.latest.state === "active" ? "attention-active" : ""}">
        <div class="attention-head">
          <div><div class="attention-symbol">${esc(lead.symbol)}</div><div class="row-sub">${esc(lead.timeframe)} · Spot</div></div>
          <div class="state-pill ${stateClass(lead.latest.state)}">${esc(human(lead.latest.state))}</div>
        </div>
        <div class="attention-direction ${directionClass(lead.latest.direction)}">${esc(human(lead.latest.direction))}</div>
        <div class="attention-summary"><strong>${esc(agreementStrength(lead.latest.confluence_score))}</strong><span>${esc(providerConsensus(cards))}</span></div>
        <div class="provider-proof-list">${providers}</div>
        <div class="truth-note">${uncertainty.length
          ? `Belirsizlik: ${esc(uncertainty.map(human).join(" · "))}`
          : "Belirgin ek belirsizlik bayrağı yok."}</div>
      </article>`;
  }).join("");
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
    symbolSelect.innerHTML = "<option>Varlık yok</option>";
    timeframeSelect.innerHTML = "<option>Zaman dilimi yok</option>";
    providerSelect.innerHTML = '<option value="all">Tüm sağlayıcılar</option>';
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
    '<option value="all">Tüm sağlayıcılar</option>' + optionMarkup(providers, provider);
  providerSelect.value = provider;
}

async function loadSelectedAsset() {
  if (!navigationContexts.length) {
    $("#assetCockpit").innerHTML =
      '<div class="performance-empty">Kullanılabilir piyasa bağlamı yok.</div>';
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
    root.innerHTML = `<div class="performance-empty">Varlık Merkezi: ${esc(human(data.status))}.</div>`;
    return;
  }
  const cards = provider === "all"
    ? data.latest_by_provider
    : data.latest_by_provider.filter((card) => card.exchange === provider);

  root.innerHTML = cards.length
    ? cards.map((card) => `
      <div class="asset-row" data-signal-id="${esc(card.signal_freeze_identity)}">
        <div>
          <div class="value-label">Sağlayıcı</div>
          <div class="row-title">${esc(card.exchange.toUpperCase())}</div>
        </div>
        <div>
          <div class="value-label">Karar durumu</div>
          <div class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</div>
        </div>
        <div>
          <div class="value-label">Metodoloji uyumu</div>
          <div class="value-main">${esc(card.confluence_score)}</div>
          <div class="row-sub">${esc(card.probability_status)}</div>
        </div>
      </div>
    `).join("")
    : '<div class="performance-empty">Seçili sağlayıcı için dondurulmuş karar yok.</div>';
}

function renderPerformanceGroup(group) {
  if (!group.segments?.length) {
    return '<div class="performance-empty">Bu ufuk için değerlendirilmiş segment yok.</div>';
  }
  return group.segments.map((segment) => {
    const key = segment.key;
    const frequency = segment.historical_success_fraction === null
      ? "—"
      : segment.historical_success_fraction;
    return `
      <div class="performance-segment">
        <div class="row-title">${esc(key.symbol)} · ${esc(key.timeframe)} · ${esc(human(key.setup_type))}</div>
        <div class="row-sub">${esc(human(key.signal_direction))} · ${esc(human(key.confluence_score_bucket))} · ufuk ${esc(group.max_holding_bars)} mum</div>
        <div class="performance-grid">
          <div class="performance-stat"><div class="value-label">Kararlı örnek N</div><strong>${esc(segment.decisive_n)}</strong></div>
          <div class="performance-stat"><div class="value-label">Geçmiş başarı frekansı</div><strong>${esc(frequency)}</strong><div class="row-sub">betimleyici frekans · olasılık değil</div></div>
          <div class="performance-stat"><div class="value-label">R değerlendirilebilir N</div><strong>${esc(segment.r_evaluable_n)}</strong></div>
          <div class="performance-stat"><div class="value-label">Ortalama gölge R</div><strong>${esc(segment.average_r ?? "—")}</strong></div>
          <div class="performance-stat"><div class="value-label">Kümülatif gölge R</div><strong>${esc(segment.cumulative_r ?? "—")}</strong></div>
          <div class="performance-stat"><div class="value-label">Maksimum düşüş R</div><strong>${esc(segment.max_drawdown_r ?? "—")}</strong></div>
        </div>
        <div class="truth-note">
          Saklanan gözlem: ${esc(group.stored_snapshot_count)} · sinyal başına kullanılan son kayıt: ${esc(group.selected_latest_signal_count)} · yükseltme politikasına uygun: ${esc(segment.promotion_eligible)}
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
      <div class="small-label">Açık sonuç kanıtı</div>
      <div class="performance-count">${esc(count?.count ?? 0)}</div>
      <div class="truth-note">Kanıt sınıfı: ${esc(human(selectedEvidenceClass))}. Tutma ufukları ayrı değerlendirilir.</div>
      ${groups.map(renderPerformanceGroup).join("")}
      <div class="truth-note">Geçmiş frekans, metodoloji uyumu ve kalibre olasılık birbirinden ayrı kavramlardır.</div>`;

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
      <div class="small-label">Sonuç kanıtı</div>
      <div class="performance-count">0</div>
      <div class="performance-empty">
        Henüz açık sonuç gözlemi yok. Bu boş bir kanıt kümesidir; %0 başarı oranı değildir.
      </div>`;
    return;
  }
  root.innerHTML = `
    <div class="performance-empty">
      Performans veri durumu: ${esc(human(data.status))}. Eksik veriden metrik türetilmez.
    </div>`;
}

function deliveryMarkup(event) {
  if (!event.delivery_states?.length) {
    return '<span class="delivery-pill delivery-pending">bekliyor · teslimat denemesi yok</span>';
  }
  return event.delivery_states.map((item) => `
    <span class="delivery-pill delivery-${esc(item.latest_status)}">
      ${esc(item.sink_id)} · ${esc(human(item.latest_status))} · deneme ${esc(item.attempts)}
    </span>
  `).join("");
}

function renderAlertCenter(data) {
  $("#alertCount").textContent = `${data.total_count ?? 0} olay`;
  const root = $("#alertCenter");

  if (data.status === "empty") {
    root.innerHTML = `
      <div class="performance-empty">
        Henüz bildirime uygun olay yok. Varsayılan politikada “İzleniyor” bildirim üretmez.
        Yeni Aktif Sinyal ve Geçersizleşti geçişleri bildirime uygundur.
      </div>`;
    return;
  }
  if (data.status !== "ready") {
    root.innerHTML = `
      <div class="performance-empty">
        Uyarı kutusu durumu: ${esc(human(data.status))}. Eksik veriden uyarı türetilmez.
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
        <div class="value-label">Sinyal durumu</div>
        <div class="state-pill ${stateClass(event.signal_state)}">${esc(human(event.signal_state))}</div>
      </div>
      <div>
        <div class="value-label">Yön / uyum</div>
        <div class="value-main ${directionClass(event.direction)}">${esc(human(event.direction))}</div>
        <div class="row-sub">${esc(event.confluence_score)} · olasılık değil</div>
      </div>
      <div>
        <div class="value-label">Teslimat</div>
        <div class="delivery-list">${deliveryMarkup(event)}</div>
      </div>
      <div class="notification-preview">
        <div class="value-label">Bildirim önizlemesi</div>
        <div class="row-title">${esc(event.notification_title)}</div>
        <div class="truth-note">${esc(event.notification_body).replaceAll("\n", "<br>")}</div>
      </div>
    </div>
  `).join("");
}

function renderArchive(data) {
  $("#archiveCount").textContent = `${data.total_count ?? 0} kayıt`;
  const body = $("#archiveBody");
  if (!data.signals?.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty-cell">Henüz değiştirilemez sinyal kaydı yok.</td></tr>';
    return;
  }
  body.innerHTML = data.signals.map((card) => `
    <tr data-signal-id="${esc(card.signal_freeze_identity)}">
      <td>${esc(fmtTime(card.frozen_at_ms))}</td>
      <td><strong>${esc(card.exchange.toUpperCase())}</strong> · ${esc(card.symbol)} · ${esc(card.timeframe)}</td>
      <td><span class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</span></td>
      <td class="${directionClass(card.direction)}">${esc(human(card.direction))}</td>
      <td>${esc(card.confluence_score)}<div class="row-sub">uyum endeksi</div></td>
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
      ${item.key_levels?.length ? `<div class="truth-note">Seviyeler: ${item.key_levels.map((level) => `${esc(level.label)}=${esc(level.price)}`).join(" · ")}</div>` : ""}
      ${item.metrics?.length ? `<div class="truth-note">Metrikler: ${item.metrics.map((metric) => `${esc(metric.name)}=${esc(metric.value)} ${esc(metric.unit)}`).join(" · ")}</div>` : ""}
    </div>`;
}

function renderMethodologies(detail) {
  if (!detail.methodologies?.length) {
    return '<div class="performance-empty">Metodoloji seçimi kanıtı yok.</div>';
  }
  return `<div class="methodology-grid">${detail.methodologies.map((method) => `
    <div class="methodology-card">
      <div class="methodology-head">
        <div>
          <div class="row-title">${esc(human(method.methodology))}</div>
          <div class="row-sub">kaynak N=${esc(method.source_count)} · seçilen N=${esc(method.selected_count)}</div>
        </div>
        <div class="state-pill">${esc(human(method.resolved_direction))}</div>
      </div>
      <div class="truth-note">İç çelişki: ${esc(method.has_internal_direction_conflict)}</div>
      ${method.selected?.length
        ? method.selected.map(renderEvidenceItem).join("")
        : '<div class="performance-empty">Karar anında seçilmiş kanıt yok.</div>'}
    </div>
  `).join("")}</div>`;
}

function renderAgreement(detail) {
  if (!detail.pairwise_relations?.length) {
    return '<div class="performance-empty">İkili metodoloji karşılaştırması yok.</div>';
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
    return '<div class="performance-empty">Tam giriş / geçersizleşme / hedef geometrisi yok. Bu karar uygulanabilir işlem kurulumu gibi sunulamaz.</div>';
  }
  return `
    <div class="detail-grid">
      <div class="detail-item"><div class="value-label">Giriş bölgesi</div><div class="value-main">${esc(geometry.entry_zone_low)} — ${esc(geometry.entry_zone_high)}</div></div>
      <div class="detail-item"><div class="value-label">Referans giriş</div><div class="value-main">${esc(geometry.entry_reference_price)}</div><div class="row-sub">${esc(human(geometry.entry_reference_model))}</div></div>
      <div class="detail-item"><div class="value-label">Geçersizleşme</div><div class="value-main">${esc(geometry.invalidation_price)}</div><div class="row-sub">${esc(human(geometry.invalidation_trigger))}</div></div>
      <div class="detail-item"><div class="value-label">Kaynak metodoloji</div><div class="value-main">${esc(human(geometry.source_methodology))}</div></div>
    </div>
    <div class="truth-note">Hedefler: ${geometry.targets.map((target) => `${esc(target.label)}=${esc(target.target_price)} (${esc(target.reference_rr)}R reference)`).join(" · ")}</div>`;
}

async function openSignal(signalId) {
  const detail = await fetchJSON(`/api/signals/${encodeURIComponent(signalId)}`);
  if (detail.status !== "ready" || !detail.signal) {
    showNotice(`Sinyal detayı durumu: ${human(detail.status)}.`);
    return;
  }
  const card = detail.signal;
  $("#dialogTitle").textContent = `${card.exchange.toUpperCase()} · ${card.symbol} · ${card.timeframe}`;
  $("#dialogBody").innerHTML = `
    <div class="detail-grid">
      <div class="detail-item"><div class="value-label">Durum</div><div class="value-main">${esc(human(card.state))}</div></div>
      <div class="detail-item"><div class="value-label">Yön</div><div class="value-main ${directionClass(card.direction)}">${esc(human(card.direction))}</div></div>
      <div class="detail-item"><div class="value-label">Metodoloji uyumu</div><div class="value-main">${esc(card.confluence_score)}</div><div class="row-sub">${esc(card.confluence_score_semantic)}</div></div>
      <div class="detail-item"><div class="value-label">Olasılık</div><div class="value-main">${esc(human(card.probability_status))}</div></div>
      <div class="detail-item"><div class="value-label">Karar zamanı</div><div class="value-main">${esc(fmtTime(card.as_of_ms))}</div></div>
      <div class="detail-item"><div class="value-label">Kaydedildi</div><div class="value-main">${esc(fmtTime(card.frozen_at_ms))}</div></div>
    </div>
    <div class="detail-item">
      <div class="value-label">Kanıt / belirsizlik</div>
      <div class="truth-note">${esc(detail.evidence_summary?.length ? detail.evidence_summary.join(" · ") : "kanıt özeti yok")}</div>
      <div class="truth-note">${esc(card.uncertainty_flags?.length ? card.uncertainty_flags.join(" · ") : "ek belirsizlik bayrağı yok")}</div>
    </div>
    <div class="detail-item">
      <div class="value-label">Dondurulmuş mum kapsamı</div>
      <div class="value-main">${esc(detail.candle_count)} mum</div>
      <div class="row-sub">${esc(fmtTime(detail.first_candle_open_time_ms))} → ${esc(fmtTime(detail.last_candle_open_time_ms))}</div>
    </div>
    <div class="detail-item"><div class="value-label">Metodoloji kanıtı</div>${renderMethodologies(detail)}</div>
    <div class="detail-item"><div class="value-label">Uyum matrisi</div>${renderAgreement(detail)}</div>
    <div class="detail-item"><div class="value-label">Dondurulmuş geometri</div>${renderGeometry(detail.geometry)}</div>
    <div class="detail-item"><div class="value-label">Kanıt sınıfı durumu</div><div class="value-main">${esc(human(card.evidence_class_status))}</div></div>
    <div class="detail-item"><div class="value-label">Sinyal kimliği</div><div class="mono">${esc(card.signal_freeze_identity)}</div></div>
    <div class="detail-item"><div class="value-label">Kanıt paketi kimliği</div><div class="mono">${esc(card.bundle_identity)}</div></div>`;
  $("#signalDialog").showModal();
}

function bindSignalClicks() {
  document.querySelectorAll("[data-signal-id]").forEach((node) => {
    node.addEventListener("click", () => openSignal(node.dataset.signalId).catch(showError));
  });
}

function showError(error) {
  console.error(error);
  showNotice(`Salt okunur panel hatası: ${error.message}`);
  $("#healthChip").textContent = "Okuma hatası";
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

  $("#healthChip").textContent = health.ledger_present ? "Kanıt deposu bağlı" : "Kanıt deposu yok";
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
