"""Unit tests for pokellm.state_render."""

from __future__ import annotations

from pokecore.state import BattleState, FieldState, KnownMove, PokemonState
from pokellm.state_render import default_state_formatter, format_battle_state


def _battle() -> BattleState:
    active = PokemonState(
        species="Pikachu",
        nickname="Pikachu",
        types=("electric",),
        level=84,
        hp_fraction=0.82,
        status=None,
        ability="static",
        item="light-ball",
        tera_type="electric",
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
        boosts={"spe": 1},
        moves=(
            KnownMove(
                id="thunderbolt",
                name="Thunderbolt",
                type="electric",
                category="special",
                base_power=90,
                accuracy=100,
                pp=16,
                max_pp=24,
            ),
        ),
    )
    bench = (
        PokemonState(
            species="Charizard",
            nickname="Charizard",
            types=("fire", "flying"),
            level=80,
            hp_fraction=1.0,
            status=None,
            ability="blaze",
            item=None,
            tera_type=None,
            is_terastallized=False,
            is_active=False,
            is_fainted=False,
        ),
    )
    opp_active = PokemonState(
        species="Garchomp",
        nickname="Garchomp",
        types=("dragon", "ground"),
        level=84,
        hp_fraction=0.55,
        status="par",
        ability="rough-skin",
        item=None,
        tera_type=None,
        is_terastallized=False,
        is_active=True,
        is_fainted=False,
    )
    opp_bench: tuple[PokemonState, ...] = ()
    return BattleState(
        battle_id="battle-1",
        turn=12,
        format="gen9randombattle",
        player_username="alice",
        opponent_username="bob",
        player=(active, *bench),
        opponent=(opp_active, *opp_bench),
        field=FieldState(
            weather=None,
            terrain="electric",
            trick_room=False,
            player_hazards={"stealthrock": 1},
            opponent_hazards={},
        ),
        can_tera=True,
    )


class TestFormatBattleState:
    def test_includes_sides_and_active_marker(self) -> None:
        rendered = format_battle_state(_battle())
        assert "alice" in rendered
        assert "bob" in rendered
        assert "Pikachu" in rendered
        assert "[active]" in rendered
        assert "Garchomp" in rendered
        assert "82% HP" in rendered
        assert "55% HP" in rendered

    def test_includes_moves_and_field(self) -> None:
        rendered = format_battle_state(_battle())
        assert "thunderbolt" in rendered
        assert "BP90" in rendered
        assert "terrain=electric" in rendered
        assert "your_hazards=stealthrock:1" in rendered

    def test_tera_marker_when_available(self) -> None:
        rendered = format_battle_state(_battle())
        assert "tera=electric" in rendered
        assert "tera available" in rendered

    def test_tera_already_used_marker(self) -> None:
        battle = _battle()
        active = battle.player[0]
        battle = BattleState(
            battle_id=battle.battle_id,
            turn=battle.turn,
            format=battle.format,
            player_username=battle.player_username,
            opponent_username=battle.opponent_username,
            player=(
                PokemonState(
                    species=active.species,
                    nickname=active.nickname,
                    types=active.types,
                    level=active.level,
                    hp_fraction=active.hp_fraction,
                    status=active.status,
                    ability=active.ability,
                    item=active.item,
                    tera_type=active.tera_type,
                    is_terastallized=True,
                    is_active=active.is_active,
                    is_fainted=active.is_fainted,
                    boosts=active.boosts,
                    moves=active.moves,
                ),
                *battle.player[1:],
            ),
            opponent=battle.opponent,
            field=battle.field,
            can_tera=False,
        )
        rendered = format_battle_state(battle)
        assert "tera=electric!" in rendered
        assert "tera available" not in rendered


class TestDefaultStateFormatter:
    def test_str_passthrough(self) -> None:
        assert default_state_formatter("state text") == "state text"

    def test_dict_with_formatted_key(self) -> None:
        assert default_state_formatter({"formatted": "pre-rendered"}) == "pre-rendered"

    def test_dict_falls_back_to_keyvalue(self) -> None:
        rendered = default_state_formatter({"a": 1, "b": 2})
        assert "a: 1" in rendered
        assert "b: 2" in rendered

    def test_battle_state_renders_via_formatter(self) -> None:
        rendered = default_state_formatter(_battle())
        assert "Pikachu" in rendered
        assert "Garchomp" in rendered

    def test_falls_back_to_str(self) -> None:
        assert default_state_formatter(42) == "42"
