"""WebSocket route for live battle event streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._raw_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, battle_id: str, ws: WebSocket, *, raw: bool = False) -> None:
        await ws.accept()
        async with self._lock:
            target = self._raw_connections if raw else self._connections
            target[battle_id].add(ws)

    async def disconnect(self, battle_id: str, ws: WebSocket, *, raw: bool = False) -> None:
        async with self._lock:
            target = self._raw_connections if raw else self._connections
            target[battle_id].discard(ws)
            if not target[battle_id]:
                del target[battle_id]

    async def broadcast(self, battle_id: str, event: dict[str, object]) -> None:
        async with self._lock:
            sockets = list(self._connections.get(battle_id, ()))
        if not sockets:
            return
        payload = json.dumps(event)
        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                logger.exception("WS send failed; dropping client")

    async def broadcast_raw(self, battle_id: str, line: str) -> None:
        async with self._lock:
            sockets = list(self._raw_connections.get(battle_id, ()))
        if not sockets:
            return
        for ws in sockets:
            try:
                await ws.send_text(line)
            except Exception:
                logger.exception("WS raw send failed; dropping client")


manager = ConnectionManager()


@router.websocket("/ws/battles/{battle_id}")
async def battle_ws(websocket: WebSocket, battle_id: str) -> None:
    await manager.connect(battle_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(battle_id, websocket)


@router.websocket("/ws/battles/{battle_id}/raw")
async def battle_raw_ws(websocket: WebSocket, battle_id: str) -> None:
    await manager.connect(battle_id, websocket, raw=True)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(battle_id, websocket, raw=True)


__all__ = ["ConnectionManager", "manager"]
