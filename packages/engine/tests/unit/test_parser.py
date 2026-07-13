"""Unit tests for pokeengine.parser."""

from __future__ import annotations

from pokeengine.events import EventKind
from pokeengine.parser import parse_line, parse_stream


class TestParseLine:
    def test_empty_line(self) -> None:
        assert parse_line("") is None
        assert parse_line("not a protocol line") is None

    def test_turn(self) -> None:
        ev = parse_line("|turn|3")
        assert ev is not None
        assert ev.kind == EventKind.TURN_START
        assert ev.turn == 3

    def test_move(self) -> None:
        ev = parse_line("|move|p1a: Charizard|Flare Blitz|p2a: Venusaur")
        assert ev is not None
        assert ev.kind == EventKind.MOVE
        assert ev.source == "p1a: Charizard"
        assert ev.target == "p2a: Venusaur"
        assert ev.detail == "Flare Blitz"
        assert ev.raw["source"]["species_id"] == "charizard"
        assert ev.raw["target"]["side"] == "p2"

    def test_switch(self) -> None:
        ev = parse_line("|switch|p1a: Charizard|100/100")
        assert ev is not None
        assert ev.kind == EventKind.SWITCH
        assert ev.side == "p1a: Charizard"
        assert ev.detail == "100/100"
        assert ev.raw["pokemon"]["pokemon"] == "Charizard"
        assert ev.raw["hp"]["hp_percent"] == 100

    def test_switch_uses_details_for_variant_species(self) -> None:
        ev = parse_line("|switch|p1a: Slowking|Slowking-Galar, L50|100/100")
        assert ev is not None
        assert ev.kind == EventKind.SWITCH
        assert ev.raw["pokemon"]["pokemon"] == "Slowking"
        assert ev.raw["pokemon"]["species"] == "Slowking-Galar"
        assert ev.raw["pokemon"]["species_id"] == "slowkinggalar"
        assert ev.raw["pokemon"]["sprite_id"] == "slowking-galar"
        assert ev.raw["details"] == "Slowking-Galar, L50"
        assert ev.raw["hp"]["hp_percent"] == 100

    def test_damage(self) -> None:
        ev = parse_line("|-damage|p2a: Venusaur|45/100")
        assert ev is not None
        assert ev.kind == EventKind.DAMAGE
        assert ev.target == "p2a: Venusaur"
        assert ev.detail == "45/100"
        assert ev.quantity == 45
        assert ev.raw["target"]["species_id"] == "venusaur"
        assert ev.raw["hp"]["hp_percent"] == 45

    def test_faint_via_damage(self) -> None:
        ev = parse_line("|-damage|p2a: Venusaur|0 fnt")
        assert ev is not None
        assert ev.kind == EventKind.FAINT
        assert ev.target == "p2a: Venusaur"
        assert ev.quantity == 0
        assert ev.raw["hp"]["status"] == "fnt"

    def test_faint_direct(self) -> None:
        ev = parse_line("|faint|p2a: Venusaur")
        assert ev is not None
        assert ev.kind == EventKind.FAINT
        assert ev.target == "p2a: Venusaur"

    def test_boost(self) -> None:
        ev = parse_line("|-boost|p1a: Charizard|atk|1")
        assert ev is not None
        assert ev.kind == EventKind.BOOST
        assert ev.target == "p1a: Charizard"
        assert ev.detail == "atk"

    def test_unboost(self) -> None:
        ev = parse_line("|-unboost|p1a: Charizard|def|1")
        assert ev is not None
        assert ev.kind == EventKind.UNBOOST
        assert ev.target == "p1a: Charizard"

    def test_status(self) -> None:
        ev = parse_line("|-status|p1a: Charizard|brn")
        assert ev is not None
        assert ev.kind == EventKind.STATUS
        assert ev.detail == "brn"

    def test_weather_start(self) -> None:
        ev = parse_line("|-weather|SunnyDay")
        assert ev is not None
        assert ev.kind == EventKind.WEATHER_START
        assert ev.detail == "SunnyDay"

    def test_weather_end(self) -> None:
        ev = parse_line("|-weather|none")
        assert ev is not None
        assert ev.kind == EventKind.WEATHER_END
        assert ev.detail == "none"

    def test_fieldstart(self) -> None:
        ev = parse_line("|-fieldstart|Electric Terrain")
        assert ev is not None
        assert ev.kind == EventKind.FIELD_START

    def test_sidestart(self) -> None:
        ev = parse_line("|-sidestart|p1: Alice|Stealth Rock")
        assert ev is not None
        assert ev.kind == EventKind.SIDE_CONDITION_START
        assert ev.side == "p1: Alice"
        assert ev.detail == "Stealth Rock"

    def test_item_reveal_with_explicit_source(self) -> None:
        ev = parse_line("|-item|p1a: Pikachu|Light Ball|[from] ability: Pickup|[of] p2a: Meowth")
        assert ev is not None
        assert ev.kind == EventKind.ITEM
        assert ev.target == "p1a: Pikachu"
        assert ev.source == "p2a: Meowth"
        assert ev.detail == "Light Ball"
        assert ev.raw["target"]["species_id"] == "pikachu"
        assert ev.raw["source"]["species_id"] == "meowth"
        assert ev.raw["annotations"] == ["[from] ability: Pickup", "[of] p2a: Meowth"]

    def test_item_removal(self) -> None:
        ev = parse_line("|-enditem|p1a: Pikachu|Sitrus Berry|[eat]")
        assert ev is not None
        assert ev.kind == EventKind.END_ITEM
        assert ev.target == "p1a: Pikachu"
        assert ev.detail == "Sitrus Berry"
        assert ev.raw["item"] == "Sitrus Berry"
        assert ev.raw["annotations"] == ["[eat]"]

    def test_ability_reveal_and_end(self) -> None:
        reveal = parse_line("|-ability|p1a: Gyarados|Intimidate")
        end = parse_line("|-endability|p1a: Slaking|[from] move: Gastro Acid")
        assert reveal is not None
        assert end is not None
        assert reveal.kind == EventKind.ABILITY
        assert reveal.detail == "Intimidate"
        assert end.kind == EventKind.END_ABILITY
        assert end.detail is None
        assert end.raw["annotations"] == ["[from] move: Gastro Acid"]

    def test_tera_and_dynamax_events(self) -> None:
        tera = parse_line("|-terastallize|p1a: Charizard|Fire")
        dynamax = parse_line("|-dynamax|p1a: Charizard")
        end_dynamax = parse_line("|-enddynamax|p1a: Charizard")
        assert tera is not None
        assert dynamax is not None
        assert end_dynamax is not None
        assert tera.kind == EventKind.TERASTALLIZE
        assert tera.detail == "Fire"
        assert tera.raw["type"] == "Fire"
        assert dynamax.kind == EventKind.DYNAMAX
        assert dynamax.target == "p1a: Charizard"
        assert end_dynamax.kind == EventKind.END_DYNAMAX

    def test_effectiveness_events(self) -> None:
        super_effective = parse_line("|-supereffective|p2a: Venusaur")
        resisted = parse_line("|-resisted|p2a: Venusaur")
        immune = parse_line("|-immune|p2a: Venusaur|[from] ability: Levitate")
        assert super_effective is not None
        assert resisted is not None
        assert immune is not None
        assert super_effective.kind == EventKind.SUPER_EFFECTIVE
        assert resisted.kind == EventKind.RESISTED
        assert immune.kind == EventKind.IMMUNE
        assert immune.raw["annotations"] == ["[from] ability: Levitate"]

    def test_form_change_events(self) -> None:
        transform = parse_line("|-transform|p1a: Ditto|Mew|[from] move: Transform")
        mega = parse_line("|-mega|p1a: Charizard|Charizardite X")
        primal = parse_line("|-primal|p1a: Kyogre")
        burst = parse_line("|-burst|p1a: Necrozma|Necrozma-Ultra|Ultranecrozium Z")
        zmove = parse_line("|-zpower|p1a: Pikachu")
        assert transform is not None
        assert mega is not None
        assert primal is not None
        assert burst is not None
        assert zmove is not None
        assert transform.kind == EventKind.TRANSFORM
        assert transform.source is None
        assert transform.detail == "Mew"
        assert transform.raw["species"] == "Mew"
        assert mega.kind == EventKind.MEGA
        assert mega.detail == "Charizardite X"
        assert mega.raw["item"] == "Charizardite X"
        assert primal.kind == EventKind.PRIMAL
        assert burst.kind == EventKind.BURST
        assert burst.detail == "Necrozma-Ultra"
        assert burst.raw["species"] == "Necrozma-Ultra"
        assert burst.raw["item"] == "Ultranecrozium Z"
        assert zmove.kind == EventKind.ZMOVE

    def test_win(self) -> None:
        ev = parse_line("|win|Alice")
        assert ev is not None
        assert ev.kind == EventKind.BATTLE_END
        assert ev.detail == "Alice"

    def test_tie(self) -> None:
        ev = parse_line("|tie")
        assert ev is not None
        assert ev.kind == EventKind.BATTLE_END
        assert ev.detail == "tie"

    def test_request(self) -> None:
        ev = parse_line('|request|{"active":[{"moves":[]}]}')
        assert ev is not None
        assert ev.kind == EventKind.SWITCH_REQUEST

    def test_ignores_chat(self) -> None:
        assert parse_line("|c|Alice|gg") is None
        assert parse_line("|j| Spectator") is None
        assert parse_line("|html|<b>Hello</b>") is None


class TestParseStream:
    def test_full_battle_sequence(self) -> None:
        lines = [
            "|turn|1",
            "|switch|p1a: Charizard|100/100",
            "|switch|p2a: Venusaur|100/100",
            "|move|p1a: Charizard|Flare Blitz|p2a: Venusaur",
            "|-damage|p2a: Venusaur|45/100",
            "|move|p2a: Venusaur|Razor Leaf|p1a: Charizard",
            "|-damage|p1a: Charizard|78/100",
            "|turn|2",
            "|-damage|p2a: Venusaur|0 fnt",
            "|win|Alice",
        ]
        events = parse_stream(lines)
        kinds = [e.kind for e in events]
        assert EventKind.TURN_START in kinds
        assert EventKind.SWITCH in kinds
        assert EventKind.MOVE in kinds
        assert EventKind.DAMAGE in kinds
        assert EventKind.FAINT in kinds
        assert EventKind.BATTLE_END in kinds
        assert len(events) == 10
