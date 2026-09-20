"""Tests for bounded paper observation-log retention."""

from __future__ import annotations

from crypto_signal.paper.log_retention import rotate_single_backup_log


def test_log_below_limit_is_unchanged(tmp_path) -> None:
    path = tmp_path / "dryrun.log"
    path.write_text("abc", encoding="utf-8")

    result = rotate_single_backup_log(path, max_bytes=3)

    assert result.rotated is False
    assert result.previous_size_bytes == 3
    assert result.backup_path is None
    assert path.read_text(encoding="utf-8") == "abc"
    assert not (tmp_path / "dryrun.log.1").exists()


def test_log_above_limit_rotates_to_single_backup(tmp_path) -> None:
    path = tmp_path / "dryrun.log"
    backup = tmp_path / "dryrun.log.1"
    backup.write_text("older", encoding="utf-8")
    path.write_text("abcdef", encoding="utf-8")

    result = rotate_single_backup_log(path, max_bytes=5)

    assert result.rotated is True
    assert result.previous_size_bytes == 6
    assert result.backup_path == backup
    assert not path.exists()
    assert backup.read_text(encoding="utf-8") == "abcdef"


def test_missing_log_is_a_noop(tmp_path) -> None:
    path = tmp_path / "missing.log"

    result = rotate_single_backup_log(path, max_bytes=5)

    assert result.rotated is False
    assert result.previous_size_bytes == 0
    assert result.backup_path is None
