"""Unit tests for pokeapi.services.team_validation.

The Showdown-side ``/utm`` + ``/vtm`` protocol is mocked: the WebSocket pool
and the network round-trip are stubbed so the tests are hermetic and fast.
What we *do* exercise is the popup-parser (``_collect_vtm``), the public
``validate()`` entry point, the empty-format early return, and the
exception-to-"validator unavailable" fallback.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from pokeapi.services.team_validation import (
    ShowdownTeamValidator,
    TeamValidationResult,
)


class _FakeWebSocket:
    """Minimal stand-in for the websockets.ClientConnection used in tests."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if not self._replies:
            raise RuntimeError("no more replies")
        return self._replies.pop(0)

    async def close(self) -> None:
        self.closed = True


class _StubSession:
    def __init__(self) -> None:
        self.ws = _FakeWebSocket([])


def _validator() -> ShowdownTeamValidator:
    return ShowdownTeamValidator(websocket_url="ws://localhost:0/showdown/websocket")


class TestToDetail:
    def test_ok_returns_empty(self) -> None:
        result = TeamValidationResult(ok=True, reason="")
        assert result.to_detail("Team 1") == ""

    def test_rejection_uses_label(self) -> None:
        result = TeamValidationResult(ok=False, reason="Hatterene is level 50")
        assert result.to_detail("Team 1") == "Team 1 rejected by Showdown: Hatterene is level 50"

    def test_rejection_without_reason(self) -> None:
        result = TeamValidationResult(ok=False, reason="")
        assert result.to_detail("Team 1") == "Team 1 rejected by Showdown (no reason given)"


class TestValidatePublicSurface:
    @pytest.mark.asyncio
    async def test_empty_format_returns_false(self) -> None:
        result = await _validator().validate("any paste", "")
        assert result.ok is False
        assert "empty" in result.reason

    @pytest.mark.asyncio
    async def test_runs_through_acquire_and_returns_run_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        @asynccontextmanager
        async def fake_acquire(self: ShowdownTeamValidator) -> Any:
            captured["acquired"] = True
            yield _StubSession()

        async def fake_run(
            self: ShowdownTeamValidator,
            session: Any,
            team_paste: str | None,
            battle_format: str,
        ) -> TeamValidationResult:
            captured["paste"] = team_paste
            captured["format"] = battle_format
            return TeamValidationResult(ok=True, reason="")

        monkeypatch.setattr(ShowdownTeamValidator, "_acquire", fake_acquire)
        monkeypatch.setattr(ShowdownTeamValidator, "_run", fake_run)
        result = await _validator().validate("the paste", "gen9ou")
        assert result.ok is True
        assert captured["paste"] == "the paste"
        assert captured["format"] == "gen9ou"
        assert captured.get("acquired") is True

    @pytest.mark.asyncio
    async def test_acquire_failure_falls_back_to_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @asynccontextmanager
        async def boom_acquire(self: ShowdownTeamValidator) -> Any:
            raise OSError("connection refused")
            yield  # pragma: no cover -- never reached

        monkeypatch.setattr(ShowdownTeamValidator, "_acquire", boom_acquire)
        result = await _validator().validate("the paste", "gen9ou")
        assert result.ok is False
        assert result.reason == "validator unavailable"


class TestCollectVtm:
    @pytest.mark.asyncio
    async def test_valid_popup_yields_ok(self) -> None:
        ws = _FakeWebSocket(["|popup|Your team is valid for OU."])
        result = await _validator()._collect_vtm(ws, timeout=2.0)
        assert result.ok is True
        assert result.reason == ""

    @pytest.mark.asyncio
    async def test_rejected_popup_yields_reason(self) -> None:
        ws = _FakeWebSocket(
            [
                "|popup|Your team was rejected for the following reasons:||"
                "- Hatterene is level 50, but this format allows level 100 Pokémon. (If this was intentional, add exactly 1 to one of your EVs...)",
            ]
        )
        result = await _validator()._collect_vtm(ws, timeout=2.0)
        assert result.ok is False
        assert "Hatterene is level 50" in result.reason
        assert "Your team" not in result.reason  # the wrapper strips the "Your team ..." preamble

    @pytest.mark.asyncio
    async def test_ignores_non_popup_lines(self) -> None:
        ws = _FakeWebSocket(
            [
                "|updates|",
                "|c|alice|hi",
                "|popup|Your team is valid for OU.",
            ]
        )
        result = await _validator()._collect_vtm(ws, timeout=2.0)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_timeout_yields_timed_out(self) -> None:
        import asyncio as _asyncio

        class _HangingWebSocket:
            async def recv(self) -> str:
                await _asyncio.sleep(10)
                raise RuntimeError  # pragma: no cover -- never reached

        result = await _validator()._collect_vtm(_HangingWebSocket(), timeout=0.05)  # type: ignore[arg-type]
        assert result.ok is False
        assert "timed out" in result.reason
