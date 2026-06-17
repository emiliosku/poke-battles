"""Unit tests for pokellm.memory."""

from __future__ import annotations

from pokellm.memory import Memory, OpponentModel, ShortTermMemory


class TestShortTermMemory:
    def test_empty(self) -> None:
        m = ShortTermMemory()
        assert m.recent() == []
        assert (
            "no prior data" in m.to_prompt_block().lower() or "none" in m.to_prompt_block().lower()
        )

    def test_append_caps(self) -> None:
        m = ShortTermMemory(maxlen=3)
        for i in range(5):
            m.append(f"action {i}")
        assert len(m.entries) == 3
        assert m.recent() == ["action 2", "action 3", "action 4"]

    def test_recent_n(self) -> None:
        m = ShortTermMemory(maxlen=10)
        for i in range(5):
            m.append(f"action {i}")
        assert m.recent(2) == ["action 3", "action 4"]

    def test_prompt_block(self) -> None:
        m = ShortTermMemory(maxlen=10)
        m.append("a")
        m.append("b")
        block = m.to_prompt_block()
        assert "Turn -1: b" in block
        assert "Turn -2: a" in block

    def test_extend(self) -> None:
        m = ShortTermMemory(maxlen=5)
        m.extend(["x", "y", "z"])
        assert m.recent() == ["x", "y", "z"]


class TestOpponentModel:
    def test_empty_prompt(self) -> None:
        m = OpponentModel()
        assert (
            "no prior data" in m.to_prompt_block().lower() or "none" in m.to_prompt_block().lower()
        )

    def test_update_species(self) -> None:
        m = OpponentModel()
        m.update(species_seen=["Garchomp", "Pikachu"])
        assert "Garchomp" in m.species_seen
        assert "Pikachu" in m.species_seen
        assert m.sample_size == 1

    def test_update_items_and_moves(self) -> None:
        m = OpponentModel()
        m.update(revealed_items=[("Garchomp", "Choice Scarf")])
        m.update(revealed_moves=[("Garchomp", "Earthquake")])
        assert "Choice Scarf" in m.items_revealed["Garchomp"]
        assert "Earthquake" in m.moves_revealed["Garchomp"]
        assert m.sample_size == 2

    def test_prompt_block(self) -> None:
        m = OpponentModel()
        m.update(species_seen=["Garchomp"], revealed_moves=[("Garchomp", "Outrage")])
        block = m.to_prompt_block()
        assert "Garchomp" in block
        assert "Outrage" in block


class TestMemory:
    def test_note_action(self) -> None:
        mem = Memory()
        mem.note_action("Used move: tackle")
        assert "tackle" in mem.short_term.entries[0]

    def test_note_opponent(self) -> None:
        mem = Memory()
        mem.note_opponent("Pikachu", item="Light Ball", move="Volt Tackle")
        assert "Light Ball" in mem.opponent.items_revealed["Pikachu"]
        assert "Volt Tackle" in mem.opponent.moves_revealed["Pikachu"]
