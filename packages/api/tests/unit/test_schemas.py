"""Unit tests for pokeapi.schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pokeapi.schemas import (
    BattleCreate,
    BattleParticipant,
    HealthResponse,
    SimulationCreate,
    TeamCreate,
)


class TestTeamCreate:
    def test_minimal(self) -> None:
        t = TeamCreate(name="My team", paste="Garchomp @ Scarf\nAbility: Rough Skin\n- Earthquake")
        assert t.name == "My team"
        assert t.format is None
        assert t.is_public is False

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TeamCreate(name="", paste="any")

    def test_empty_paste_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TeamCreate(name="x", paste="")


class TestBattleCreate:
    def test_minimal(self) -> None:
        b = BattleCreate(
            format="gen9randombattle",
            player1=BattleParticipant(model_name="random", username="alice"),
            player2=BattleParticipant(model_name="random", username="bob"),
        )
        assert b.format == "gen9randombattle"
        assert b.team1_id is None


class TestSimulationCreate:
    def test_defaults(self) -> None:
        s = SimulationCreate(mode="round_robin")
        assert s.n_battles == 20
        assert s.models == []

    def test_battle_count_clamped(self) -> None:
        with pytest.raises(ValidationError):
            SimulationCreate(mode="round_robin", n_battles=0)
        with pytest.raises(ValidationError):
            SimulationCreate(mode="round_robin", n_battles=1000)

    def test_name_is_trimmed(self) -> None:
        simulation = SimulationCreate(mode="round_robin", name="  benchmark  ")
        assert simulation.name == "benchmark"

    def test_blank_name_is_omitted(self) -> None:
        simulation = SimulationCreate(mode="round_robin", name="   ")
        assert simulation.name is None


class TestHealthResponse:
    def test_construction(self) -> None:
        h = HealthResponse(status="ok", version="0.1.0", uptime_s=12.5)
        assert h.status == "ok"
