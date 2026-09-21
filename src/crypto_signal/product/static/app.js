const $ = (selector) => document.querySelector(selector);

let navigationContexts = [];
let selectedEvidenceClass = null;
let performanceData = null;
let educationData = null;

const AUTO_REFRESH_MS = 15_000;
const STALE_AFTER_MS = 45_000;
let refreshTimer = null;
let freshnessTimer = null;
let refreshInFlight = false;
let lastSuccessfulRefreshAt = null;
let consecutiveRefreshFailures = 0;

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
  evidence: "Kanıt",
  entry: "Giriş",
  target: "Hedef",
  invalidation: "Geçersizleşme",
  hold_cash: "Nakitte Kal",
  buy: "Sanal Alım",
  exit: "Sanal Çıkış",
  waiting_execution_input: "İşlem girdisi bekleniyor",
  waiting_venue_rules: "Piyasa kuralları bekleniyor",
  sizing_rejected: "Boyutlandırma reddedildi",
  pretrade_rejected: "İşlem planı reddedildi",
  pretrade_ready: "Sanal işlem planı hazır",
  signal_not_active: "Sinyal aktif değil",
  unsafe_uncertainty: "Belirsizlik güvenli sınırı aşıyor",
  future_signal: "Gelecek kanıtı bekleniyor",
  cooldown_active: "Bekleme süresi aktif",
  missing_mark_price: "Güncel değerleme kanıtı eksik",
  no_4h_evidence: "4 saatlik kanıt yok",
  waiting_provider_pair: "İkinci sağlayıcı bekleniyor",
  provider_cutoff_mismatch: "Sağlayıcı kapanışları eşleşmiyor",
  pre_activation_pair: "Aktivasyon öncesi kanıt",
  post_activation_pair: "Yeni 4 saatlik çift hazır",
  not_yet_measured: "Henüz ölçülmedi",
  available: "Ölçülebilir",
  missing_marks: "Değerleme kanıtı eksik",
  win: "Kazanç",
  loss: "Kayıp",
  breakeven: "Başa Baş",
};

function fmtTime(ms) {
  if (ms === null || ms === undefined) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(Number(ms)));
}

function fmtAgeMs(value) {
  if (value === null || value === undefined) return "—";
  const ms = Math.max(0, Number(value));
  if (!Number.isFinite(ms)) return "—";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds} sn`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} dk`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} sa`;
  return `${Math.floor(hours / 24)} gün`;
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

function setLiveStatus(state) {
  const chip = $("#liveStatusChip");
  if (!chip) return;
  chip.classList.remove("chip-live", "chip-refreshing", "chip-stale", "chip-error");
  if (state === "live") {
    chip.textContent = "Canlı · otomatik yenileme";
    chip.classList.add("chip-live");
    return;
  }
  if (state === "refreshing") {
    chip.textContent = "Yeni kanıt kontrol ediliyor…";
    chip.classList.add("chip-refreshing");
    return;
  }
  if (state === "offline") {
    chip.textContent = "Çevrimdışı · son kanıt korunuyor";
    chip.classList.add("chip-stale");
    return;
  }
  if (state === "stale") {
    chip.textContent = "Veri bağlantısı gecikmiş";
    chip.classList.add("chip-stale");
    return;
  }
  chip.textContent = "Canlı okuma hatası";
  chip.classList.add("chip-error");
}

function updateFreshnessStatus() {
  const chip = $("#lastRefreshChip");
  if (!chip) return;
  if (lastSuccessfulRefreshAt === null) {
    chip.textContent = "Son yenileme · bekleniyor";
  } else {
    const ageMs = Math.max(0, Date.now() - lastSuccessfulRefreshAt);
    const ageSeconds = Math.floor(ageMs / 1000);
    chip.textContent = ageSeconds < 5
      ? "Son yenileme · şimdi"
      : `Son yenileme · ${ageSeconds} sn önce`;
  }

  const freshness = CryptoSignalFreshness.classifyRefreshFreshness({
    online: navigator.onLine,
    lastSuccessfulRefreshAt,
    nowMs: Date.now(),
    staleAfterMs: STALE_AFTER_MS,
  });
  if (freshness === "offline") {
    setLiveStatus("offline");
  } else if (freshness === "stale") {
    setLiveStatus("stale");
  }
}

async function refreshAll() {
  if (refreshInFlight) return;
  if (!navigator.onLine) {
    setLiveStatus("offline");
    updateFreshnessStatus();
    return;
  }
  refreshInFlight = true;
  setLiveStatus("refreshing");
  try {
    await loadAll();
    lastSuccessfulRefreshAt = Date.now();
    consecutiveRefreshFailures = 0;
    setLiveStatus("live");
    updateFreshnessStatus();
  } catch (error) {
    consecutiveRefreshFailures += 1;
    setLiveStatus(consecutiveRefreshFailures >= 2 ? "stale" : "error");
    showError(error);
  } finally {
    refreshInFlight = false;
  }
}

function startAutoRefresh() {
  if (refreshTimer !== null) window.clearInterval(refreshTimer);
  if (freshnessTimer !== null) window.clearInterval(freshnessTimer);
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) refreshAll();
  }, AUTO_REFRESH_MS);
  freshnessTimer = window.setInterval(updateFreshnessStatus, 5_000);
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

function fmtMoney(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${number.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })} USDT`;
}

function fmtFractionPercent(value, maximumFractionDigits = 2) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `%${(number * 100).toLocaleString("tr-TR", { maximumFractionDigits })}`;
}

function paperCadenceExplanation(item) {
  const messages = {
    no_4h_evidence: "Henüz iki sağlayıcıdan 4 saatlik kapanış kanıtı yok.",
    waiting_provider_pair: "Bir sağlayıcı hazır; diğer sağlayıcının aynı piyasa kapanışı bekleniyor.",
    provider_cutoff_mismatch: "İki sağlayıcının son 4 saatlik piyasa kapanışı aynı değil.",
    pre_activation_pair: "Eşleşen kanıt var ancak sanal portföy aktivasyonundan önce oluşmuş.",
    post_activation_pair: item.candidate_available
      ? "İki sağlayıcı aynı yeni 4 saatlik kapanışı doğruladı; aday değerlendirildi."
      : "Yeni sağlayıcı çifti var ancak işlenecek güncel aday kalmadı.",
  };
  return messages[item.status] ?? human(item.status);
}

function paperCandidateExplanation(item) {
  if (item.terminal_status === "pretrade_ready") {
    return "Kurallar ve risk kontrolleri sanal işlem planına kadar ulaştı. Bu ekran yine de gerçek emir vermez.";
  }
  if (item.terminal_status === "hold_cash") {
    return "Sistem kanıtı gördü ama işlem açmak yerine nakitte kalmayı seçti.";
  }
  if (item.terminal_status === "waiting_execution_input") {
    return "Karar var; güvenli simülasyon için gereken yürütme kanıtı henüz tamamlanmadı.";
  }
  if (item.terminal_status === "waiting_venue_rules") {
    return "Karar var; güncel ve doğrulanmış piyasa kuralı olmadan ilerlemiyor.";
  }
  return "Aday güvenlik kapılarından birinde durduruldu.";
}

function fmtRate(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `%${(number * 100).toLocaleString("tr-TR", { maximumFractionDigits: 4 })}`;
}

