"""Async agent player wrapping poke-env.

The :class:`AgentPlayer` extends :class:`poke_env.player.Player` and
captures battle events into a normalized stream. Subclass and override
the ``choose_move_for_turn`` callable to plug in any decision logic
(random, LLM, heuristic, …).

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.player.battle_order import BattleOrder, SingleBattleOrder
from poke_env.player.player import Player
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import (
    LocalhostServerConfiguration,
    ServerConfiguration,
)

from pokecore.state import BattleState, FieldState, KnownMove, PokemonState
from pokeengine.events import BattleResult, Event
from pokeengine.parser import parse_line

logger = logging.getLogger(__name__)


MoveChooser = Callable[["AgentPlayer", AbstractBattle], Awaitable[BattleOrder]]


class AgentPlayer(Player):
    """Async player that records battle events and delegates move choice.

    Parameters
    ----------
    choose_move_for_turn:
        Async callable that returns a :class:`BattleOrder`. Receives
        ``(self, battle)``.
    on_event:
        Optional async callback called for each parsed event during a battle.
        Receives ``(battle_tag, event)``.
    on_raw_line:
        Optional async callback called for each raw protocol line.
        Receives ``(battle_tag, line)``.
    """

    def __init__(
        self,
        choose_move_for_turn: MoveChooser | None = None,
        on_event: Callable[[str, Event], Awaitable[None]] | None = None,
        on_raw_line: Callable[[str, str], Awaitable[None]] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self._choose_move_for_turn: MoveChooser = choose_move_for_turn or _default_random_choice
        self._on_event = on_event
        self._on_raw_line = on_raw_line
        self._events: dict[str, list[Event]] = {}
        self._raw_logs: dict[str, list[str]] = {}
        self._battle_starts: dict[str, float] = {}
        self._battle_winners: dict[str, str | None] = {}
        self._battle_turns: dict[str, int] = {}
        self._battle_formats: dict[str, str] = {}
        super().__init__(*args, **kwargs)

    @classmethod
    def from_config(
        cls,
        username: str,
        *,
        password: str | None = None,
        battle_format: str = "gen9randombattle",
        server: ServerConfiguration | None = None,
        choose_move_for_turn: MoveChooser | None = None,
    ) -> AgentPlayer:
        account = AccountConfiguration(username, password or "")
        server_config = server if server is not None else LocalhostServerConfiguration
        return cls(
            account_configuration=account,
            server_configuration=server_config,
            battle_format=battle_format,
            choose_move_for_turn=choose_move_for_turn,
        )

    def events_for(self, battle_id: str) -> list[Event]:
        return list(self._events.get(battle_id, []))

    def raw_log_for(self, battle_id: str) -> str:
        return "\n".join(self._raw_logs.get(battle_id, []))

    def result_for(self, battle_id: str) -> BattleResult | None:
        if battle_id not in self._battle_winners:
            return None
        start = self._battle_starts.get(battle_id, 0.0)
        return BattleResult(
            winner=self._battle_winners[battle_id],
            turns=self._battle_turns.get(battle_id, 0),
            duration_s=time.monotonic() - start if start else 0.0,
            format=self._battle_formats.get(battle_id, "unknown"),
            events=tuple(self._events.get(battle_id, [])),
            raw_log=self.raw_log_for(battle_id),
        )

    def _battle_start_callback(self, battle: AbstractBattle) -> None:
        bid = battle.battle_tag
        self._events[bid] = []
        self._raw_logs[bid] = []
        self._battle_starts[bid] = time.monotonic()
        self._battle_turns[bid] = 0
        self._battle_formats[bid] = str(battle.format) if battle.format is not None else "unknown"
        logger.info("[%s] battle started: %s (%s)", bid, battle.format, battle.player_username)

    def _battle_finished_callback(self, battle: AbstractBattle) -> None:
        bid = battle.battle_tag
        winner = getattr(battle, "winner", None)
        self._battle_winners[bid] = str(winner) if winner is not None else None
        self._battle_turns[bid] = battle.turn
        logger.info("[%s] battle ended: winner=%s turns=%d", bid, winner, battle.turn)

    async def _handle_battle_message(self, split_messages: list[list[str]]) -> None:
        if not split_messages:
            return
        head = split_messages[0][0] if split_messages[0] else ""
        is_init = (
            len(split_messages) > 1
            and len(split_messages[1]) > 1
            and split_messages[1][1] == "init"
        )
        battle = None
        if not is_init and head:
            try:
                battle = await self._get_battle(head)
            except Exception:
                battle = None
            if battle is not None:
                bt = battle.battle_tag
                for parts in split_messages[1:]:
                    if not parts or len(parts) < 2:
                        continue
                    line = "|" + "|".join(parts[1:])
                    self._raw_logs.setdefault(bt, []).append(line)
                    if self._on_raw_line is not None:
                        try:
                            await self._on_raw_line(bt, line)
                        except Exception:
                            pass
                    ev = parse_line(line, turn=battle.turn)
                    if ev is not None:
                        self._events.setdefault(bt, []).append(ev)
                        if self._on_event is not None:
                            try:
                                await self._on_event(bt, ev)
                            except Exception:
                                pass
        await super()._handle_battle_message(split_messages)

    def choose_move(self, battle: AbstractBattle) -> Awaitable[BattleOrder]:
        return self._choose_move_for_turn(self, battle)


async def _default_random_choice(player: AgentPlayer, battle: AbstractBattle) -> BattleOrder:
    return player.choose_random_move(battle)


def make_order(message: str) -> BattleOrder:
    """Build a :class:`BattleOrder` from a raw Showdown order string."""
    return SingleBattleOrder(order=message)


def parse_showdown_message_for_testing(line: str, turn: int = 0) -> Event | None:
    """Exposed for unit tests; wraps the parser."""
    return parse_line(line, turn=turn)


def battle_to_state_dict(battle: AbstractBattle | None) -> dict[str, Any]:
    """Best-effort snapshot of a poke-env Battle for logging/tests."""
    if battle is None:
        return {}
    out: dict[str, Any] = {
        "battle_id": getattr(battle, "battle_tag", None),
        "turn": getattr(battle, "turn", 0),
        "format": getattr(battle, "format", None),
        "player_username": getattr(battle, "player_username", None),
        "opponent_username": getattr(battle, "opponent_username", None),
    }
    active = getattr(battle, "active_pokemon", None)
    if active is not None:
        out["active"] = {
            "species": getattr(active, "species", None),
            "hp_fraction": getattr(active, "current_hp_fraction", 1.0),
            "status": getattr(active, "status", None) and active.status.name,
            "types": [str(t) for t in (getattr(active, "types", None) or [])],
        }
    opponent = getattr(battle, "opponent_active_pokemon", None)
    if opponent is not None:
        out["opponent"] = {
            "species": getattr(opponent, "species", None),
            "hp_fraction": getattr(opponent, "current_hp_fraction", 1.0),
            "status": getattr(opponent, "status", None) and opponent.status.name,
            "types": [str(t) for t in (getattr(opponent, "types", None) or [])],
        }
    return out


__all__ = [
    "AgentPlayer",
    "MoveChooser",
    "battle_to_state_dict",
    "make_order",
    "parse_showdown_message_for_testing",
    "state_from_battle",
]


def state_from_battle(battle: AbstractBattle) -> BattleState:
    """Build a :class:`BattleState` snapshot from a live poke-env battle.

    This is the only place in the codebase that knows about poke-env types.
    """
    active = battle.active_pokemon
    opp_active = battle.opponent_active_pokemon
    player_team = list(battle.team.values()) if hasattr(battle, "team") else []
    opponent_team = list(battle.opponent_team.values()) if hasattr(battle, "opponent_team") else []
    return BattleState(
        battle_id=str(getattr(battle, "battle_tag", "")),
        turn=int(getattr(battle, "turn", 0) or 0),
        format=str(getattr(battle, "format", "") or ""),
        player_username=str(getattr(battle, "player_username", "") or ""),
        opponent_username=str(getattr(battle, "opponent_username", "") or ""),
        player=_side_from_team(player_team, active_mon=active),
        opponent=_side_from_team(opponent_team, active_mon=opp_active),
        field=_field_from_battle(battle),
        can_tera=_read_can_tera(battle),
    )


def _read_can_tera(battle: AbstractBattle) -> bool:
    """Read ``can_tera`` whether it's a property or a method."""
    value = getattr(battle, "can_tera", False)
    if callable(value):
        return bool(value())
    return bool(value)


