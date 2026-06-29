"""Unit tests for the in-process log ring buffer."""

from __future__ import annotations

import logging

from pokeapi.debug import MemoryLogHandler, format_records


def _make_handler(max_records: int = 5) -> MemoryLogHandler:
    handler = MemoryLogHandler(max_records=max_records)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    return handler


def test_captures_emit_and_drops_oldest() -> None:
    handler = _make_handler(max_records=3)
    logger = logging.getLogger("pokeapi.test_buffer_caps")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    handler.install([logger])
    try:
        for i in range(5):
            logger.info("msg-%d", i)
        snap = handler.snapshot()
        assert [r.message for r in snap] == [
            "INFO pokeapi.test_buffer_caps: msg-2",
            "INFO pokeapi.test_buffer_caps: msg-3",
            "INFO pokeapi.test_buffer_caps: msg-4",
        ]
        assert snap[0].level == "INFO"
        assert snap[0].logger == "pokeapi.test_buffer_caps"
    finally:
        handler.uninstall()
        logger.setLevel(previous_level)


def test_uninstall_detaches_handler() -> None:
    handler = _make_handler(max_records=10)
    logger = logging.getLogger("pokeapi.test_buffer_detach")
    handler.install([logger])
    handler.uninstall()
    assert handler not in logger.handlers
    assert handler._installed_loggers == []


def test_install_is_idempotent() -> None:
    handler = _make_handler(max_records=10)
    logger = logging.getLogger("pokeapi.test_buffer_idem")
    handler.install([logger])
    handler.install([logger])
    matching = [h for h in logger.handlers if h is handler]
    assert len(matching) == 1
    handler.uninstall()


def test_format_records_preserves_order() -> None:
    handler = _make_handler(max_records=3)
    logger = logging.getLogger("pokeapi.test_buffer_format")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    handler.install([logger])
    try:
        logger.warning("first")
        logger.error("second")
    finally:
        handler.uninstall()
        logger.setLevel(previous_level)
    out = format_records(handler.snapshot())
    assert [r["message"] for r in out] == [
        "WARNING pokeapi.test_buffer_format: first",
        "ERROR pokeapi.test_buffer_format: second",
    ]
    assert all(set(r) >= {"ts", "level", "logger", "message"} for r in out)
