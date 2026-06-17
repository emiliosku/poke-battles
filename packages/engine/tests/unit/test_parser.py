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
        assert ev.detail == "Flare Blitz"

    def test_switch(self) -> None:
        ev = parse_line("|switch|p1a: Charizard|100/100")
        assert ev is not None
        assert ev.kind == EventKind.SWITCH
        assert ev.side == "p1a: Charizard"
        assert ev.detail == "100/100"

    def test_damage(self) -> None:
        ev = parse_line("|-damage|p2a: Venusaur|45/100")
        assert ev is not None
        assert ev.kind == EventKind.DAMAGE
        assert ev.target == "p2a: Venusaur"
        assert ev.detail == "45/100"

    def test_faint_via_damage(self) -> None:
        ev = parse_line("|-damage|p2a: Venusaur|0 fnt")
        assert ev is not None
        assert ev.kind == EventKind.FAINT
        assert ev.target == "p2a: Venusaur"

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
