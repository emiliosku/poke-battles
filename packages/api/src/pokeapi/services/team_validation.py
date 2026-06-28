"""Showdown team validator.

poke-env sends ``/utm <team>`` for every challenge and the server silently
drops the challenge when the team is invalid, so a bad team paste or a
mismatched format causes the player to wait forever with no error visible
to the user. We pre-validate the team by issuing ``/utm`` + ``/vtm <format>``
over a small WebSocket pool, parse the server's popup response, and return
a ``(ok, reason)`` tuple that the API can surface to the caller.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import string
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)


def _anon_name() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"validator{suffix}"


@dataclass
class TeamValidationResult:
    ok: bool
    reason: str

    def to_detail(self, team_label: str) -> str:
        if self.ok:
            return ""
        if self.reason:
            return f"{team_label} rejected by Showdown: {self.reason}"
        return f"{team_label} rejected by Showdown (no reason given)"


def _host_port_from_websocket_url(websocket_url: str) -> tuple[str, int]:
    from urllib.parse import urlparse

    parsed = urlparse(websocket_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    return host, port


class _Session:
    __slots__ = ("in_use", "lock", "ws")

    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.lock = asyncio.Lock()
        self.in_use = False


class ShowdownTeamValidator:
    """Pool of guest WebSocket connections that run ``/utm`` + ``/vtm``."""

    def __init__(
        self,
        *,
        websocket_url: str,
        pool_size: int = 2,
        open_timeout: float = 10.0,
        validation_timeout: float = 5.0,
    ) -> None:
        self._websocket_url = websocket_url
        self._pool_size = max(1, pool_size)
        self._open_timeout = open_timeout
        self._validation_timeout = validation_timeout
        self._sessions: asyncio.Queue[_Session] | None = None
        self._created = 0
        self._lock = asyncio.Lock()
        self._closing = False

    async def start(self) -> None:
        if self._sessions is not None:
            return
        self._sessions = asyncio.Queue()
        for _ in range(self._pool_size):
            session = await self._open_session()
            await self._sessions.put(session)

    async def stop(self) -> None:
        self._closing = True
        sessions: list[_Session] = []
        if self._sessions is not None:
            while not self._sessions.empty():
                try:
                    sessions.append(self._sessions.get_nowait())
                except asyncio.QueueEmpty:
                    break
        for session in sessions:
            try:
                await session.ws.close()
            except Exception:
                pass

    async def _open_session(self) -> _Session:
        ws = await websockets.connect(
            self._websocket_url,
            open_timeout=self._open_timeout,
            max_size=2**20,
        )
        await ws.send(f"|/trn {_anon_name()},0,")
        try:
            await asyncio.wait_for(ws.recv(), timeout=self._open_timeout)
        except TimeoutError:
            await ws.close()
            raise
        session = _Session(ws)
        session.in_use = False
        return session

    @asynccontextmanager
    async def _acquire(self) -> Any:
        if self._sessions is None:
            await self.start()
        assert self._sessions is not None
        session: _Session | None = None
        try:
            session = await asyncio.wait_for(self._sessions.get(), timeout=self._open_timeout)
        except TimeoutError:
            async with self._lock:
                if self._created < self._pool_size + 1:
                    self._created += 1
                    try:
                        session = await self._open_session()
                    except Exception:
                        self._created -= 1
                        raise
        assert session is not None
        session.in_use = True
        try:
            yield session
        finally:
            session.in_use = False
            if self._closing:
                try:
                    await session.ws.close()
                except Exception:
                    pass
            elif self._sessions is not None:
                try:
                    self._sessions.put_nowait(session)
                except asyncio.QueueFull:
                    try:
                        await session.ws.close()
                    except Exception:
                        pass

    async def validate(self, team_paste: str | None, battle_format: str) -> TeamValidationResult:
        if not battle_format:
            return TeamValidationResult(False, "battle format is empty")
        try:
            async with self._acquire() as session:
                return await self._run(session, team_paste, battle_format)
        except Exception:
            logger.exception("team validation failed")
            return TeamValidationResult(False, "validator unavailable")

    async def _run(
        self, session: _Session, team_paste: str | None, battle_format: str
    ) -> TeamValidationResult:
        ws = session.ws
        if team_paste is not None and team_paste.strip():
            packed = self._pack(team_paste)
            if packed is None:
                return TeamValidationResult(False, "could not convert team paste to packed format")
            await ws.send(f"|/utm {packed}")
        else:
            await ws.send("|/utm null")
        await self._drain(ws, timeout=self._validation_timeout)
        await ws.send(f"|/vtm {battle_format}")
        return await self._collect_vtm(ws, timeout=self._validation_timeout)

    @staticmethod
    def _pack(team_paste: str) -> str | None:
        try:
            from poke_env.teambuilder.constant_teambuilder import ConstantTeambuilder
        except Exception:
            return None
        try:
            return ConstantTeambuilder(team_paste).packed_team
        except Exception as exc:
            logger.warning("ConstantTeambuilder failed: %s", exc)
            return None

    async def _drain(self, ws: ClientConnection, *, timeout: float, max_messages: int = 12) -> None:
        deadline = time.monotonic() + timeout
        for _ in range(max_messages):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError:
                return

    async def _collect_vtm(self, ws: ClientConnection, *, timeout: float) -> TeamValidationResult:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return TeamValidationResult(False, "validator timed out")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError:
                return TeamValidationResult(False, "validator timed out")
            for line in raw.splitlines():
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                if not line.startswith("|popup|"):
                    continue
                body = line[len("|popup|") :]
                if "is valid" in body:
                    return TeamValidationResult(True, "")
                if "rejected" in body or "require" in body.lower():
                    reasons = [
                        chunk.strip()
                        for chunk in body.split("|")
                        if chunk.strip() and not chunk.startswith("Your team ")
                    ]
                    return TeamValidationResult(False, " | ".join(reasons) if reasons else body)
                return TeamValidationResult(False, body[:240])


def build_default_validator(server_configuration: Any) -> ShowdownTeamValidator:
    websocket_url = getattr(server_configuration, "websocket_url", None)
    if not websocket_url:
        raise RuntimeError("server_configuration has no websocket_url")
    return ShowdownTeamValidator(websocket_url=websocket_url)


def env_showdown_dir() -> str:
    return os.environ.get("SHOWDOWN_SERVER_DIR", "server")


def env_showdown_port() -> int:
    return int(os.environ.get("SHOWDOWN_PORT", "0") or 0)


__all__ = [
    "ShowdownTeamValidator",
    "TeamValidationResult",
    "build_default_validator",
    "env_showdown_dir",
    "env_showdown_port",
]
