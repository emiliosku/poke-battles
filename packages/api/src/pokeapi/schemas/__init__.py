"""Pydantic schemas for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_s: float


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    paste: str = Field(min_length=1, description="Showdown paste format")
    format: str | None = None
    is_public: bool = False


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    format: str | None
    is_public: bool
    created_at: datetime
    paste: str
    pokemon_count: int


class UserResponse(BaseModel):
    id: str
    display_name: str | None = None
    avatar_url: str | None = None


class AuthMeResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None = None


class BattleCreate(BaseModel):
    format: str = "gen9randombattle"
    player1: BattleParticipant
    player2: BattleParticipant
    team1_id: int | None = None
    team2_id: int | None = None


class BattleParticipant(BaseModel):
    model_name: str = Field(description="Key in models.yaml (e.g. 'cerebras/llama3.1-8b')")
    username: str = Field(min_length=1, max_length=64, description="Showdown username")


class BattleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    format: str
    status: str
    player1_username: str
    player2_username: str
    model1: str
    model2: str
    winner: str | None
    turns: int | None
    duration_s: float | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SimulationCreate(BaseModel):
    mode: str = Field(description="'round_robin', 'team_vs_team', or 'ladder'")
    format: str = "gen9randombattle"
    team_a_id: int | None = None
    team_b_id: int | None = None
    models: list[str] = Field(default_factory=list)
    n_battles: int = Field(default=20, ge=1, le=500)


class SimulationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    mode: str
    n_battles: int
    wins: int | None
    losses: int | None
    draws: int | None
    win_rate: float | None
    ci_95: float | None
    results_json: dict[str, Any] | None = None
    created_at: datetime
    finished_at: datetime | None


class ReplayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    battle_id: str
    format: str
    events: list[dict[str, Any]]
    raw_log: str | None = None
    duration_s: float | None
    turns: int | None


class LeaderboardEntry(BaseModel):
    subject: str
    format: str
    rating: float
    rd: float
    games: int


class FormatResponse(BaseModel):
    id: str
    name: str
    generation: str
    kind: str
    team_size: int
    level: int
    random_team: bool


class ModelResponse(BaseModel):
    name: str
    provider: str
    tier: str
    supports_tools: bool
    rate_limit_rpm: int | None = None
    notes: str = ""


class ErrorResponse(BaseModel):
    detail: str


__all__ = [
    "AuthMeResponse",
    "BattleCreate",
    "BattleParticipant",
    "BattleResponse",
    "ErrorResponse",
    "FormatResponse",
    "HealthResponse",
    "LeaderboardEntry",
    "ModelResponse",
    "ReplayResponse",
    "SimulationCreate",
    "SimulationResponse",
    "TeamCreate",
    "TeamResponse",
    "UserResponse",
]
