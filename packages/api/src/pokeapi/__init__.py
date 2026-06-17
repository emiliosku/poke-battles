"""FastAPI service: REST API + WebSocket + orchestrator + DB.

Re-exported from :mod:`pokeapi`.
"""

from __future__ import annotations

from pokeapi import db, orchestrator, routes, schemas
from pokeapi.main import app, create_app
from pokeapi.orchestrator import BattleJob, JobResult, Orchestrator, default_runner
from pokeapi.routes.ws import ConnectionManager, manager
from pokeapi.schemas import (
    BattleCreate,
    BattleParticipant,
    BattleResponse,
    HealthResponse,
    LeaderboardEntry,
    ReplayResponse,
    SimulationCreate,
    SimulationResponse,
    TeamCreate,
    TeamResponse,
)
from pokeapi.settings import Settings, get_settings

__all__ = [
    "BattleCreate",
    "BattleJob",
    "BattleParticipant",
    "BattleResponse",
    "ConnectionManager",
    "HealthResponse",
    "JobResult",
    "LeaderboardEntry",
    "Orchestrator",
    "ReplayResponse",
    "Settings",
    "SimulationCreate",
    "SimulationResponse",
    "TeamCreate",
    "TeamResponse",
    "app",
    "create_app",
    "db",
    "default_runner",
    "get_settings",
    "manager",
    "orchestrator",
    "routes",
    "schemas",
]
