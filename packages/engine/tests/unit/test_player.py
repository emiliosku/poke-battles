"""Unit tests for pokeengine.player (event capture and decision handling).

These test pure logic without a live Showdown server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from poke_env.ps_client.account_configuration import AccountConfiguration

from pokeengine.player import AgentPlayer, make_order

if TYPE_CHECKING:
    from poke_env.battle.abstract_battle import AbstractBattle


class TestMakeOrder:
    def test_basic_order(self) -> None:
        o = make_order("/choose move thunderbolt")
        assert o.message == "/choose move thunderbolt"

    def test_switch_order(self) -> None:
        o = make_order("/choose switch charizard")
        assert o.message == "/choose switch charizard"

    def test_default_order(self) -> None:
        o = make_order("/choose default")
        assert o.message == "/choose default"


class TestAgentPlayerInit:
    def test_init_with_chooser(self) -> None:
        from poke_env.player.battle_order import BattleOrder

        async def chooser(p: AgentPlayer, b: AbstractBattle) -> BattleOrder:
            return p.choose_random_move(b)

        player = AgentPlayer(
            choose_move_for_turn=chooser,
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        assert player._choose_move_for_turn is chooser

    def test_init_default_random(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        assert player._choose_move_for_turn is not None
        assert player._events == {}


class TestAgentPlayerEvents:
    def test_events_for_empty(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        assert player.events_for("battle-x") == []

    def test_result_for_nonexistent(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        assert player.result_for("battle-x") is None

    def test_battle_start_callback(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        battle = MagicMock()
        battle.battle_tag = "battle-1"
        battle.format = "gen9randombattle"
        battle.player_username = "alice"
        player._battle_start_callback(battle)
        assert "battle-1" in player._events
        assert "battle-1" in player._battle_starts
        assert player._battle_formats["battle-1"] == "gen9randombattle"

    def test_battle_finished_callback(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        battle = MagicMock()
        battle.battle_tag = "battle-1"
        battle.winner = "alice"
        battle.turn = 42
        player._battle_finished_callback(battle)
        assert player._battle_winners["battle-1"] == "alice"
        assert player._battle_turns["battle-1"] == 42

    def test_battle_finished_tie(self) -> None:
        player = AgentPlayer(
            account_configuration=AccountConfiguration("alice", None),
            start_listening=False,
        )
        battle = MagicMock()
        battle.battle_tag = "battle-1"
        battle.winner = None
        battle.turn = 50
        player._battle_finished_callback(battle)
        assert player._battle_winners["battle-1"] is None
