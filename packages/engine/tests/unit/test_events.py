"""Smoke tests for pokeengine.events."""

from __future__ import annotations

from pokeengine.events import BattleResult, Event, EventKind


class TestEvent:
    def test_to_dict_minimal(self) -> None:
        ev = Event(kind=EventKind.TURN_START, turn=1)
        d = ev.to_dict()
        assert d == {"kind": "turn_start", "turn": 1}

    def test_to_dict_full(self) -> None:
        ev = Event(
            kind=EventKind.MOVE,
            turn=3,
            side="p1a: Charizard",
            target="p2a: Venusaur",
            detail="Flare Blitz",
            quantity=2,
            source="p1a: Charizard",
            raw={"species_id": "charizard"},
        )
        d = ev.to_dict()
        assert d["kind"] == "move"
        assert d["turn"] == 3
        assert d["side"] == "p1a: Charizard"
        assert d["target"] == "p2a: Venusaur"
        assert d["detail"] == "Flare Blitz"
        assert d["quantity"] == 2
        assert d["source"] == "p1a: Charizard"
        assert d["raw"] == {"species_id": "charizard"}


class TestBattleResult:
    def test_construction(self) -> None:
        r = BattleResult(winner="Alice", turns=42, duration_s=120.5, format="gen9ou", events=())
        assert r.winner == "Alice"
        assert r.turns == 42
        assert r.duration_s == 120.5
        assert r.format == "gen9ou"
        assert r.events == ()
