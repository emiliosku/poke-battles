"""In-process log ring buffer for the /api/debug endpoint.

The OCI host doesn't expose the API container's stdout, so when a
battle silently fails there's no way to see *why* from outside. This
handler keeps the last ``max_records`` log records in memory and
exposes them through :mod:`pokeapi.routes.debug` so a curl from the
public internet can tell whether the Showdown subprocess is alive,
the orchestrator is processing jobs, and which log lines appeared
just before the failure.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class LogRecord:
    ts: str
    level: str
    logger: str
    message: str


class MemoryLogHandler(logging.Handler):
    """Thread-safe ring buffer of the most recent log records."""

    def __init__(self, max_records: int = 200) -> None:
        super().__init__(level=logging.INFO)
        self._records: deque[LogRecord] = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._installed_loggers: list[logging.Logger] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        entry = LogRecord(
            ts=datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            level=logging.getLevelName(record.levelno),
            logger=record.name,
            message=message,
        )
        with self._lock:
            self._records.append(entry)

    def snapshot(self) -> list[LogRecord]:
        with self._lock:
            return list(self._records)

    def install(self, loggers: Iterable[logging.Logger]) -> None:
        """Attach this handler to ``loggers`` (idempotent)."""
        for logger in loggers:
            if any(h is self for h in logger.handlers):
                continue
            logger.addHandler(self)
            self._installed_loggers.append(logger)

    def uninstall(self) -> None:
        for logger in self._installed_loggers:
            with contextlib.suppress(ValueError):
                logger.removeHandler(self)
        self._installed_loggers.clear()


def format_records(records: Iterable[LogRecord]) -> list[dict[str, str]]:
    return [
        {"ts": r.ts, "level": r.level, "logger": r.logger, "message": r.message} for r in records
    ]


__all__ = ["LogRecord", "MemoryLogHandler", "format_records"]
