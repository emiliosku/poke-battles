"""Pydantic schemas for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_s: float


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    paste: str = Field(min_length=1, description="Showdown paste format")
    format: str | None = None
    is_public: bool = False


class TeamUpdate(BaseModel):
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


class TeamPreviewRequest(BaseModel):
    paste: str = Field(min_length=1, description="Showdown paste format")


class TeamValidateRequest(BaseModel):
    paste: str = Field(min_length=1, description="Showdown paste format")
    format: str = Field(min_length=1, description="Showdown format id, e.g. 'gen9ou'")


class TeamValidateResponse(BaseModel):
    ok: bool
    detail: str = ""


class PokemonPreview(BaseModel):
    nickname: str | None
    species: str
    species_id: str
    sprite_id: str
    item: str | None
    ability: str
    types: list[str] = Field(default_factory=list)
    moves: list[str] = Field(default_factory=list)


class TeamPreviewResponse(BaseModel):
    pokemon: list[PokemonPreview]


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


class PracticeBattleCreate(BaseModel):
    format: str = "gen9randombattle"
    player_username: str = Field(min_length=1, max_length=64)
    ai_username: str = Field(default="AI", min_length=1, max_length=64)
    ai_model: str = "random"
    user_team_id: int | None = None
    ai_team_id: int | None = None
    total_timer_s: int | None = Field(default=None, ge=60, le=600)


class PracticeActionSubmit(BaseModel):
    request_id: str
    option_id: str


class PracticeTeamPreviewSubmit(BaseModel):
    request_id: str
    option_ids: list[str] = Field(default_factory=list, min_length=1)


class PracticeActionResponse(BaseModel):
    accepted: bool


class SimulationCreate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    mode: str = Field(description="'round_robin', 'team_vs_team', or 'ladder'")
    format: str = "gen9randombattle"
    team_a_id: int | None = None
    team_b_id: int | None = None
    models: list[str] = Field(default_factory=list)
    n_battles: int = Field(default=20, ge=1, le=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class SimulationProgress(BaseModel):
    battles_done: int
    n_battles: int
    wins: int
    losses: int
    draws: int


class SimulationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str | None
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
    progress: SimulationProgress | None = None


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
    requires_team: bool
    active_slots: int
    practice_supported: bool
    experimental: bool


class PokedexEntry(BaseModel):
    species_id: str
    name: str
    num: int
    types: list[str] = Field(default_factory=list)
    base_stats: dict[str, int] = Field(default_factory=dict)
    abilities: dict[str, str] = Field(default_factory=dict)


class PokedexResponse(BaseModel):
    count: int
    pokemon: list[PokedexEntry]


class SpriteResultEntry(BaseModel):
    species_id: str
    name: str
    types: list[str] = Field(default_factory=list)
    canonical_slug: str
    derived_slug: str
    canonical_hits: list[str] = Field(default_factory=list)
    derived_hits: list[str] = Field(default_factory=list)
    is_cap: bool = False


class SpriteStatusResponse(BaseModel):
    checked_at: float
    count: int
    duration_s: float
    results: list[SpriteResultEntry]


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
    "PokedexEntry",
    "PokedexResponse",
    "PokemonPreview",
    "PracticeActionResponse",
    "PracticeActionSubmit",
    "PracticeBattleCreate",
    "PracticeTeamPreviewSubmit",
    "ReplayResponse",
    "SimulationCreate",
    "SimulationProgress",
    "SimulationResponse",
    "SpriteResultEntry",
    "SpriteStatusResponse",
    "TeamCreate",
    "TeamPreviewRequest",
    "TeamPreviewResponse",
    "TeamResponse",
    "TeamUpdate",
    "TeamValidateRequest",
    "TeamValidateResponse",
    "UserResponse",
]
