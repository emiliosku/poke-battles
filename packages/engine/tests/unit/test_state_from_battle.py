"""Unit tests for the poke-env → BattleState adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from pokeengine.player import state_from_battle


def _mon(
    species: str,
    *,
    types: tuple[str, ...] = ("normal",),
    hp: float = 1.0,
    status: str | None = None,
    fainted: bool = False,
    is_terastallized: bool = False,
    tera_type: str | None = None,
) -> MagicMock:
    mon = MagicMock()
    mon.species = species
    mon.types = list(types)
    mon.level = 84
    mon.current_hp_fraction = hp
    status_enum = MagicMock()
    status_enum.name = status
    mon.status = status_enum if status else None
    mon.ability = "static"
    mon.item = None
    mon.tera_type = tera_type
    mon.is_terastallized = is_terastallized
    mon.fainted = fainted
    mon.boosts = {"spe": 1}
    mon.moves = {}
    return mon


def _battle(active: MagicMock, bench: list[MagicMock], opp_active: MagicMock) -> MagicMock:
    battle = MagicMock()
    battle.battle_tag = "battle-42"
    battle.turn = 12
    battle.format = "gen9randombattle"
    battle.player_username = "alice"
    battle.opponent_username = "bob"
    battle.active_pokemon = active
    battle.opponent_active_pokemon = opp_active
    battle.team = {f"p:{mon.species}": mon for mon in [active, *bench]}
    battle.opponent_team = {f"o:{opp_active.species}": opp_active}
    battle.weather = {}
    battle.fields = {}
    battle.side_conditions = {"stealthrock": 1}
    battle.opponent_side_conditions = {}
    battle.can_tera = MagicMock(return_value=True)
    return battle


class TestStateFromBattle:
    def test_builds_battle_state_with_active_first(self) -> None:
        active = _mon("Pikachu", types=("electric",), hp=0.82)
        bench = [_mon("Charizard", types=("fire", "flying"))]
        opp = _mon("Garchomp", types=("dragon", "ground"), hp=0.55, status="par")
        battle = _battle(active, bench, opp)

        state = state_from_battle(battle)

        assert state.battle_id == "battle-42"
        assert state.turn == 12
        assert state.format == "gen9randombattle"
        assert state.player_username == "alice"
        assert state.opponent_username == "bob"
        assert state.can_tera is True
        assert state.player[0].species == "Pikachu"
        assert state.player[0].is_active is True
        assert state.player[1].species == "Charizard"
        assert state.player[1].is_active is False
        assert state.opponent[0].species == "Garchomp"
        assert state.opponent[0].status == "par"

    def test_field_and_hazards(self) -> None:
        active = _mon("Pikachu")
        opp = _mon("Garchomp")
        battle = _battle(active, [], opp)
        battle.fields = {"electric_terrain": 1}

        state = state_from_battle(battle)

        assert state.field.terrain == "electric"
        assert state.field.player_hazards == {"stealthrock": 1}
        assert state.field.opponent_hazards == {}

    def test_handles_unknown_status_and_no_tera(self) -> None:
        active = _mon("Pikachu", status=None)
        opp = _mon("Garchomp")
        battle = _battle(active, [], opp)
        battle.can_tera = MagicMock(return_value=False)

        state = state_from_battle(battle)

        assert state.player[0].status is None
        assert state.can_tera is False

    def test_falls_back_when_team_does_not_contain_active(self) -> None:
        active = _mon("Pikachu", hp=0.4)
        bench = [_mon("Charizard")]
        opp = _mon("Garchomp")
        battle = _battle(active, bench, opp)
        battle.team = {f"p:{mon.species}": mon for mon in bench}

        state = state_from_battle(battle)

        assert state.player[0].species == "Pikachu"
        assert state.player[0].is_active is True
        assert state.player[1].species == "Charizard"

    def test_ignores_simple_namespace_objects(self) -> None:
        battle = SimpleNamespace(
            battle_tag="battle-99",
            turn=3,
            format="gen9randombattle",
            player_username="alice",
            opponent_username="bob",
            active_pokemon=None,
            opponent_active_pokemon=None,
            team={},
            opponent_team={},
            weather={},
            fields={},
            side_conditions={},
            opponent_side_conditions={},
            can_tera=lambda: False,
        )

        state = state_from_battle(battle)

        assert state.player == ()
        assert state.opponent == ()
        assert state.can_tera is False
