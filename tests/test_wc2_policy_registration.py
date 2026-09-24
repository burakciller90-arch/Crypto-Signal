from __future__ import annotations

from pathlib import Path

from crypto_signal.evaluation.untouched_forward_policy import (
    WC2PolicyStore,
)
from ops.register_wc2_forward_policy import (
    FIFTEEN_MINUTES_MS,
    register_or_reuse_policy,
)


def test_wc2_policy_registration_freezes_future_collection_boundary(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2-policy.sqlite3"
    now_ms = 1_000_000

    result = register_or_reuse_policy(
        db_path=path,
        now_ms=now_ms,
    )

    assert result.inserted is True
    assert result.policy.preregistered_at_ms == now_ms
    assert result.policy.collection_start_ms > now_ms
    assert (
        result.policy.collection_start_ms - now_ms
        >= FIFTEEN_MINUTES_MS
    )
    assert result.policy.automatic_promotion is False
    assert result.policy.performance_thresholds_included is False
    assert result.policy.real_capital == 0
    assert WC2PolicyStore(path).count() == 1


def test_wc2_policy_registration_retry_reuses_exact_policy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wc2-policy.sqlite3"

    first = register_or_reuse_policy(
        db_path=path,
        now_ms=1_000_000,
    )
    second = register_or_reuse_policy(
        db_path=path,
        now_ms=9_000_000,
    )

    assert first.inserted is True
    assert second.inserted is False
    assert second.policy == first.policy
    assert WC2PolicyStore(path).count() == 1


def test_wc2_policy_latest_read_is_side_effect_free(tmp_path: Path) -> None:
    path = tmp_path / "wc2-policy.sqlite3"
    store = WC2PolicyStore(path)

    assert store.latest() is None
    assert not path.exists()

    registered = register_or_reuse_policy(
        db_path=path,
        now_ms=1_000_000,
    )
    before = path.read_bytes()

    latest = store.latest()

    assert latest == registered.policy
    assert path.read_bytes() == before