def _side_from_team(team: list[Any], *, active_mon: Any) -> tuple[PokemonState, ...]:
    ordered: list[Any] = []
    seen: set[int] = set()
    if active_mon is not None:
        for mon in team:
            if mon is active_mon:
                ordered.append(mon)
                seen.add(id(mon))
                break
    for mon in team:
        if id(mon) in seen:
            continue
        ordered.append(mon)
        seen.add(id(mon))
    if active_mon is not None and active_mon not in team:
        ordered.insert(0, active_mon)
    return tuple(_pokemon_from(mon, is_active=mon is active_mon) for mon in ordered)


def _pokemon_from(mon: Any, *, is_active: bool) -> PokemonState:
    species = str(getattr(mon, "species", "") or "")
    nickname = species or "?"
    types_raw = getattr(mon, "types", None) or ()
    types: tuple[str, ...]
    types = tuple(str(t) for t in types_raw)
    return PokemonState(
        species=species,
        nickname=nickname,
        types=types,
        level=int(getattr(mon, "level", 100) or 100),
        hp_fraction=float(getattr(mon, "current_hp_fraction", 1.0) or 0.0),
        status=_status_name(mon),
        ability=_str_or_none(getattr(mon, "ability", None)),
        item=_str_or_none(getattr(mon, "item", None)),
        tera_type=_str_or_none(getattr(mon, "tera_type", None)),
        is_terastallized=bool(getattr(mon, "is_terastallized", False) or False),
        is_active=is_active,
        is_fainted=bool(getattr(mon, "fainted", False) or False),
        boosts=dict(getattr(mon, "boosts", {}) or {}),
        moves=tuple(_move_from(mv) for mv in (getattr(mon, "moves", {}) or {}).values()),
    )


