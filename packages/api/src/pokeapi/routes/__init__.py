"""REST + WebSocket routes."""

from __future__ import annotations

from fastapi import APIRouter

from pokeapi.routes import battles, health, leaderboard, replays, simulations, teams, ws

router = APIRouter()
router.include_router(health.router)
router.include_router(teams.router)
router.include_router(battles.router)
router.include_router(simulations.router)
router.include_router(leaderboard.router)
router.include_router(replays.router)
router.include_router(ws.router)

__all__ = ["router"]