function paperCandidateEvidenceChange(item) {
  const byReason = {
    signal_not_active: "Binance ve Bybit aynı yeni 4 saatlik kapanışta gerekli ACTIVE koşullarını birlikte sağlarsa aday yeniden değerlendirilir.",
    unsafe_uncertainty: "Belirsizlik bayrakları güvenli politika sınırına döner ve iki sağlayıcının kanıtı hâlâ eşleşirse karar yeniden değerlendirilir.",
    future_signal: "Karar zamanından sonra oluşan geçerli kapalı mum kanıtı gelmeden sistem ilerlemez.",
    cooldown_active: "Politika bekleme süresi sona erdikten sonra yalnızca yeni ve geçerli kanıtla tekrar değerlendirme yapılır.",
    missing_mark_price: "Açık pozisyonların güvenilir değerleme fiyatı tamamlanmadan risk hesabı ilerlemez.",
  };
  if (byReason[item.reason_code]) return byReason[item.reason_code];
  if (item.terminal_status === "waiting_execution_input") {
    return "Karardan sonra ilk uygun, tamamen kapanmış Binance 15m referans mumu oluştuğunda yürütme girdisi yeniden denenir.";
  }
  if (item.terminal_status === "waiting_venue_rules") {
    return "Karar zamanına uygun doğrulanmış venue-rule snapshot bulunursa sonraki güvenlik kapısına geçilebilir.";
  }
  if (item.terminal_status === "sizing_rejected") {
    return "Risk mesafesi, mevcut NAV ve pozisyon durumu boyutlandırma politikasının güvenli sınırlarına girmeden plan kurulmaz.";
  }
  if (item.terminal_status === "pretrade_rejected") {
    return "Miktar, minimum notional, nakit rezervi, yoğunlaşma ve maliyet kapıları birlikte geçilmeden sanal plan hazır sayılmaz.";
  }
  if (item.terminal_status === "pretrade_ready") {
    return "Bu plan yalnızca bu dondurulmuş kanıt seti için geçerlidir; yeni 4 saatlik kanıt, invalidation, fon durumu veya venue kuralı değişirse yeniden hesaplanır.";
  }
  return "Yeni dondurulmuş piyasa kanıtı geldiğinde politika zinciri baştan ve deterministik olarak yeniden değerlendirilir.";
}

function renderPaperTradePlan(item) {
  const bound = item.venue_bound_pretrade ?? null;
  const pretrade = bound?.pretrade ?? null;
  const plan = pretrade?.plan ?? null;
  const sizing = item.sizing ?? null;
  const execution = bound?.execution_snapshot ?? null;
  const costs = item.cost_preview ?? null;
  const steps = item.trace?.steps ?? [];
  const gateSummary = steps.length
    ? steps.map((step) => `${human(step.stage)}: ${human(step.state)} · ${human(step.code)}`).join(" → ")
    : "Karar kapısı ayrıntısı yok.";

  if (!plan) {
    return `
      <details class="paper-plan-disclosure">
        <summary>İşlem planı · neden yok?</summary>
        <div class="paper-plan-body">
          <div class="truth-note"><strong>Plan oluşturulmadı.</strong> Sistem eksik veya güvenli olmayan kanıtı sanal işleme çevirmiyor.</div>
          <div class="paper-plan-question"><span>Hangi kanıt bunu değiştirebilir?</span><strong>${esc(paperCandidateEvidenceChange(item))}</strong></div>
          <div class="paper-plan-trace">${esc(gateSummary)}</div>
        </div>
      </details>`;
  }

  return `
    <details class="paper-plan-disclosure">
      <summary>İşlem planı · rakamları ve riskleri göster</summary>
      <div class="paper-plan-body">
        <div class="paper-plan-grid">
          <div><span>Sistem ne yapmak istiyor?</span><strong>${esc(human(plan.action))} · ${esc(plan.symbol ?? item.symbol)}</strong></div>
          <div><span>Sanal miktar</span><strong>${esc(plan.quantity ?? "—")}</strong></div>
          <div><span>Referans fiyat</span><strong>${esc(plan.reference_price ?? "—")} USDT</strong></div>
          <div><span>Sanal tutar</span><strong>${esc(fmtMoney(plan.virtual_notional_usdt))}</strong></div>
          <div><span>Toplam maliyet bütçesi</span><strong>${esc(fmtMoney(plan.cost_budget_usdt))}</strong></div>
          <div><span>Plan sonrası nakit</span><strong>${esc(fmtMoney(plan.projected_cash_usdt))}</strong></div>
          <div><span>Plan sonrası miktar</span><strong>${esc(plan.projected_quantity ?? "0")}</strong></div>
          <div><span>Maks. pozisyon riski</span><strong>${esc(fmtMoney(sizing?.max_position_risk_usdt))}</strong></div>
          <div><span>Konservatif invalidation</span><strong>${esc(sizing?.conservative_invalidation_price ?? "—")}</strong></div>
          <div><span>Fee tahmini</span><strong>${esc(fmtMoney(costs?.fee_usdt))} · ${esc(fmtRate(execution?.fee_rate))}</strong></div>
          <div><span>Spread tahmini</span><strong>${esc(fmtMoney(costs?.spread_usdt))} · ${esc(fmtRate(execution?.spread_rate))}</strong></div>
          <div><span>Slippage tahmini</span><strong>${esc(fmtMoney(costs?.slippage_usdt))} · ${esc(fmtRate(execution?.slippage_rate))}</strong></div>
        </div>
        <div class="paper-plan-question"><span>Neden şimdi?</span><strong>Tüm kabul edilmiş dry-run kapıları bu dondurulmuş kanıt için sanal plan seviyesine kadar geçti.</strong></div>
        <div class="paper-plan-question"><span>Fikir ne zaman bozulur?</span><strong>${esc(plan.invalidation_context ?? "Açık invalidation bağlamı yok.")}</strong></div>
        <div class="paper-plan-question"><span>Hangi kanıt kararı değiştirebilir?</span><strong>${esc(paperCandidateEvidenceChange(item))}</strong></div>
        <div class="paper-plan-trace">${esc(gateSummary)}</div>
        <div class="truth-note">Bu yalnızca sanal plan önizlemesidir. Gerçek emir, credential veya gerçek sermaye yetkisi yoktur.</div>
      </div>
    </details>`;
}

function paperBenchmarkLabel(kind) {
  const labels = {
    cash_100_usdt: "100 USDT nakit",
    btc_buy_hold_100_usdt: "100 USDT BTC al-tut",
    btc_eth_sol_equal_weight_100_usdt: "BTC / ETH / SOL eşit ağırlık",
  };
  return labels[kind] ?? human(kind);
}

