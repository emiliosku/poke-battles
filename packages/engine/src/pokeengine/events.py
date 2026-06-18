"""Normalized event stream for Pokémon Showdown battles.

LLM agents subscribe to these events instead of raw poke-env / Showdown protocol
messages. Decouples the agent logic from the transport.

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventKind(StrEnum):
    BATTLE_START = "battle_start"
    TURN_START = "turn_start"
    SWITCH = "switch"
    MOVE = "move"
    DAMAGE = "damage"
    HEAL = "heal"
    BOOST = "boost"
    UNBOOST = "unboost"
    STATUS = "status"
    CURESTATUS = "cure_status"
    FAINT = "faint"
    WEATHER_START = "weather_start"
    WEATHER_END = "weather_end"
    FIELD_START = "field_start"
    FIELD_END = "field_end"
    SIDE_CONDITION_START = "side_condition_start"
    SIDE_CONDITION_END = "side_condition_end"
    SWITCH_REQUEST = "switch_request"
    TURN_END = "turn_end"
    BATTLE_END = "battle_end"
    MESSAGE = "message"


@dataclass(frozen=True, slots=True)
class Event:
    kind: EventKind
    turn: int
    side: str | None = None
    target: str | None = None
    detail: str | None = None
    quantity: int | None = None
    source: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind.value, "turn": self.turn}
        if self.side is not None:
            out["side"] = self.side
        if self.target is not None:
            out["target"] = self.target
        if self.detail is not None:
            out["detail"] = self.detail
        if self.quantity is not None:
            out["quantity"] = self.quantity
        if self.source is not None:
            out["source"] = self.source
        return out


@dataclass(frozen=True, slots=True)
class BattleResult:
    winner: str | None
    turns: int
    duration_s: float
    format: str
    events: tuple[Event, ...]
    raw_log: str = ""
