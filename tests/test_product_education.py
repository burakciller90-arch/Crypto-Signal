"""Focused tests for the Stage 6B deterministic education core."""

from __future__ import annotations

import pytest

from crypto_signal.product.education import (
    REQUIRED_CONCEPT_IDS,
    EducationConceptId,
    EducationLookupFound,
    EducationLookupMissing,
    EducationLookupStatus,
    all_education_lessons,
    lookup_education_lesson,
    require_education_lesson,
)

REQUIRED_IDS = (
    EducationConceptId.BOS,
    EducationConceptId.CHOCH,
    EducationConceptId.LIQUIDITY_SWEEP,
    EducationConceptId.CVD,
    EducationConceptId.ABSORPTION,
    EducationConceptId.LIQUIDATION_HEATMAP,
    EducationConceptId.FVG,
    EducationConceptId.HARMONIC_PRZ,
    EducationConceptId.ELLIOTT_WAVE,
    EducationConceptId.INVALIDATION,
    EducationConceptId.RISK_REWARD,
    EducationConceptId.AGREEMENT_VS_PROBABILITY,
    EducationConceptId.CALIBRATION,
    EducationConceptId.ABSTAIN,
    EducationConceptId.PAPER_TRADING,
)


def test_required_concepts_are_present_and_unique() -> None:
    lessons = all_education_lessons()
    ids = [lesson.concept_id for lesson in lessons]

    assert frozenset(ids) == REQUIRED_CONCEPT_IDS
    assert frozenset(REQUIRED_IDS) == REQUIRED_CONCEPT_IDS
    assert len(ids) == len(set(ids))
    assert ids == list(EducationConceptId)
    for concept_id in REQUIRED_IDS:
        assert concept_id in ids


def test_turkish_beginner_text_is_present_for_every_lesson() -> None:
    turkish_markers = ("ı", "İ", "ş", "Ş", "ğ", "Ğ", "ü", "Ü", "ö", "Ö", "ç", "Ç")
    for lesson in all_education_lessons():
        assert lesson.title_tr.strip()
        assert lesson.beginner_tr.strip()
        assert lesson.why_it_matters_tr.strip()
        blob = f"{lesson.title_tr} {lesson.beginner_tr} {lesson.why_it_matters_tr}"
        assert any(marker in blob for marker in turkish_markers)
        assert "%" not in lesson.beginner_tr
        assert "win rate" not in lesson.beginner_tr.lower()


def test_agreement_is_not_probability_rule() -> None:
    lesson = require_education_lesson(EducationConceptId.AGREEMENT_VS_PROBABILITY)
    beginner = lesson.beginner_tr.lower()
    advanced = (lesson.advanced_tr or "").lower()

    assert "uyum" in beginner or "agreement" in beginner
    assert "olasılık" in beginner
    assert "değildir" in beginner or "uydurmaz" in beginner
    assert "kalibre" in beginner or "kalibr" in advanced
    assert "kazanma olasılığı değildir" in beginner or "olasılık değildir" in beginner
    assert "%" not in lesson.beginner_tr
    assert "probability" in advanced or "ProbabilityStatus" in (lesson.advanced_tr or "")


def test_liquidity_sweep_is_bounded_candidate_not_stop_hunt_proof() -> None:
    lesson = require_education_lesson(EducationConceptId.LIQUIDITY_SWEEP)
    text = " ".join(
        part
        for part in (lesson.beginner_tr, lesson.why_it_matters_tr, lesson.advanced_tr)
        if part is not None
    ).lower()

    assert "aday" in text
    assert "manipülasyon" in text
    assert "kanıtlandığı anlamına gelmez" in text or "ispatı değildir" in text
    assert "görünür derinlik" in text
    assert "agresif" in text
    assert "displacement" in text


def test_new_microstructure_and_trust_lessons_preserve_boundaries() -> None:
    cvd = require_education_lesson(EducationConceptId.CVD)
    absorption = require_education_lesson(EducationConceptId.ABSORPTION)
    liquidation = require_education_lesson(EducationConceptId.LIQUIDATION_HEATMAP)
    calibration = require_education_lesson(EducationConceptId.CALIBRATION)
    abstain = require_education_lesson(EducationConceptId.ABSTAIN)

    assert "tek başına yön emri değildir" in cvd.beginner_tr
    assert "otomatik alım veya satım sinyali değildir" in absorption.beginner_tr
    assert "gelecekte" in liquidation.beginner_tr
    assert "stoplarının nerede olduğunu söylemez" in liquidation.beginner_tr
    assert "kalibre edilmiş olasılık değildir" in calibration.beginner_tr
    assert "NOT CALIBRATED" in (calibration.advanced_tr or "")
    assert "işlem fikri üretmemeyi" in abstain.beginner_tr
    assert "track record'dan silinmez" in (abstain.advanced_tr or "")


def test_paper_trading_states_real_capital_zero() -> None:
    lesson = require_education_lesson(EducationConceptId.PAPER_TRADING)
    text = " ".join(
        part
        for part in (lesson.beginner_tr, lesson.why_it_matters_tr, lesson.advanced_tr)
        if part is not None
    )

    assert "REAL_CAPITAL=0" in text
    assert "sanal" in text.lower() or "paper" in text.lower() or "kâğıt" in text.lower()
    assert "gerçek borsa emri yoktur" in lesson.beginner_tr.lower() or "gerçek borsa emri yoktur" in text
    assert "Epoch 1" in text
    assert "100 USDT" in text
    assert "Epoch 2" in text
    assert "1.000 USDT" in text
    assert "ölçeklenmez" in text


def test_deterministic_lookup_by_canonical_id() -> None:
    first = lookup_education_lesson("bos")
    second = lookup_education_lesson(EducationConceptId.BOS)
    third = require_education_lesson("bos")

    assert isinstance(first, EducationLookupFound)
    assert isinstance(second, EducationLookupFound)
    assert first.status is EducationLookupStatus.FOUND
    assert first.lesson is second.lesson
    assert first.lesson is third
    assert first.lesson.concept_id is EducationConceptId.BOS
    assert first.lesson.title_tr.startswith("BOS")


def test_unknown_concept_returns_typed_missing_and_require_fails() -> None:
    result = lookup_education_lesson("not_a_real_concept")

    assert isinstance(result, EducationLookupMissing)
    assert result.status is EducationLookupStatus.MISSING
    assert result.requested_id == "not_a_real_concept"

    with pytest.raises(KeyError, match="unknown education concept id"):
        require_education_lesson("not_a_real_concept")


def test_optional_advanced_notes_exist_for_catalog() -> None:
    for lesson in all_education_lessons():
        assert lesson.advanced_tr is not None
        assert lesson.advanced_tr.strip()


def test_lookup_is_stable_across_repeated_calls() -> None:
    results = [lookup_education_lesson(EducationConceptId.FVG) for _ in range(5)]
    assert all(isinstance(item, EducationLookupFound) for item in results)
    lessons = [item.lesson for item in results if isinstance(item, EducationLookupFound)]
    assert all(lesson is lessons[0] for lesson in lessons)
    assert all(lesson.concept_id is EducationConceptId.FVG for lesson in lessons)