function renderPaperBenchmarks(snapshot) {
  const results = snapshot?.benchmarks?.results ?? [];
  const comparisons = new Map(
    (snapshot?.benchmark_comparisons ?? []).map((item) => [item.kind, item])
  );
  if (!results.length) {
    return `
      <div class="paper-benchmark-block">
        <div class="value-label">Aynı başlangıç benchmarkları</div>
        <div class="paper-empty compact">
          <strong>Benchmark kanıtı yok.</strong>
          <span>Eksik karşılaştırmadan göreli performans türetilmez.</span>
        </div>
      </div>`;
  }

  return `
    <div class="paper-benchmark-block">
      <div class="paper-benchmark-head">
        <div>
          <div class="value-label">Aynı başlangıç benchmarkları</div>
          <strong>Paper fon aynı anda pasif kalsaydı ne olurdu?</strong>
        </div>
        <span>${esc(fmtTime(snapshot.benchmarks.start_at_ms))} başlangıç</span>
      </div>
      <div class="paper-benchmark-list">
        ${results.map((item) => {
          const comparison = comparisons.get(item.kind) ?? {};
          const available = item.availability === "available";
          return `
            <div class="paper-benchmark-row">
              <div>
                <strong>${esc(paperBenchmarkLabel(item.kind))}</strong>
                <span>${available ? "PIT-safe kapalı mum referansı" : "Mark kanıtı eksik"}</span>
              </div>
              <div>
                <span>Benchmark NAV</span>
                <strong>${available ? esc(fmtMoney(item.nav_usdt)) : "—"}</strong>
              </div>
              <div>
                <span>Benchmark getirisi</span>
                <strong>${available ? esc(fmtFractionPercent(item.total_return_fraction)) : "—"}</strong>
              </div>
              <div>
                <span>Paper göreli getiri</span>
                <strong>${comparison.relative_return_fraction === null || comparison.relative_return_fraction === undefined
                  ? "—"
                  : esc(fmtFractionPercent(comparison.relative_return_fraction))}</strong>
              </div>
            </div>`;
        }).join("")}
      </div>
      <div class="truth-note">Benchmarklar aynı aktivasyon başlangıcından hesaplanan frictionless referanslardır; gerçek emir veya execution sonucu değildir.</div>
    </div>`;
}
function renderPaperPortfolioPerformanceLab(data) {
  const exposureRoot = $("#paperPortfolioExposure");
  const performanceRoot = $("#paperPerformanceLab");
  const exposureTag = $("#paperExposureTag");
  const performanceTag = $("#paperPerformanceTag");
  if (!exposureRoot || !performanceRoot || !exposureTag || !performanceTag) return;

  if (data?.status !== "ready" || !data.snapshot) {
    exposureTag.textContent = "KANIT YOK";
    performanceTag.textContent = "KANIT YOK";
    exposureRoot.classList.remove("loading-block");
    performanceRoot.classList.remove("loading-block");
    exposureRoot.innerHTML = '<div class="paper-empty compact"><strong>Portföy maruziyeti kullanılamıyor.</strong><span>Eksik veriden risk oranı türetilmez.</span></div>';
    performanceRoot.innerHTML = '<div class="paper-empty compact"><strong>Paper performansı kullanılamıyor.</strong><span>Eksik veriden başarı metriği türetilmez.</span></div>';
    return;
  }

  const snapshot = data.snapshot;
  const portfolio = snapshot.portfolio ?? {};
  const exposure = snapshot.portfolio_exposure ?? {};
  const performance = snapshot.performance ?? {};
  const performanceWindow = performance.window ?? {};
  const positions = exposure.positions ?? [];

  exposureRoot.classList.remove("loading-block");
  if (exposure.availability !== "available") {
    exposureTag.textContent = "MARK KANITI EKSİK";
    exposureRoot.innerHTML = `
      <div class="paper-empty compact">
        <strong>Maruziyet hesabı bilinçli olarak kapalı.</strong>
        <span>Açık pozisyonların tümü güvenilir, kapanmış piyasa mumu ile değerlenmeden NAV veya oran uydurulmaz.</span>
      </div>`;
  } else {
    exposureTag.textContent = positions.length ? `${positions.length} POZİSYON` : "TAMAMI NAKİT";
    const cashWidth = Math.max(0, Math.min(100, Number(exposure.cash_fraction ?? 0) * 100));
    const investedWidth = Math.max(0, Math.min(100, Number(exposure.invested_fraction ?? 0) * 100));
    exposureRoot.innerHTML = `
      <div class="paper-lab-metrics">
        <div><span>Nakit</span><strong>${esc(fmtMoney(exposure.cash_usdt))}</strong><small>${esc(fmtFractionPercent(exposure.cash_fraction))} NAV</small></div>
        <div><span>Piyasa maruziyeti</span><strong>${esc(fmtMoney(exposure.marked_positions_value_usdt))}</strong><small>${esc(fmtFractionPercent(exposure.invested_fraction))} NAV</small></div>
        <div><span>Sanal NAV</span><strong>${esc(fmtMoney(exposure.nav_usdt))}</strong><small>Başlangıç ${esc(fmtMoney(portfolio.initial_cash_usdt))}</small></div>
        <div><span>Toplam PnL</span><strong>${esc(fmtMoney(portfolio.pnl_usdt))}</strong><small>Getiri ${esc(fmtFractionPercent(portfolio.total_return_fraction))}</small></div>
      </div>
      <div class="paper-allocation" aria-label="Sanal portföy dağılımı">
        <div class="paper-allocation-cash" style="width:${cashWidth}%"></div>
        <div class="paper-allocation-invested" style="width:${investedWidth}%"></div>
      </div>
      <div class="paper-allocation-legend">
        <span>Nakit · ${esc(fmtFractionPercent(exposure.cash_fraction))}</span>
        <span>Pozisyonlar · ${esc(fmtFractionPercent(exposure.invested_fraction))}</span>
      </div>
      <div class="paper-exposure-list">
        ${positions.length ? positions.map((item) => `
          <div class="paper-exposure-row">
            <div><strong>${esc(item.symbol)}</strong><span>${esc(item.quantity)} adet · mark ${esc(item.mark_price ?? "—")} USDT</span></div>
            <div><strong>${esc(fmtMoney(item.marked_value_usdt))}</strong><span>${esc(fmtFractionPercent(item.nav_fraction))} NAV</span></div>
            <div class="paper-evidence-mini">Mark kapanışı · ${esc(fmtTime(item.mark_candle_close_time_ms))}</div>
          </div>`).join("") : `
          <div class="paper-empty compact">
            <strong>Şu anda piyasa maruziyeti yok.</strong>
            <span>Sanal fon nakitte. Bu tek başına başarı ya da başarısızlık değildir; açık pozisyon olmadığı anlamına gelir.</span>
          </div>`}
      </div>`;
  }

  performanceRoot.classList.remove("loading-block");
  if (performance.status === "not_yet_measured") {
    performanceTag.textContent = "HENÜZ ÖLÇÜLMEDİ";
    performanceRoot.innerHTML = `
      <div class="paper-performance-empty">
        <div class="paper-performance-zero">Ölçüm bekleniyor</div>
        <strong>Henüz kapanmış sanal işlem yok.</strong>
        <p>Bu nedenle win rate, ortalama işlem getirisi ve profit factor için <em>%0</em> yazmıyoruz. Örneklem oluşmadı.</p>
      </div>
      <div class="paper-lab-metrics paper-lab-metrics-compact">
        <div><span>Kapanmış işlem</span><strong>${esc(performance.closed_trade_count ?? 0)}</strong><small>ölçüme giren round trip</small></div>
        <div><span>Açık işlem</span><strong>${esc(performance.open_trade_count ?? 0)}</strong><small>henüz skorlanmaz</small></div>
        <div><span>Turnover</span><strong>${esc(fmtFractionPercent(performanceWindow.turnover_fraction))}</strong><small>işlem gören notional / 100 USDT</small></div>
        <div><span>Nakitte geçen zaman</span><strong>${esc(fmtFractionPercent(performanceWindow.cash_time_fraction))}</strong><small>aktivasyondan beri</small></div>
        <div><span>Observed expectancy</span><strong>—</strong><small>kapanmış işlem örneklemi yok</small></div>
        <div><span>Profit factor</span><strong>—</strong><small>örneklem yok</small></div>
      </div>
      ${renderPaperBenchmarks(snapshot)}`;
    return;
  }

  const closedTrades = performance.closed_trades ?? [];
  performanceTag.textContent = `${performance.closed_trade_count ?? closedTrades.length} KAPANMIŞ`;
  performanceRoot.innerHTML = `
    <div class="paper-lab-metrics">
      <div><span>Win rate</span><strong>${esc(fmtFractionPercent(performance.win_rate_fraction))}</strong><small>${esc(performance.win_count ?? 0)} kazanç · ${esc(performance.loss_count ?? 0)} kayıp · ${esc(performance.breakeven_count ?? 0)} başa baş</small></div>
      <div><span>Net kapanmış PnL</span><strong>${esc(fmtMoney(performance.total_closed_trade_net_pnl_usdt))}</strong><small>yalnızca kapanmış işlemler</small></div>
      <div><span>Ort. işlem getirisi</span><strong>${esc(fmtFractionPercent(performance.average_closed_trade_return_fraction))}</strong><small>net round-trip kanıtı</small></div>
      <div><span>Profit factor</span><strong>${esc(performance.profit_factor ?? "—")}</strong><small>tanımlı olduğu yerde</small></div>
      <div><span>En iyi işlem</span><strong>${esc(fmtMoney(performance.best_trade_pnl_usdt))}</strong><small>net PnL</small></div>
      <div><span>En kötü işlem</span><strong>${esc(fmtMoney(performance.worst_trade_pnl_usdt))}</strong><small>net PnL</small></div>
      <div><span>Observed expectancy</span><strong>${esc(fmtMoney(performance.expectancy_usdt_per_closed_trade))}</strong><small>kapanmış işlem başına net PnL ortalaması</small></div>
      <div><span>Turnover</span><strong>${esc(fmtFractionPercent(performanceWindow.turnover_fraction))}</strong><small>işlem gören notional / 100 USDT</small></div>
      <div><span>Nakitte geçen zaman</span><strong>${esc(fmtFractionPercent(performanceWindow.cash_time_fraction))}</strong><small>aktivasyondan gözlem anına</small></div>
      <div><span>Piyasada geçen zaman</span><strong>${esc(fmtFractionPercent(performanceWindow.invested_time_fraction))}</strong><small>açık pozisyon taşınan süre</small></div>
      <div><span>Execution maliyeti</span><strong>${esc(fmtMoney(performance.total_explicit_execution_cost_usdt))}</strong><small>fee + spread + slippage kanıtı</small></div>
    </div>
    <div class="paper-closed-trade-list">
      ${closedTrades.map((trade) => `
        <details class="paper-trade-row">
          <summary>
            <span><strong>${esc(trade.symbol)}</strong> · ${esc(human(trade.outcome))}</span>
            <span>${esc(fmtMoney(trade.net_pnl_usdt))} · ${esc(fmtFractionPercent(trade.return_fraction))}</span>
          </summary>
          <div class="paper-trade-detail">
            <span>Giriş: ${esc(trade.entry_fill_price)} USDT · ${esc(fmtTime(trade.entered_at_ms))}</span>
            <span>Çıkış: ${esc(trade.exit_fill_price)} USDT · ${esc(fmtTime(trade.exited_at_ms))}</span>
            <span>Miktar: ${esc(trade.quantity)} · explicit maliyet: ${esc(fmtMoney(trade.explicit_execution_cost_usdt))}</span>
          </div>
        </details>`).join("") || '<div class="paper-empty compact">Kapanmış işlem detayı yok.</div>'}
    </div>
    ${renderPaperBenchmarks(snapshot)}
    <div class="truth-note">Bu laboratuvar yalnızca değiştirilemez sanal fill + muhasebe kanıtını ölçer; sinyal güveni veya geçmiş frekans burada işlem başarısı sayılmaz.</div>`;
}


