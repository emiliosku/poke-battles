"""Unit tests for practice battle helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from poke_env.battle.move import Move
from poke_env.battle.pokemon import Pokemon
from poke_env.player.battle_order import SingleBattleOrder

from pokeapi.services.practice import (
    PracticeActionController,
    _compact_double_orders,
    _order_kind,
    _order_label,
    decide_points,
    score_from_raw_log,
)


class TestPracticeScoring:
    def test_score_from_latest_request_snapshot(self) -> None:
        raw_log = (
            '|request|{"side":{"pokemon":[{"condition":"100/100"},'
            '{"condition":"0 fnt"},{"condition":"45/90 brn"}]}}'
        )

        score = score_from_raw_log(raw_log)

        assert score.remaining == 2
        assert score.hp_percent_total == 150

    def test_decide_points_prefers_remaining_pokemon(self) -> None:
        player_log = '|request|{"side":{"pokemon":[{"condition":"1/100"}]}}'
        ai_log = '|request|{"side":{"pokemon":[{"condition":"100/100"},{"condition":"1/100"}]}}'

        decision = decide_points(
            player_name="human",
            ai_name="ai",
            player_raw_log=player_log,
            ai_raw_log=ai_log,
        )

        assert decision.winner == "ai"
        assert decision.reason == "remaining_pokemon"

    def test_decide_points_uses_hp_when_remaining_tied(self) -> None:
        player_log = '|request|{"side":{"pokemon":[{"condition":"80/100"}]}}'
        ai_log = '|request|{"side":{"pokemon":[{"condition":"25/100"}]}}'

        decision = decide_points(
            player_name="human",
            ai_name="ai",
            player_raw_log=player_log,
            ai_raw_log=ai_log,
        )

        assert decision.winner == "human"
        assert decision.reason == "remaining_hp"


class TestPracticeActionController:
    @pytest.mark.asyncio
    async def test_submit_choice_resolves_pending_order(self) -> None:
        controller = PracticeActionController(move_timeout_s=1)
        order = SingleBattleOrder("/choose move 1")
        battle = SimpleNamespace(valid_orders=[order])

        choice_task = asyncio.create_task(controller.request_choice("battle-1", battle))
        await asyncio.sleep(0)
        request = controller.current_request("battle-1")
        assert request is not None

        assert await controller.submit_choice("battle-1", request.request_id, "0") is True
        selected = await choice_task

        assert selected.message == "/choose move 1"

    @pytest.mark.asyncio
    async def test_request_choice_emits_structured_options(self) -> None:
        controller = PracticeActionController(move_timeout_s=1)
        move = Move("flamethrower", gen=9)
        switch_target = Pokemon(species="pikachu", gen=9)
        battle = SimpleNamespace(
            valid_orders=[SingleBattleOrder(move), SingleBattleOrder(switch_target)],
            wait=False,
            _force_switch=False,
        )

        task = asyncio.create_task(controller.request_choice("battle-2", battle))
        await asyncio.sleep(0)
        request = controller.current_request("battle-2")
        assert request is not None
        assert request.phase == "move"
        assert request.options[0].kind == "move"
        assert request.options[0].move is not None
        assert request.options[0].move["id"] == "flamethrower"
        assert request.options[1].kind == "switch"
        assert request.options[1].pokemon is not None

        await controller.submit_choice("battle-2", request.request_id, "0")
        await task

    @pytest.mark.asyncio
    async def test_team_preview_picks_yield_team_order(self) -> None:
        controller = PracticeActionController(move_timeout_s=1)
        members = [SimpleNamespace(species=f"poke{i}", name=f"Poke{i}", types=[]) for i in range(6)]
        battle = SimpleNamespace(
            team={f"p{i + 1}": m for i, m in enumerate(members)},
            _max_team_size=2,
        )

        task = asyncio.create_task(controller.request_team_preview("battle-3", battle))
        await asyncio.sleep(0)
        preview = controller.current_team_preview("battle-3")
        assert preview is not None
        assert preview.pick == 2
        assert len(preview.options) == 6

        accepted = await controller.submit_team_preview("battle-3", preview.request_id, ["1", "2"])
        assert accepted is True
        order = await task
        assert order == "/team 1,2,3,4,5,6"


class TestOrderLabeling:
    def test_order_label_strips_choose_prefix(self) -> None:
        assert _order_label(SingleBattleOrder("/choose move flamethrower")) == "Move flamethrower"
        assert _order_label(SingleBattleOrder("/choose switch pikachu")) == "Switch pikachu"

    def test_order_kind_classifies_singles_and_doubles(self) -> None:
        move = Move("flamethrower", gen=9)
        mon = Pokemon(species="pikachu", gen=9)
        assert _order_kind(SingleBattleOrder(move)) == "move"
        assert _order_kind(SingleBattleOrder(mon)) == "switch"


class TestDoubleOrderCompaction:
    def test_dedupe_slot_orders(self) -> None:
        move = Move("flamethrower", gen=9)
        mon_a = Pokemon(species="pikachu", gen=9)
        mon_b = Pokemon(species="charizard", gen=9)
        slot_a = [
            SingleBattleOrder(move),
            SingleBattleOrder(move),
            SingleBattleOrder(mon_a),
        ]
        slot_b = [SingleBattleOrder(move), SingleBattleOrder(mon_b)]

        battle = SimpleNamespace(valid_orders=[slot_a, slot_b])

        orders = _compact_double_orders(battle)
        # slot_a dedupes to [move, mon_a]; slot_b is [move, mon_b].
        # Combinations: (move,move), (move,mon_b), (mon_a,move), (mon_a,mon_b) => 4.
        assert len(orders) == 4
