from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from crypto_signal.decision_ledger import (
    DecisionLedgerConflictError,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.paper.epoch2_accounting import (
    Epoch2MetricsStatus,
    Epoch2VaultAccountingSnapshot,
    read_epoch2_state_read_only,
)
from crypto_signal.paper.epochs import PaperVaultId
from crypto_signal.paper.transaction_tape_atomic import R22Epoch2AtomicTape
from crypto_signal.product.event_source_runtime import (
    EventSourceCalendarCoverageTruth,
    EventSourceCalendarEventTruth,
    EventSourceCalendarRailTruth,
    read_event_source_calendar_rail,
)
from crypto_signal.product.intelligence_stream_exact_evidence import (
    IntelligenceStreamExactEvidenceReadModel,
    StreamExactEvidenceError,
)
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamMessageQuery,
    StreamReadModelError,
)
from crypto_signal.product.intelligence_stream_system_view import (
    verified_system_view_record,
)
from crypto_signal.product.models import ProductDataStatus
from crypto_signal.product.reader import DashboardReadError, DashboardReader

FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION = "final-product-read-model-v1/1"
DEFAULT_MARKET_PULSE_STALE_AFTER_MS = 15 * 60 * 1000
DEFAULT_EVENT_RAIL_FRESH_AFTER_MS = 30 * 60 * 1000
DEFAULT_CAPITAL_MOVEMENTS_LIMIT = 50
MAX_CAPITAL_MOVEMENTS_LIMIT = 200
DEFAULT_GLOBAL_SEARCH_LIMIT = 30
MAX_GLOBAL_SEARCH_LIMIT = 100
DEFAULT_ATTENTION_LIMIT = 5
MAX_ATTENTION_LIMIT = 20
_ATTENTION_SCAN_LIMIT = 200
REAL_CAPITAL = 0

_FAMILY_ORDER = {
    "geometry": 0,
    "geometry_pa_elliott_harmonic": 0,
    "liquidity": 1,
    "liquidity_structure": 1,
    "order_flow": 2,
    "order_flow_absorption": 2,
    "derivatives": 3,
    "derivatives_leverage": 3,
    "onchain": 4,
    "onchain_smart_money": 4,
}
_FAMILY_LABELS = {
    "geometry": "Geometri",
    "geometry_pa_elliott_harmonic": "Geometri",
    "liquidity": "Likidite",
    "liquidity_structure": "Likidite",
    "order_flow": "Emir Akışı",
    "order_flow_absorption": "Emir Akışı",
    "derivatives": "Türevler",
    "derivatives_leverage": "Türevler",
    "onchain": "On-chain",
    "onchain_smart_money": "On-chain",
}
_CATEGORY_LABELS = {
    "market": "Piyasa",
    "intelligence": "İstihbarat",
    "decision": "Karar",
    "capital": "Sermaye",
    "risk": "Risk",
    "outcome": "Sonuç",
    "system": "Sistem",
    "routine": "Rutin",
}
_IMPORTANCE_LABELS = {
    "critical": "Kritik",
    "important": "Önemli",
}
_EVIDENCE_DOMAIN_LABELS = {
    "geometry": "Geometri",
    "frozen_chart": "Dondurulmuş grafik",
    "order_book": "Emir defteri",
    "public_trades": "Gerçekleşen işlemler",
    "liquidity": "Likidite",
    "liquidity_structure": "Likidite yapısı",
    "liquidity_sweep": "Likidite süpürmesi",
    "order_flow": "Emir akışı",
    "order_flow_cvd": "Emir akışı / CVD",
    "derivatives": "Türevler",
    "liquidation_map": "Likidasyon haritası",
    "onchain": "On-chain",
    "stablecoin": "Stablecoin akışı",
    "event_context": "Event bağlamı",
    "methodology": "Metodoloji",
}
_STANCE_LABELS = {
    "bullish": "Yükseliş yönlü destek",
    "bearish": "Düşüş yönlü destek",
    "watch": "Karışık / izle",
    "blocked": "Event riski nedeniyle bloklu",
}
_DIRECTION_LABELS = {
    "bullish": "Yükseliş",
    "bearish": "Düşüş",
}
_EVENT_RISK_LABELS = {
    "event_block": "İşlem riski yüksek",
    "caution": "Dikkat",
    "abstain": "Event verisi yetersiz",
    "degraded_data": "Event verisi güncel değil",
    "healthy": "Normal",
}
_PROVIDER_QUALITY_LABELS = {
    "healthy": "Kaynaklar sağlıklı",
    "degraded_provider_stale": "Bir sağlayıcı güncel değil",
    "degraded": "Kaynak kalitesi düştü",
    "unavailable": "Kaynak verisi eksik",
    "unresolved": "Kaynak durumu kararsız",
}
_EVENT_CATEGORY_LABELS = {
    "inflation": "Enflasyon",
    "central_bank": "Merkez bankası",
    "employment": "İstihdam",
    "regulatory": "Düzenleme",
    "exchange_security": "Borsa güvenliği",
    "listing": "Listeleme",
    "delisting": "Listeden çıkarma",
    "other": "Diğer",
}
_EVENT_SOURCE_QUALITY_LABELS = {
    "official": "Resmî kaynak",
    "primary_provider": "Birincil sağlayıcı",
    "secondary_aggregator": "İkincil toplayıcı",
    "unverified": "Doğrulanmamış kaynak",
}
_EVENT_COVERAGE_LABELS = {
    "COMPLETE": "Takvim kapsamı doğrulandı",
    "INCOMPLETE": "Takvim kapsamı eksik",
    "UNAVAILABLE": "Takvim kapsamı kullanılamıyor",
    "SOURCE_SCOPED_ONLY": "Takvim kapsamı kaynak bazında",
}
_PORTFOLIO_VAULT_ORDER = {
    PaperVaultId.CORE: 0,
    PaperVaultId.TACTICAL: 1,
    PaperVaultId.OPPORTUNITY_RESERVE: 2,
}
_PORTFOLIO_VAULT_LABELS = {
    PaperVaultId.CORE: "Core",
    PaperVaultId.TACTICAL: "Taktik",
    PaperVaultId.OPPORTUNITY_RESERVE: "Fırsat Rezervi",
}


