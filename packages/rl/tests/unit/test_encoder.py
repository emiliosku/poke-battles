"""Unit tests for the battle state encoder."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np

from pokerl.encoder import (
    _FEATURES_PER_POKEMON,
    _SIDE_SIZE,
    OBSERVATION_SIZE,
    encode_battle,
)


def _make_move(
    *,
    base_power: int = 90,
    type_: str = "fire",
    category: str = "special",
    current_pp: int = 10,
    max_pp: int = 15,
) -> SimpleNamespace:
    return SimpleNamespace(
        base_power=base_power,
        type=type_,
        category=category,
        current_pp=current_pp,
        max_pp=max_pp,
    )


def _make_pokemon(
    *,
    species: str = "charizard",
    types: tuple[str, ...] = ("fire", "flying"),
    hp_fraction: float = 0.8,
    status: str | None = None,
    fainted: bool = False,
    boosts: dict[str, int] | None = None,
    moves: dict[str, Any] | None = None,
) -> SimpleNamespace:
    if moves is None:
        moves = {
            "flamethrower": _make_move(base_power=90, type_="fire", category="special"),
            "airslash": _make_move(base_power=75, type_="flying", category="special"),
        }
    return SimpleNamespace(
        species=species,
        types=types,
        current_hp_fraction=hp_fraction,
        status=status,
        fainted=fainted,
        boosts=boosts or {},
        moves=moves,
        level=84,
    )


def _make_battle(
    *,
    player_team: dict[str, Any] | None = None,
    opponent_team: dict[str, Any] | None = None,
    turn: int = 5,
    weather: dict[str, int] | None = None,
    fields: dict[str, int] | None = None,
    side_conditions: dict[str, int] | None = None,
    opponent_side_conditions: dict[str, int] | None = None,
    can_tera: bool = False,
) -> SimpleNamespace:
    active = None
    if player_team:
        active = next(iter(player_team.values()))
    opp_active = None
    if opponent_team:
        opp_active = next(iter(opponent_team.values()))

    return SimpleNamespace(
        team=player_team or {},
        opponent_team=opponent_team or {},
        active_pokemon=active,
        opponent_active_pokemon=opp_active,
        turn=turn,
        weather=weather or {},
        fields=fields or {},
        side_conditions=side_conditions or {},
        opponent_side_conditions=opponent_side_conditions or {},
        can_tera=can_tera,
    )


class TestEncodeEmpty:
    """Test encoding with empty/minimal battle state."""

    def test_empty_battle_returns_correct_shape(self):
        battle = _make_battle()
        obs = encode_battle(battle)
        assert obs.shape == (OBSERVATION_SIZE,)
        assert obs.dtype == np.float32

    def test_empty_battle_all_zeros(self):
        battle = _make_battle(turn=0)
        obs = encode_battle(battle)
        # Should be all zeros (no team, no field effects, turn=0)
        assert np.allclose(obs, 0.0, atol=1e-7)


class TestEncodePokemon:
    """Test encoding with actual pokemon data."""

    def test_player_hp_encoded(self):
        mon = _make_pokemon(hp_fraction=0.5)
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        # First feature of first pokemon is HP fraction
        assert abs(obs[0] - 0.5) < 1e-5

    def test_full_hp(self):
        mon = _make_pokemon(hp_fraction=1.0)
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        assert abs(obs[0] - 1.0) < 1e-5

    def test_fainted_pokemon(self):
        mon = _make_pokemon(hp_fraction=0.0, fainted=True)
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        assert obs[0] == 0.0  # hp
        assert obs[5] == 1.0  # is_fainted

    def test_type_encoding(self):
        mon = _make_pokemon(types=("fire", "flying"))
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        # type1 index for "fire" = 1, normalized = 1/18
        assert obs[1] > 0.0  # fire type has non-zero index
        assert obs[2] > 0.0  # flying type has non-zero index

    def test_boosts_encoded(self):
        mon = _make_pokemon(boosts={"atk": 2, "spe": -1})
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        # Boosts start at index 6, normalized by /6
        assert abs(obs[6] - 2.0 / 6.0) < 1e-5  # atk boost
        assert abs(obs[10] - (-1.0 / 6.0)) < 1e-5  # spe boost

    def test_moves_encoded(self):
        moves = {
            "flamethrower": _make_move(base_power=90, type_="fire", category="special"),
        }
        mon = _make_pokemon(moves=moves)
        team = {"charizard": mon}
        battle = _make_battle(player_team=team)
        obs = encode_battle(battle)
        # First move starts at index 13
        # base_power / 250
        assert abs(obs[13] - 90.0 / 250.0) < 1e-5


class TestEncodeOpponent:
    """Test encoding of opponent side."""

    def test_opponent_encoded_in_second_half(self):
        opp = _make_pokemon(hp_fraction=0.3)
        battle = _make_battle(opponent_team={"garchomp": opp})
        obs = encode_battle(battle)
        # Opponent starts at _SIDE_SIZE offset
        assert abs(obs[_SIDE_SIZE] - 0.3) < 1e-5


class TestEncodeField:
    """Test field condition encoding."""

    def test_trick_room(self):
        battle = _make_battle(fields={"trick_room": 1})
        obs = encode_battle(battle)
        field_offset = 2 * _SIDE_SIZE
        assert obs[field_offset + 2] == 1.0  # trick_room flag

    def test_stealth_rock(self):
        battle = _make_battle(side_conditions={"stealth_rock": 1})
        obs = encode_battle(battle)
        field_offset = 2 * _SIDE_SIZE
        assert obs[field_offset + 4] == 1.0  # player stealth rock

    def test_spikes(self):
        battle = _make_battle(opponent_side_conditions={"spikes": 2})
        obs = encode_battle(battle)
        field_offset = 2 * _SIDE_SIZE
        assert abs(obs[field_offset + 6] - 2.0 / 3.0) < 1e-5  # opp spikes


class TestEncodeGlobal:
    """Test global state encoding."""

    def test_turn_normalized(self):
        battle = _make_battle(turn=50)
        obs = encode_battle(battle)
        global_offset = 2 * _SIDE_SIZE + 10
        assert abs(obs[global_offset] - 0.5) < 1e-5

    def test_can_tera(self):
        battle = _make_battle(can_tera=True)
        obs = encode_battle(battle)
        global_offset = 2 * _SIDE_SIZE + 10
        assert obs[global_offset + 1] == 1.0

    def test_turn_capped_at_100(self):
        battle = _make_battle(turn=200)
        obs = encode_battle(battle)
        global_offset = 2 * _SIDE_SIZE + 10
        assert obs[global_offset] == 1.0  # capped


class TestObservationSize:
    """Verify observation size constants."""

    def test_features_per_pokemon(self):
        # 6 scalar + 7 boosts + 4 moves * 4 features = 29
        assert _FEATURES_PER_POKEMON == 29

    def test_side_size(self):
        # 6 pokemon * 29 = 174
        assert _SIDE_SIZE == 174

    def test_total_size(self):
        # 174 + 174 + 10 + 2 = 360
        assert OBSERVATION_SIZE == 360
