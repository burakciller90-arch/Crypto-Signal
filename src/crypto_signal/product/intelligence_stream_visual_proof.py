from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from crypto_signal.decision_ledger import (
    DecisionLedgerConflictError,
    ImmutableDecisionEvidenceLedger,
)
from crypto_signal.ledger.serialization import canonical_sha256, sha256_text
from crypto_signal.ledger.store import ImmutableSignalLedger, LedgerConflictError
from crypto_signal.product.intelligence_stream_read_model import (
    IntelligenceStreamReadModel,
    StreamReadModelError,
)

STREAM_VISUAL_PROOF_SCHEMA_VERSION = "intelligence-stream-visual-proof-v1/1"
DECISION_FREEZE_SCHEMA_VERSION = "decision-freeze-v1/1"
REAL_CAPITAL = 0


class StreamVisualProofError(ValueError):
    """Raised when persisted frozen proof lineage cannot be trusted."""


class IntelligenceStreamVisualProofReadModel:
    """Read-only S10 projection over exact persisted Stream/Proof/Freeze lineage."""

    def __init__(
        self,
        *,
        stream_ledger_path: Path,
        signal_ledger_path: Path,
        decision_evidence_path: Path,
    ) -> None:
        self.stream_ledger_path = stream_ledger_path
        self.signal_ledger_path = signal_ledger_path
        self.decision_evidence_path = decision_evidence_path

    def read_for_narrative(
        self,
        narrative_identity: str,
    ) -> dict[str, Any] | None:
        _require_sha256(narrative_identity, "visual proof narrative identity")
        try:
            detail = IntelligenceStreamReadModel(
                self.stream_ledger_path
            ).read_message_detail(narrative_identity)
        except StreamReadModelError as exc:
            raise StreamVisualProofError(str(exc)) from exc
        if detail is None:
            return None

        fact = _mapping(detail.get("fact_bundle"), "visual proof fact bundle")
        forecast_identity = _sha_from(
            fact,
            "forecast_identity",
            "visual proof forecast identity",
        )
        expected_proof_identity = _sha_from(
            fact,
            "proof_identity",
            "visual proof expected proof identity",
        )

        try:
            proof = ImmutableDecisionEvidenceLedger(
                self.decision_evidence_path
            ).read_proof_for_forecast(forecast_identity)
        except (DecisionLedgerConflictError, ValueError, FileNotFoundError) as exc:
            raise StreamVisualProofError(str(exc)) from exc
        if proof is None:
            return self._unavailable_projection(
                narrative_identity=narrative_identity,
                fact=fact,
                reason="persisted_decision_proof_missing",
                lineage={
                    "narrative_identity": narrative_identity,
                    "forecast_identity": forecast_identity,
                    "proof_identity": expected_proof_identity,
                },
            )

        self._verify_proof_lineage(
            fact=fact,
            proof=proof,
            forecast_identity=forecast_identity,
            expected_proof_identity=expected_proof_identity,
        )
        signal_freeze_identity = _sha_from(
            proof,
            "signal_freeze_identity",
            "visual proof signal freeze identity",
        )

        try:
            freeze = ImmutableSignalLedger(
                self.signal_ledger_path
            ).read_freeze_by_signal(signal_freeze_identity)
        except (LedgerConflictError, ValueError) as exc:
            raise StreamVisualProofError(str(exc)) from exc
        if freeze is None:
            return self._unavailable_projection(
                narrative_identity=narrative_identity,
                fact=fact,
                reason="persisted_signal_freeze_missing",
                lineage={
                    "narrative_identity": narrative_identity,
                    "forecast_identity": forecast_identity,
                    "proof_identity": expected_proof_identity,
                    "signal_freeze_identity": signal_freeze_identity,
                },
                proof=proof,
            )

        if sha256_text(freeze.bundle_json) != freeze.bundle_identity:
            raise StreamVisualProofError(
                "visual proof persisted decision-freeze bundle digest mismatch"
            )
        try:
            bundle = json.loads(freeze.bundle_json)
        except json.JSONDecodeError as exc:
            raise StreamVisualProofError(
                "visual proof decision-freeze bundle JSON is invalid"
            ) from exc
        if not isinstance(bundle, dict):
            raise StreamVisualProofError(
                "visual proof decision-freeze bundle must decode to object"
            )

        self._verify_bundle_lineage(
            fact=fact,
            proof=proof,
            bundle=bundle,
            freeze=freeze,
        )
        candles = self._verified_candles(
            bundle=bundle,
            freeze=freeze,
            proof=proof,
        )
        annotations = self._annotations(
            bundle=bundle,
            freeze=freeze,
            proof=proof,
        )
        domain_evidence = self._domain_manifest(proof, freeze_available=True)
        family_scores = self._family_scores(fact)

        return {
            "schema_version": STREAM_VISUAL_PROOF_SCHEMA_VERSION,
            "status": "ready",
            "visual_kind": "frozen_ohlc",
            "narrative_identity": narrative_identity,
            "symbol": proof.get("symbol"),
            "timeframe": proof.get("timeframe"),
            "lineage": {
                "narrative_identity": narrative_identity,
                "forecast_identity": forecast_identity,
                "proof_identity": expected_proof_identity,
                "signal_freeze_identity": signal_freeze_identity,
                "decision_freeze_bundle_identity": freeze.bundle_identity,
            },
            "provenance": {
                "source_as_of_ms": _int_from(
                    proof,
                    "source_as_of_ms",
                    "visual proof source as-of",
                ),
                "issued_at_ms": _int_from(
                    proof,
                    "issued_at_ms",
                    "visual proof issued-at",
                ),
                "frozen_at_ms": freeze.frozen_at_ms,
                "source_cutoff_open_time_ms": freeze.source_cutoff_open_time_ms,
                "candle_source": "immutable_signal_freeze_bundle",
                "current_data_substitution": False,
                "exact_persisted": True,
            },
            "candles": candles,
            "annotations": annotations,
            "score_components": {
                "confluence_support_score_0_100": proof.get(
                    "confluence_support_score_0_100"
                ),
                "confluence_opposition_score_0_100": proof.get(
                    "confluence_opposition_score_0_100"
                ),
                "family_contributions": family_scores,
                "evidence_summary": proof.get("evidence_summary"),
            },
            "domain_evidence": domain_evidence,
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }

    @staticmethod
    def _verify_proof_lineage(
        *,
        fact: dict[str, Any],
        proof: dict[str, Any],
        forecast_identity: str,
        expected_proof_identity: str,
    ) -> None:
        if proof.get("forecast_identity") != forecast_identity:
            raise StreamVisualProofError(
                "visual proof forecast/proof identity mismatch"
            )
        if proof.get("proof_identity") != expected_proof_identity:
            raise StreamVisualProofError(
                "visual proof message/proof identity mismatch"
            )
        for key in ("symbol", "timeframe"):
            if proof.get(key) != fact.get(key):
                raise StreamVisualProofError(
                    f"visual proof fact/proof lineage mismatch for {key}"
                )
        source_as_of = _int_from(
            proof,
            "source_as_of_ms",
            "visual proof source as-of",
        )
        fact_as_of = _int_from(
            fact,
            "source_as_of_ms",
            "visual proof fact source as-of",
        )
        if source_as_of != fact_as_of:
            raise StreamVisualProofError(
                "visual proof fact/proof source-as-of mismatch"
            )
        if proof.get("read_only") is not True:
            raise StreamVisualProofError("visual proof proof is not read-only")
        if proof.get("production_authority") is not False:
            raise StreamVisualProofError(
                "visual proof proof has production authority"
            )
        if proof.get("real_capital") != REAL_CAPITAL:
            raise StreamVisualProofError(
                "visual proof proof REAL_CAPITAL mismatch"
            )

    @staticmethod
    def _verify_bundle_lineage(
        *,
        fact: dict[str, Any],
        proof: dict[str, Any],
        bundle: dict[str, Any],
        freeze: Any,
    ) -> None:
        if bundle.get("schema_version") != DECISION_FREEZE_SCHEMA_VERSION:
            raise StreamVisualProofError(
                "visual proof decision-freeze schema mismatch"
            )
        decision = _mapping(
            bundle.get("signal_decision"),
            "visual proof signal decision",
        )
        signal_identity = _sha_from(
            proof,
            "signal_freeze_identity",
            "visual proof signal freeze identity",
        )
        if decision.get("freeze_identity") != signal_identity:
            raise StreamVisualProofError(
                "visual proof proof/freeze signal identity mismatch"
            )
        if freeze.signal_freeze_identity != signal_identity:
            raise StreamVisualProofError(
                "visual proof freeze record signal identity mismatch"
            )
        if freeze.bundle_identity == signal_identity:
            raise StreamVisualProofError(
                "visual proof bundle identity cannot alias signal identity"
            )
        for key, expected in (
            ("symbol", proof.get("symbol")),
            ("timeframe", proof.get("timeframe")),
            ("as_of_ms", proof.get("source_as_of_ms")),
        ):
            if decision.get(key) != expected:
                raise StreamVisualProofError(
                    f"visual proof freeze/proof mismatch for {key}"
                )
        if freeze.symbol != proof.get("symbol"):
            raise StreamVisualProofError(
                "visual proof freeze record symbol mismatch"
            )
        if freeze.timeframe != proof.get("timeframe"):
            raise StreamVisualProofError(
                "visual proof freeze record timeframe mismatch"
            )
        if freeze.as_of_ms != _int_from(
            proof,
            "source_as_of_ms",
            "visual proof source as-of",
        ):
            raise StreamVisualProofError(
                "visual proof freeze record as-of mismatch"
            )
        if fact.get("symbol") != freeze.symbol or fact.get("timeframe") != freeze.timeframe:
            raise StreamVisualProofError(
                "visual proof Stream/freeze market lineage mismatch"
            )

    @staticmethod
    def _verified_candles(
        *,
        bundle: dict[str, Any],
        freeze: Any,
        proof: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        raw = bundle.get("candles")
        if not isinstance(raw, list) or not raw:
            raise StreamVisualProofError(
                "visual proof freeze contains no consumed candles"
            )
        source_as_of = _int_from(
            proof,
            "source_as_of_ms",
            "visual proof source as-of",
        )
        candles: list[dict[str, Any]] = []
        previous_open: int | None = None
        for index, value in enumerate(raw):
            candle = _mapping(value, f"visual proof candle[{index}]")
            open_time = _int_from(
                candle,
                "open_time_ms",
                f"visual proof candle[{index}] open",
            )
            close_time = _int_from(
                candle,
                "close_time_ms",
                f"visual proof candle[{index}] close",
            )
            ingested_at = _int_from(
                candle,
                "ingested_at_ms",
                f"visual proof candle[{index}] ingested-at",
            )
            if close_time <= open_time:
                raise StreamVisualProofError(
                    "visual proof candle time bounds are invalid"
                )
            if close_time > source_as_of or ingested_at > source_as_of:
                raise StreamVisualProofError(
                    "visual proof candle leaks future information"
                )
            if candle.get("is_closed") is not True:
                raise StreamVisualProofError(
                    "visual proof candle must be closed"
                )
            if (
                candle.get("exchange") != freeze.exchange
                or candle.get("market_type") != freeze.market_type
                or candle.get("symbol") != freeze.symbol
                or candle.get("timeframe") != freeze.timeframe
            ):
                raise StreamVisualProofError(
                    "visual proof candle market context mismatch"
                )
            if previous_open is not None and open_time <= previous_open:
                raise StreamVisualProofError(
                    "visual proof candles must be strictly chronological"
                )
            previous_open = open_time
            prices = {
                name: _positive_decimal(
                    candle.get(name),
                    f"visual proof candle[{index}] {name}",
                )
                for name in ("open", "high", "low", "close")
            }
            if prices["high"] < max(prices["open"], prices["close"]):
                raise StreamVisualProofError(
                    "visual proof candle high is inconsistent"
                )
            if prices["low"] > min(prices["open"], prices["close"]):
                raise StreamVisualProofError(
                    "visual proof candle low is inconsistent"
                )
            if prices["low"] > prices["high"]:
                raise StreamVisualProofError(
                    "visual proof candle low exceeds high"
                )
            candles.append(
                {
                    "candle_identity": (
                        freeze.exchange,
                        freeze.market_type,
                        freeze.symbol,
                        freeze.timeframe,
                        open_time,
                    ),
                    "open_time_ms": open_time,
                    "close_time_ms": close_time,
                    "open": str(prices["open"]),
                    "high": str(prices["high"]),
                    "low": str(prices["low"]),
                    "close": str(prices["close"]),
                    "volume": candle.get("volume"),
                    "source": candle.get("source"),
                    "source_timestamp_ms": candle.get("source_timestamp_ms"),
                    "ingested_at_ms": ingested_at,
                }
            )
        if candles[-1]["open_time_ms"] != freeze.source_cutoff_open_time_ms:
            raise StreamVisualProofError(
                "visual proof newest candle does not match source cutoff"
            )
        return tuple(candles)

    @staticmethod
    def _annotations(
        *,
        bundle: dict[str, Any],
        freeze: Any,
        proof: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        decision = _mapping(
            bundle.get("signal_decision"),
            "visual proof signal decision",
        )
        geometry = _mapping(
            decision.get("geometry"),
            "visual proof signal geometry",
        )
        source_evidence_identity = str(
            geometry.get("source_evidence_id") or ""
        )
        if not source_evidence_identity:
            raise StreamVisualProofError(
                "visual proof geometry source evidence identity missing"
            )
        signal_identity = _sha_from(
            proof,
            "signal_freeze_identity",
            "visual proof signal freeze identity",
        )
        base = {
            "signal_freeze_identity": signal_identity,
            "decision_freeze_bundle_identity": freeze.bundle_identity,
            "source_evidence_identity": source_evidence_identity,
            "source_methodology": geometry.get("source_methodology"),
        }

        entry = _mapping(
            geometry.get("entry_zone"),
            "visual proof entry zone",
        )
        entry_low = _positive_decimal(
            entry.get("low"),
            "visual proof entry low",
        )
        entry_high = _positive_decimal(
            entry.get("high"),
            "visual proof entry high",
        )
        if entry_low > entry_high:
            raise StreamVisualProofError(
                "visual proof entry zone is inverted"
            )
        annotations: list[dict[str, Any]] = []
        annotations.append(
            _annotation(
                base=base,
                kind="entry_zone",
                label="Tetik bölgesi",
                low=entry_low,
                high=entry_high,
            )
        )
        annotations.append(
            _annotation(
                base=base,
                kind="invalidation",
                label="Geçersizleşme",
                price=_positive_decimal(
                    geometry.get("invalidation_price"),
                    "visual proof invalidation price",
                ),
            )
        )
        targets = geometry.get("targets")
        if not isinstance(targets, list) or not targets:
            raise StreamVisualProofError(
                "visual proof geometry targets missing"
            )
        for index, item in enumerate(targets):
            target = _mapping(
                item,
                f"visual proof target[{index}]",
            )
            label = str(target.get("label") or "").strip()
            if not label:
                raise StreamVisualProofError(
                    "visual proof target label missing"
                )
            annotations.append(
                _annotation(
                    base=base,
                    kind="target",
                    label=label,
                    price=_positive_decimal(
                        target.get("target_price"),
                        f"visual proof target[{index}] price",
                    ),
                )
            )
        return tuple(annotations)

    @staticmethod
    def _domain_manifest(
        proof: dict[str, Any],
        *,
        freeze_available: bool,
    ) -> tuple[dict[str, Any], ...]:
        raw = proof.get("evidence_slices")
        if not isinstance(raw, list):
            raise StreamVisualProofError(
                "visual proof evidence slices missing"
            )
        domains: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, value in enumerate(raw):
            item = _mapping(
                value,
                f"visual proof evidence slice[{index}]",
            )
            domain = str(item.get("domain") or "")
            if not domain or domain in seen:
                raise StreamVisualProofError(
                    "visual proof evidence domain is missing or duplicated"
                )
            seen.add(domain)
            availability = str(item.get("availability") or "")
            identities_raw = item.get("evidence_identities")
            if not isinstance(identities_raw, list):
                raise StreamVisualProofError(
                    "visual proof evidence identities must be list"
                )
            identities = tuple(str(value) for value in identities_raw)
            for identity in identities:
                _require_sha256(
                    identity,
                    f"visual proof {domain} evidence identity",
                )
            if availability == "available" and not identities:
                raise StreamVisualProofError(
                    "visual proof available domain lacks evidence identity"
                )
            if availability != "available" and identities:
                raise StreamVisualProofError(
                    "visual proof unavailable domain carries evidence identity"
                )

            if domain in {"frozen_chart", "consumed_candles"} and freeze_available:
                visual_state = "resolved_frozen_bundle"
            elif availability == "available":
                visual_state = "identity_only"
            else:
                visual_state = "unavailable"

            domains.append(
                {
                    "slice_identity": item.get("slice_identity"),
                    "domain": domain,
                    "availability": availability,
                    "verdict": item.get("verdict"),
                    "evidence_identities": identities,
                    "market_available_at_ms": item.get(
                        "market_available_at_ms"
                    ),
                    "observed_at_ms": item.get("observed_at_ms"),
                    "freshness_0_1": item.get("freshness_0_1"),
                    "source_quality": item.get("source_quality"),
                    "summary_codes": item.get("summary_codes"),
                    "visual_state": visual_state,
                    "visual_reason": (
                        "exact_frozen_bundle_resolved"
                        if visual_state == "resolved_frozen_bundle"
                        else (
                            "exact_identity_exists_but_no_bound_persisted_visual_payload"
                            if visual_state == "identity_only"
                            else "proof_domain_not_available"
                        )
                    ),
                }
            )
        return tuple(domains)

    @staticmethod
    def _family_scores(fact: dict[str, Any]) -> tuple[dict[str, Any], ...]:
        raw = fact.get("family_contributions")
        if not isinstance(raw, list):
            raise StreamVisualProofError(
                "visual proof family contribution list missing"
            )
        return tuple(
            {
                "family": item.get("family"),
                "state": item.get("state"),
                "direction": item.get("direction"),
                "support_points": item.get("support_points"),
                "opposition_points": item.get("opposition_points"),
                "evidence_quality_0_1": item.get("evidence_quality_0_1"),
                "freshness_0_1": item.get("freshness_0_1"),
                "source_evidence_identities": item.get(
                    "source_evidence_identities"
                ),
            }
            for item in (
                _mapping(value, "visual proof family contribution")
                for value in raw
            )
        )

    @staticmethod
    def _unavailable_projection(
        *,
        narrative_identity: str,
        fact: dict[str, Any],
        reason: str,
        lineage: dict[str, Any],
        proof: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": STREAM_VISUAL_PROOF_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": reason,
            "narrative_identity": narrative_identity,
            "symbol": fact.get("symbol"),
            "timeframe": fact.get("timeframe"),
            "lineage": lineage,
            "domain_evidence": (
                ()
                if proof is None
                else IntelligenceStreamVisualProofReadModel._domain_manifest(
                    proof,
                    freeze_available=False,
                )
            ),
            "read_only": True,
            "production_authority": False,
            "real_capital": REAL_CAPITAL,
        }


def _annotation(
    *,
    base: dict[str, Any],
    kind: str,
    label: str,
    low: Decimal | None = None,
    high: Decimal | None = None,
    price: Decimal | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **base,
        "kind": kind,
        "label": label,
        "low": None if low is None else str(low),
        "high": None if high is None else str(high),
        "price": None if price is None else str(price),
    }
    return {
        "annotation_identity": canonical_sha256(payload),
        **payload,
    }


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StreamVisualProofError(f"{label} must be object")
    return value


def _sha_from(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise StreamVisualProofError(f"{label} missing")
    _require_sha256(value, label)
    return value


def _int_from(
    payload: dict[str, Any],
    key: str,
    label: str,
) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StreamVisualProofError(f"{label} must be non-negative integer")
    return value


def _positive_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise StreamVisualProofError(f"{label} must be exact decimal string")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise StreamVisualProofError(f"{label} is invalid decimal") from exc
    if parsed <= 0:
        raise StreamVisualProofError(f"{label} must be positive")
    return parsed


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise StreamVisualProofError(f"{label} must be lowercase SHA256")
