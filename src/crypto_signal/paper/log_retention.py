"""Bounded single-backup log rotation for paper observation clocks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "PaperLogRotationError",
    "PaperLogRotationResult",
    "rotate_single_backup_log",
]


class PaperLogRotationError(RuntimeError):
    """Raised when bounded observation-log rotation cannot be completed."""


@dataclass(frozen=True, slots=True)
class PaperLogRotationResult:
    path: Path
    previous_size_bytes: int
    max_bytes: int
    rotated: bool
    backup_path: Path | None

    def __post_init__(self) -> None:
        if self.previous_size_bytes < 0:
            raise ValueError("previous_size_bytes cannot be negative")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.rotated != (self.backup_path is not None):
            raise ValueError("rotation flag/backup path mismatch")


def rotate_single_backup_log(
    path: Path,
    *,
    max_bytes: int,
) -> PaperLogRotationResult:
    """Rotate path -> path.1 only when the current file exceeds max_bytes."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        size = path.stat().st_size if path.exists() else 0
        if size <= max_bytes:
            return PaperLogRotationResult(
                path=path,
                previous_size_bytes=size,
                max_bytes=max_bytes,
                rotated=False,
                backup_path=None,
            )

        backup = Path(f"{path}.1")
        if backup.exists():
            backup.unlink()
        path.replace(backup)
        return PaperLogRotationResult(
            path=path,
            previous_size_bytes=size,
            max_bytes=max_bytes,
            rotated=True,
            backup_path=backup,
        )
    except OSError as exc:
        raise PaperLogRotationError(
            f"failed to rotate observation log {path}: {exc}"
        ) from exc
