"""Unit tests for pokeengine.runner (pure functions and process management).

Skips integration tests that require a live Showdown server.
"""

from __future__ import annotations

import socket
from pathlib import Path

from pokeengine.runner import (
    DEFAULT_PORT,
    SHOWDOWN_REPO,
    _find_free_port,
    _port_is_open,
    ensure_showdown,
)


class TestFindFreePort:
    def test_returns_int_in_valid_range(self) -> None:
        port = _find_free_port()
        assert isinstance(port, int)
        assert 1024 < port < 65536

    def test_returns_different_ports(self) -> None:
        a = _find_free_port()
        b = _find_free_port()
        assert a != b


class TestPortIsOpen:
    def test_closed_port(self) -> None:
        assert _port_is_open("127.0.0.1", 1) is False

    def test_listening_port(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        try:
            port = sock.getsockname()[1]
            assert _port_is_open("127.0.0.1", port) is True
        finally:
            sock.close()


class TestEnsureShowdown:
    def test_idempotent_when_exists(self, tmp_path: Path) -> None:
        server = tmp_path / "server"
        node_modules = server / "node_modules"
        node_modules.mkdir(parents=True)
        result = ensure_showdown(server)
        assert result == server


class TestConstants:
    def test_default_port(self) -> None:
        assert DEFAULT_PORT == 8000

    def test_showdown_repo(self) -> None:
        assert "smogon/pokemon-showdown" in SHOWDOWN_REPO
        assert SHOWDOWN_REPO.startswith("https://")