class FinalProductReadError(ValueError):
    """Raised when accepted source truth cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class MarketPulseFamilyAudit:
    source_narrative_identity: str | None
    source_evidence_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketPulseFamilyView:
    family: str
    family_label: str
    weight_points: str
    state_label: str
    direction_label: str | None
    relationship_label: str
    source_quality_label: str
    timeframe: str | None
    audit: MarketPulseFamilyAudit | None = None


@dataclass(frozen=True, slots=True)
class MarketPulseAudit:
    narrative_identity: str
    semantic_identity: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class MarketPulseAssetView:
    symbol: str
    timeframe: str
    updated_at_ms: int
    freshness_label: str
    stance_label: str
    support_score_0_100: str
    opposition_score_0_100: str
    evidence_coverage_0_100: str
    probability_label: str
    event_risk_label: str
    provider_quality_label: str
    trigger_zone: dict[str, Any] | None
    target_zone: dict[str, Any] | None
    invalidation_price: str | None
    main_contradiction_label: str | None
    summary: str
    families: tuple[MarketPulseFamilyView, ...]
    audit: MarketPulseAudit | None = None


@dataclass(frozen=True, slots=True)
class MarketPulseView:
    availability_label: str
    observed_at_ms: int
    source_label: str
    items: tuple[MarketPulseAssetView, ...]
    missing_symbols: tuple[str, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class AttentionAudit:
    narrative_identity: str
    story_identity: str | None
    source_event_identity: str | None
    message_identity: str | None
    materiality_decision_identity: str | None
    materiality_policy_identity: str | None


@dataclass(frozen=True, slots=True)
class AttentionSituationView:
    symbol: str
    timeframe: str
    updated_at_ms: int
    freshness_label: str
    category_label: str
    importance_label: str
    state_label: str | None
    headline: str
    detail: str
    materiality_label: str
    risk_label: str | None
    source_label: str
    audit: AttentionAudit | None = None


@dataclass(frozen=True, slots=True)
class AttentionSituationsView:
    availability_label: str
    observed_at_ms: int
    items: tuple[AttentionSituationView, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class FamilySummaryAudit:
    source_narrative_identity: str
    fact_bundle_identity: str
    analytical_view_identity: str
    source_evidence_identities: tuple[str, ...]
    raw_state_label: str
    uncertainty_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FamilySummaryItem:
    family_label: str
    state_label: str
    direction_label: str | None
    relationship_label: str
    source_quality_label: str
    source_as_of_ms: int | None
    freshness_label: str
    evidence_domain_labels: tuple[str, ...]
    uncertainty_label: str
    changed_label: str
    timeframe: str | None
    audit: FamilySummaryAudit | None = None


@dataclass(frozen=True, slots=True)
class FiveFamilySummaryView:
    availability_label: str
    symbol: str
    timeframe: str | None
    updated_at_ms: int | None
    stance_label: str | None
    families: tuple[FamilySummaryItem, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class WorkspaceAudit:
    narrative_identity: str
    detail_kind: str
    story_identity: str | None
    fact_bundle_identity: str | None
    analytical_view_identity: str | None
    forecast_identity: str | None
    proof_identity: str | None
    signal_freeze_identity: str | None
    evidence_resolution_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class WorkspaceSummaryView:
    availability_label: str
    message_kind_label: str
    symbol: str | None
    timeframe: str | None
    updated_at_ms: int | None
    source_as_of_ms: int | None
    freshness_label: str
    headline: str | None
    detail: str | None
    state_label: str | None
    direction_label: str | None
    support_balance_label: str | None
    trigger_zone: dict[str, Any] | None
    target_zone: dict[str, Any] | None
    invalidation_price: str | None
    main_contradiction_label: str | None
    event_risk_label: str | None
    uncertainty_label: str
    probability_label: str
    evidence_label: str
    decision_evidence_label: str
    capital_consequence_label: str | None
    resolution_label: str | None
    audit: WorkspaceAudit | None = None
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class EventRailItemAudit:
    event_identity: str


@dataclass(frozen=True, slots=True)
class EventRailCoverageAudit:
    coverage_identity: str


@dataclass(frozen=True, slots=True)
class EventRailAudit:
    raw_coverage_status: str
    latest_calendar_fetch_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventRailItem:
    title: str
    category_label: str
    scheduled_at_ms: int
    temporal_label: str
    affected_assets: tuple[str, ...]
    scope_label: str
    source_provider: str
    source_quality_label: str
    source_timestamp_ms: int
    freshness_label: str
    audit: EventRailItemAudit | None = None


@dataclass(frozen=True, slots=True)
class EventRailCoverageView:
    source_provider: str
    window_start_ms: int
    window_end_ms: int
    category_labels: tuple[str, ...]
    source_quality_label: str
    observed_at_ms: int
    freshness_label: str
    audit: EventRailCoverageAudit | None = None


@dataclass(frozen=True, slots=True)
class EventRailView:
    availability_label: str
    observed_at_ms: int
    window_start_ms: int
    window_end_ms: int
    asset: str | None
    coverage_label: str
    summary_label: str
    total_matching_events: int
    items: tuple[EventRailItem, ...]
    coverages: tuple[EventRailCoverageView, ...]
    audit: EventRailAudit | None = None
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PortfolioPositionView:
    symbol: str
    quantity: str


@dataclass(frozen=True, slots=True)
class PortfolioVaultAudit:
    snapshot_identity: str
    source_record_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioVaultView:
    vault_label: str
    starting_budget_usdt: str
    cash_usdt: str
    used_capital_usdt: str
    nav_usdt: str
    realized_pnl_usdt: str
    unrealized_pnl_usdt: str
    total_pnl_usdt: str
    current_drawdown_percent: str
    fee_usdt: str
    spread_usdt: str
    slippage_usdt: str
    turnover_percent: str
    open_position_count: int
    positions: tuple[PortfolioPositionView, ...]
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_label: str
    performance_status_label: str
    audit: PortfolioVaultAudit | None = None


@dataclass(frozen=True, slots=True)
class PortfolioAudit:
    activation_identity: str
    consolidated_snapshot_identity: str
    vault_snapshot_identities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioSummaryView:
    availability_label: str
    program_label: str
    snapshot_at_ms: int | None
    starting_capital_usdt: str | None
    current_equity_usdt: str | None
    cash_usdt: str | None
    used_capital_usdt: str | None
    realized_pnl_usdt: str | None
    unrealized_pnl_usdt: str | None
    total_pnl_usdt: str | None
    current_drawdown_percent: str | None
    fee_usdt: str | None
    spread_usdt: str | None
    slippage_usdt: str | None
    turnover_percent: str | None
    open_position_count: int
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    expectancy_label: str
    performance_status_label: str
    vaults: tuple[PortfolioVaultView, ...]
    audit: PortfolioAudit | None = None
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CapitalMovementAudit:
    narrative_identity: str
    story_identity: str
    source_event_identity: str
    stream_event_identity: str
    lineage_identities: tuple[str, ...]
    raw_subtype: str
    raw_action: str | None
    raw_disposition: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CapitalMovementItem:
    event_at_ms: int
    source_as_of_ms: int | None
    freshness_label: str
    vault_label: str | None
    symbol: str
    timeframe: str
    action_label: str
    headline: str
    detail: str
    quantity: str | None
    notional_usdt: str | None
    fraction_of_vault_percent: str | None
    current_cash_usdt: str | None
    current_nav_usdt: str | None
    cash_before_usdt: str | None
    cash_after_usdt: str | None
    vault_nav_before_usdt: str | None
    vault_nav_after_usdt: str | None
    consolidated_nav_before_usdt: str | None
    consolidated_nav_after_usdt: str | None
    fee_usdt: str | None
    spread_usdt: str | None
    slippage_usdt: str | None
    realized_pnl_delta_usdt: str | None
    outcome_label: str | None
    audit: CapitalMovementAudit | None = None


@dataclass(frozen=True, slots=True)
class CapitalMovementsView:
    availability_label: str
    observed_at_ms: int
    from_ms: int
    to_ms: int
    vault_label: str | None
    items: tuple[CapitalMovementItem, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class TradePassportAudit:
    bundle_identity: str
    activation_identity: str
    intent_identity: str
    fill_identity: str
    forecast_identity: str
    proof_identity: str
    signal_freeze_identity: str
    policy_identity: str
    sizing_assessment_identity: str
    sizing_decision_identity: str
    allocator_candidate_identity: str
    decision_identity: str
    source_evidence_identities: tuple[str, ...]
    source_fill_identity: str
    mutation_identity: str
    mark_evidence_identity: str
    outcome_identity: str | None
    before_vault_snapshot_identity: str
    after_vault_snapshot_identity: str
    before_consolidated_snapshot_identity: str
    after_consolidated_snapshot_identity: str
    raw_action: str
    raw_outcome: str
    reason_codes: tuple[str, ...]
    execution_policy_version: str
    venue_reference: str


@dataclass(frozen=True, slots=True)
class TradePassportView:
    availability_label: str
    program_label: str
    action_label: str | None
    outcome_label: str | None
    vault_label: str | None
    symbol: str | None
    timeframe: str | None
    decided_at_ms: int | None
    filled_at_ms: int | None
    snapshot_at_ms: int | None
    proof_source_as_of_ms: int | None
    decision_thesis: str | None
    direction_label: str | None
    trigger_zone_label: str | None
    target_zone_label: str | None
    invalidation_price: str | None
    uncertainty_label: str | None
    proof_availability_label: str
    quantity: str | None
    reference_price: str | None
    simulated_fill_price: str | None
    notional_usdt: str | None
    fee_usdt: str | None
    spread_usdt: str | None
    slippage_usdt: str | None
    cash_before_usdt: str | None
    cash_after_usdt: str | None
    vault_nav_before_usdt: str | None
    vault_nav_after_usdt: str | None
    consolidated_nav_before_usdt: str | None
    consolidated_nav_after_usdt: str | None
    position_quantity_before: str | None
    position_quantity_after: str | None
    realized_pnl_delta_usdt: str | None
    unrealized_pnl_delta_usdt: str | None
    audit: TradePassportAudit | None = None
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION



@dataclass(frozen=True, slots=True)
class ScreenerAudit:
    narrative_identity: str


@dataclass(frozen=True, slots=True)
class ScreenerRow:
    symbol: str
    timeframe: str
    updated_at_ms: int
    freshness_label: str
    stance_label: str
    support_score_0_100: str
    opposition_score_0_100: str
    evidence_coverage_0_100: str
    event_risk_label: str
    provider_quality_label: str
    main_contradiction_label: str | None
    summary: str
    family_state_labels: tuple[str, ...]
    audit: ScreenerAudit | None = None


@dataclass(frozen=True, slots=True)
class ScreenerView:
    availability_label: str
    observed_at_ms: int
    items: tuple[ScreenerRow, ...]
    missing_symbols: tuple[str, ...]
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class GlobalSearchAudit:
    source_identity: str
    stream_narrative_identity: str | None = None
    event_identity: str | None = None
    bundle_identity: str | None = None
    forecast_identity: str | None = None
    proof_identity: str | None = None
    signal_freeze_identity: str | None = None
    raw_category: str | None = None
    raw_subtype: str | None = None


@dataclass(frozen=True, slots=True)
class GlobalSearchItem:
    kind_label: str
    title: str
    summary: str
    symbol: str | None
    timestamp_ms: int | None
    source_label: str
    audit: GlobalSearchAudit | None = None


@dataclass(frozen=True, slots=True)
class GlobalSearchView:
    query: str
    items: tuple[GlobalSearchItem, ...]
    stream_coverage_label: str
    event_coverage_label: str
    trade_coverage_label: str
    proof_coverage_label: str
    direct_proof_identity_label: str = "Ham proof kimliği doğrudan aranamaz"
    read_only: bool = True
    real_capital: int = REAL_CAPITAL
    schema_version: str = FINAL_PRODUCT_READ_MODEL_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class _AttentionCandidate:
    dedupe_key: tuple[str, ...]
    importance_rank: int
    event_at_ms: int
    narrative_identity: str
    view: AttentionSituationView


class FinalProductReadModel:
    """Customer-safe, read-only projections over already accepted Product truth."""

    def __init__(
        self,
        *,
        stream_ledger_path: Path,
        decision_evidence_path: Path | None = None,
        signal_ledger_path: Path | None = None,
        event_source_runtime_path: Path | None = None,
        epoch2_path: Path | None = None,
    ) -> None:
        self.stream_ledger_path = stream_ledger_path
        self.decision_evidence_path = decision_evidence_path
        self.signal_ledger_path = signal_ledger_path
        self.event_source_runtime_path = event_source_runtime_path
        self.epoch2_path = epoch2_path

    def market_pulse(
        self,
        *,
        symbols: tuple[str, ...],
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> MarketPulseView:
        if observed_at_ms < 0:
            raise ValueError("market pulse observation time must be non-negative")
        if stale_after_ms <= 0:
            raise ValueError("market pulse stale_after_ms must be positive")
        normalized = _normalize_symbols(symbols)
        if not self.stream_ledger_path.is_file():
            return MarketPulseView(
                availability_label="Veri eksik",
                observed_at_ms=observed_at_ms,
                source_label="Crypto Signal Intelligence Stream",
                items=(),
                missing_symbols=normalized,
            )

        uri = f"{self.stream_ledger_path.resolve().as_uri()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                if not _table_exists(connection, "stream_system_view_messages"):
                    return MarketPulseView(
                        availability_label="Veri eksik",
                        observed_at_ms=observed_at_ms,
                        source_label="Crypto Signal Intelligence Stream",
                        items=(),
                        missing_symbols=normalized,
                    )
                rows = {
                    symbol: _latest_system_view_row(
                        connection,
                        symbol=symbol,
                        observed_at_ms=observed_at_ms,
                    )
                    for symbol in normalized
                }
        except sqlite3.DatabaseError as exc:
            raise FinalProductReadError(
                "market pulse source database cannot be read safely"
            ) from exc

        items: list[MarketPulseAssetView] = []
        missing: list[str] = []
        for symbol in normalized:
            row = rows[symbol]
            if row is None:
                missing.append(symbol)
                continue
            try:
                payload = verified_system_view_record(
                    narrative_identity=str(row[0]),
                    event_at_ms=_row_non_negative_int(row[1], "system-view event time"),
                    payload_json=str(row[2]),
                    expected_digest=str(row[3]),
                )
                items.append(
                    _market_pulse_asset(
                        payload,
                        observed_at_ms=observed_at_ms,
                        stale_after_ms=stale_after_ms,
                        include_audit=include_audit,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise FinalProductReadError(
                    f"market pulse source for {symbol} is semantically invalid"
                ) from exc

        availability = (
            "Veri eksik"
            if not items
            else "Kısmi veri"
            if missing
            else "Doğrulanmış veri"
        )
        return MarketPulseView(
            availability_label=availability,
            observed_at_ms=observed_at_ms,
            source_label="Crypto Signal Intelligence Stream",
            items=tuple(items),
            missing_symbols=tuple(missing),
        )

    def attention_situations(
        self,
        *,
        observed_at_ms: int,
        limit: int = DEFAULT_ATTENTION_LIMIT,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> AttentionSituationsView:
        if observed_at_ms < 0:
            raise ValueError("attention observation time must be non-negative")
        if limit < 1 or limit > MAX_ATTENTION_LIMIT:
            raise ValueError(
                f"attention limit must be inside 1..{MAX_ATTENTION_LIMIT}"
            )
        if stale_after_ms <= 0:
            raise ValueError("attention stale_after_ms must be positive")
        if not self.stream_ledger_path.is_file():
            return AttentionSituationsView(
                availability_label="Veri eksik",
                observed_at_ms=observed_at_ms,
                items=(),
            )

        reader = IntelligenceStreamReadModel(self.stream_ledger_path)
        try:
            page = reader.read_messages(
                StreamMessageQuery(
                    limit=_ATTENTION_SCAN_LIMIT,
                    to_ms=observed_at_ms,
                )
            )
            candidates: dict[tuple[str, ...], _AttentionCandidate] = {}
            for record in page.items:
                narrative_identity = _required_sha(record, "narrative_identity")
                detail = reader.read_message_detail(narrative_identity)
                if detail is None:
                    raise FinalProductReadError(
                        "attention source disappeared during verified read"
                    )
                candidate = _attention_candidate(
                    detail,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
                if candidate is None:
                    continue
                previous = candidates.get(candidate.dedupe_key)
                if previous is None or (
                    candidate.event_at_ms,
                    candidate.narrative_identity,
                ) > (
                    previous.event_at_ms,
                    previous.narrative_identity,
                ):
                    candidates[candidate.dedupe_key] = candidate
        except (
            FileNotFoundError,
            StreamReadModelError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "attention source cannot be projected safely"
            ) from exc

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                item.importance_rank,
                item.event_at_ms,
                item.narrative_identity,
            ),
            reverse=True,
        )
        items = tuple(item.view for item in ordered[:limit])
        return AttentionSituationsView(
            availability_label=(
                "Dikkat gerektiren durum yok"
                if not items
                else "Doğrulanmış veri"
            ),
            observed_at_ms=observed_at_ms,
            items=items,
        )

    def five_family_summary(
        self,
        *,
        symbol: str,
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> FiveFamilySummaryView:
        if observed_at_ms < 0:
            raise ValueError("family summary observation time must be non-negative")
        if stale_after_ms <= 0:
            raise ValueError("family summary stale_after_ms must be positive")
        normalized = _normalize_symbols((symbol,))[0]
        if not self.stream_ledger_path.is_file():
            return FiveFamilySummaryView(
                availability_label="Veri eksik",
                symbol=normalized,
                timeframe=None,
                updated_at_ms=None,
                stance_label=None,
                families=(),
            )

        try:
            payload = _latest_verified_system_view(
                self.stream_ledger_path,
                symbol=normalized,
                observed_at_ms=observed_at_ms,
            )
            if payload is None:
                return FiveFamilySummaryView(
                    availability_label="Veri eksik",
                    symbol=normalized,
                    timeframe=None,
                    updated_at_ms=None,
                    stance_label=None,
                    families=(),
                )
            fact = _required_mapping(payload, "fact_bundle")
            analytical = _required_mapping(payload, "analytical_view")
            stance = _required_mapping(analytical, "stance")
            raw_stance = _required_text(stance, "effective_stance")
            reader = IntelligenceStreamReadModel(self.stream_ledger_path)
            rows = sorted(
                (
                    _mapping_value(value, "family contribution")
                    for value in _required_sequence(fact, "family_contributions")
                ),
                key=lambda value: (
                    _FAMILY_ORDER.get(str(value.get("family")), 99),
                    str(value.get("family")),
                ),
            )
            families = tuple(
                _enriched_family_summary(
                    row,
                    raw_stance=raw_stance,
                    reader=reader,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
                for row in rows
            )
            return FiveFamilySummaryView(
                availability_label="Doğrulanmış veri",
                symbol=normalized,
                timeframe=_required_text(payload, "timeframe"),
                updated_at_ms=_required_int(payload, "event_at_ms"),
                stance_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
                families=families,
            )
        except (
            sqlite3.DatabaseError,
            StreamReadModelError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "five-family source cannot be projected safely"
            ) from exc

    def workspace_summary(
        self,
        *,
        narrative_identity: str,
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> WorkspaceSummaryView:
        _sha_text(narrative_identity, "workspace narrative identity")
        if observed_at_ms < 0:
            raise ValueError("workspace observation time must be non-negative")
        if stale_after_ms <= 0:
            raise ValueError("workspace stale_after_ms must be positive")
        if not self.stream_ledger_path.is_file():
            return _workspace_unavailable(
                availability_label="Veri eksik",
                message_kind_label="Çalışma alanı",
            )

        reader = IntelligenceStreamReadModel(self.stream_ledger_path)
        try:
            detail = reader.read_message_detail(narrative_identity)
        except StreamReadModelError as exc:
            raise FinalProductReadError(
                "workspace Stream source cannot be read safely"
            ) from exc
        if detail is None:
            return _workspace_unavailable(
                availability_label="Mesaj bulunamadı",
                message_kind_label="Çalışma alanı",
            )

        capital_kind = _capital_detail_kind(detail)
        if capital_kind is not None:
            return _workspace_capital_deferred(
                detail,
                capital_kind=capital_kind,
                observed_at_ms=observed_at_ms,
                stale_after_ms=stale_after_ms,
                include_audit=include_audit,
            )

        if "system_view" in detail:
            try:
                return _workspace_system_view(
                    detail,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, FinalProductReadError):
                    raise
                raise FinalProductReadError(
                    "system-view workspace source is invalid"
                ) from exc

        try:
            fact = _required_mapping(detail, "fact_bundle")
            if isinstance(fact.get("projector_id"), str):
                evidence = self._workspace_exact_evidence(
                    narrative_identity=narrative_identity,
                )
                return _workspace_family(
                    detail,
                    evidence=evidence,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )

            evidence = self._workspace_exact_evidence(
                narrative_identity=narrative_identity,
            )
            proof, proof_label = self._workspace_decision_proof(fact)
            return _workspace_decision(
                detail,
                evidence=evidence,
                decision_proof=proof,
                decision_evidence_label=proof_label,
                observed_at_ms=observed_at_ms,
                stale_after_ms=stale_after_ms,
                include_audit=include_audit,
            )
        except (
            DecisionLedgerConflictError,
            StreamExactEvidenceError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "workspace source cannot be projected safely"
            ) from exc

    def event_rail(
        self,
        *,
        observed_at_ms: int,
        window_start_ms: int,
        window_end_ms: int,
        asset: str | None = None,
        categories: tuple[str, ...] = (),
        limit: int = 50,
        fresh_after_ms: int = DEFAULT_EVENT_RAIL_FRESH_AFTER_MS,
        include_audit: bool = False,
    ) -> EventRailView:
        if fresh_after_ms <= 0:
            raise ValueError("event rail fresh_after_ms must be positive")
        if (
            self.event_source_runtime_path is None
            or not self.event_source_runtime_path.is_file()
        ):
            return EventRailView(
                availability_label="Veri eksik",
                observed_at_ms=observed_at_ms,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                asset=None if asset is None else asset.strip().upper(),
                coverage_label="Takvim kapsamı kullanılamıyor",
                summary_label="Planlı olay verisi doğrulanamadı",
                total_matching_events=0,
                items=(),
                coverages=(),
            )
        try:
            truth = read_event_source_calendar_rail(
                self.event_source_runtime_path,
                observed_at_ms=observed_at_ms,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                asset=asset,
                categories=categories,
                limit=limit,
            )
            return _event_rail_view(
                truth,
                fresh_after_ms=fresh_after_ms,
                include_audit=include_audit,
            )
        except (TypeError, ValueError) as exc:
            raise FinalProductReadError(
                "event rail source cannot be projected safely"
            ) from exc

    def portfolio_summary(
        self,
        *,
        include_audit: bool = False,
    ) -> PortfolioSummaryView:
        if self.epoch2_path is None or not self.epoch2_path.is_file():
            return _portfolio_unavailable("Epoch 2 portföy verisi kullanılamıyor")
        try:
            state = read_epoch2_state_read_only(self.epoch2_path)
        except ValueError as exc:
            raise FinalProductReadError(
                "Epoch 2 portföy kaynağı güvenli okunamadı"
            ) from exc
        if state is None:
            return _portfolio_unavailable("Epoch 2 henüz etkin değil")

        consolidated = state.consolidated_snapshot
        ordered_vaults = tuple(
            sorted(
                state.vault_snapshots,
                key=lambda item: _PORTFOLIO_VAULT_ORDER[item.vault_id],
            )
        )
        vaults = tuple(
            _portfolio_vault_view(item, include_audit=include_audit)
            for item in ordered_vaults
        )
        total_pnl = (
            consolidated.realized_pnl_usdt
            + consolidated.unrealized_pnl_usdt
        )
        audit = None
        if include_audit:
            audit = PortfolioAudit(
                activation_identity=state.activation.activation_identity,
                consolidated_snapshot_identity=consolidated.snapshot_identity,
                vault_snapshot_identities=tuple(
                    item.snapshot_identity
                    for item in ordered_vaults
                ),
            )
        return PortfolioSummaryView(
            availability_label="Doğrulanmış veri",
            program_label="Paper Capital · Epoch 2",
            snapshot_at_ms=consolidated.snapshot_at_ms,
            starting_capital_usdt=_money_text(
                state.activation.starting_cash_usdt
            ),
            current_equity_usdt=_money_text(consolidated.nav_usdt),
            cash_usdt=_money_text(consolidated.cash_usdt),
            used_capital_usdt=_money_text(
                consolidated.marked_exposure_usdt
            ),
            realized_pnl_usdt=_signed_money_text(
                consolidated.realized_pnl_usdt
            ),
            unrealized_pnl_usdt=_signed_money_text(
                consolidated.unrealized_pnl_usdt
            ),
            total_pnl_usdt=_signed_money_text(total_pnl),
            current_drawdown_percent=_fraction_percent_text(
                consolidated.drawdown_fraction
            ),
            fee_usdt=_money_text(consolidated.fee_usdt),
            spread_usdt=_money_text(consolidated.spread_usdt),
            slippage_usdt=_money_text(consolidated.slippage_usdt),
            turnover_percent=_fraction_percent_text(
                consolidated.turnover_fraction
            ),
            open_position_count=sum(
                len(item.positions)
                for item in ordered_vaults
            ),
            closed_trade_count=consolidated.closed_trade_count,
            win_count=consolidated.win_count,
            loss_count=consolidated.loss_count,
            breakeven_count=consolidated.breakeven_count,
            expectancy_label=_expectancy_label(
                consolidated.metrics_status,
                consolidated.expectancy_usdt_per_closed_trade,
            ),
            performance_status_label=_metrics_status_label(
                consolidated.metrics_status
            ),
            vaults=vaults,
            audit=audit,
        )

    def capital_movements(
        self,
        *,
        observed_at_ms: int,
        from_ms: int,
        to_ms: int,
        vault: str | None = None,
        limit: int = DEFAULT_CAPITAL_MOVEMENTS_LIMIT,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> CapitalMovementsView:
        if observed_at_ms < 0:
            raise ValueError("capital movements observation time must be non-negative")
        if from_ms < 0 or to_ms < 0 or from_ms > to_ms:
            raise ValueError("capital movements time window is invalid")
        if to_ms > observed_at_ms:
            raise ValueError("capital movements cannot read future event time")
        if stale_after_ms <= 0:
            raise ValueError("capital movements stale_after_ms must be positive")
        if limit < 1 or limit > MAX_CAPITAL_MOVEMENTS_LIMIT:
            raise ValueError(
                "capital movements limit must be inside "
                f"1..{MAX_CAPITAL_MOVEMENTS_LIMIT}"
            )
        normalized_vault = None
        if vault is not None:
            try:
                normalized_vault = PaperVaultId(vault.strip().upper()).value
            except (ValueError, AttributeError) as exc:
                raise ValueError("capital movements vault is invalid") from exc

        if not self.stream_ledger_path.is_file():
            return CapitalMovementsView(
                availability_label="Sermaye hareketleri verisi kullanılamıyor",
                observed_at_ms=observed_at_ms,
                from_ms=from_ms,
                to_ms=to_ms,
                vault_label=_capital_vault_label(normalized_vault),
                items=(),
            )

        reader = IntelligenceStreamReadModel(self.stream_ledger_path)
        try:
            page = reader.read_messages(
                StreamMessageQuery(
                    limit=limit,
                    category="capital",
                    vault=normalized_vault,
                    from_ms=from_ms,
                    to_ms=to_ms,
                )
            )
            items = tuple(
                _capital_movement_item(
                    record,
                    observed_at_ms=observed_at_ms,
                    stale_after_ms=stale_after_ms,
                    include_audit=include_audit,
                )
                for record in page.items
            )
        except (StreamReadModelError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "capital movements source cannot be projected safely"
            ) from exc

        return CapitalMovementsView(
            availability_label=(
                "Doğrulanmış veri"
                if items
                else "Bu aralıkta sermaye hareketi yok"
            ),
            observed_at_ms=observed_at_ms,
            from_ms=from_ms,
            to_ms=to_ms,
            vault_label=_capital_vault_label(normalized_vault),
            items=items,
        )

    def trade_passport(
        self,
        *,
        bundle_identity: str,
        include_audit: bool = False,
    ) -> TradePassportView:
        _sha_text(bundle_identity, "trade passport bundle identity")
        if self.epoch2_path is None or not self.epoch2_path.is_file():
            return _trade_passport_unavailable(
                "Trade Passport verisi kullanılamıyor"
            )

        try:
            context = cast(
                dict[str, Any],
                R22Epoch2AtomicTape(
                    self.epoch2_path
                ).read_bundle_story_context(bundle_identity),
            )
        except ValueError as exc:
            if str(exc) == "R22 audit bundle not found":
                return _trade_passport_unavailable(
                    "Trade Passport bulunamadı"
                )
            raise FinalProductReadError(
                "Trade Passport kaynağı güvenli doğrulanamadı"
            ) from exc

        try:
            intent = _required_mapping(context, "intent")
            forecast_identity = _required_sha(intent, "forecast_identity")
            expected_proof_identity = _required_sha(intent, "proof_identity")
            expected_signal_identity = _required_sha(
                intent,
                "signal_freeze_identity",
            )

            proof: dict[str, Any] | None = None
            proof_label = "Karar kanıtı kaynağı bağlı değil"
            if (
                self.decision_evidence_path is not None
                and self.decision_evidence_path.is_file()
            ):
                proof = ImmutableDecisionEvidenceLedger(
                    self.decision_evidence_path
                ).read_proof_for_forecast(forecast_identity)
                if proof is None:
                    proof_label = "Karar kanıtı bulunamadı"
                else:
                    if (
                        proof.get("forecast_identity") != forecast_identity
                        or proof.get("proof_identity")
                        != expected_proof_identity
                        or proof.get("signal_freeze_identity")
                        != expected_signal_identity
                        or proof.get("read_only") is not True
                        or proof.get("production_authority") is not False
                        or proof.get("real_capital") != REAL_CAPITAL
                    ):
                        raise FinalProductReadError(
                            "Trade Passport karar kanıtı lineage uyuşmuyor"
                        )
                    proof_label = "Karar kanıtı doğrulandı"

            return _trade_passport_view(
                bundle_identity=bundle_identity,
                context=context,
                proof=proof,
                proof_label=proof_label,
                include_audit=include_audit,
            )
        except (
            DecisionLedgerConflictError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            if isinstance(exc, FinalProductReadError):
                raise
            raise FinalProductReadError(
                "Trade Passport güvenli projekte edilemedi"
            ) from exc

    def screener(
        self,
        *,
        symbols: tuple[str, ...],
        observed_at_ms: int,
        stale_after_ms: int = DEFAULT_MARKET_PULSE_STALE_AFTER_MS,
        include_audit: bool = False,
    ) -> ScreenerView:
        pulse = self.market_pulse(
            symbols=symbols,
            observed_at_ms=observed_at_ms,
            stale_after_ms=stale_after_ms,
            include_audit=True,
        )
        rows = tuple(
            ScreenerRow(
                symbol=item.symbol,
                timeframe=item.timeframe,
                updated_at_ms=item.updated_at_ms,
                freshness_label=item.freshness_label,
                stance_label=item.stance_label,
                support_score_0_100=item.support_score_0_100,
                opposition_score_0_100=item.opposition_score_0_100,
                evidence_coverage_0_100=item.evidence_coverage_0_100,
                event_risk_label=item.event_risk_label,
                provider_quality_label=item.provider_quality_label,
                main_contradiction_label=item.main_contradiction_label,
                summary=item.summary,
                family_state_labels=tuple(
                    f"{family.family_label}: {family.state_label}"
                    for family in item.families
                ),
                audit=(
                    ScreenerAudit(
                        narrative_identity=item.audit.narrative_identity
                    )
                    if include_audit and item.audit is not None
                    else None
                ),
            )
            for item in sorted(
                pulse.items,
                key=lambda value: (value.symbol, value.timeframe),
            )
        )
        return ScreenerView(
            availability_label=pulse.availability_label,
            observed_at_ms=observed_at_ms,
            items=rows,
            missing_symbols=pulse.missing_symbols,
        )

    def global_search(
        self,
        *,
        query: str,
        configured_symbols: tuple[str, ...],
        observed_at_ms: int,
        event_window_start_ms: int,
        event_window_end_ms: int,
        limit: int = DEFAULT_GLOBAL_SEARCH_LIMIT,
        include_audit: bool = False,
    ) -> GlobalSearchView:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("global search query cannot be blank")
        if observed_at_ms < 0:
            raise ValueError("global search observation time must be non-negative")
        if (
            event_window_start_ms < 0
            or event_window_end_ms < 0
            or event_window_start_ms > event_window_end_ms
        ):
            raise ValueError("global search event window is invalid")
        if limit < 1 or limit > MAX_GLOBAL_SEARCH_LIMIT:
            raise ValueError(
                f"global search limit must be inside 1..{MAX_GLOBAL_SEARCH_LIMIT}"
            )

        symbols = _normalize_symbols(configured_symbols)
        lowered = normalized_query.casefold()
        exact_identity = _looks_like_sha256(normalized_query)
        candidates: list[
            tuple[
                int,
                int,
                int,
                str,
                str,
                tuple[str, str],
                GlobalSearchItem,
            ]
        ] = []

        stream_coverage = (
            "Stream araması kullanılabilir"
            if self.stream_ledger_path.is_file()
            else "Stream araması kullanılamıyor"
        )
        event_coverage = (
            "Olay araması kullanılabilir"
            if self.event_source_runtime_path is not None
            and self.event_source_runtime_path.is_file()
            else "Olay araması kullanılamıyor"
        )
        trade_coverage = (
            "Trade Passport araması kullanılabilir"
            if self.epoch2_path is not None and self.epoch2_path.is_file()
            else "Trade Passport araması kullanılamıyor"
        )
        proof_coverage = (
            "Karar kanıtı araması kullanılabilir"
            if self.decision_evidence_path is not None
            and self.decision_evidence_path.is_file()
            else "Karar kanıtı araması kullanılamıyor"
        )

        try:
            screener = self.screener(
                symbols=symbols,
                observed_at_ms=observed_at_ms,
                include_audit=True,
            )
            for row in screener.items:
                base_asset = (
                    row.symbol[:-4]
                    if row.symbol.endswith("USDT")
                    else row.symbol
                )
                exact_asset = lowered in {
                    row.symbol.casefold(),
                    base_asset.casefold(),
                }
                partial_asset = (
                    lowered in row.symbol.casefold()
                    or lowered in base_asset.casefold()
                )
                if not partial_asset:
                    continue
                source_identity = (
                    row.audit.narrative_identity
                    if row.audit is not None
                    else row.symbol
                )
                item = GlobalSearchItem(
                    kind_label="Varlık",
                    title=f"{row.symbol} · {row.stance_label}",
                    summary=row.summary,
                    symbol=row.symbol,
                    timestamp_ms=row.updated_at_ms,
                    source_label="Crypto Signal Screener",
                    audit=(
                        GlobalSearchAudit(
                            source_identity=source_identity,
                            stream_narrative_identity=(
                                row.audit.narrative_identity
                                if row.audit is not None
                                else None
                            ),
                        )
                        if include_audit
                        else None
                    ),
                )
                _append_search_candidate(
                    candidates,
                    priority=1 if exact_asset else 2,
                    item=item,
                    source_key=("asset", source_identity),
                )
        except FinalProductReadError:
            stream_coverage = "Stream araması doğrulanamadı"

        if self.stream_ledger_path.is_file():
            reader = IntelligenceStreamReadModel(self.stream_ledger_path)
            try:
                page_limit = min(100, max(20, limit * 3))
                stream_records: dict[str, dict[str, Any]] = {}
                for record in reader.read_messages(
                    StreamMessageQuery(
                        limit=page_limit,
                        text=normalized_query,
                    )
                ).items:
                    stream_records[
                        _required_sha(record, "narrative_identity")
                    ] = record

                normalized_symbol = normalized_query.upper()
                if normalized_symbol in symbols:
                    for record in reader.read_messages(
                        StreamMessageQuery(
                            limit=page_limit,
                            symbol=normalized_symbol,
                        )
                    ).items:
                        stream_records[
                            _required_sha(record, "narrative_identity")
                        ] = record

                if exact_identity:
                    exact_record = reader.read_message(normalized_query)
                    if exact_record is not None:
                        stream_records[
                            _required_sha(
                                exact_record,
                                "narrative_identity",
                            )
                        ] = exact_record

                for narrative_identity, record in stream_records.items():
                    item, source_key = _global_search_stream_item(
                        record,
                        include_audit=include_audit,
                    )
                    _append_search_candidate(
                        candidates,
                        priority=(
                            0
                            if exact_identity
                            and narrative_identity == normalized_query
                            else 2
                        ),
                        item=item,
                        source_key=source_key,
                    )
            except (FileNotFoundError, StreamReadModelError, KeyError, TypeError, ValueError):
                stream_coverage = "Stream araması doğrulanamadı"

        if (
            self.event_source_runtime_path is not None
            and self.event_source_runtime_path.is_file()
        ):
            try:
                rail = self.event_rail(
                    observed_at_ms=observed_at_ms,
                    window_start_ms=event_window_start_ms,
                    window_end_ms=event_window_end_ms,
                    limit=200,
                    include_audit=True,
                )
                for event in rail.items:
                    event_identity = (
                        event.audit.event_identity
                        if event.audit is not None
                        else ""
                    )
                    exact_event = (
                        exact_identity
                        and event_identity == normalized_query
                    )
                    haystack = " ".join(
                        (
                            event.title,
                            event.category_label,
                            event.source_provider,
                            *event.affected_assets,
                        )
                    ).casefold()
                    if not exact_event and lowered not in haystack:
                        continue
                    item = GlobalSearchItem(
                        kind_label="Olay",
                        title=event.title,
                        summary=(
                            f"{event.category_label} · "
                            f"{event.temporal_label} · {event.scope_label}"
                        ),
                        symbol=(
                            event.affected_assets[0]
                            if len(event.affected_assets) == 1
                            else None
                        ),
                        timestamp_ms=event.scheduled_at_ms,
                        source_label=event.source_provider,
                        audit=(
                            GlobalSearchAudit(
                                source_identity=event_identity,
                                event_identity=event_identity,
                            )
                            if include_audit and event_identity
                            else None
                        ),
                    )
                    _append_search_candidate(
                        candidates,
                        priority=0 if exact_event else 3,
                        item=item,
                        source_key=("event", event_identity or event.title),
                    )
            except FinalProductReadError:
                event_coverage = "Olay araması doğrulanamadı"

        if exact_identity and self.signal_ledger_path is not None:
            if self.signal_ledger_path.is_file():
                try:
                    detail = DashboardReader(
                        self.signal_ledger_path
                    ).signal_detail(normalized_query)
                    if (
                        detail.status is ProductDataStatus.READY
                        and detail.signal is not None
                    ):
                        signal = detail.signal
                        item = GlobalSearchItem(
                            kind_label="Kanıt",
                            title=(
                                f"{signal.symbol} · "
                                f"{signal.direction.value}"
                            ),
                            summary=(
                                f"{signal.setup_type} · "
                                f"{signal.state.value} · {signal.timeframe}"
                            ),
                            symbol=signal.symbol,
                            timestamp_ms=signal.frozen_at_ms,
                            source_label="Frozen Signal Archive",
                            audit=(
                                GlobalSearchAudit(
                                    source_identity=signal.signal_freeze_identity,
                                    signal_freeze_identity=(
                                        signal.signal_freeze_identity
                                    ),
                                )
                                if include_audit
                                else None
                            ),
                        )
                        _append_search_candidate(
                            candidates,
                            priority=0,
                            item=item,
                            source_key=(
                                "signal",
                                signal.signal_freeze_identity,
                            ),
                        )
                except (DashboardReadError, ValueError):
                    stream_coverage = "Signal araması doğrulanamadı"

        if exact_identity and self.epoch2_path is not None and self.epoch2_path.is_file():
            try:
                passport = self.trade_passport(
                    bundle_identity=normalized_query,
                    include_audit=True,
                )
                if passport.availability_label == "Doğrulanmış veri":
                    item = GlobalSearchItem(
                        kind_label="İşlem",
                        title=(
                            f"{passport.symbol or 'İşlem'} · "
                            f"{passport.action_label or 'Trade Passport'}"
                        ),
                        summary=" · ".join(
                            value
                            for value in (
                                passport.outcome_label,
                                passport.vault_label,
                                passport.proof_availability_label,
                            )
                            if value
                        ),
                        symbol=passport.symbol,
                        timestamp_ms=passport.filled_at_ms,
                        source_label="Paper Capital · Epoch 2",
                        audit=(
                            GlobalSearchAudit(
                                source_identity=normalized_query,
                                bundle_identity=normalized_query,
                                forecast_identity=(
                                    passport.audit.forecast_identity
                                    if passport.audit is not None
                                    else None
                                ),
                                proof_identity=(
                                    passport.audit.proof_identity
                                    if passport.audit is not None
                                    else None
                                ),
                                signal_freeze_identity=(
                                    passport.audit.signal_freeze_identity
                                    if passport.audit is not None
                                    else None
                                ),
                            )
                            if include_audit
                            else None
                        ),
                    )
                    _append_search_candidate(
                        candidates,
                        priority=0,
                        item=item,
                        source_key=("trade", normalized_query),
                    )
            except FinalProductReadError:
                trade_coverage = "Trade Passport araması doğrulanamadı"

        if (
            exact_identity
            and self.decision_evidence_path is not None
            and self.decision_evidence_path.is_file()
        ):
            try:
                ledger = ImmutableDecisionEvidenceLedger(
                    self.decision_evidence_path
                )
                issuance = ledger.read_issuance_for_signal(
                    normalized_query
                )
                proof: dict[str, Any] | None = None
                if issuance is not None:
                    _, proof = issuance
                else:
                    proof = ledger.read_proof_for_forecast(
                        normalized_query
                    )
                if proof is not None:
                    proof_identity = _required_sha(
                        proof,
                        "proof_identity",
                    )
                    forecast_identity = _required_sha(
                        proof,
                        "forecast_identity",
                    )
                    signal_identity = _required_sha(
                        proof,
                        "signal_freeze_identity",
                    )
                    symbol = _required_text(proof, "symbol")
                    item = GlobalSearchItem(
                        kind_label="Kanıt",
                        title=f"{symbol} · Karar kanıtı",
                        summary=_required_text(
                            proof,
                            "conditional_thesis",
                        ),
                        symbol=symbol,
                        timestamp_ms=_required_int(
                            proof,
                            "issued_at_ms",
                        ),
                        source_label="Decision Evidence",
                        audit=(
                            GlobalSearchAudit(
                                source_identity=proof_identity,
                                forecast_identity=forecast_identity,
                                proof_identity=proof_identity,
                                signal_freeze_identity=signal_identity,
                            )
                            if include_audit
                            else None
                        ),
                    )
                    _append_search_candidate(
                        candidates,
                        priority=0,
                        item=item,
                        source_key=("proof", proof_identity),
                    )
            except (
                DecisionLedgerConflictError,
                KeyError,
                TypeError,
                ValueError,
            ):
                proof_coverage = "Karar kanıtı araması doğrulanamadı"

        ordered = _ordered_search_items(candidates, limit=limit)
        return GlobalSearchView(
            query=normalized_query,
            items=ordered,
            stream_coverage_label=stream_coverage,
            event_coverage_label=event_coverage,
            trade_coverage_label=trade_coverage,
            proof_coverage_label=proof_coverage,
        )

    def _workspace_exact_evidence(
        self,
        *,
        narrative_identity: str,
    ) -> dict[str, Any] | None:
        signal_path = (
            self.signal_ledger_path
            if self.signal_ledger_path is not None
            and self.signal_ledger_path.is_file()
            else None
        )
        decision_path = (
            self.decision_evidence_path
            if self.decision_evidence_path is not None
            and self.decision_evidence_path.is_file()
            else None
        )
        return IntelligenceStreamExactEvidenceReadModel(
            stream_ledger_path=self.stream_ledger_path,
            signal_ledger_path=signal_path,
            decision_evidence_path=decision_path,
        ).read_for_narrative(narrative_identity)

    def _workspace_decision_proof(
        self,
        fact: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        forecast_identity = _required_sha(fact, "forecast_identity")
        expected_proof_identity = _required_sha(fact, "proof_identity")
        if (
            self.decision_evidence_path is None
            or not self.decision_evidence_path.is_file()
        ):
            return None, "Ek karar kanıtı kaynağı bağlı değil"

        proof = ImmutableDecisionEvidenceLedger(
            self.decision_evidence_path
        ).read_proof_for_forecast(forecast_identity)
        if proof is None:
            return None, "Ek karar kanıtı bulunamadı"
        if proof.get("forecast_identity") != forecast_identity:
            raise FinalProductReadError(
                "Decision Evidence forecast lineage mismatch"
            )
        if proof.get("proof_identity") != expected_proof_identity:
            raise FinalProductReadError(
                "Decision Evidence proof lineage mismatch"
            )
        return proof, "Ek karar kanıtı doğrulandı"


def _portfolio_unavailable(reason: str) -> PortfolioSummaryView:
    return PortfolioSummaryView(
        availability_label=reason,
        program_label="Paper Capital · Epoch 2",
        snapshot_at_ms=None,
        starting_capital_usdt=None,
        current_equity_usdt=None,
        cash_usdt=None,
        used_capital_usdt=None,
        realized_pnl_usdt=None,
        unrealized_pnl_usdt=None,
        total_pnl_usdt=None,
        current_drawdown_percent=None,
        fee_usdt=None,
        spread_usdt=None,
        slippage_usdt=None,
        turnover_percent=None,
        open_position_count=0,
        closed_trade_count=0,
        win_count=0,
        loss_count=0,
        breakeven_count=0,
        expectancy_label="Henüz ölçülmedi",
        performance_status_label="Henüz ölçülmedi",
        vaults=(),
    )


def _portfolio_vault_view(
    snapshot: Epoch2VaultAccountingSnapshot,
    *,
    include_audit: bool,
) -> PortfolioVaultView:
    positions = tuple(
        PortfolioPositionView(
            symbol=item.symbol.value,
            quantity=_plain_decimal_text(item.quantity),
        )
        for item in snapshot.positions
    )
    total_pnl = snapshot.realized_pnl_usdt + snapshot.unrealized_pnl_usdt
    audit = None
    if include_audit:
        audit = PortfolioVaultAudit(
            snapshot_identity=snapshot.snapshot_identity,
            source_record_identities=snapshot.source_record_identities,
        )
    return PortfolioVaultView(
        vault_label=_PORTFOLIO_VAULT_LABELS[snapshot.vault_id],
        starting_budget_usdt=_money_text(snapshot.starting_cash_usdt),
        cash_usdt=_money_text(snapshot.cash_usdt),
        used_capital_usdt=_money_text(snapshot.marked_exposure_usdt),
        nav_usdt=_money_text(snapshot.nav_usdt),
        realized_pnl_usdt=_signed_money_text(snapshot.realized_pnl_usdt),
        unrealized_pnl_usdt=_signed_money_text(
            snapshot.unrealized_pnl_usdt
        ),
        total_pnl_usdt=_signed_money_text(total_pnl),
        current_drawdown_percent=_fraction_percent_text(
            snapshot.drawdown_fraction
        ),
        fee_usdt=_money_text(snapshot.fee_usdt),
        spread_usdt=_money_text(snapshot.spread_usdt),
        slippage_usdt=_money_text(snapshot.slippage_usdt),
        turnover_percent=_fraction_percent_text(snapshot.turnover_fraction),
        open_position_count=len(snapshot.positions),
        positions=positions,
        closed_trade_count=snapshot.closed_trade_count,
        win_count=snapshot.win_count,
        loss_count=snapshot.loss_count,
        breakeven_count=snapshot.breakeven_count,
        expectancy_label=_expectancy_label(
            snapshot.metrics_status,
            snapshot.expectancy_usdt_per_closed_trade,
        ),
        performance_status_label=_metrics_status_label(
            snapshot.metrics_status
        ),
        audit=audit,
    )


def _metrics_status_label(status: Epoch2MetricsStatus) -> str:
    if status is Epoch2MetricsStatus.AVAILABLE:
        return "Ölçülebilir"
    return "Henüz ölçülmedi"


def _expectancy_label(
    status: Epoch2MetricsStatus,
    value: Decimal | None,
) -> str:
    if status is not Epoch2MetricsStatus.AVAILABLE or value is None:
        return "Henüz ölçülmedi"
    return f"{_signed_money_text(value)} / kapalı işlem"


def _fraction_percent_text(value: Decimal) -> str:
    if not value.is_finite() or value < Decimal(0):
        raise ValueError("portfolio fraction must be finite and non-negative")
    percent = (value * Decimal(100)).quantize(Decimal("0.01"))
    return f"{percent:.2f}%"


def _money_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("portfolio amount must be finite")
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _signed_money_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("portfolio PnL must be finite")
    return f"{value.quantize(Decimal('0.01')):+.2f}"


def _plain_decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("portfolio quantity must be finite")
    raw = format(value, "f")
    if "." in raw:
        raw = raw.rstrip("0").rstrip(".")
    return raw or "0"


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef"
        for character in value
    )


def _append_search_candidate(
    candidates: list[
        tuple[
            int,
            int,
            int,
            str,
            str,
            tuple[str, str],
            GlobalSearchItem,
        ]
    ],
    *,
    priority: int,
    item: GlobalSearchItem,
    source_key: tuple[str, str],
) -> None:
    timestamp = item.timestamp_ms
    candidates.append(
        (
            priority,
            1 if timestamp is None else 0,
            0 if timestamp is None else -timestamp,
            item.kind_label,
            item.title,
            source_key,
            item,
        )
    )


def _ordered_search_items(
    candidates: list[
        tuple[
            int,
            int,
            int,
            str,
            str,
            tuple[str, str],
            GlobalSearchItem,
        ]
    ],
    *,
    limit: int,
) -> tuple[GlobalSearchItem, ...]:
    seen: set[tuple[str, str]] = set()
    ordered: list[GlobalSearchItem] = []
    for _, _, _, _, _, source_key, item in sorted(
        candidates,
        key=lambda row: row[:-1],
    ):
        if source_key in seen:
            continue
        seen.add(source_key)
        ordered.append(item)
        if len(ordered) >= limit:
            break
    return tuple(ordered)


def _global_search_stream_item(
    record: dict[str, Any],
    *,
    include_audit: bool,
) -> tuple[GlobalSearchItem, tuple[str, str]]:
    narrative_identity = _required_sha(
        record,
        "narrative_identity",
    )
    text = _required_mapping(record, "text")
    title = _required_text(text, "collapsed_text")
    summary = (
        _optional_text_value(text.get("simple_text"))
        or _optional_text_value(text.get("capital_text"))
        or _optional_text_value(text.get("intelligence_text"))
        or title
    )
    symbol = _optional_text_value(record.get("symbol"))
    event_at_ms = _optional_non_negative_int_value(
        record.get("event_at_ms")
    )
    category = _optional_text_value(record.get("category"))
    subtype = _optional_text_value(record.get("subtype"))
    bundle_identity = _optional_sha(record.get("bundle_identity"))
    trade_subtypes = {
        "capital_executed",
        "capital_reduced",
        "capital_exited",
    }
    is_trade = (
        category == "capital"
        and subtype in trade_subtypes
        and bundle_identity is not None
    )
    kind_label = "İşlem" if is_trade else "Akış"
    source_label = (
        "Crypto Signal Capital Stream"
        if is_trade
        else "Crypto Signal Intelligence Stream"
    )
    audit = None
    if include_audit:
        audit = GlobalSearchAudit(
            source_identity=(
                bundle_identity
                if is_trade and bundle_identity is not None
                else narrative_identity
            ),
            stream_narrative_identity=narrative_identity,
            bundle_identity=bundle_identity if is_trade else None,
            raw_category=category,
            raw_subtype=subtype,
        )
    return (
        GlobalSearchItem(
            kind_label=kind_label,
            title=title,
            summary=summary,
            symbol=symbol,
            timestamp_ms=event_at_ms,
            source_label=source_label,
            audit=audit,
        ),
        (
            "trade" if is_trade else "stream",
            bundle_identity if is_trade and bundle_identity else narrative_identity,
        ),
    )


def _trade_passport_unavailable(reason: str) -> TradePassportView:
    return TradePassportView(
        availability_label=reason,
        program_label="Paper Capital · Epoch 2",
        action_label=None,
        outcome_label=None,
        vault_label=None,
        symbol=None,
        timeframe=None,
        decided_at_ms=None,
        filled_at_ms=None,
        snapshot_at_ms=None,
        proof_source_as_of_ms=None,
        decision_thesis=None,
        direction_label=None,
        trigger_zone_label=None,
        target_zone_label=None,
        invalidation_price=None,
        uncertainty_label=None,
        proof_availability_label="Karar kanıtı kullanılamıyor",
        quantity=None,
        reference_price=None,
        simulated_fill_price=None,
        notional_usdt=None,
        fee_usdt=None,
        spread_usdt=None,
        slippage_usdt=None,
        cash_before_usdt=None,
        cash_after_usdt=None,
        vault_nav_before_usdt=None,
        vault_nav_after_usdt=None,
        consolidated_nav_before_usdt=None,
        consolidated_nav_after_usdt=None,
        position_quantity_before=None,
        position_quantity_after=None,
        realized_pnl_delta_usdt=None,
        unrealized_pnl_delta_usdt=None,
    )


def _trade_passport_view(
    *,
    bundle_identity: str,
    context: dict[str, Any],
    proof: dict[str, Any] | None,
    proof_label: str,
    include_audit: bool,
) -> TradePassportView:
    bundle = _required_mapping(context, "bundle")
    intent = _required_mapping(context, "intent")
    fill = _required_mapping(context, "fill")
    before_vault = _required_mapping(context, "before_vault")
    after_vault = _required_mapping(context, "after_vault")
    before_parent = _required_mapping(context, "before_consolidated")
    after_parent = _required_mapping(context, "after_consolidated")

    if _required_sha(bundle, "bundle_identity") != bundle_identity:
        raise ValueError("Trade Passport bundle identity mismatch")

    raw_action = _required_text(fill, "action")
    if _required_text(intent, "action") != raw_action:
        raise ValueError("Trade Passport intent/fill action mismatch")
    action_label = _trade_passport_action_label(raw_action)

    raw_outcome = _required_text(fill, "financial_outcome")
    outcome_label = _trade_passport_outcome_label(raw_outcome)

    raw_vault = _required_text(fill, "vault_id")
    if _required_text(intent, "vault_id") != raw_vault:
        raise ValueError("Trade Passport intent/fill vault mismatch")
    vault_label = _capital_vault_label(raw_vault)

    symbol = _required_text(fill, "symbol")
    if _required_text(intent, "symbol") != symbol:
        raise ValueError("Trade Passport intent/fill symbol mismatch")

    reason_codes = _text_sequence(
        _required_sequence(intent, "reason_codes"),
        "Trade Passport reason codes",
    )
    source_evidence_identities = tuple(
        _sha_text(value, "Trade Passport source evidence identity")
        for value in _required_sequence(intent, "source_evidence_identities")
    )

    proof_source_as_of_ms = None
    timeframe = None
    thesis = None
    direction_label = None
    trigger_zone_label = None
    target_zone_label = None
    invalidation_price = None
    uncertainty_label = None
    if proof is not None:
        if _required_text(proof, "symbol") != symbol:
            raise ValueError("Trade Passport proof symbol mismatch")
        timeframe = _required_text(proof, "timeframe")
        proof_source_as_of_ms = _required_int(proof, "source_as_of_ms")
        if proof_source_as_of_ms > _required_int(intent, "decided_at_ms"):
            raise ValueError("Trade Passport proof source is after decision")
        thesis = _required_text(proof, "conditional_thesis")
        direction_label = _trade_passport_direction_label(
            _required_text(proof, "direction")
        )
        trigger_zone_label = _trade_passport_zone_label(
            proof.get("trigger_zone"),
            "Trade Passport trigger zone",
        )
        target_zone_label = _trade_passport_zone_label(
            proof.get("target_zone"),
            "Trade Passport target zone",
        )
        invalidation_price = _decimal_text(
            proof.get("invalidation_price"),
            "Trade Passport invalidation",
        )
        uncertainty_flags = _text_sequence(
            _required_sequence(proof, "uncertainty_flags"),
            "Trade Passport uncertainty flags",
        )
        uncertainty_label = (
            "Ek belirsizlik işareti yok"
            if not uncertainty_flags
            else f"{len(uncertainty_flags)} belirsizlik işareti mevcut"
        )

    outcome_identity = _optional_sha(fill.get("outcome_evidence_identity"))
    audit = None
    if include_audit:
        audit = TradePassportAudit(
            bundle_identity=bundle_identity,
            activation_identity=_required_sha(fill, "activation_identity"),
            intent_identity=_required_sha(intent, "intent_identity"),
            fill_identity=_required_sha(fill, "fill_identity"),
            forecast_identity=_required_sha(intent, "forecast_identity"),
            proof_identity=_required_sha(intent, "proof_identity"),
            signal_freeze_identity=_required_sha(
                intent,
                "signal_freeze_identity",
            ),
            policy_identity=_required_sha(intent, "policy_identity"),
            sizing_assessment_identity=_required_sha(
                intent,
                "sizing_assessment_identity",
            ),
            sizing_decision_identity=_required_sha(
                intent,
                "sizing_decision_identity",
            ),
            allocator_candidate_identity=_required_sha(
                intent,
                "allocator_candidate_identity",
            ),
            decision_identity=_required_sha(intent, "decision_identity"),
            source_evidence_identities=source_evidence_identities,
            source_fill_identity=_required_sha(fill, "source_fill_identity"),
            mutation_identity=_required_sha(fill, "mutation_identity"),
            mark_evidence_identity=_required_sha(
                fill,
                "mark_evidence_identity",
            ),
            outcome_identity=outcome_identity,
            before_vault_snapshot_identity=_required_sha(
                fill,
                "before_snapshot_identity",
            ),
            after_vault_snapshot_identity=_required_sha(
                fill,
                "after_snapshot_identity",
            ),
            before_consolidated_snapshot_identity=_required_sha(
                bundle,
                "before_consolidated_snapshot_identity",
            ),
            after_consolidated_snapshot_identity=_required_sha(
                bundle,
                "after_consolidated_snapshot_identity",
            ),
            raw_action=raw_action,
            raw_outcome=raw_outcome,
            reason_codes=reason_codes,
            execution_policy_version=_required_text(
                fill,
                "execution_policy_version",
            ),
            venue_reference=_required_text(fill, "venue_reference"),
        )

    return TradePassportView(
        availability_label="Doğrulanmış veri",
        program_label="Paper Capital · Epoch 2",
        action_label=action_label,
        outcome_label=outcome_label,
        vault_label=vault_label,
        symbol=symbol,
        timeframe=timeframe,
        decided_at_ms=_required_int(intent, "decided_at_ms"),
        filled_at_ms=_required_int(fill, "filled_at_ms"),
        snapshot_at_ms=_required_int(fill, "snapshot_at_ms"),
        proof_source_as_of_ms=proof_source_as_of_ms,
        decision_thesis=thesis,
        direction_label=direction_label,
        trigger_zone_label=trigger_zone_label,
        target_zone_label=target_zone_label,
        invalidation_price=invalidation_price,
        uncertainty_label=uncertainty_label,
        proof_availability_label=proof_label,
        quantity=_decimal_text(fill.get("quantity"), "Trade Passport quantity"),
        reference_price=_decimal_text(
            fill.get("reference_price"),
            "Trade Passport reference price",
        ),
        simulated_fill_price=_decimal_text(
            fill.get("simulated_fill_price"),
            "Trade Passport fill price",
        ),
        notional_usdt=_decimal_text(
            fill.get("notional_usdt"),
            "Trade Passport notional",
        ),
        fee_usdt=_decimal_text(fill.get("fee_usdt"), "Trade Passport fee"),
        spread_usdt=_decimal_text(
            fill.get("spread_usdt"),
            "Trade Passport spread",
        ),
        slippage_usdt=_decimal_text(
            fill.get("slippage_usdt"),
            "Trade Passport slippage",
        ),
        cash_before_usdt=_decimal_text(
            before_vault.get("cash_usdt"),
            "Trade Passport cash before",
        ),
        cash_after_usdt=_decimal_text(
            after_vault.get("cash_usdt"),
            "Trade Passport cash after",
        ),
        vault_nav_before_usdt=_decimal_text(
            before_vault.get("nav_usdt"),
            "Trade Passport vault NAV before",
        ),
        vault_nav_after_usdt=_decimal_text(
            after_vault.get("nav_usdt"),
            "Trade Passport vault NAV after",
        ),
        consolidated_nav_before_usdt=_decimal_text(
            before_parent.get("nav_usdt"),
            "Trade Passport consolidated NAV before",
        ),
        consolidated_nav_after_usdt=_decimal_text(
            after_parent.get("nav_usdt"),
            "Trade Passport consolidated NAV after",
        ),
        position_quantity_before=_plain_decimal_text(
            _decimal(
                fill.get("position_before_quantity"),
                "Trade Passport position before",
            )
        ),
        position_quantity_after=_plain_decimal_text(
            _decimal(
                fill.get("position_after_quantity"),
                "Trade Passport position after",
            )
        ),
        realized_pnl_delta_usdt=_signed_money_text(
            _decimal(
                fill.get("realized_pnl_delta_usdt"),
                "Trade Passport realized PnL",
            )
        ),
        unrealized_pnl_delta_usdt=_signed_money_text(
            _decimal(
                fill.get("unrealized_pnl_delta_usdt"),
                "Trade Passport unrealized PnL",
            )
        ),
        audit=audit,
    )


def _trade_passport_action_label(value: str) -> str:
    labels = {
        "BUY": "Pozisyon açıldı / artırıldı",
        "REDUCE": "Pozisyon azaltıldı",
        "EXIT": "Pozisyon kapatıldı",
    }
    try:
        return labels[value]
    except KeyError as exc:
        raise ValueError("unsupported Trade Passport action") from exc


def _trade_passport_outcome_label(value: str) -> str:
    labels = {
        "OPEN": "Pozisyon açık",
        "PARTIAL_REDUCTION": "Kısmi azaltma",
        "CLOSED_WIN": "Kârla kapandı",
        "CLOSED_LOSS": "Zararla kapandı",
        "CLOSED_BREAKEVEN": "Başa baş kapandı",
    }
    try:
        return labels[value]
    except KeyError as exc:
        raise ValueError("unsupported Trade Passport outcome") from exc


def _trade_passport_direction_label(value: str) -> str:
    labels = {
        "bullish": "Yukarı yönlü",
        "bearish": "Aşağı yönlü",
        "neutral": "Nötr",
    }
    try:
        return labels[value.strip().lower()]
    except KeyError as exc:
        raise ValueError("unsupported Trade Passport direction") from exc


def _trade_passport_zone_label(value: object, label: str) -> str:
    raw = _mapping_value(value, label)
    low = _decimal_text(raw.get("low"), f"{label} low")
    high = _decimal_text(raw.get("high"), f"{label} high")
    return low if low == high else f"{low} – {high}"


def _capital_vault_label(vault_id: str | None) -> str | None:
    if vault_id is None:
        return None
    try:
        canonical = PaperVaultId(vault_id)
    except ValueError as exc:
        raise ValueError("capital movement vault is not canonical") from exc
    return _PORTFOLIO_VAULT_LABELS[canonical]


def _capital_movement_item(
    record: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> CapitalMovementItem:
    if _required_text(record, "category") != "capital":
        raise ValueError("capital movement record is not capital category")

    subtype = _required_text(record, "subtype")
    event_at_ms = _required_int(record, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise ValueError("capital movement event cannot be in the future")

    source_as_of_ms = _optional_non_negative_int_value(
        record.get("source_as_of_ms")
    )
    if source_as_of_ms is not None and source_as_of_ms > event_at_ms:
        raise ValueError("capital movement source time cannot follow event time")
    freshness_label = _capital_movement_freshness_label(
        observed_at_ms=observed_at_ms,
        source_as_of_ms=source_as_of_ms,
        event_at_ms=event_at_ms,
        stale_after_ms=stale_after_ms,
    )

    raw_vault = record.get("vault_id")
    vault_id = None
    if raw_vault is not None:
        if not isinstance(raw_vault, str) or not raw_vault.strip():
            raise TypeError("capital movement vault must be non-empty text")
        vault_id = raw_vault

    raw_action = _optional_text_value(record.get("action"))
    raw_disposition = _optional_text_value(record.get("disposition"))
    action_label = _capital_movement_action_label(
        subtype=subtype,
        action=raw_action,
        disposition=raw_disposition,
    )

    text = _required_mapping(record, "text")
    headline = _required_text(text, "collapsed_text")
    detail = _required_text(text, "capital_text")

    reason_codes_raw = record.get("reason_codes")
    if reason_codes_raw is None:
        reason_codes: tuple[str, ...] = ()
    else:
        reason_codes = _text_sequence(
            reason_codes_raw,
            "capital movement reason codes",
        )

    lineage_raw = _required_sequence(record, "capital_reference_identities")
    lineage_identities = tuple(
        _sha_text(value, "capital movement lineage identity")
        for value in lineage_raw
    )

    audit = None
    if include_audit:
        audit = CapitalMovementAudit(
            narrative_identity=_required_sha(record, "narrative_identity"),
            story_identity=_required_sha(record, "story_identity"),
            source_event_identity=_required_sha(record, "source_event_identity"),
            stream_event_identity=_required_sha(record, "stream_event_identity"),
            lineage_identities=lineage_identities,
            raw_subtype=subtype,
            raw_action=raw_action,
            raw_disposition=raw_disposition,
            reason_codes=reason_codes,
        )

    return CapitalMovementItem(
        event_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        freshness_label=freshness_label,
        vault_label=_capital_vault_label(vault_id),
        symbol=_required_text(record, "symbol"),
        timeframe=_required_text(record, "timeframe"),
        action_label=action_label,
        headline=headline,
        detail=detail,
        quantity=_optional_plain_decimal_text(record.get("quantity")),
        notional_usdt=_optional_decimal_text(
            record.get("notional_usdt")
            if record.get("notional_usdt") is not None
            else record.get("canonical_notional_usdt")
        ),
        fraction_of_vault_percent=_optional_fraction_percent_text(
            record.get("fraction_of_vault")
        ),
        current_cash_usdt=_optional_decimal_text(record.get("current_cash_usdt")),
        current_nav_usdt=_optional_decimal_text(record.get("current_nav_usdt")),
        cash_before_usdt=_optional_decimal_text(record.get("cash_before_usdt")),
        cash_after_usdt=_optional_decimal_text(record.get("cash_after_usdt")),
        vault_nav_before_usdt=_optional_decimal_text(
            record.get("vault_nav_before_usdt")
        ),
        vault_nav_after_usdt=_optional_decimal_text(
            record.get("vault_nav_after_usdt")
        ),
        consolidated_nav_before_usdt=_optional_decimal_text(
            record.get("consolidated_nav_before_usdt")
        ),
        consolidated_nav_after_usdt=_optional_decimal_text(
            record.get("consolidated_nav_after_usdt")
        ),
        fee_usdt=_optional_decimal_text(record.get("fee_usdt")),
        spread_usdt=_optional_decimal_text(record.get("spread_usdt")),
        slippage_usdt=_optional_decimal_text(record.get("slippage_usdt")),
        realized_pnl_delta_usdt=_optional_signed_decimal_text(
            record.get("realized_pnl_delta_usdt")
        ),
        outcome_label=_capital_financial_outcome_label(
            record.get("financial_outcome")
        ),
        audit=audit,
    )


def _capital_movement_action_label(
    *,
    subtype: str,
    action: str | None,
    disposition: str | None,
) -> str:
    decision_contract = {
        "capital_eligible": ("eligible", "İşleme uygun bulundu"),
        "capital_hold": ("hold", "Nakit korunuyor / işlem yapılmadı"),
        "capital_blocked": ("blocked", "İşlem engellendi"),
    }
    if subtype in decision_contract:
        expected, label = decision_contract[subtype]
        if disposition != expected or action is not None:
            raise ValueError("capital decision subtype/disposition mismatch")
        return label

    execution_contract = {
        "capital_executed": ("BUY", "Pozisyon açıldı / artırıldı"),
        "capital_reduced": ("REDUCE", "Pozisyon azaltıldı"),
        "capital_exited": ("EXIT", "Pozisyon kapatıldı"),
    }
    if subtype in execution_contract:
        expected, label = execution_contract[subtype]
        if action != expected or disposition is not None:
            raise ValueError("capital execution subtype/action mismatch")
        return label

    if subtype == "capital_sized":
        if action is not None or disposition is not None:
            raise ValueError("capital sizing cannot carry action/disposition")
        return "Pozisyon boyutu belirlendi"
    if subtype == "capital_candidate":
        if action is not None or disposition is not None:
            raise ValueError("capital candidate cannot carry action/disposition")
        return "Aday sermaye değerlendirmesi"
    if subtype == "capital_accounting_updated":
        if action not in {"BUY", "REDUCE", "EXIT"} or disposition is not None:
            raise ValueError("capital accounting action is invalid")
        return "Portföy hesabı güncellendi"
    if subtype == "capital_outcome":
        if action not in {"REDUCE", "EXIT"} or disposition is not None:
            raise ValueError("capital outcome action is invalid")
        return "İşlem sonucu kaydedildi"
    raise ValueError("unsupported capital movement subtype")


def _capital_movement_freshness_label(
    *,
    observed_at_ms: int,
    source_as_of_ms: int | None,
    event_at_ms: int,
    stale_after_ms: int,
) -> str:
    if source_as_of_ms is not None:
        return _freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        )
    if event_at_ms > observed_at_ms:
        raise ValueError("capital event time cannot be in the future")
    return (
        "Olay zamanı güncel"
        if observed_at_ms - event_at_ms <= stale_after_ms
        else "Olay zamanı güncel değil"
    )


def _capital_financial_outcome_label(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("capital financial outcome must be non-empty text")
    labels = {
        "PARTIAL_REDUCTION": "Kısmi azaltma",
        "CLOSED_WIN": "Kârla kapandı",
        "CLOSED_LOSS": "Zararla kapandı",
        "CLOSED_BREAKEVEN": "Başa baş kapandı",
    }
    try:
        return labels[value]
    except KeyError as exc:
        raise ValueError("unsupported capital financial outcome") from exc


def _optional_plain_decimal_text(value: object) -> str | None:
    if value is None:
        return None
    return _plain_decimal_text(_decimal(value, "optional quantity"))


def _optional_fraction_percent_text(value: object) -> str | None:
    if value is None:
        return None
    return _fraction_percent_text(_decimal(value, "optional fraction"))


def _optional_signed_decimal_text(value: object) -> str | None:
    if value is None:
        return None
    return _signed_money_text(_decimal(value, "optional signed amount"))


def _event_rail_view(
    truth: EventSourceCalendarRailTruth,
    *,
    fresh_after_ms: int,
    include_audit: bool,
) -> EventRailView:
    items = tuple(
        _event_rail_item(
            item,
            observed_at_ms=truth.observed_at_ms,
            fresh_after_ms=fresh_after_ms,
            include_audit=include_audit,
        )
        for item in truth.events
    )
    coverages = tuple(
        _event_rail_coverage(
            item,
            observed_at_ms=truth.observed_at_ms,
            fresh_after_ms=fresh_after_ms,
            include_audit=include_audit,
        )
        for item in truth.coverages
    )
    if truth.total_matching_events > 0:
        summary = f"{truth.total_matching_events} planlı olay bulundu"
    elif truth.coverage_status == "COMPLETE":
        summary = "Bu kapsamda planlı olay yok"
    else:
        summary = "Planlı olay verisi doğrulanamadı"

    audit = None
    if include_audit:
        audit = EventRailAudit(
            raw_coverage_status=truth.coverage_status,
            latest_calendar_fetch_identities=tuple(
                item.fetch_identity
                for item in truth.latest_calendar_fetches
            ),
        )

    return EventRailView(
        availability_label="Doğrulanmış veri",
        observed_at_ms=truth.observed_at_ms,
        window_start_ms=truth.window_start_ms,
        window_end_ms=truth.window_end_ms,
        asset=truth.asset,
        coverage_label=_EVENT_COVERAGE_LABELS.get(
            truth.coverage_status,
            "Takvim kapsamı kullanılamıyor",
        ),
        summary_label=summary,
        total_matching_events=truth.total_matching_events,
        items=items,
        coverages=coverages,
        audit=audit,
    )


def _event_rail_item(
    item: EventSourceCalendarEventTruth,
    *,
    observed_at_ms: int,
    fresh_after_ms: int,
    include_audit: bool,
) -> EventRailItem:
    if item.scheduled_at_ms > observed_at_ms:
        temporal = "Yaklaşan olay"
    elif item.scheduled_at_ms == observed_at_ms:
        temporal = "Şimdi"
    else:
        temporal = "Yakın geçmiş olayı"
    audit = (
        EventRailItemAudit(event_identity=item.event_identity)
        if include_audit
        else None
    )
    return EventRailItem(
        title=item.title,
        category_label=_EVENT_CATEGORY_LABELS.get(item.category, "Diğer"),
        scheduled_at_ms=item.scheduled_at_ms,
        temporal_label=temporal,
        affected_assets=item.affected_assets,
        scope_label="Global" if not item.affected_assets else "Varlık odaklı",
        source_provider=item.source_provider,
        source_quality_label=_EVENT_SOURCE_QUALITY_LABELS.get(
            item.source_quality,
            "Kaynak kalitesi doğrulanmadı",
        ),
        source_timestamp_ms=item.source_timestamp_ms,
        freshness_label=_event_source_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=item.source_timestamp_ms,
            fresh_after_ms=fresh_after_ms,
        ),
        audit=audit,
    )


def _event_rail_coverage(
    item: EventSourceCalendarCoverageTruth,
    *,
    observed_at_ms: int,
    fresh_after_ms: int,
    include_audit: bool,
) -> EventRailCoverageView:
    audit = (
        EventRailCoverageAudit(coverage_identity=item.coverage_identity)
        if include_audit
        else None
    )
    return EventRailCoverageView(
        source_provider=item.source_provider,
        window_start_ms=item.coverage_start_ms,
        window_end_ms=item.coverage_end_ms,
        category_labels=tuple(
            _EVENT_CATEGORY_LABELS.get(value, "Diğer")
            for value in item.categories
        ),
        source_quality_label=_EVENT_SOURCE_QUALITY_LABELS.get(
            item.source_quality,
            "Kaynak kalitesi doğrulanmadı",
        ),
        observed_at_ms=item.observed_at_ms,
        freshness_label=_event_source_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=item.observed_at_ms,
            fresh_after_ms=fresh_after_ms,
        ),
        audit=audit,
    )


def _event_source_freshness_label(
    *,
    observed_at_ms: int,
    source_as_of_ms: int,
    fresh_after_ms: int,
) -> str:
    if source_as_of_ms > observed_at_ms:
        raise ValueError("event source as-of cannot be in the future")
    return (
        "Güncel kaynak"
        if observed_at_ms - source_as_of_ms <= fresh_after_ms
        else "Kaynak güncel değil"
    )


def _workspace_unavailable(
    *,
    availability_label: str,
    message_kind_label: str,
) -> WorkspaceSummaryView:
    return WorkspaceSummaryView(
        availability_label=availability_label,
        message_kind_label=message_kind_label,
        symbol=None,
        timeframe=None,
        updated_at_ms=None,
        source_as_of_ms=None,
        freshness_label="Veri yok",
        headline=None,
        detail=None,
        state_label=None,
        direction_label=None,
        support_balance_label=None,
        trigger_zone=None,
        target_zone=None,
        invalidation_price=None,
        main_contradiction_label=None,
        event_risk_label=None,
        uncertainty_label="Belirsizlik değerlendirilemedi",
        probability_label="Olasılık verisi yok",
        evidence_label="Kanıt ayrıntısı kullanılamıyor",
        decision_evidence_label="Ek karar kanıtı yok",
        capital_consequence_label=None,
        resolution_label=None,
    )


def _capital_detail_kind(detail: dict[str, Any]) -> str | None:
    for key in (
        "capital_story",
        "capital_decision",
        "capital_sizing",
        "capital_lifecycle",
    ):
        if key in detail:
            return key
    return None


def _workspace_capital_deferred(
    detail: dict[str, Any],
    *,
    capital_kind: str,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> WorkspaceSummaryView:
    narrative = _required_mapping(detail, "narrative")
    narrative_identity = _required_sha(narrative, "narrative_identity")
    event_at_ms = _required_int(narrative, "event_at_ms")
    source_as_of_ms = _optional_non_negative_int_value(
        narrative.get("source_as_of_ms")
    )
    if source_as_of_ms is None:
        source_as_of_ms = event_at_ms
    headline, simple = _workspace_text(narrative)
    kind_labels = {
        "capital_story": "Sermaye hikâyesi",
        "capital_decision": "Sermaye kararı",
        "capital_sizing": "Pozisyon boyutlandırma",
        "capital_lifecycle": "Sermaye yaşam döngüsü",
    }
    audit = (
        WorkspaceAudit(
            narrative_identity=narrative_identity,
            detail_kind=capital_kind,
            story_identity=_optional_sha(narrative.get("story_identity")),
            fact_bundle_identity=None,
            analytical_view_identity=None,
            forecast_identity=None,
            proof_identity=None,
            signal_freeze_identity=None,
            evidence_resolution_counts={},
        )
        if include_audit
        else None
    )
    return WorkspaceSummaryView(
        availability_label="Bu mesaj türü bu çalışma alanında desteklenmiyor",
        message_kind_label=kind_labels[capital_kind],
        symbol=_optional_text_value(narrative.get("symbol")),
        timeframe=_optional_text_value(narrative.get("timeframe")),
        updated_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        ),
        headline=headline,
        detail=simple,
        state_label=None,
        direction_label=None,
        support_balance_label=None,
        trigger_zone=None,
        target_zone=None,
        invalidation_price=None,
        main_contradiction_label=None,
        event_risk_label=None,
        uncertainty_label="Bu çalışma alanında değerlendirilmedi",
        probability_label="Bu mesaj türü için uygulanmaz",
        evidence_label="Sermaye ayrıntıları Portföy görünümüne ayrıldı",
        decision_evidence_label="Bu mesaj türü için uygulanmaz",
        capital_consequence_label=None,
        resolution_label=None,
        audit=audit,
    )


def _workspace_system_view(
    detail: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> WorkspaceSummaryView:
    narrative = _required_mapping(detail, "narrative")
    fact = _required_mapping(detail, "fact_bundle")
    analytical = _required_mapping(detail, "analytical_view")
    stance = _required_mapping(analytical, "stance")
    uncertainty = _required_mapping(analytical, "uncertainty")
    event_at_ms = _required_int(narrative, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise FinalProductReadError("workspace System View is from the future")
    raw_stance = _required_text(stance, "effective_stance")
    headline, simple = _workspace_text(narrative)
    audit = None
    if include_audit:
        audit = WorkspaceAudit(
            narrative_identity=_required_sha(narrative, "narrative_identity"),
            detail_kind="system_view",
            story_identity=None,
            fact_bundle_identity=None,
            analytical_view_identity=None,
            forecast_identity=None,
            proof_identity=None,
            signal_freeze_identity=None,
            evidence_resolution_counts={},
        )
    return WorkspaceSummaryView(
        availability_label="Doğrulanmış veri",
        message_kind_label="Sistem görünümü",
        symbol=_required_text(narrative, "symbol"),
        timeframe=_required_text(narrative, "timeframe"),
        updated_at_ms=event_at_ms,
        source_as_of_ms=event_at_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=event_at_ms,
            stale_after_ms=stale_after_ms,
        ),
        headline=headline,
        detail=simple,
        state_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
        direction_label=_direction_label(raw_stance),
        support_balance_label=_support_balance_label(
            stance.get("support_score_0_100"),
            stance.get("opposition_score_0_100"),
        ),
        trigger_zone=_optional_mapping(fact.get("trigger_zone")),
        target_zone=_optional_mapping(fact.get("target_zone")),
        invalidation_price=_optional_decimal_text(fact.get("invalidation_price")),
        main_contradiction_label=_contradiction_label(
            analytical.get("main_contradiction")
        ),
        event_risk_label=_event_risk_label(
            uncertainty.get("event_risk_state")
        ),
        uncertainty_label=_system_uncertainty_label(uncertainty),
        probability_label=_probability_label(
            uncertainty.get("probability_status"),
            uncertainty.get("calibrated_probability_0_1"),
        ),
        evidence_label="Beş kanıt ailesinin doğrulanmış özeti mevcut",
        decision_evidence_label="Bu görünüm için ayrı karar kanıtı uygulanmaz",
        capital_consequence_label=None,
        resolution_label=None,
        audit=audit,
    )


def _workspace_family(
    detail: dict[str, Any],
    *,
    evidence: dict[str, Any] | None,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> WorkspaceSummaryView:
    narrative = _required_mapping(detail, "narrative")
    fact = _required_mapping(detail, "fact_bundle")
    analytical = _required_mapping(detail, "analytical_view")
    event_at_ms = _required_int(narrative, "event_at_ms")
    source_as_of_ms = _required_int(fact, "source_as_of_ms")
    if max(event_at_ms, source_as_of_ms) > observed_at_ms:
        raise FinalProductReadError("family workspace source is from the future")
    headline, simple = _workspace_text(narrative)
    family = _required_text(fact, "family")
    direction = _optional_text_value(fact.get("direction"))
    source_quality = _required_text(fact, "source_quality")
    uncertainty_flags = _text_sequence(
        fact.get("uncertainty_flags"),
        "workspace family uncertainty flags",
    )
    counts = _evidence_resolution_counts(evidence)
    audit = None
    if include_audit:
        audit = WorkspaceAudit(
            narrative_identity=_required_sha(narrative, "narrative_identity"),
            detail_kind="family",
            story_identity=_required_sha(narrative, "story_identity"),
            fact_bundle_identity=_required_sha(fact, "fact_bundle_identity"),
            analytical_view_identity=_required_sha(
                analytical,
                "analytical_view_identity",
            ),
            forecast_identity=None,
            proof_identity=None,
            signal_freeze_identity=None,
            evidence_resolution_counts=counts,
        )
    return WorkspaceSummaryView(
        availability_label="Doğrulanmış veri",
        message_kind_label=f"{_FAMILY_LABELS.get(family, 'Kanıt ailesi')} görünümü",
        symbol=_required_text(narrative, "symbol"),
        timeframe=_required_text(narrative, "timeframe"),
        updated_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        ),
        headline=headline,
        detail=simple,
        state_label=(
            "Veri eksik"
            if source_quality.lower() in {"unavailable", "missing"}
            else "Aile durumu doğrulandı"
        ),
        direction_label=_direction_label(direction),
        support_balance_label=None,
        trigger_zone=None,
        target_zone=None,
        invalidation_price=None,
        main_contradiction_label=None,
        event_risk_label=None,
        uncertainty_label=_uncertainty_count_label(uncertainty_flags),
        probability_label="Bu kanıt ailesi için uygulanmaz",
        evidence_label=_evidence_resolution_label(counts),
        decision_evidence_label="Bu kanıt ailesi için uygulanmaz",
        capital_consequence_label=None,
        resolution_label=None,
        audit=audit,
    )


def _workspace_decision(
    detail: dict[str, Any],
    *,
    evidence: dict[str, Any] | None,
    decision_proof: dict[str, Any] | None,
    decision_evidence_label: str,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> WorkspaceSummaryView:
    narrative = _required_mapping(detail, "narrative")
    fact = _required_mapping(detail, "fact_bundle")
    analytical = _required_mapping(detail, "analytical_view")
    stance = _required_mapping(analytical, "stance")
    event_at_ms = _required_int(narrative, "event_at_ms")
    source_as_of_ms = _required_int(fact, "source_as_of_ms")
    if max(event_at_ms, source_as_of_ms) > observed_at_ms:
        raise FinalProductReadError("decision workspace source is from the future")
    headline, simple = _workspace_text(narrative)
    uncertainty_flags = _text_sequence(
        fact.get("uncertainty_flags"),
        "workspace decision uncertainty flags",
    )
    counts = _evidence_resolution_counts(evidence)
    raw_stance = _required_text(stance, "effective_stance")
    signal_identity = (
        None
        if decision_proof is None
        else _optional_sha(decision_proof.get("signal_freeze_identity"))
    )
    audit = None
    if include_audit:
        audit = WorkspaceAudit(
            narrative_identity=_required_sha(narrative, "narrative_identity"),
            detail_kind="decision",
            story_identity=_required_sha(narrative, "story_identity"),
            fact_bundle_identity=_required_sha(fact, "fact_bundle_identity"),
            analytical_view_identity=_required_sha(
                analytical,
                "analytical_view_identity",
            ),
            forecast_identity=_required_sha(fact, "forecast_identity"),
            proof_identity=_required_sha(fact, "proof_identity"),
            signal_freeze_identity=signal_identity,
            evidence_resolution_counts=counts,
        )
    return WorkspaceSummaryView(
        availability_label="Doğrulanmış veri",
        message_kind_label=(
            "Sonuç görünümü"
            if fact.get("resolution_identity") is not None
            else "Karar görünümü"
        ),
        symbol=_required_text(narrative, "symbol"),
        timeframe=_required_text(narrative, "timeframe"),
        updated_at_ms=event_at_ms,
        source_as_of_ms=source_as_of_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        ),
        headline=headline,
        detail=simple,
        state_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
        direction_label=_direction_label(fact.get("direction")),
        support_balance_label=_support_balance_label(
            fact.get("confluence_support_score_0_100"),
            fact.get("confluence_opposition_score_0_100"),
        ),
        trigger_zone=_optional_mapping(fact.get("trigger_zone")),
        target_zone=_optional_mapping(fact.get("target_zone")),
        invalidation_price=_optional_decimal_text(fact.get("invalidation_price")),
        main_contradiction_label=_contradiction_label(
            analytical.get("main_contradiction")
        ),
        event_risk_label=_event_risk_label(fact.get("event_context_state")),
        uncertainty_label=_uncertainty_count_label(uncertainty_flags),
        probability_label=_probability_label(
            fact.get("probability_status"),
            fact.get("calibrated_probability_0_1"),
        ),
        evidence_label=_evidence_resolution_label(counts),
        decision_evidence_label=decision_evidence_label,
        capital_consequence_label=_capital_consequence_label(
            analytical.get("capital_consequence")
        ),
        resolution_label=(
            "Sonuç kaydı mevcut"
            if fact.get("resolution_identity") is not None
            else "Karar henüz sonuç kaydına dönüşmedi"
        ),
        audit=audit,
    )


def _workspace_text(
    narrative: dict[str, Any],
) -> tuple[str | None, str | None]:
    text = narrative.get("text")
    if isinstance(text, dict):
        return (
            _optional_text_value(text.get("collapsed_text")),
            _optional_text_value(text.get("simple_text")),
        )
    return (
        _optional_text_value(narrative.get("collapsed_text")),
        _optional_text_value(narrative.get("simple_text")),
    )


def _support_balance_label(
    support: object,
    opposition: object,
) -> str | None:
    if support is None or opposition is None:
        return None
    support_value = _decimal(support, "workspace support")
    opposition_value = _decimal(opposition, "workspace opposition")
    if support_value > opposition_value:
        return "Destek tarafı daha güçlü"
    if opposition_value > support_value:
        return "Çelişki tarafı daha güçlü"
    return "Destek ve çelişki dengeli"


def _direction_label(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"bullish", "long", "up", "buy", "buy_pressure"}:
        return "Yükseliş"
    if raw in {"bearish", "short", "down", "sell", "sell_pressure"}:
        return "Düşüş"
    return "Yön karışık"


def _system_uncertainty_label(uncertainty: dict[str, Any]) -> str:
    conflict = uncertainty.get("material_conflict_count")
    if isinstance(conflict, int) and not isinstance(conflict, bool) and conflict > 0:
        return f"{conflict} maddi çelişki mevcut"
    return "Belirsizlik bilgisi kaynakta mevcut"


def _uncertainty_count_label(values: tuple[str, ...]) -> str:
    if not values:
        return "Belirgin belirsizlik işareti yok"
    return f"{len(values)} belirsizlik işareti"


def _probability_label(
    status: object,
    calibrated_probability: object,
) -> str:
    if calibrated_probability is not None:
        value = _decimal(calibrated_probability, "workspace calibrated probability")
        if value < Decimal(0) or value > Decimal(1):
            raise ValueError("workspace calibrated probability outside [0,1]")
        percent = (value * Decimal(100)).quantize(Decimal("0.01"))
        return f"Kalibre edilmiş olasılık: {percent:.2f}%"
    if str(status).strip().lower() == "not_calibrated":
        return "Kalibre edilmiş olasılık değil"
    return "Olasılık verisi doğrulanmadı"


def _evidence_resolution_counts(
    evidence: dict[str, Any] | None,
) -> dict[str, int]:
    if evidence is None:
        return {}
    raw = evidence.get("resolution_counts")
    if not isinstance(raw, dict):
        raise TypeError("workspace evidence resolution counts must be an object")
    result: dict[str, int] = {}
    for key in (
        "READY_EXACT",
        "IDENTITY_ONLY_EXACT",
        "UNAVAILABLE_EXPLICIT",
    ):
        value = raw.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise TypeError("workspace evidence resolution count must be non-negative")
        result[key] = value
    return result


def _evidence_resolution_label(counts: dict[str, int]) -> str:
    if counts.get("READY_EXACT", 0) > 0:
        return "Doğrulanmış kanıt mevcut"
    if counts.get("IDENTITY_ONLY_EXACT", 0) > 0:
        return "Kanıt kimliği doğrulandı; ayrıntı sınırlı"
    return "Kanıt ayrıntısı kullanılamıyor"


def _capital_consequence_label(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = str(value.get("state", "")).strip().lower()
    labels = {
        "not_bound": "Sanal sermayeye bağlı yeni referans yok",
        "bound_unchanged": "Sanal sermaye bağlantısı değişmedi",
        "references_added": "Yeni sanal sermaye referansı eklendi",
        "references_removed": "Sanal sermaye referansı kaldırıldı",
        "references_changed": "Sanal sermaye referansları değişti",
    }
    return labels.get(raw, "Sanal sermaye bağlantısı mevcut")


def _optional_text_value(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("optional workspace text must be non-empty text")
    return value


def _optional_non_negative_int_value(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError("optional workspace time must be non-negative integer")
    return value


def _optional_sha(value: object) -> str | None:
    if value is None:
        return None
    return _sha_text(value, "optional workspace identity")


def _attention_candidate(
    detail: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> _AttentionCandidate | None:
    narrative = _required_mapping(detail, "narrative")
    narrative_identity = _required_sha(narrative, "narrative_identity")
    text = _required_mapping(narrative, "text")
    headline = _required_text(text, "collapsed_text")
    simple_text = _required_text(text, "simple_text")
    event_at_ms = _required_int(narrative, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise FinalProductReadError("attention source is from the future")

    if "system_view" in detail:
        importance = _required_text(narrative, "importance")
        if importance not in _IMPORTANCE_LABELS:
            return None
        symbol = _required_text(narrative, "symbol")
        timeframe = _required_text(narrative, "timeframe")
        subtype = _required_text(narrative, "subtype")
        analytical = _required_mapping(detail, "analytical_view")
        uncertainty = _required_mapping(analytical, "uncertainty")
        raw_stance = _required_text(narrative, "state")
        audit = (
            AttentionAudit(
                narrative_identity=narrative_identity,
                story_identity=None,
                source_event_identity=None,
                message_identity=None,
                materiality_decision_identity=None,
                materiality_policy_identity=None,
            )
            if include_audit
            else None
        )
        return _AttentionCandidate(
            dedupe_key=("system_view", symbol, timeframe, subtype),
            importance_rank=_attention_importance_rank(importance),
            event_at_ms=event_at_ms,
            narrative_identity=narrative_identity,
            view=AttentionSituationView(
                symbol=symbol,
                timeframe=timeframe,
                updated_at_ms=event_at_ms,
                freshness_label=_freshness_label(
                    observed_at_ms=observed_at_ms,
                    source_as_of_ms=event_at_ms,
                    stale_after_ms=stale_after_ms,
                ),
                category_label=_CATEGORY_LABELS["intelligence"],
                importance_label=_IMPORTANCE_LABELS[importance],
                state_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
                headline=headline,
                detail=simple_text,
                materiality_label="Güncel sistem görünümü",
                risk_label=_event_risk_label(
                    uncertainty.get("event_risk_state")
                ),
                source_label="System View",
                audit=audit,
            ),
        )

    message_input_raw = detail.get("message_input")
    if not isinstance(message_input_raw, dict):
        return None
    message_input = message_input_raw
    if (
        message_input.get("materiality") != "material"
        or message_input.get("publication_disposition") != "publish"
    ):
        return None

    importance = _required_text(message_input, "importance")
    if importance not in _IMPORTANCE_LABELS:
        return None
    category = _required_text(message_input, "category")
    symbol = _required_text(narrative, "symbol")
    timeframe = _required_text(narrative, "timeframe")
    story_identity = _required_sha(narrative, "story_identity")
    source_as_of_ms = _required_int(message_input, "source_as_of_ms")
    analytical = _required_mapping(detail, "analytical_view")
    fact = _required_mapping(detail, "fact_bundle")
    risk_label = (
        _event_risk_label(fact.get("event_context_state"))
        if fact.get("event_context_state") is not None
        else None
    )
    audit = None
    if include_audit:
        audit = AttentionAudit(
            narrative_identity=narrative_identity,
            story_identity=story_identity,
            source_event_identity=_required_sha(
                message_input,
                "source_event_identity",
            ),
            message_identity=_required_sha(message_input, "message_identity"),
            materiality_decision_identity=_required_sha(
                message_input,
                "materiality_decision_identity",
            ),
            materiality_policy_identity=_required_sha(
                message_input,
                "materiality_policy_identity",
            ),
        )
    return _AttentionCandidate(
        dedupe_key=("story", story_identity),
        importance_rank=_attention_importance_rank(importance),
        event_at_ms=event_at_ms,
        narrative_identity=narrative_identity,
        view=AttentionSituationView(
            symbol=symbol,
            timeframe=timeframe,
            updated_at_ms=event_at_ms,
            freshness_label=_freshness_label(
                observed_at_ms=observed_at_ms,
                source_as_of_ms=source_as_of_ms,
                stale_after_ms=stale_after_ms,
            ),
            category_label=_CATEGORY_LABELS.get(category, "İstihbarat"),
            importance_label=_IMPORTANCE_LABELS[importance],
            state_label=_attention_state_label(analytical, fact),
            headline=headline,
            detail=simple_text,
            materiality_label="Önemli değişim",
            risk_label=risk_label,
            source_label="Intelligence Stream",
            audit=audit,
        ),
    )


def _attention_importance_rank(value: str) -> int:
    return 2 if value == "critical" else 1


def _attention_state_label(
    analytical: dict[str, Any],
    fact: dict[str, Any],
) -> str | None:
    stance = analytical.get("stance")
    if isinstance(stance, dict):
        raw = stance.get("effective_stance")
        if isinstance(raw, str):
            return _STANCE_LABELS.get(raw, "Karışık / izle")
    family_state = analytical.get("family_state_label")
    if isinstance(family_state, str):
        if str(fact.get("source_quality", "")).lower() in {
            "unavailable",
            "missing",
        }:
            return "Veri eksik"
        direction = fact.get("direction")
        if isinstance(direction, str) and direction in _DIRECTION_LABELS:
            return f"{_DIRECTION_LABELS[direction]} yönlü aile değişimi"
        return "Aile durumu güncellendi"
    return None


def _latest_verified_system_view(
    path: Path,
    *,
    symbol: str,
    observed_at_ms: int,
) -> dict[str, Any] | None:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        if not _table_exists(connection, "stream_system_view_messages"):
            return None
        row = _latest_system_view_row(
            connection,
            symbol=symbol,
            observed_at_ms=observed_at_ms,
        )
    if row is None:
        return None
    return verified_system_view_record(
        narrative_identity=str(row[0]),
        event_at_ms=_row_non_negative_int(row[1], "system-view event time"),
        payload_json=str(row[2]),
        expected_digest=str(row[3]),
    )


def _enriched_family_summary(
    row: dict[str, Any],
    *,
    raw_stance: str,
    reader: IntelligenceStreamReadModel,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> FamilySummaryItem:
    base = _family_view(
        row,
        raw_stance=raw_stance,
        include_audit=False,
    )
    source_narrative = row.get("source_narrative_identity")
    if source_narrative is None:
        return FamilySummaryItem(
            family_label=base.family_label,
            state_label=base.state_label,
            direction_label=base.direction_label,
            relationship_label=base.relationship_label,
            source_quality_label=base.source_quality_label,
            source_as_of_ms=None,
            freshness_label="Veri eksik",
            evidence_domain_labels=(),
            uncertainty_label="Kaynak kanıtı yok",
            changed_label="Değişim bilgisi yok",
            timeframe=base.timeframe,
            audit=None,
        )

    narrative_identity = _sha_text(
        source_narrative,
        "family source narrative",
    )
    detail = reader.read_message_detail(narrative_identity)
    if detail is None:
        raise FinalProductReadError("family source narrative is missing")
    fact = _required_mapping(detail, "fact_bundle")
    analytical = _required_mapping(detail, "analytical_view")
    source_as_of_ms = _required_int(fact, "source_as_of_ms")
    if source_as_of_ms > observed_at_ms:
        raise FinalProductReadError("family source is from the future")
    domains = _text_sequence(
        fact.get("available_evidence_domains"),
        "family evidence domains",
    )
    uncertainty_flags = _text_sequence(
        fact.get("uncertainty_flags"),
        "family uncertainty flags",
    )
    changed_components = _text_sequence(
        analytical.get("changed_components"),
        "family changed components",
    )
    previous_state = analytical.get("previous_family_state_label")
    changed_label = (
        "İlk kayıt"
        if previous_state is None
        else f"{len(changed_components)} bileşen değişti"
    )
    uncertainty_label = (
        "Belirgin belirsizlik işareti yok"
        if not uncertainty_flags
        else f"{len(uncertainty_flags)} belirsizlik işareti"
    )

    audit = None
    if include_audit:
        audit = FamilySummaryAudit(
            source_narrative_identity=narrative_identity,
            fact_bundle_identity=_required_sha(fact, "fact_bundle_identity"),
            analytical_view_identity=_required_sha(
                analytical,
                "analytical_view_identity",
            ),
            source_evidence_identities=tuple(
                _sha_text(value, "family evidence identity")
                for value in _required_sequence(fact, "evidence_identities")
            ),
            raw_state_label=_required_text(fact, "state_label"),
            uncertainty_flags=uncertainty_flags,
        )
    return FamilySummaryItem(
        family_label=base.family_label,
        state_label=base.state_label,
        direction_label=base.direction_label,
        relationship_label=base.relationship_label,
        source_quality_label=base.source_quality_label,
        source_as_of_ms=source_as_of_ms,
        freshness_label=_freshness_label(
            observed_at_ms=observed_at_ms,
            source_as_of_ms=source_as_of_ms,
            stale_after_ms=stale_after_ms,
        ),
        evidence_domain_labels=tuple(
            _EVIDENCE_DOMAIN_LABELS.get(
                value,
                "Diğer doğrulanmış kanıt",
            )
            for value in domains
        ),
        uncertainty_label=uncertainty_label,
        changed_label=changed_label,
        timeframe=base.timeframe,
        audit=audit,
    )


def _freshness_label(
    *,
    observed_at_ms: int,
    source_as_of_ms: int,
    stale_after_ms: int,
) -> str:
    if source_as_of_ms > observed_at_ms:
        raise ValueError("source as-of cannot be in the future")
    return (
        "Güncel"
        if observed_at_ms - source_as_of_ms <= stale_after_ms
        else "Güncel değil"
    )


def _text_sequence(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a sequence")
    result = tuple(str(item) for item in value)
    if any(not item.strip() for item in result):
        raise ValueError(f"{label} cannot contain blank text")
    return result


def _normalize_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    if not symbols:
        raise ValueError("market pulse requires at least one symbol")
    result: list[str] = []
    seen: set[str] = set()
    for value in symbols:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("market pulse symbol must be non-empty")
        if symbol in seen:
            continue
        seen.add(symbol)
        result.append(symbol)
    return tuple(result)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _latest_system_view_row(
    connection: sqlite3.Connection,
    *,
    symbol: str,
    observed_at_ms: int,
) -> tuple[object, ...] | None:
    row = connection.execute(
        """
        SELECT narrative_identity, event_at_ms, payload_json, payload_sha256
        FROM stream_system_view_messages
        WHERE symbol = ?
          AND event_at_ms <= ?
        ORDER BY event_at_ms DESC, narrative_identity DESC
        LIMIT 1
        """,
        (symbol, observed_at_ms),
    ).fetchone()
    return None if row is None else tuple(row)


def _market_pulse_asset(
    payload: dict[str, Any],
    *,
    observed_at_ms: int,
    stale_after_ms: int,
    include_audit: bool,
) -> MarketPulseAssetView:
    symbol = _required_text(payload, "symbol")
    timeframe = _required_text(payload, "timeframe")
    event_at_ms = _required_int(payload, "event_at_ms")
    if event_at_ms > observed_at_ms:
        raise FinalProductReadError("market pulse source is from the future")

    fact = _required_mapping(payload, "fact_bundle")
    analytical = _required_mapping(payload, "analytical_view")
    stance = _required_mapping(analytical, "stance")
    uncertainty = _required_mapping(analytical, "uncertainty")
    raw_stance = _required_text(stance, "effective_stance")
    family_rows = _required_sequence(fact, "family_contributions")
    families = tuple(
        _family_view(
            row,
            raw_stance=raw_stance,
            include_audit=include_audit,
        )
        for row in sorted(
            (_mapping_value(value, "family contribution") for value in family_rows),
            key=lambda value: (
                _FAMILY_ORDER.get(str(value.get("family")), 99),
                str(value.get("family")),
            ),
        )
    )

    contradiction = analytical.get("main_contradiction")
    contradiction_label = _contradiction_label(contradiction)
    text = _required_mapping(payload, "text")
    summary = _required_text(text, "collapsed_text")

    audit = None
    if include_audit:
        audit = MarketPulseAudit(
            narrative_identity=_required_sha(payload, "narrative_identity"),
            semantic_identity=_required_sha(payload, "semantic_identity"),
            schema_version=_required_text(payload, "schema_version"),
        )

    return MarketPulseAssetView(
        symbol=symbol,
        timeframe=timeframe,
        updated_at_ms=event_at_ms,
        freshness_label=(
            "Güncel"
            if observed_at_ms - event_at_ms <= stale_after_ms
            else "Güncel değil"
        ),
        stance_label=_STANCE_LABELS.get(raw_stance, "Karışık / izle"),
        support_score_0_100=_decimal_text(
            stance.get("support_score_0_100"),
            "support score",
        ),
        opposition_score_0_100=_decimal_text(
            stance.get("opposition_score_0_100"),
            "opposition score",
        ),
        evidence_coverage_0_100=_decimal_text(
            fact.get("evidence_coverage_0_100"),
            "evidence coverage",
        ),
        probability_label=(
            "Kalibre edilmiş olasılık değil"
            if uncertainty.get("probability_status") == "not_calibrated"
            else "Olasılık durumu doğrulanmadı"
        ),
        event_risk_label=_event_risk_label(
            uncertainty.get("event_risk_state")
        ),
        provider_quality_label=_provider_quality_label(
            uncertainty.get("provider_quality_state")
        ),
        trigger_zone=_optional_mapping(fact.get("trigger_zone")),
        target_zone=_optional_mapping(fact.get("target_zone")),
        invalidation_price=_optional_decimal_text(
            fact.get("invalidation_price")
        ),
        main_contradiction_label=contradiction_label,
        summary=summary,
        families=families,
        audit=audit,
    )


def _family_view(
    row: dict[str, Any],
    *,
    raw_stance: str,
    include_audit: bool,
) -> MarketPulseFamilyView:
    family = _required_text(row, "family")
    raw_state = str(row.get("state", ""))
    direction = row.get("direction")
    direction_text = direction if isinstance(direction, str) else None
    support = _decimal(row.get("support_points"), "family support")
    opposition = _decimal(row.get("opposition_points"), "family opposition")

    if raw_state == "no_evidence":
        state_label = "Veri eksik"
    elif raw_state == "abstain":
        state_label = "Teyit yetersiz"
    elif raw_state == "observed":
        state_label = "Veri mevcut"
    else:
        state_label = "Durum doğrulanmadı"

    if support > 0:
        relationship = "Destekliyor"
    elif opposition > 0:
        relationship = "Çelişiyor"
    elif raw_state == "observed" and direction_text in {"bullish", "bearish"}:
        relationship = (
            "Destekliyor"
            if direction_text == raw_stance
            else "Karışık"
        )
    elif raw_state == "no_evidence":
        relationship = "Veri eksik"
    else:
        relationship = "Karışık"

    audit = None
    if include_audit:
        source_narrative = row.get("source_narrative_identity")
        if source_narrative is not None:
            source_narrative = _sha_text(
                source_narrative,
                "family source narrative",
            )
        source_ids_raw = row.get("source_evidence_identities", ())
        if not isinstance(source_ids_raw, (list, tuple)):
            raise TypeError("family source evidence identities must be a sequence")
        source_ids = tuple(
            _sha_text(value, "family source evidence")
            for value in source_ids_raw
        )
        audit = MarketPulseFamilyAudit(
            source_narrative_identity=source_narrative,
            source_evidence_identities=source_ids,
        )

    return MarketPulseFamilyView(
        family=family,
        family_label=_FAMILY_LABELS.get(family, family.replace("_", " ").title()),
        weight_points=_decimal_text(row.get("weight_points"), "family weight"),
        state_label=state_label,
        direction_label=(
            None
            if direction_text is None
            else _DIRECTION_LABELS.get(direction_text, "Karışık")
        ),
        relationship_label=relationship,
        source_quality_label=_source_quality_label(row.get("source_quality")),
        timeframe=(
            None
            if row.get("timeframe") is None
            else str(row.get("timeframe"))
        ),
        audit=audit,
    )


def _contradiction_label(value: object) -> str | None:
    if value is None:
        return None
    raw = _mapping_value(value, "main contradiction")
    family = raw.get("family")
    points = raw.get("opposition_points")
    if not isinstance(family, str):
        return "Ana çelişki mevcut"
    label = _FAMILY_LABELS.get(family, family.replace("_", " ").title())
    if points is None:
        return f"{label} çelişiyor"
    return f"{label} çelişiyor ({_decimal_text(points, 'opposition points')} puan)"


def _source_quality_label(value: object) -> str:
    raw = "" if value is None else str(value).strip().lower()
    if raw in {"unavailable", "no_evidence", "missing"}:
        return "Veri eksik"
    if raw in {"stale", "degraded", "degraded_provider_stale"}:
        return "Güncel değil"
    if raw in {"unresolved", "not_evaluable"}:
        return "Kararsız"
    return "Kaynak gözlemlendi"


def _event_risk_label(value: object) -> str:
    if value is None:
        return "Event verisi yok"
    raw = str(value).strip().lower()
    return _EVENT_RISK_LABELS.get(raw, "Event durumu mevcut")


def _provider_quality_label(value: object) -> str:
    if value is None:
        return "Kaynak durumu yok"
    raw = str(value).strip().lower()
    return _PROVIDER_QUALITY_LABELS.get(raw, "Kaynak durumu mevcut")


def _required_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    return _mapping_value(value.get(key), key)


def _mapping_value(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _optional_mapping(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    return _mapping_value(value, "optional market pulse mapping")


def _required_sequence(
    value: dict[str, Any],
    key: str,
) -> tuple[object, ...]:
    raw = value.get(key)
    if not isinstance(raw, (list, tuple)):
        raise TypeError(f"{key} must be a sequence")
    return tuple(raw)


def _required_text(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise TypeError(f"{key} must be non-empty text")
    return raw


def _row_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.isdigit():
        result = int(value)
    else:
        raise TypeError(f"{label} must be a non-negative integer")
    if result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def _required_int(value: dict[str, Any], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise TypeError(f"{key} must be a non-negative integer")
    return raw


def _decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be decimal-compatible") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _decimal_text(value: object, label: str) -> str:
    return f"{_decimal(value, label).quantize(Decimal('0.01')):.2f}"


def _optional_decimal_text(value: object) -> str | None:
    if value is None:
        return None
    return _decimal_text(value, "optional decimal")


def _required_sha(value: dict[str, Any], key: str) -> str:
    return _sha_text(value.get(key), key)


def _sha_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be SHA256 text")
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{label} must be exact lowercase SHA256")
    return value
