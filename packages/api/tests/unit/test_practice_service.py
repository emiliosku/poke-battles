"""Unit tests for practice battle helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from poke_env.player.battle_order import SingleBattleOrder

from pokeapi.services.practice import PracticeActionController, decide_points, score_from_raw_log


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