function renderPaperMissionControl(data) {
  renderPaperPortfolioPerformanceLab(data);
  const root = $("#paperMissionControl");
  const tag = $("#paperPolicyTag");
  if (!root || !tag) return;

  if (data?.status !== "ready" || !data.snapshot) {
    tag.textContent = "YAZMA KAPALI · SALT OKUNUR";
    root.classList.remove("loading-block");
    root.innerHTML = `
      <div class="paper-empty">
        <strong>Sanal portföy kanıtı henüz bu runtime'da bağlı değil.</strong>
        <span>Bu durum gerçek sermaye veya emir yetkisi açmaz. Sistem salt okunur piyasa izlemeye devam eder.</span>
      </div>`;
    return;
  }

  const snapshot = data.snapshot;
  const portfolio = snapshot.portfolio ?? {};
  const performance = snapshot.performance ?? {};
  const candidates = snapshot.candidates ?? [];
  const cadence = snapshot.decision_cadence ?? [];
  const positionCount = (portfolio.positions ?? []).length;

  tag.textContent = snapshot.trade_policy === "NOT_ACTIVATED"
    ? "YAZMA KAPALI · SALT OKUNUR"
    : esc(snapshot.trade_policy);

  const performanceValue = performance.status === "not_yet_measured"
    ? "Henüz ölçülmedi"
    : `Kapanan ${performance.closed_trade_count ?? 0} işlem`;
  const winRate = performance.win_rate_fraction === null || performance.win_rate_fraction === undefined
    ? "Win rate yok"
    : `Win rate %${(Number(performance.win_rate_fraction) * 100).toLocaleString("tr-TR", { maximumFractionDigits: 2 })}`;

  root.classList.remove("loading-block");
  root.innerHTML = `
    <div class="paper-summary-grid">
      <article class="paper-summary-card paper-summary-primary">
        <div class="value-label">Nakit</div>
        <strong>${esc(fmtMoney(portfolio.cash_usdt))}</strong>
        <span>Başlangıç: ${esc(fmtMoney(portfolio.initial_cash_usdt))}</span>
      </article>
      <article class="paper-summary-card">
        <div class="value-label">Sanal portföy değeri</div>
        <strong>${esc(fmtMoney(portfolio.nav_usdt))}</strong>
        <span>PnL: ${esc(fmtMoney(portfolio.pnl_usdt))}</span>
      </article>
      <article class="paper-summary-card">
        <div class="value-label">Açık pozisyon</div>
        <strong>${esc(positionCount)}</strong>
        <span>${esc(portfolio.simulated_fill_count ?? 0)} simüle fill kaydı</span>
      </article>
      <article class="paper-summary-card">
        <div class="value-label">İşlem performansı</div>
        <strong>${esc(performanceValue)}</strong>
        <span>${esc(winRate)}</span>
      </article>
    </div>

    <div class="paper-mission-columns">
      <div class="paper-subpanel">
        <div class="paper-subpanel-head">
          <div><div class="value-label">4 saatlik karar ritmi</div><strong>Binance + Bybit birlikte ne durumda?</strong></div>
          <span class="panel-tag">${esc(snapshot.eligible_post_activation_freezes ?? 0)} uygun kanıt</span>
        </div>
        <div class="paper-cadence-list">
          ${cadence.map((item) => `
            <div class="paper-cadence-row">
              <div><strong>${esc(item.symbol)}</strong><div class="row-sub">${esc(paperCadenceExplanation(item))}</div></div>
              <div class="state-pill ${item.candidate_available ? "state-active" : "state-neutral"}">${esc(human(item.status))}</div>
            </div>`).join("") || '<div class="truth-note">Karar ritmi kanıtı yok.</div>'}
        </div>
      </div>

      <div class="paper-subpanel">
        <div class="paper-subpanel-head">
          <div><div class="value-label">Son sanal karar adayları</div><strong>Neden işlem yaptı / yapmadı?</strong></div>
          <span class="panel-tag">${esc(snapshot.ready_candidate_count ?? 0)} plan hazır</span>
        </div>
        <div class="paper-candidate-list">
          ${candidates.map((item) => `
            <div class="paper-candidate-row">
              <div class="paper-candidate-main">
                <strong>${esc(item.symbol)} · ${esc(human(item.candidate_action))}</strong>
                <div class="row-sub">${esc(paperCandidateExplanation(item))}</div>
                <div class="truth-note">Motor gerekçesi: ${esc(human(item.reason_code))}</div>
                ${renderPaperTradePlan(item)}
              </div>
              <div class="state-pill ${item.terminal_status === "pretrade_ready" ? "state-active" : "state-neutral"}">${esc(human(item.terminal_status))}</div>
            </div>`).join("") || `
            <div class="paper-empty compact">
              <strong>Yeni işlenecek aday yok.</strong>
              <span>Sistem kanıt gelmediğinde işlem uydurmaz.</span>
            </div>`}
        </div>
      </div>
    </div>

    <div class="paper-truth-bar">
      <span>Gerçek sermaye: <strong>0</strong></span>
      <span>Politika: <strong>${esc(snapshot.trade_policy)}</strong></span>
      <span>Hazır aday: <strong>${esc(snapshot.ready_candidate_count ?? 0)}</strong></span>
      <span>Performans: <strong>${esc(human(performance.status))}</strong></span>
    </div>`;
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

function renderPaperTradeArchive(data) {
  const root = $("#paperTradeArchive");
  const tag = $("#paperTradeArchiveTag");
  if (!root || !tag) return;

  if (data?.status !== "ready" || !data.snapshot) {
    tag.textContent = "KANIT YOK";
    root.classList.remove("loading-block");
    root.innerHTML = `
      <div class="paper-empty compact">
        <strong>Sanal işlem arşivi şu anda kullanılamıyor.</strong>
        <span>Eksik paper kanıtından işlem geçmişi türetilmez.</span>
      </div>`;
    return;
  }

  const snapshot = data.snapshot;
  const portfolio = snapshot.portfolio ?? {};
  const exposure = snapshot.portfolio_exposure ?? {};
  const performance = snapshot.performance ?? {};
  const closedTrades = performance.closed_trades ?? [];
  const openPositions = exposure.positions ?? [];
  const fillCount = Number(portfolio.simulated_fill_count ?? 0);
  const closedCount = Number(performance.closed_trade_count ?? closedTrades.length);
  const openCount = Number(performance.open_trade_count ?? openPositions.length);

  tag.textContent = `${fillCount} FILL · ${closedCount} KAPANMIŞ`;
  root.classList.remove("loading-block");

  if (fillCount === 0 && closedCount === 0 && openCount === 0) {
    root.innerHTML = `
      <div class="paper-empty compact">
        <strong>Henüz sanal işlem kaydı yok.</strong>
        <span>Bu %0 başarı oranı değildir. Paper write politikası ${esc(snapshot.trade_policy ?? "—")} ve ledger’da fill kanıtı bulunmuyor.</span>
      </div>`;
    return;
  }

  root.innerHTML = `
    ${openPositions.length ? `
      <div class="paper-archive-group">
        <div class="value-label">Açık sanal pozisyonlar · henüz skorlanmaz</div>
        ${openPositions.map((item) => `
          <div class="paper-archive-row">
            <div><strong>${esc(item.symbol)}</strong><span>${esc(item.quantity)} adet</span></div>
            <div><strong>${esc(fmtMoney(item.marked_value_usdt))}</strong><span>${esc(fmtFractionPercent(item.nav_fraction))} NAV</span></div>
            <div><span>Mark</span><strong>${esc(item.mark_price ?? "—")} USDT</strong></div>
          </div>`).join("")}
      </div>` : ""}
    <div class="paper-archive-group">
      <div class="value-label">Kapanmış sanal round-trip kayıtları</div>
      ${closedTrades.length ? closedTrades.map((trade) => `
        <details class="paper-trade-row paper-archive-trade">
          <summary>
            <span><strong>${esc(trade.symbol)}</strong> · ${esc(human(trade.outcome))}</span>
            <span>${esc(fmtMoney(trade.net_pnl_usdt))} · ${esc(fmtFractionPercent(trade.return_fraction))}</span>
          </summary>
          <div class="paper-trade-detail">
            <span>Giriş: ${esc(trade.entry_fill_price)} USDT · ${esc(fmtTime(trade.entered_at_ms))}</span>
            <span>Çıkış: ${esc(trade.exit_fill_price)} USDT · ${esc(fmtTime(trade.exited_at_ms))}</span>
            <span>Miktar: ${esc(trade.quantity)} · explicit maliyet: ${esc(fmtMoney(trade.explicit_execution_cost_usdt))}</span>
            <span class="mono">Trade identity: ${esc(trade.trade_identity)}</span>
          </div>
        </details>`).join("") : `
        <div class="paper-empty compact">
          <strong>Kapanmış sanal işlem yok.</strong>
          <span>Açık pozisyon varsa performans skoru oluşmadan burada ayrı tutulur.</span>
        </div>`}
    </div>`;
}

function renderSystemHealth(health, command, paperMission) {
  const root = $("#systemHealth");
  const tag = $("#systemHealthTag");
  if (!root || !tag) return;

  const snapshot = paperMission?.snapshot ?? null;
  const stream = snapshot?.signal_stream ?? {};
  const productOk = health?.status === "ok"
    && health?.read_only === true
    && Number(health?.real_capital) === 0;
  const ledgerOk = Boolean(health?.ledger_present) && command?.status === "ready";
  const paperOk = paperMission?.status === "ready"
    && paperMission?.read_only === true
    && Number(paperMission?.real_capital) === 0;
  const authorityClosed = snapshot?.trade_policy === "NOT_ACTIVATED";
  const overallOk = productOk && ledgerOk && paperOk && authorityClosed;

  tag.textContent = overallOk ? "READ-ONLY · SAĞLIKLI" : "DİKKAT GEREKİYOR";
  root.classList.remove("loading-block");
  root.innerHTML = `
    <article class="system-health-card ${productOk ? "health-ok" : "health-warn"}">
      <span>Ürün API</span>
      <strong>${productOk ? "Çalışıyor" : "Kontrol gerekli"}</strong>
      <small>${esc(health?.product_version ?? "sürüm yok")} · read-only=${esc(health?.read_only)}</small>
    </article>
    <article class="system-health-card ${ledgerOk ? "health-ok" : "health-warn"}">
      <span>Signal ledger</span>
      <strong>${ledgerOk ? "Bağlı" : "Eksik / okunamıyor"}</strong>
      <small>${esc(command?.freeze_count ?? 0)} immutable kayıt · son kayıt ${esc(fmtTime(command?.latest_frozen_at_ms))}</small>
    </article>
    <article class="system-health-card ${paperOk ? "health-ok" : "health-warn"}">
      <span>Paper kanıtı</span>
      <strong>${paperOk ? "Okunabilir" : "Kullanılamıyor"}</strong>
      <small>${paperOk ? `snapshot ${esc(String(snapshot?.snapshot_identity ?? "").slice(0, 12))}…` : esc(paperMission?.reason ?? "neden yok")}</small>
    </article>
    <article class="system-health-card ${authorityClosed ? "health-ok" : "health-warn"}">
      <span>Write authority</span>
      <strong>${authorityClosed ? "Kapalı" : esc(snapshot?.trade_policy ?? "bilinmiyor")}</strong>
      <small>REAL_CAPITAL=${esc(paperMission?.real_capital ?? health?.real_capital ?? "—")}</small>
    </article>
    <article class="system-health-card ${health?.alert_outbox_present ? "health-ok" : "health-neutral"}">
      <span>Alert outbox</span>
      <strong>${health?.alert_outbox_present ? "Bağlı" : "Bağlı değil"}</strong>
      <small>Uyarı yüzeyi yalnızca mevcut outbox kanıtını okur.</small>
    </article>
    <article class="system-health-card health-neutral">
      <span>Kanıt tazeliği</span>
      <strong>${esc(fmtAgeMs(stream.latest_freeze_age_ms))}</strong>
      <small>Son immutable signal freeze yaşı · otomatik ürün yenileme 15 sn</small>
    </article>
    <div class="system-health-note">
      Sistem Sağlığı burada ürün API’si ve read-only kanıt katmanını ifade eder. Eksik kanıt sağlıklı kabul edilmez; gerçek emir veya sermaye yetkisi açılmaz.
    </div>`;
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


function renderDecisionExplanation(detail) {
  const card = detail.signal;
  if (!card) return "";

  const methods = detail.methodologies ?? [];
  const supporting = methods.filter(
    (method) =>
      method.resolved_direction === card.direction
      && !method.has_internal_direction_conflict
  );
  const unresolved = methods.filter(
    (method) =>
      method.resolved_direction === "unresolved"
      || method.has_internal_direction_conflict
  );
  const opposing = methods.filter(
    (method) =>
      ["bullish", "bearish"].includes(method.resolved_direction)
      && method.resolved_direction !== card.direction
      && !method.has_internal_direction_conflict
  );

  const explicitInvalidations = methods
    .flatMap((method) => method.selected ?? [])
    .map((item) => item.invalidation_price)
    .filter((value) => value !== null && value !== undefined);

  const invalidation = detail.geometry?.invalidation_price
    ?? explicitInvalidations[0]
    ?? null;

  const stateNote = card.state === "active"
    ? "Aktif Sinyal: tam sinyal koşulları dondurulmuş kararda karşılanmış."
    : card.state === "watch"
      ? "İzleniyor: yapı dikkat çekiyor fakat Aktif Sinyal koşulları henüz tamamlanmış değil."
      : `${human(card.state)}: sistem bu görünümde işlem kurulumu ilan etmiyor.`;

  const supportText = supporting.length
    ? supporting.map((method) => human(method.methodology)).join(" + ")
    : "Yönü bağımsız olarak destekleyen çözümlenmiş metodoloji yok";

  const missingParts = [];
  if (unresolved.length) {
    missingParts.push(
      `çözümlenmemiş/çelişkili: ${unresolved.map((method) => human(method.methodology)).join(", ")}`
    );
  }
  if (opposing.length) {
    missingParts.push(
      `karşı yönde: ${opposing.map((method) => human(method.methodology)).join(", ")}`
    );
  }
  if (card.uncertainty_flags?.length) {
    missingParts.push(card.uncertainty_flags.map(human).join(" · "));
  }

  return `
    <div class="decision-brief">
      <div class="decision-brief-head">
        <div>
          <div class="small-label">Karar özeti</div>
          <div class="decision-brief-title">${esc(stateNote)}</div>
        </div>
        <div class="state-pill ${stateClass(card.state)}">${esc(human(card.state))}</div>
      </div>
      <div class="decision-brief-grid">
        <div>
          <div class="value-label">Neden önemli?</div>
          <div class="truth-note">
            ${esc(card.symbol)} · ${esc(card.timeframe)} görünümünde yön
            <strong class="${directionClass(card.direction)}">${esc(human(card.direction))}</strong>.
            Metodoloji uyumu ${esc(card.confluence_score)}; bu değer olasılık değildir.
          </div>
        </div>
        <div>
          <div class="value-label">Ne destekliyor?</div>
          <div class="truth-note">${esc(supportText)}</div>
        </div>
        <div>
          <div class="value-label">Neden işlem yapmamalıyız?</div>
          <div class="truth-note">${esc(missingParts.length
            ? missingParts.join(" · ")
            : "Belirgin karşı kanıt bayrağı yok; yine de metodoloji uyumu olasılık değildir ve bu tek başına işlem zorunluluğu yaratmaz.")}</div>
        </div>
        <div>
          <div class="value-label">Ne bozabilir?</div>
          <div class="truth-note">${invalidation === null
            ? "Tam ve açık bir geçersizleşme fiyatı bu kararda yok; uygulanabilir işlem geometrisi varsayılmaz."
            : `Açık geçersizleşme seviyesi: ${esc(invalidation)}`}</div>
        </div>
      </div>
    </div>`;
}

function frozenChartData(detail) {
  if (!detail.bundle_json) return { candles: [], levels: [] };
  let root;
  try {
    root = JSON.parse(detail.bundle_json);
  } catch {
    return { candles: [], levels: [] };
  }

  const candles = (root.candles ?? [])
    .map((item) => ({
      openTime: Number(item.open_time_ms),
      open: Number(item.open),
      high: Number(item.high),
      low: Number(item.low),
      close: Number(item.close),
    }))
    .filter((item) =>
      Number.isFinite(item.openTime)
      && Number.isFinite(item.open)
      && Number.isFinite(item.high)
      && Number.isFinite(item.low)
      && Number.isFinite(item.close)
      && item.high >= item.low
    )
    .slice(-120);

  const levels = [];
  (detail.methodologies ?? []).forEach((method) => {
    (method.selected ?? []).forEach((item) => {
      (item.key_levels ?? []).forEach((level) => {
        const price = Number(level.price);
        if (Number.isFinite(price)) {
          levels.push({
            label: `${human(method.methodology)} · ${human(level.label)}`,
            price,
            kind: "evidence",
          });
        }
      });
      const invalidation = Number(item.invalidation_price);
      if (item.invalidation_price !== null && Number.isFinite(invalidation)) {
        levels.push({
          label: `${human(method.methodology)} · geçersizleşme`,
          price: invalidation,
          kind: "invalidation",
        });
      }
    });
  });

  if (detail.geometry) {
    [
      ["Giriş alt", detail.geometry.entry_zone_low, "entry"],
      ["Giriş üst", detail.geometry.entry_zone_high, "entry"],
      ["Geçersizleşme", detail.geometry.invalidation_price, "invalidation"],
    ].forEach(([label, raw, kind]) => {
      const price = Number(raw);
      if (Number.isFinite(price)) levels.push({ label, price, kind });
    });
    (detail.geometry.targets ?? []).forEach((target) => {
      const price = Number(target.target_price);
      if (Number.isFinite(price)) {
        levels.push({ label: `Hedef · ${target.label}`, price, kind: "target" });
      }
    });
  }

  const unique = [];
  const seen = new Set();
  levels.forEach((level) => {
    const key = `${level.label}|${level.price}`;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(level);
    }
  });
  return { candles, levels: unique.slice(0, 12) };
}

function renderEvidenceChart(detail) {
  const canvas = $("#evidenceChart");
  const meta = $("#evidenceChartMeta");
  if (!canvas || !meta) return;

  const { candles, levels } = frozenChartData(detail);
  if (!candles.length) {
    canvas.classList.add("hidden");
    meta.textContent = "Bu dondurulmuş kayıtta çizilebilir OHLC mum verisi yok.";
    return;
  }

  canvas.classList.remove("hidden");
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(640, canvas.clientWidth || 640);
  const height = 330;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  canvas.style.height = `${height}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

  const style = getComputedStyle(document.documentElement);
  const text = style.getPropertyValue("--text").trim() || "#edf5fb";
  const muted = style.getPropertyValue("--muted").trim() || "#8ea0b3";
  const accent = style.getPropertyValue("--accent").trim() || "#66e3c4";
  const danger = style.getPropertyValue("--danger").trim() || "#ff8f8f";
  const warn = style.getPropertyValue("--warn").trim() || "#f4c95d";
  const line = "rgba(148,163,184,.13)";

  const pad = { left: 12, right: 84, top: 18, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const allPrices = candles.flatMap((c) => [c.low, c.high]).concat(levels.map((l) => l.price));
  let min = Math.min(...allPrices);
  let max = Math.max(...allPrices);
  if (max <= min) {
    max += 1;
    min -= 1;
  }
  const margin = (max - min) * 0.05;
  min -= margin;
  max += margin;
  const y = (price) => pad.top + ((max - price) / (max - min)) * plotH;

  ctx.clearRect(0, 0, width, height);
  ctx.font = "11px Inter, -apple-system, sans-serif";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= 4; i += 1) {
    const price = max - ((max - min) * i) / 4;
    const yy = y(price);
    ctx.strokeStyle = line;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.fillText(price.toLocaleString("tr-TR", { maximumFractionDigits: 2 }), width - pad.right + 8, yy);
  }

  const step = plotW / candles.length;
  const bodyW = Math.max(2, Math.min(7, step * 0.62));
  candles.forEach((candle, index) => {
    const x = pad.left + step * index + step / 2;
    const rising = candle.close >= candle.open;
    const color = rising ? accent : danger;
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y(candle.high));
    ctx.lineTo(x, y(candle.low));
    ctx.stroke();
    const top = y(Math.max(candle.open, candle.close));
    const bottom = y(Math.min(candle.open, candle.close));
    ctx.fillRect(x - bodyW / 2, top, bodyW, Math.max(1, bottom - top));
  });

  levels.forEach((level, index) => {
    const yy = y(level.price);
    const color = level.kind === "invalidation"
      ? danger
      : level.kind === "target"
        ? accent
        : level.kind === "entry"
          ? warn
          : "rgba(124,185,255,.9)";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.setLineDash([]);
    if (index < 6) {
      ctx.fillStyle = text;
      ctx.fillText(level.label, pad.left + 6, Math.max(10, yy - 8));
    }
  });

  const first = candles[0];
  const last = candles[candles.length - 1];
  ctx.fillStyle = muted;
  ctx.fillText(fmtTime(first.openTime), pad.left, height - 12);
  const endText = fmtTime(last.openTime);
  const endWidth = ctx.measureText(endText).width;
  ctx.fillText(endText, width - pad.right - endWidth, height - 12);

  meta.textContent = `${candles.length} dondurulmuş mum · ${levels.length} açık kanıt seviyesi · yeniden veri çekilmez`;
}


function frozenEvidenceSearchText(detail) {
  const parts = [];
  (detail.methodologies ?? []).forEach((method) => {
    parts.push(method.methodology ?? "");
    (method.selected ?? []).forEach((item) => {
      parts.push(item.setup_type ?? "", item.evidence_id ?? "");
      (item.evidence_summary ?? []).forEach((value) => parts.push(value));
      (item.key_levels ?? []).forEach((level) => parts.push(level.label ?? ""));
    });
  });
  (detail.evidence_summary ?? []).forEach((value) => parts.push(value));
  return parts.join(" ").toLowerCase();
}

function contextualLessonIds(detail) {
  const ids = new Set(["agreement_vs_probability"]);
  const text = frozenEvidenceSearchText(detail);
  const methods = detail.methodologies ?? [];

  const hasSelected = (name) => methods.some(
    (method) => method.methodology === name && (method.selected ?? []).length
  );
  const hasInvalidation = Boolean(detail.geometry?.invalidation_price)
    || methods.some((method) =>
      (method.selected ?? []).some(
        (item) => item.invalidation_price !== null && item.invalidation_price !== undefined
      )
    );

  if (/(^|[^a-z])bos([^a-z]|$)|break[_ -]?of[_ -]?structure/.test(text)) ids.add("bos");
  if (/choch|change[_ -]?of[_ -]?character/.test(text)) ids.add("choch");
  if (/liquidity[_ -]?sweep|likidite[_ -]?süp/.test(text)) ids.add("liquidity_sweep");
  if (/(^|[^a-z])fvg([^a-z]|$)|fair[_ -]?value[_ -]?gap/.test(text)) ids.add("fvg");
  if (hasSelected("harmonic")) ids.add("harmonic_prz");
  if (hasSelected("elliott")) ids.add("elliott_wave");
  if (hasInvalidation) ids.add("invalidation");
  if (
    detail.geometry?.invalidation_price !== null
    && detail.geometry?.invalidation_price !== undefined
    && (detail.geometry?.targets ?? []).length
  ) {
    ids.add("risk_reward");
  }
  return [...ids];
}

function contextualLessonReason(conceptId, detail) {
  const score = detail.signal?.confluence_score ?? "—";
  const reasons = {
    bos: "Dondurulmuş kanıt alanlarında BOS / break-of-structure etiketi bulundu.",
    choch: "Dondurulmuş kanıt alanlarında CHoCH / change-of-character etiketi bulundu.",
    liquidity_sweep: "Dondurulmuş kanıt alanlarında likidite süpürmesi etiketi bulundu.",
    fvg: "Dondurulmuş kanıt alanlarında FVG / fair-value-gap etiketi bulundu.",
    harmonic_prz: "Bu kararda seçilmiş Harmonic metodoloji kanıtı var.",
    elliott_wave: "Bu kararda seçilmiş Elliott metodoloji kanıtı var.",
    invalidation: "Bu kararda açık bir geçersizleşme seviyesi/koşulu var.",
    risk_reward: "Bu kararda giriş, geçersizleşme ve hedef geometrisi birlikte mevcut.",
    agreement_vs_probability: `Kararda metodoloji uyumu ${score} gösteriliyor; bunun olasılık olmadığını ayırmak gerekiyor.`,
  };
  return reasons[conceptId] ?? "Bu kavram mevcut dondurulmuş kanıtı anlamaya yardımcı olur.";
}

function renderContextTeaching(detail) {
  const lessons = educationData?.lessons ?? [];
  if (!lessons.length) {
    return '<div class="truth-note">Bağlamsal ders kataloğu henüz yüklenmedi.</div>';
  }
  const byId = new Map(lessons.map((lesson) => [lesson.concept_id, lesson]));
  const selected = contextualLessonIds(detail)
    .map((id) => byId.get(id))
    .filter(Boolean);
  if (!selected.length) {
    return '<div class="truth-note">Bu dondurulmuş kanıta özel ek ders eşleşmesi yok.</div>';
  }
  return `
    <div class="context-lesson-list">
      ${selected.map((lesson) => `
        <details class="context-lesson">
          <summary>
            <span>${esc(lesson.title_tr)}</span>
            <span class="evidence-linked-tag">kanıta bağlı</span>
          </summary>
          <div class="context-lesson-body">
            <div class="context-reason">${esc(contextualLessonReason(lesson.concept_id, detail))}</div>
            <p>${esc(lesson.beginner_tr)}</p>
            <div class="truth-note"><strong>Neden önemli?</strong> ${esc(lesson.why_it_matters_tr)}</div>
          </div>
        </details>
      `).join("")}
    </div>`;
}

function renderEvidenceLegend(detail) {
  const { levels } = frozenChartData(detail);
  if (!levels.length) {
    return '<div class="truth-note">Bu kayıtta ayrıca etiketlenmiş fiyat seviyesi yok.</div>';
  }
  return `
    <div class="evidence-legend">
      ${levels.map((level) => `
        <div class="evidence-legend-row">
          <span class="evidence-kind evidence-kind-${esc(level.kind)}">${esc(human(level.kind))}</span>
          <span class="evidence-legend-label">${esc(level.label)}</span>
          <strong>${esc(Number(level.price).toLocaleString("tr-TR", { maximumFractionDigits: 8 }))}</strong>
        </div>
      `).join("")}
    </div>
    <div class="truth-note">Bu seviyeler karar anındaki dondurulmuş kanıttan gelir; daha yeni fiyat verisi geçmiş kararı yeniden yazmaz.</div>`;
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
    ${renderDecisionExplanation(detail)}
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
    <div class="detail-item chart-detail">
      <div class="value-label">Kanıt grafiği</div>
      <div class="chart-shell">
        <canvas id="evidenceChart" class="evidence-chart" aria-label="Dondurulmuş mum ve kanıt seviyeleri"></canvas>
      </div>
      <div id="evidenceChartMeta" class="truth-note">Grafik hazırlanıyor…</div>
      <div class="evidence-legend-title">Grafikte çizilen dondurulmuş kanıt</div>
      ${renderEvidenceLegend(detail)}
    </div>
    <div class="detail-item context-teaching">
      <div class="value-label">Bu sinyali bana öğret</div>
      <div class="truth-note">Aşağıdaki dersler yalnızca bu dondurulmuş kayıtta bulunan metodoloji, geometri veya açık kanıt etiketlerine göre seçildi.</div>
      ${renderContextTeaching(detail)}
    </div>
    <div class="detail-item"><div class="value-label">Metodoloji kanıtı</div>${renderMethodologies(detail)}</div>
    <div class="detail-item"><div class="value-label">Uyum matrisi</div>${renderAgreement(detail)}</div>
    <div class="detail-item"><div class="value-label">Dondurulmuş geometri</div>${renderGeometry(detail.geometry)}</div>
    <div class="detail-item"><div class="value-label">Kanıt sınıfı durumu</div><div class="value-main">${esc(human(card.evidence_class_status))}</div></div>
    <div class="detail-item"><div class="value-label">Sinyal kimliği</div><div class="mono">${esc(card.signal_freeze_identity)}</div></div>
    <div class="detail-item"><div class="value-label">Kanıt paketi kimliği</div><div class="mono">${esc(card.bundle_identity)}</div></div>`;
  $("#signalDialog").showModal();
  requestAnimationFrame(() => renderEvidenceChart(detail));
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

function renderEducation(data) {
  educationData = data;
  const root = $("#educationCenter");
  const lessons = data?.status === "ready" ? (data.lessons ?? []) : [];
  $("#educationCount").textContent = lessons.length ? `${lessons.length} kısa ders` : "Ders yok";
  if (!lessons.length) {
    root.innerHTML = '<div class="performance-empty">Eğitim kataloğu şu anda kullanılamıyor.</div>';
    return;
  }
  root.classList.remove("loading-block");
  root.innerHTML = lessons.map((lesson) => `
    <details class="lesson-card">
      <summary>
        <span class="lesson-title">${esc(lesson.title_tr)}</span>
        <span class="lesson-open-hint">Aç ve öğren</span>
      </summary>
      <div class="lesson-body">
        <div>
          <div class="value-label">Bu nedir?</div>
          <p>${esc(lesson.beginner_tr)}</p>
        </div>
        <div>
          <div class="value-label">Neden önemli?</div>
          <p>${esc(lesson.why_it_matters_tr)}</p>
        </div>
        ${lesson.advanced_tr ? `
          <div class="lesson-advanced">
            <div class="value-label">Biraz daha derin</div>
            <p>${esc(lesson.advanced_tr)}</p>
          </div>
        ` : ""}
      </div>
    </details>
  `).join("");
}

async function loadAll() {
  clearNotice();
  const [health, command, radar, navigation, archive, performance, alerts, education, paperMission] = await Promise.all([
    fetchJSON("/api/health"),
    fetchJSON("/api/command-center?recent_limit=8"),
    fetchJSON("/api/market-radar"),
    fetchJSON("/api/navigation"),
    fetchJSON("/api/signals?limit=50&offset=0"),
    fetchJSON("/api/performance"),
    fetchJSON("/api/alerts?limit=50"),
    educationData ? Promise.resolve(educationData) : fetchJSON("/api/education"),
    fetchJSON("/api/paper/mission-control").catch((error) => ({
      status: "unavailable",
      reason: "paper_mission_control_read_error",
      detail: error.message,
      trade_policy: "NOT_ACTIVATED",
      real_capital: 0,
      read_only: true,
    })),
  ]);

  $("#healthChip").textContent = health.ledger_present ? "Kanıt deposu bağlı" : "Kanıt deposu yok";
  renderCommandCenter(command);
  renderPaperMissionControl(paperMission);
  renderPaperTradeArchive(paperMission);
  renderSystemHealth(health, command, paperMission);
  renderRadar(radar);
  renderArchive(archive);
  renderPerformance(performance);
  renderAlertCenter(alerts);
  renderEducation(education);
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
$("#refreshButton").addEventListener("click", () => refreshAll());
$("#closeDialog").addEventListener("click", () => $("#signalDialog").close());

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshAll();
});
window.addEventListener("online", () => refreshAll());
window.addEventListener("offline", () => {
  setLiveStatus("offline");
  updateFreshnessStatus();
});

startAutoRefresh();
refreshAll();
