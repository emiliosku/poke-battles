"""Unit tests for pokeapi.services.team_validation.

The Showdown-side ``/utm`` + ``/vtm`` protocol is mocked: the WebSocket pool
and the network round-trip are stubbed so the tests are hermetic and fast.
What we *do* exercise is the popup-parser (``_collect_vtm``), the public
``validate()`` entry point, the empty-format early return, the
exception-to-"validator unavailable" fallback, the pool lifecycle, the
``_pack`` / ``_drain`` helpers, and the URL-parsing utilities.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from pokeapi.services import team_validation as tv
from pokeapi.services.team_validation import (
    ShowdownTeamValidator,
    TeamValidationResult,
    _anon_name,
    _host_port_from_websocket_url,
    build_default_validator,
    env_showdown_dir,
    env_showdown_port,
)


class _FakeWebSocket:
    """Minimal stand-in for the websockets.ClientConnection used in tests.

    ``recv()`` blocks (sleeps forever) once the canned reply list is
    exhausted, so callers that wrap it in ``asyncio.wait_for`` see a
    clean timeout instead of a ``RuntimeError`` from the fake.
    """

    def __init__(self, replies: list[str] | None = None) -> None:
        self._replies: list[str] = list(replies or [])
        self.sent: list[str] = []
        self.closed = False

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if self._replies:
            return self._replies.pop(0)
        # Block forever; the caller is expected to time out.
        await asyncio.sleep(3600)
        raise RuntimeError("fake websocket exhausted")  # pragma: no cover

    async def close(self) -> None:
        self.closed = True


class _StubSession:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.ws = _FakeWebSocket(replies)


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


class TestUtilities:
    def test_anon_name_format(self) -> None:
        name = _anon_name()
        assert name.startswith("validator")
        assert len(name) == len("validator") + 6

    def test_anon_name_uniqueness(self) -> None:
        names = {_anon_name() for _ in range(50)}
        assert len(names) > 40  # collisions are astronomically unlikely with 36^6

    def test_host_port_from_websocket_url(self) -> None:
        host, port = _host_port_from_websocket_url("ws://example.test:8000/x")
        assert host == "example.test"
        assert port == 8000

    def test_host_port_default_port(self) -> None:
        host, port = _host_port_from_websocket_url("ws://h/")
        assert host == "h"
        assert port == 8000

    def test_host_port_no_hostname_falls_back(self) -> None:
        host, port = _host_port_from_websocket_url("ws:///path")
        assert host == "127.0.0.1"
        assert port == 8000

    def test_env_showdown_dir_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SHOWDOWN_SERVER_DIR", raising=False)
        assert env_showdown_dir() == "server"

    def test_env_showdown_dir_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOWDOWN_SERVER_DIR", "/tmp/showdown")  # noqa: S108
        assert env_showdown_dir() == "/tmp/showdown"  # noqa: S108

    def test_env_showdown_port_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SHOWDOWN_PORT", raising=False)
        assert env_showdown_port() == 0

    def test_env_showdown_port_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHOWDOWN_PORT", "8123")
        assert env_showdown_port() == 8123

    def test_build_default_validator_ok(self) -> None:
        class _Cfg:
            websocket_url = "ws://localhost:8000/showdown/websocket"

        v = build_default_validator(_Cfg())
        assert isinstance(v, ShowdownTeamValidator)
        assert v._websocket_url == "ws://localhost:8000/showdown/websocket"

    def test_build_default_validator_missing_url(self) -> None:
        class _Cfg:
            websocket_url = ""

        with pytest.raises(RuntimeError):
            build_default_validator(_Cfg())


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
        class _HangingWebSocket:
            async def recv(self) -> str:
                await asyncio.sleep(10)
                raise RuntimeError  # pragma: no cover -- never reached

        result = await _validator()._collect_vtm(_HangingWebSocket(), timeout=0.05)  # type: ignore[arg-type]
        assert result.ok is False
        assert "timed out" in result.reason

    @pytest.mark.asyncio
    async def test_unparseable_popup_yields_truncated_body(self) -> None:
        ws = _FakeWebSocket(["|popup|??? what is this"])
        result = await _validator()._collect_vtm(ws, timeout=2.0)
        assert result.ok is False
        assert "what is this" in result.reason

    @pytest.mark.asyncio
    async def test_require_in_popup_is_treated_as_rejection(self) -> None:
        ws = _FakeWebSocket(["|popup|Your team requires at least one Pokémon."])
        result = await _validator()._collect_vtm(ws, timeout=2.0)
        assert result.ok is False
        assert "requires" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_deadline_exhausted_returns_timed_out(self) -> None:
        """A WebSocket that returns immediately but never sends a popup
        forces the loop to spin and eventually exhaust the deadline."""

        class _ChattyWebSocket:
            async def recv(self) -> str:
                return "|c|someone|hi"

        result = await _validator()._collect_vtm(_ChattyWebSocket(), timeout=0.05)  # type: ignore[arg-type]
        assert result.ok is False
        assert "timed out" in result.reason

    @pytest.mark.asyncio
    async def test_bytes_popup_is_decoded(self) -> None:
        """The wrapper must handle bytes as well as str from the wire."""

        class _BytesWebSocket:
            def __init__(self) -> None:
                self._sent = False

            async def recv(self) -> bytes:
                if not self._sent:
                    self._sent = True
                    return b"|popup|Your team is valid for OU."
                await asyncio.sleep(3600)
                raise RuntimeError  # pragma: no cover

        result = await _validator()._collect_vtm(_BytesWebSocket(), timeout=2.0)  # type: ignore[arg-type]
        assert result.ok is True


class TestPackAndDrain:
    def test_pack_returns_packed_string(self) -> None:
        # ConstantTeambuilder is the real thing — we just want to know
        # _pack returns its output and handles errors.
        packed = ShowdownTeamValidator._pack(
            "Garchomp @ Choice Scarf\nAbility: Rough Skin\n"
            "EVs: 252 Atk / 4 SpD / 252 Spe\nJolly Nature\n"
            "- Earthquake\n- Outrage\n- Stone Edge\n- Stealth Rock\n"
        )
        # The exact packed format isn't important here — only that
        # _pack doesn't blow up on a valid paste and returns a string.
        assert packed is not None
        assert isinstance(packed, str)
        assert len(packed) > 0

    def test_pack_returns_none_when_constant_teambuilder_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_paste: str) -> None:
            raise RuntimeError("teambuilder not importable")

        # Force the import inside _pack to fail.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "poke_env.teambuilder.constant_teambuilder":
                raise ImportError("nope")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert ShowdownTeamValidator._pack("any paste") is None

    def test_pack_includes_species_for_variant_forms(self) -> None:
        """Regression: poke-env 0.15.0's ``from_showdown`` only sets the
        species field on the parsed ``TeambuilderPokemon`` when the
        header has the ``Nickname (Species) @ Item`` form. For a plain
        ``Species @ Item`` header the packed team ends up with an empty
        species field. ``_pack`` must normalise the paste so variant
        forms like ``Typhlosion-Hisui`` ship a non-empty species."""
        packed = ShowdownTeamValidator._pack(
            "Typhlosion-Hisui @ Choice Specs\n"
            "Ability: Blaze\n"
            "EVs: 252 SpA / 4 SpD / 252 Spe\n"
            "Timid Nature\n"
            "- Eruption"
        )
        assert packed is not None
        # The packed format begins with `nickname|species|item|...`. The
        # bug presented as `Typhlosion-Hisui||choicespecs|...` (empty
        # species). After the fix it should read
        # `Typhlosion-Hisui|typhlosionhisui|choicespecs|...`.
        assert packed.startswith("Typhlosion-Hisui|typhlosionhisui|")

    @pytest.mark.asyncio
    async def test_drain_reads_until_quiet(self) -> None:
        ws = _FakeWebSocket(["|a|", "|b|", "|c|"])
        await _validator()._drain(ws, timeout=0.1, max_messages=12)
        # All three should be drained; sent list is empty since drain only reads.
        assert ws.sent == []
        assert len(ws._replies) == 0  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_drain_stops_at_max_messages(self) -> None:
        ws = _FakeWebSocket([f"|msg{i}|" for i in range(50)])
        await _validator()._drain(ws, timeout=0.1, max_messages=5)
        # Only 5 should be consumed; the rest remain.
        assert len(ws._replies) == 45  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_drain_handles_timeout(self) -> None:
        class _HangingWebSocket:
            async def recv(self) -> str:
                await asyncio.sleep(10)
                raise RuntimeError  # pragma: no cover

        await _validator()._drain(_HangingWebSocket(), timeout=0.05, max_messages=100)  # type: ignore[arg-type]


class TestRun:
    @staticmethod
    def _drain_then_popup_replies(popup: str) -> list[str]:
        """Replies that keep ``_drain`` busy without consuming the popup.

        ``_drain`` reads up to 12 messages; we feed it 12 non-popup lines so
        the next ``recv`` blocks (and the surrounding ``wait_for`` times out),
        and only after that does ``_collect_vtm`` see the popup.
        """
        return ["|updates|" for _ in range(12)] + [popup]

    @pytest.mark.asyncio
    async def test_run_sends_utm_and_vtm(self) -> None:
        replies = self._drain_then_popup_replies("|popup|Your team is valid for OU.")
        session = _StubSession(replies)
        result = await _validator()._run(
            session,  # type: ignore[arg-type]
            "Garchomp @ Choice Scarf\nAbility: Rough Skin\nEVs: 252 Atk\nJolly Nature\n- Earthquake\n",
            "gen9ou",
        )
        assert result.ok is True
        # First message is /utm, then /vtm is sent after the drain.
        sent = session.ws.sent
        assert any(line.startswith("|/utm ") for line in sent)
        assert any(line == "|/vtm gen9ou" for line in sent)

    @pytest.mark.asyncio
    async def test_run_with_null_team_sends_utm_null(self) -> None:
        replies = self._drain_then_popup_replies("|popup|Your team is valid for OU.")
        session = _StubSession(replies)
        result = await _validator()._run(session, None, "gen9randombattle")  # type: ignore[arg-type]
        assert result.ok is True
        assert "|/utm null" in session.ws.sent

    @pytest.mark.asyncio
    async def test_run_returns_pack_failure(self) -> None:
        # Force the import inside _pack to fail so packed is None and
        # _run returns the "could not convert" error without ever
        # touching the websocket.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "poke_env.teambuilder.constant_teambuilder":
                raise ImportError("forced")
            return real_import(name, *args, **kwargs)

        import pytest as _pytest

        # We can't use monkeypatch here because the test isn't taking
        # it as a fixture, so use a temporary setattr + restore.
        original = builtins.__import__
        builtins.__import__ = fake_import
        try:
            session = _StubSession([])
            result = await _validator()._run(  # type: ignore[arg-type]
                session, "anything", "gen9ou"
            )
            assert result.ok is False
            assert "could not convert" in result.reason
        finally:
            builtins.__import__ = original
        _ = _pytest  # silence linter

    @pytest.mark.asyncio
    async def test_run_with_empty_paste_sends_utm_null(self) -> None:
        replies = self._drain_then_popup_replies("|popup|Your team is valid for OU.")
        session = _StubSession(replies)
        result = await _validator()._run(session, "   \n  \n", "gen9randombattle")  # type: ignore[arg-type]
        assert result.ok is True
        assert "|/utm null" in session.ws.sent


class TestPoolLifecycle:
    """The pool is exercised via a monkey-patched ``websockets.connect``."""

    @pytest.mark.asyncio
    async def test_start_opens_pool_size_sessions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opens: list[str] = []

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            opens.append(url)
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=3)
        await v.start()
        try:
            assert len(opens) == 3
        finally:
            await v.stop()

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opens: list[str] = []

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            opens.append(url)
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=2)
        await v.start()
        await v.start()
        assert len(opens) == 2
        await v.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_sessions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sockets: list[_FakeWebSocket] = []

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            ws = _FakeWebSocket(["|updates|"])
            sockets.append(ws)
            return ws

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=2)
        await v.start()
        await v.stop()
        assert all(s.closed for s in sockets)

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        v = _validator()
        await v.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_open_session_sends_trn_and_receives(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|", "|c|server|hi"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = _validator()
        session = await v._open_session()
        # The /trn message should have been sent.
        assert session.ws.sent[0].startswith("|/trn validator")
        assert session.in_use is False

    @pytest.mark.asyncio
    async def test_open_session_timeout_closes_ws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _HangingWebSocket:
            def __init__(self) -> None:
                self.sent: list[str] = []
                self.closed = False

            async def send(self, data: str) -> None:
                self.sent.append(data)

            async def recv(self) -> str:
                await asyncio.sleep(10)
                raise RuntimeError  # pragma: no cover

            async def close(self) -> None:
                self.closed = True

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _HangingWebSocket()  # type: ignore[return-value]

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", open_timeout=0.05)
        with pytest.raises(asyncio.TimeoutError):
            await v._open_session()


class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_yields_session_from_queue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        await v.start()
        try:
            async with v._acquire() as session:
                assert session.in_use is True
            # After exit, session is back in the pool.
            assert v._sessions is not None
            assert v._sessions.qsize() == 1
        finally:
            await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_grows_pool_when_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        opens: list[str] = []

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            opens.append(url)
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        # pool_size=1 so the second concurrent acquire must grow the pool.
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1, open_timeout=5.0)
        await v.start()
        try:
            async with v._acquire() as s1, v._acquire() as s2:
                assert s1 is not s2
            assert len(opens) == 2
        finally:
            await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_returns_session_after_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        await v.start()
        try:
            with pytest.raises(RuntimeError):
                async with v._acquire():
                    raise RuntimeError("boom")
            # The session must be back in the pool.
            assert v._sessions is not None
            assert v._sessions.qsize() == 1
        finally:
            await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_closes_session_when_validator_closing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sockets: list[_FakeWebSocket] = []

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            ws = _FakeWebSocket(["|updates|"])
            sockets.append(ws)
            return ws

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        await v.start()
        async with v._acquire() as session:
            pass
        v._closing = True
        async with v._acquire() as session:
            assert session.ws.closed is False  # closed only on context exit
        assert session.ws.closed is True
        v._closing = False
        await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_grow_the_pool_fails_then_releases_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``_open_session`` raises while growing the pool, the
        ``_created`` budget is released so future acquires can retry."""
        # First call returns a healthy session so start() succeeds.
        # Subsequent calls (during the grow-the-pool attempt) fail.
        call_count = 0

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _FakeWebSocket(["|updates|"])
            raise OSError("grow failed")

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1, open_timeout=5.0)
        await v.start()
        # Pool is now exhausted; the next acquire must grow the pool,
        # which will fail.
        with pytest.raises(OSError):
            async with v._acquire(), v._acquire():
                pass
        # _created should be back to 0 (it briefly went 0 -> 1 -> 0
        # in the failed grow-the-pool attempt). The next acquire
        # should still be able to take from the queue.
        assert v._created == 0
        async with v._acquire():
            pass
        assert v._created == 0
        await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_closing_swallows_close_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            class _BadCloseWebSocket(_FakeWebSocket):
                async def close(self) -> None:
                    raise OSError("close failed")

            return _BadCloseWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        await v.start()
        v._closing = True
        # Should not raise even though ws.close() does.
        async with v._acquire():
            pass
        v._closing = False
        await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_starts_pool_if_not_yet_started(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        # No await v.start() — _acquire should bootstrap it.
        async with v._acquire():
            assert v._sessions is not None
            assert v._sessions.qsize() == 0
        await v.stop()

    @pytest.mark.asyncio
    async def test_acquire_caps_pool_at_pool_size_plus_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_created`` is capped at ``pool_size + 1`` so the pool can't
        grow without bound. Once the cap is reached, the no-grow branch
        leaves ``session`` unset, and the post-condition assert fires."""

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1, open_timeout=0.05)
        await v.start()
        # Drain the pool so the next acquire must grow.
        assert v._sessions is not None
        await v._sessions.get()
        # Pre-set the budget to the cap so the next grow attempt
        # takes the no-grow branch.
        v._created = v._pool_size + 1
        with pytest.raises(AssertionError):
            async with v._acquire():
                pass
        await v.stop()


class TestStopEdgeCases:
    @pytest.mark.asyncio
    async def test_stop_swallows_close_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BadCloseWebSocket(_FakeWebSocket):
            async def close(self) -> None:
                raise OSError("close failed")

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _BadCloseWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=2)
        await v.start()
        # stop() must not raise even when each session's close() does.
        await v.stop()

    @pytest.mark.asyncio
    async def test_stop_handles_queue_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Smoke test for the pool's start/acquire/stop cycle. The actual
        ``QueueFull`` branch is unreachable with an unbounded queue and
        is marked ``# pragma: no cover`` in the source — this test
        just guards against regressions in the reachable path."""

        async def fake_connect(url: str, **kwargs: Any) -> _FakeWebSocket:
            return _FakeWebSocket(["|updates|"])

        monkeypatch.setattr(tv.websockets, "connect", fake_connect)
        v = ShowdownTeamValidator(websocket_url="ws://h:1/x", pool_size=1)
        await v.start()
        async with v._acquire() as session:
            assert session is not None
        await v.stop()


class TestPackFailure:
    def test_pack_returns_none_when_constant_teambuilder_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _BadTeambuilder:
            def __init__(self, paste: str) -> None:
                raise ValueError("nope")

        import poke_env.teambuilder.constant_teambuilder as ct_module

        monkeypatch.setattr(ct_module, "ConstantTeambuilder", _BadTeambuilder)
        assert ShowdownTeamValidator._pack("any paste") is None


class TestDrainDeadline:
    @pytest.mark.asyncio
    async def test_drain_returns_immediately_when_deadline_passed(self) -> None:
        # A WebSocket that returns messages instantly — by the time the
        # loop checks `remaining`, the deadline may already be in the past
        # on a slow CI, in which case the function returns. We exercise
        # this by passing a very small timeout and many replies.
        ws = _FakeWebSocket([f"|m{i}|" for i in range(50)])
        # Force the deadline check to fire on the second iteration.
        v = _validator()
        # This call should complete in well under 1s.
        await v._drain(ws, timeout=0.0001, max_messages=100)
        # Some messages were consumed; the rest are still in the queue.
        assert len(ws._replies) < 50  # type: ignore[attr-defined]