def _move_from(mv: Any) -> KnownMove:
    return KnownMove(
        id=str(getattr(mv, "id", "") or ""),
        name=str(getattr(mv, "name", "") or getattr(mv, "id", "") or ""),
        type=str(getattr(mv, "type", "typeless") or "typeless"),
        category=str(getattr(mv, "category", "status") or "status"),
        base_power=int(getattr(mv, "base_power", 0) or 0),
        accuracy=int(getattr(mv, "accuracy", 100) or 100),
        pp=int(getattr(mv, "current_pp", 0) or 0),
        max_pp=int(getattr(mv, "max_pp", 0) or 0),
        priority=int(getattr(mv, "priority", 0) or 0),
        target=str(getattr(mv, "target", "normal") or "normal"),
        drain=float(getattr(mv, "drain", 0) or 0),
        recoil=float(getattr(mv, "recoil", 0) or 0),
        healing=float(getattr(mv, "heal", 0) or 0),
    )


def _status_name(mon: Any) -> str | None:
    status = getattr(mon, "status", None)
    if status is None:
        return None
    return str(getattr(status, "name", status))


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _field_from_battle(battle: AbstractBattle) -> FieldState:
    weather_dict = getattr(battle, "weather", {}) or {}
    weather = next(iter(weather_dict), None)
    fields_dict = getattr(battle, "fields", {}) or {}
    terrain = next((k for k in fields_dict if str(k).endswith("terrain")), None)
    player_hazards = {
        str(k): int(v) for k, v in (getattr(battle, "side_conditions", {}) or {}).items()
    }
    opp_hazards = {
        str(k): int(v) for k, v in (getattr(battle, "opponent_side_conditions", {}) or {}).items()
    }
    return FieldState(
        weather=str(weather) if weather is not None else None,
        terrain=str(terrain).replace("_terrain", "") if terrain is not None else None,
        trick_room=any("trick_room" in str(k) for k in fields_dict),
        player_hazards=player_hazards,
        opponent_hazards=opp_hazards,
    )
