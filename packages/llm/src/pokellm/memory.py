"""Memory layer: per-battle short-term and cross-battle opponent model.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ShortTermMemory:
    """Per-battle turn-by-turn log (capped at ``maxlen``)."""

    maxlen: int = 20
    entries: deque[str] = field(default_factory=deque)

    def append(self, action: str) -> None:
        self.entries.append(action)
        while len(self.entries) > self.maxlen:
            self.entries.popleft()

    def extend(self, actions: Iterable[str]) -> None:
        for a in actions:
            self.append(a)

    def recent(self, n: int | None = None) -> list[str]:
        if n is None:
            return list(self.entries)
        return list(self.entries)[-n:]

    def to_prompt_block(self) -> str:
        if not self.entries:
            return "Your recent actions: (none yet)"
        lines = [f"Turn -{len(self.entries) - i}: {a}" for i, a in enumerate(self.entries)]
        return "Your recent actions:\n" + "\n".join(lines)


@dataclass
class OpponentModel:
    """What we've inferred about the opponent across battles."""

    species_seen: set[str] = field(default_factory=set)
    leads: list[str] = field(default_factory=list)
    items_revealed: dict[str, set[str]] = field(default_factory=dict)
    moves_revealed: dict[str, set[str]] = field(default_factory=dict)
    sample_size: int = 0

    def update(
        self,
        *,
        species_seen: Iterable[str] = (),
        lead: str | None = None,
        revealed_items: Iterable[tuple[str, str]] = (),
        revealed_moves: Iterable[tuple[str, str]] = (),
    ) -> None:
        self.species_seen.update(species_seen)
        if lead:
            self.leads.append(lead)
        for species, item in revealed_items:
            self.items_revealed.setdefault(species, set()).add(item)
        for species, move in revealed_moves:
            self.moves_revealed.setdefault(species, set()).add(move)
        self.sample_size += 1

    def to_prompt_block(self) -> str:
        if not self.species_seen:
            return "Opponent profile: (no prior data)"
        species = ", ".join(sorted(self.species_seen))
        items_str = (
            "; ".join(
                f"{s}={','.join(sorted(items))}" for s, items in sorted(self.items_revealed.items())
            )
            or "(none revealed)"
        )
        moves_str = (
            "; ".join(
                f"{s}={','.join(sorted(mvs))}" for s, mvs in sorted(self.moves_revealed.items())
            )
            or "(none revealed)"
        )
        return (
            f"Opponent profile (across {self.sample_size} prior battle(s)):\n"
            f"  Species seen: {species}\n"
            f"  Revealed items: {items_str}\n"
            f"  Revealed moves: {moves_str}\n"
        )


@dataclass
class Memory:
    """Combined per-session memory: short-term + opponent model."""

    short_term: ShortTermMemory = field(default_factory=ShortTermMemory)
    opponent: OpponentModel = field(default_factory=OpponentModel)
    metadata: dict[str, Any] = field(default_factory=dict)

    def note_action(self, action: str) -> None:
        self.short_term.append(action)

    def note_opponent(
        self,
        species: str,
        *,
        item: str | None = None,
        move: str | None = None,
    ) -> None:
        self.opponent.update(
            species_seen=[species],
            revealed_items=[(species, item)] if item else [],
            revealed_moves=[(species, move)] if move else [],
        )


__all__ = ["Memory", "OpponentModel", "ShortTermMemory"]
