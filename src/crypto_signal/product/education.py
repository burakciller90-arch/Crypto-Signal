"""Deterministic beginner education core for Stage 6B \"Bana Öğret\".

Turkish-first lesson catalog only. No LLM calls, no market prediction, and no
fabricated probability. REAL_CAPITAL remains 0; paper-trading content is virtual.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class EducationConceptId(StrEnum):
    """Canonical concept identifiers for stable lesson lookup."""

    BOS = "bos"
    CHOCH = "choch"
    LIQUIDITY_SWEEP = "liquidity_sweep"
    FVG = "fvg"
    HARMONIC_PRZ = "harmonic_prz"
    ELLIOTT_WAVE = "elliott_wave"
    INVALIDATION = "invalidation"
    RISK_REWARD = "risk_reward"
    AGREEMENT_VS_PROBABILITY = "agreement_vs_probability"
    PAPER_TRADING = "paper_trading"


class EducationLookupStatus(StrEnum):
    FOUND = "found"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class EducationLesson:
    """One teachable concept for the future \"Bana Öğret\" UI."""

    concept_id: EducationConceptId
    title_tr: str
    beginner_tr: str
    why_it_matters_tr: str
    advanced_tr: str | None = None

    def __post_init__(self) -> None:
        if not self.title_tr.strip():
            raise ValueError("title_tr must be non-empty")
        if not self.beginner_tr.strip():
            raise ValueError("beginner_tr must be non-empty")
        if not self.why_it_matters_tr.strip():
            raise ValueError("why_it_matters_tr must be non-empty")
        if self.advanced_tr is not None and not self.advanced_tr.strip():
            raise ValueError("advanced_tr must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class EducationLookupFound:
    status: EducationLookupStatus
    lesson: EducationLesson

    def __post_init__(self) -> None:
        if self.status is not EducationLookupStatus.FOUND:
            raise ValueError("found result must use FOUND status")


@dataclass(frozen=True, slots=True)
class EducationLookupMissing:
    """Explicit typed miss when a concept id is unknown."""

    status: EducationLookupStatus
    requested_id: str

    def __post_init__(self) -> None:
        if self.status is not EducationLookupStatus.MISSING:
            raise ValueError("missing result must use MISSING status")
        if not self.requested_id.strip():
            raise ValueError("requested_id must be non-empty")


EducationLookupResult = EducationLookupFound | EducationLookupMissing

REQUIRED_CONCEPT_IDS: Final[frozenset[EducationConceptId]] = frozenset(EducationConceptId)


def _lesson(
    concept_id: EducationConceptId,
    *,
    title_tr: str,
    beginner_tr: str,
    why_it_matters_tr: str,
    advanced_tr: str | None = None,
) -> EducationLesson:
    return EducationLesson(
        concept_id=concept_id,
        title_tr=title_tr,
        beginner_tr=beginner_tr,
        why_it_matters_tr=why_it_matters_tr,
        advanced_tr=advanced_tr,
    )


_LESSON_CATALOG: Final[tuple[EducationLesson, ...]] = (
    _lesson(
        EducationConceptId.BOS,
        title_tr="BOS — Yapı Kırılımı",
        beginner_tr=(
            "BOS (Break of Structure), fiyatın önceki önemli zirve veya dip "
            "noktasını net biçimde geçmesi demektir. Bu, mevcut yönün devam "
            "ettiğine dair yapısal bir işarettir; tek başına alım veya satım "
            "emri değildir."
        ),
        why_it_matters_tr=(
            "Grafikte yönün hâlâ geçerli olup olmadığını sade dilde gösterir; "
            "yeni bir tahmin üretmez."
        ),
        advanced_tr=(
            "Kapanış bazlı BOS, fitil dokunuşundan daha sıkı bir doğrulama "
            "ister. Sistem yalnızca dondurulmuş kanıtta görülen kırılımı "
            "öğretir; canlı mum geçmiş kararı yeniden yazamaz."
        ),
    ),
    _lesson(
        EducationConceptId.CHOCH,
        title_tr="CHoCH — Karakter Değişimi",
        beginner_tr=(
            "CHoCH (Change of Character), önceki trend karakterinin bozulmaya "
            "başladığını gösteren yapı değişimidir. Yükselişte önemli bir dip "
            "kırılırsa veya düşüşte önemli bir zirve kırılırsa karakter "
            "değişimi konuşulur. Bu, kesin dönüş garantisi değildir."
        ),
        why_it_matters_tr=(
            "Trendin hâlâ aynı şekilde davrandığını mı, yoksa karakterinin "
            "değişip değişmediğini mi ayırmaya yardım eder."
        ),
        advanced_tr=(
            "CHoCH çoğu zaman BOS'tan önce erken bir uyarıdır. Sistem bunu "
            "olasılık yüzdesine çevirmez; yalnızca yapısal bağlam olarak "
            "sunar."
        ),
    ),
    _lesson(
        EducationConceptId.LIQUIDITY_SWEEP,
        title_tr="Likidite Süpürmesi",
        beginner_tr=(
            "Likidite süpürmesi, fiyatın kısa süreyle bariz zirve/dip "
            "seviyelerini aşıp birçok kişinin stop emrini tetiklemesi, sonra "
            "geri dönmesidir. Bu, 'tuzak' gibi görünebilir; ama sistem bunu "
            "kazanç vaadi olarak sunmaz."
        ),
        why_it_matters_tr=(
            "Neden ani bir kırılımın hemen ardından fiyatın geri gelebileceğini "
            "anlamayı kolaylaştırır."
        ),
        advanced_tr=(
            "Süpürme, eşit dip/zirve havuzları veya bariz stop kümeleri "
            "üzerinde aranır. Kanıt yoksa sistem uydurmaz; eksik veriyi "
            "sessizce doldurmaz."
        ),
    ),
    _lesson(
        EducationConceptId.FVG,
        title_tr="FVG — Adil Değer Boşluğu",
        beginner_tr=(
            "FVG (Fair Value Gap), hızlı bir hareket sırasında grafikte "
            "bırakılan fiyat boşluğudur. Fiyat bazen bu boşluğu doldurmak için "
            "geri gelebilir. Boşluk tek başına işlem sinyali değildir."
        ),
        why_it_matters_tr=(
            "Hızlı hareketlerin ardından fiyatın neden bazı bölgelere "
            "ilgilenebileceğini sade dilde açıklar."
        ),
        advanced_tr=(
            "ICT/SMC dilinde dengesizlik (imbalance) ile ilişkilidir. Sistem "
            "yalnızca ölçülebilir boşluk geometrisini gösterir; doldurma "
            "olasılığı uydurmaz."
        ),
    ),
    _lesson(
        EducationConceptId.HARMONIC_PRZ,
        title_tr="Harmonik / PRZ",
        beginner_tr=(
            "Harmonik formasyonlar, belirli Fibonacci oranlarına uyan XABCD "
            "benzeri fiyat geometrileridir. PRZ (Potential Reversal Zone), bu "
            "oranların kesiştiği potansiyel dönüş bölgesidir. Potansiyel "
            "kelimesi önemlidir: kesin dönüş demek değildir."
        ),
        why_it_matters_tr=(
            "Neden bazı bölgelerde birden fazla oran üst üste binebileceğini "
            "ve bunun hâlâ belirsizlik taşıdığını gösterir."
        ),
        advanced_tr=(
            "Geçerli adaylar oran toleransı, geçersizleşme seviyesi ve hedef "
            "geometrisi ile birlikte değerlendirilir. Tek bir PRZ, kalibre "
            "edilmiş kazanma olasılığı değildir."
        ),
    ),
    _lesson(
        EducationConceptId.ELLIOTT_WAVE,
        title_tr="Elliott Dalga",
        beginner_tr=(
            "Elliott dalga yaklaşımı, fiyat hareketini dalga dizileri olarak "
            "okumaya çalışır. Aynı grafikte birden fazla sayım mümkün olabilir. "
            "Sistem tek bir öznel sayımı 'kesin doğru' diye sunmaz."
        ),
        why_it_matters_tr=(
            "Yapısal belirsizliği gizlemeden, alternatif sayımların neden "
            "birlikte yaşayabileceğini öğretir."
        ),
        advanced_tr=(
            "Sert kurallar (ör. 3. dalga en kısa olamaz) ihlal edilirse sayım "
            "geçersiz sayılır. Belirsizlik ve çelişki korunur; tek sayım "
            "dayatılmaz."
        ),
    ),
    _lesson(
        EducationConceptId.INVALIDATION,
        title_tr="Geçersizleşme",
        beginner_tr=(
            "Geçersizleşme, bir fikrin 'artık geçerli değil' sayıldığı net "
            "koşuldur. Genellikle belirli bir fiyat seviyesi veya kapanış "
            "kuralıdır. Fikir bozulunca sistem bunu saklar; kayıpları silmez."
        ),
        why_it_matters_tr=(
            "Her tezin nerede çökeceğini önceden bilmek, umutla tutunmayı "
            "engeller."
        ),
        advanced_tr=(
            "Geçersizleşme, risk motorunun ve sanal portföyün ortak "
            "referansıdır. Canlı fiyat animasyonu, dondurulmuş "
            "geçersizleşme seviyesini geriye dönük değiştiremez."
        ),
    ),
    _lesson(
        EducationConceptId.RISK_REWARD,
        title_tr="Risk / Getiri",
        beginner_tr=(
            "Risk/getiri, bir fikrin potansiyel kazancı ile kaybedebileceği "
            "miktarı karşılaştırmaktır. Doğru yön bile, kötü risk/getiri ile "
            "zayıf bir iş olabilir. Bu bir olasılık yüzdesi değildir."
        ),
        why_it_matters_tr=(
            "Yalnızca 'yön doğru mu?' sorusundan çıkıp 'riske değer mi?' "
            "sorusuna geçmeyi öğretir."
        ),
        advanced_tr=(
            "Referans R:R, giriş bölgesi, geçersizleşme ve hedeflerden "
            "türetilebilir. Ücret, spread ve kayma bütçesi sanal işlemde "
            "ayrıca hesaba katılır."
        ),
    ),
    _lesson(
        EducationConceptId.AGREEMENT_VS_PROBABILITY,
        title_tr="Metod Uyumu ≠ Olasılık",
        beginner_tr=(
            "Birden fazla yöntemin aynı yöne işaret etmesi 'uyum' (agreement) "
            "demektir. Uyum endeksi, kazanma olasılığı değildir. Tarihsel "
            "sıklık da kalibre edilmiş olasılık değildir. Sistem sayısal "
            "olasılık uydurmaz."
        ),
        why_it_matters_tr=(
            "Çok yöntemin aynı fikirde olması ile 'kesin kazanır' iddiasını "
            "birbirinden ayırır."
        ),
        advanced_tr=(
            "Meta motor korelasyonu, çelişkiyi ve çözülmemiş metodları "
            "korur. Agreement index not probability; kalibrasyon kanıtı "
            "yoksa ProbabilityStatus kalibre edilmemiş kalır."
        ),
    ),
    _lesson(
        EducationConceptId.PAPER_TRADING,
        title_tr="Kâğıt / Sanal İşlem",
        beginner_tr=(
            "Bu platformda REAL_CAPITAL=0'dır: gerçek borsa emri yoktur. "
            "Kâğıt (paper) işlem, 100 USDT'lik tamamen sanal bir portföy ile "
            "kararları ölçer. Nakit tutmak da geçerli bir profesyonel "
            "pozisyondur."
        ),
        why_it_matters_tr=(
            "Öğrenirken gerçek para riske atmadan, dürüst sonuç kaydı ile "
            "sistemin kendini ölçmesini sağlar."
        ),
        advanced_tr=(
            "Her sanal işlem karar kimliği, referans fiyat, simüle dolum, "
            "ücret/spread/kayma, nakit ve pozisyon sonucu ile kayda geçer. "
            "Martingale, kayıp kovalama veya gizli kaldıraç yoktur."
        ),
    ),
)


def _build_lesson_index(
    lessons: tuple[EducationLesson, ...],
) -> dict[EducationConceptId, EducationLesson]:
    index: dict[EducationConceptId, EducationLesson] = {}
    for lesson in lessons:
        if lesson.concept_id in index:
            raise ValueError(f"duplicate education concept id: {lesson.concept_id}")
        index[lesson.concept_id] = lesson
    missing = REQUIRED_CONCEPT_IDS.difference(index)
    if missing:
        raise ValueError(f"education catalog missing required concepts: {sorted(missing)}")
    return index


_LESSON_BY_ID: Final[Mapping[EducationConceptId, EducationLesson]] = _build_lesson_index(
    _LESSON_CATALOG
)


def all_education_lessons() -> tuple[EducationLesson, ...]:
    """Return the full deterministic lesson catalog in stable enum order."""
    return tuple(_LESSON_BY_ID[concept_id] for concept_id in EducationConceptId)


def lookup_education_lesson(concept_id: str | EducationConceptId) -> EducationLookupResult:
    """Stable lookup by canonical concept id.

    Unknown ids return ``EducationLookupMissing`` rather than inventing content.
    """
    raw = concept_id.value if isinstance(concept_id, EducationConceptId) else concept_id
    try:
        canonical = EducationConceptId(raw)
    except ValueError:
        return EducationLookupMissing(
            status=EducationLookupStatus.MISSING,
            requested_id=raw,
        )
    return EducationLookupFound(
        status=EducationLookupStatus.FOUND,
        lesson=_LESSON_BY_ID[canonical],
    )


def require_education_lesson(concept_id: str | EducationConceptId) -> EducationLesson:
    """Lookup that fails explicitly when the concept is unknown."""
    result = lookup_education_lesson(concept_id)
    if isinstance(result, EducationLookupMissing):
        raise KeyError(f"unknown education concept id: {result.requested_id}")
    return result.lesson
