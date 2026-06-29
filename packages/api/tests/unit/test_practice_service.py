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
    _display_species_and_nickname,
    _order_kind,
    _order_label,
    _pokemon_payload,
    _team_member_label,
    _team_member_payload,
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


class TestDisplaySpeciesAndNickname:
    """Regression tests for the Showdown ident-stripping bug.

    Showdown's server (``sim/pokemon.ts``) rewrites a Pokemon's
    nickname to the base species when the nickname equals the species
    (the variant form is conveyed via ``|details|`` instead). That
    means poke-env's ``Pokemon.name`` returns ``"Slowking"`` for
    ``Slowking-Galar`` even though ``_last_details`` is
    ``"Slowking-Galar, L50"``. ``_display_species_and_nickname``
    prefers the details-based species so the web UI shows the right
    form.
    """

    def test_prefers_last_details_for_variant_form(self) -> None:
        mon = SimpleNamespace(
            species="slowkinggalar",
            name="Slowking",
            _last_details="Slowking-Galar, L50",
        )
        species, nickname = _display_species_and_nickname(mon)
        assert species == "Slowking-Galar"
        assert nickname == "Slowking"

    def test_falls_back_to_teambuilder_when_no_details(self) -> None:
        mon = SimpleNamespace(species="slowkinggalar", name="Slowking", _last_details="")
        species, nickname = _display_species_and_nickname(mon)
        assert species == "slowkinggalar"
        assert nickname == "Slowking"

    def test_base_form_uses_species_id(self) -> None:
        mon = SimpleNamespace(
            species="hatterene",
            name="Hatterene",
            _last_details="Hatterene, L50",
        )
        species, _ = _display_species_and_nickname(mon)
        assert species == "Hatterene"

    def test_mega_form_via_details(self) -> None:
        mon = SimpleNamespace(
            species="aerodactylmega",
            name="Aerodactyl",
            _last_details="Aerodactyl-Mega, L50",
        )
        species, _ = _display_species_and_nickname(mon)
        assert species == "Aerodactyl-Mega"

    def test_pom_pom_form_via_details(self) -> None:
        mon = SimpleNamespace(
            species="oricoriopompom",
            name="Oricorio",
            _last_details="Oricorio-Pom-Pom, L50",
        )
        species, _ = _display_species_and_nickname(mon)
        assert species == "Oricorio-Pom-Pom"

    def test_custom_nickname_preserved(self) -> None:
        mon = SimpleNamespace(
            species="garchomp",
            name="Big Blue",
            _last_details="Garchomp, L50",
        )
        species, nickname = _display_species_and_nickname(mon)
        assert species == "Garchomp"
        assert nickname == "Big Blue"


class TestPokemonPayload:
    """The in-battle payload must ship the variant form and a
    dash-form sprite id so the web UI can render it correctly."""

    def test_payload_uses_details_species_for_variant(self) -> None:
        mon = SimpleNamespace(
            species="slowkinggalar",
            name="Slowking",
            _last_details="Slowking-Galar, L50",
            types=[],
            current_hp_fraction=1.0,
            fainted=False,
            status=None,
        )
        payload = _pokemon_payload(mon)
        assert payload["species"] == "Slowking-Galar"
        assert payload["species_id"] == "slowkinggalar"
        assert payload["sprite_id"] == "slowking-galar"
        assert payload["name"] == "Slowking"

    def test_payload_sprite_id_for_mega(self) -> None:
        mon = SimpleNamespace(
            species="aerodactylmega",
            name="Aerodactyl",
            _last_details="Aerodactyl-Mega, L50",
            types=[],
            current_hp_fraction=1.0,
            fainted=False,
            status=None,
        )
        payload = _pokemon_payload(mon)
        assert payload["sprite_id"] == "aerodactyl-mega"

    def test_payload_sprite_id_for_pom_pom(self) -> None:
        mon = SimpleNamespace(
            species="oricoriopompom",
            name="Oricorio",
            _last_details="Oricorio-Pom-Pom, L50",
            types=[],
            current_hp_fraction=1.0,
            fainted=False,
            status=None,
        )
        payload = _pokemon_payload(mon)
        # Oricorio-Pom-Pom's CDN slug is `oricorio-pau` (Hawaiian name).
        assert payload["sprite_id"] == "oricorio-pau"

    def test_team_member_payload_includes_sprite_id(self) -> None:
        mon = SimpleNamespace(
            species="slowkinggalar",
            name="Slowking",
            _last_details="Slowking-Galar, L50",
            types=[],
            current_hp_fraction=1.0,
            fainted=False,
            status=None,
            item="assaultvest",
            ability="regenerator",
        )
        payload = _team_member_payload(mon, 1)
        assert payload["species"] == "Slowking-Galar"
        assert payload["sprite_id"] == "slowking-galar"
        assert payload["name"] == "Slowking"

    def test_team_member_label_uses_full_form(self) -> None:
        mon = SimpleNamespace(
            species="slowkinggalar",
            name="Slowking",
            _last_details="Slowking-Galar, L50",
        )
        # Nickname (from poke-env) differs from the variant species
        # (from _last_details), so the label is "Nickname (Species)".
        assert _team_member_label(mon, 0) == "Slowking (Slowking-Galar)"

    def test_team_member_label_uses_species_when_no_nickname(self) -> None:
        mon = SimpleNamespace(
            species="slowkinggalar",
            name=None,
            _last_details="Slowking-Galar, L50",
        )
        # No nickname, so the label is just the variant species.
        assert _team_member_label(mon, 0) == "Slowking-Galar"
