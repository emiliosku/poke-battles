"""Showdown protocol message parser.

The Showdown server streams lines like:

    |move|p1a: Charizard|Flare Blitz|...
    |switch|p1a: Charizard|100/100
    |-damage|p2a: Venusaur|0 fnt
    |win|Alice

This module turns those lines into structured :class:`Event` objects.

Re-exported from :mod:`pokeengine`.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any

from pokeengine.events import Event, EventKind

_HP_FRACTION = re.compile(r"^(\d+)/(\d+)(?:\s+(\w+))?$")
_NICKNAME_POKEMON = re.compile(r"^p(\d+)([ab]?):\s*(.+)$")
_HP_PERCENT = re.compile(r"^(\d+)\s*%(?:\s+(\w+))?$")

Handler = Callable[[list[str], int], Event | None]


def parse_line(line: str, turn: int = 0) -> Event | None:
    """Parse a single Showdown protocol line into an :class:`Event`."""
    if not line or not line.startswith("|"):
        return None
    parts = line.split("|")
    if len(parts) < 2:
        return None
    head = parts[1]
    args = parts[2:]
    handler: Handler = _DISPATCH.get(head, _unknown)
    return handler(args, turn)


def _e(
    kind: EventKind,
    turn: int,
    *,
    side: str | None = None,
    target: str | None = None,
    detail: str | None = None,
    quantity: int | None = None,
    source: str | None = None,
    raw: dict[str, Any] | None = None,
) -> Event:
    return Event(
        kind=kind,
        turn=turn,
        side=side,
        target=target,
        detail=detail,
        quantity=quantity,
        source=source,
        raw=raw or {},
    )


def _species_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _species_from_details(details: str | None) -> str | None:
    if not details:
        return None
    species = details.split(",", 1)[0].strip()
    return species or None


def _pokemon_ref(raw: str, details: str | None = None) -> dict[str, str]:
    match = _NICKNAME_POKEMON.match(raw)
    if not match:
        pokemon = raw.strip()
        species = _species_from_details(details) or pokemon
        return {
            "pokemon": pokemon,
            "species": species,
            "species_id": _species_id(species),
        }
    side = f"p{match.group(1)}"
    slot = match.group(2) or "a"
    pokemon = match.group(3).strip()
    species = _species_from_details(details) or pokemon
    return {
        "side": side,
        "slot": slot,
        "pokemon": pokemon,
        "species": species,
        "species_id": _species_id(species),
    }


def _hp(raw: str) -> dict[str, int | str]:
    m = _HP_FRACTION.match(raw) or _HP_PERCENT.match(raw)
    out: dict[str, int | str] = {"hp_text": raw}
    if not m:
        if "fnt" in raw:
            out["status"] = "fnt"
            out["hp_percent"] = 0
        return out
    if "/" in raw:
        num, denom = int(m.group(1)), int(m.group(2))
        out["hp_current"] = num
        out["hp_max"] = denom
        out["hp_percent"] = int((num / denom) * 100) if denom else 0
    else:
        out["hp_percent"] = int(m.group(1))
    status = m.group(3)
    if status:
        out["status"] = status
    if "fnt" in raw:
        out["status"] = "fnt"
        out["hp_percent"] = 0
    return out


def _move(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail=" ".join(args))
    raw = {"source": _pokemon_ref(args[0]), "move": args[1]}
    if len(args) > 2:
        raw["target"] = _pokemon_ref(args[2])
    return _e(
        EventKind.MOVE,
        turn,
        source=args[0],
        target=args[2] if len(args) > 2 else None,
        detail=args[1],
        raw=raw,
    )


def _switch(args: list[str], turn: int) -> Event:
    if not args:
        return _e(EventKind.MESSAGE, turn, detail="switch")
    details = args[1] if len(args) > 2 else None
    hp_arg = args[2] if len(args) > 2 else args[1] if len(args) > 1 else None
    raw: dict[str, Any] = {"pokemon": _pokemon_ref(args[0], details)}
    if details:
        raw["details"] = details
    if hp_arg:
        raw["hp"] = _hp(hp_arg)
    return _e(
        EventKind.SWITCH,
        turn,
        side=args[0],
        detail=" ".join(args[1:]) if len(args) > 1 else None,
        raw=raw,
    )


def _drag(args: list[str], turn: int) -> Event:
    if not args:
        return _e(EventKind.MESSAGE, turn, detail="drag")
    details = args[1] if len(args) > 2 else None
    hp_arg = args[2] if len(args) > 2 else args[1] if len(args) > 1 else None
    raw: dict[str, Any] = {"pokemon": _pokemon_ref(args[0], details)}
    if details:
        raw["details"] = details
    if hp_arg:
        raw["hp"] = _hp(hp_arg)
    return _e(
        EventKind.SWITCH,
        turn,
        side=args[0],
        detail=" ".join(args[1:]) if len(args) > 1 else None,
        raw=raw,
    )


def _damage(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="damage")
    target = args[0]
    hp_str = args[1]
    hp_data = _hp(hp_str)
    m = _HP_FRACTION.match(hp_str) or _HP_PERCENT.match(hp_str)
    fraction = 0.0
    if m:
        if "/" in hp_str:
            num, denom = int(m.group(1)), int(m.group(2))
            fraction = num / denom if denom else 0.0
        else:
            fraction = int(m.group(1)) / 100.0
    if "fnt" in hp_str:
        return _e(
            EventKind.FAINT,
            turn,
            target=target,
            detail=hp_str,
            quantity=int(fraction * 100),
            raw={"target": _pokemon_ref(target), "hp": hp_data},
        )
    return _e(
        EventKind.DAMAGE,
        turn,
        target=target,
        detail=hp_str,
        quantity=int(fraction * 100),
        raw={"target": _pokemon_ref(target), "hp": hp_data},
    )


def _heal(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="heal")
    return _e(
        EventKind.HEAL,
        turn,
        target=args[0],
        detail=args[1],
        raw={"target": _pokemon_ref(args[0]), "hp": _hp(args[1])},
    )


def _boost(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="boost")
    return _e(EventKind.BOOST, turn, target=args[0], detail=args[1])


def _unboost(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="unboost")
    return _e(EventKind.UNBOOST, turn, target=args[0], detail=args[1])


def _status(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="status")
    return _e(
        EventKind.STATUS,
        turn,
        target=args[0],
        detail=args[1],
        raw={"target": _pokemon_ref(args[0]), "status": args[1]},
    )


def _curestatus(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="curestatus")
    return _e(
        EventKind.CURESTATUS,
        turn,
        target=args[0],
        detail=args[1],
        raw={"target": _pokemon_ref(args[0]), "status": args[1]},
    )


def _faint(args: list[str], turn: int) -> Event:
    if not args:
        return _e(EventKind.MESSAGE, turn, detail="faint")
    return _e(
        EventKind.FAINT,
        turn,
        target=args[0],
        quantity=0,
        raw={"target": _pokemon_ref(args[0]), "hp": {"hp_percent": 0, "status": "fnt"}},
    )


def _weather(args: list[str], turn: int) -> Event:
    kind = EventKind.WEATHER_START if args and args[0] != "none" else EventKind.WEATHER_END
    return _e(kind, turn, detail=args[0] if args else None)


def _fieldstart(args: list[str], turn: int) -> Event:
    return _e(EventKind.FIELD_START, turn, detail=args[0] if args else None)


def _fieldend(args: list[str], turn: int) -> Event:
    return _e(EventKind.FIELD_END, turn, detail=args[0] if args else None)


def _sidestart(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="sidestart")
    return _e(EventKind.SIDE_CONDITION_START, turn, side=args[0], detail=args[1])


def _sideend(args: list[str], turn: int) -> Event:
    if len(args) < 2:
        return _e(EventKind.MESSAGE, turn, detail="sideend")
    return _e(EventKind.SIDE_CONDITION_END, turn, side=args[0], detail=args[1])


def _win(args: list[str], turn: int) -> Event:
    return _e(EventKind.BATTLE_END, turn, detail=args[0] if args else None)


def _tie(args: list[str], turn: int) -> Event:
    return _e(EventKind.BATTLE_END, turn, detail="tie")


def _turn(args: list[str], turn: int) -> Event:
    new_turn = int(args[0]) if args and args[0].isdigit() else turn + 1
    return _e(EventKind.TURN_START, new_turn)


def _request(args: list[str], turn: int) -> Event:
    return _e(EventKind.SWITCH_REQUEST, turn, detail=(args[0] if args else None))


def _unknown(args: list[str], turn: int) -> Event:
    return _e(EventKind.MESSAGE, turn, detail=" ".join(args))


def _no_op(args: list[str], turn: int) -> Event | None:
    return None


_DISPATCH: dict[str, Handler] = {
    "move": _move,
    "switch": _switch,
    "drag": _drag,
    "damage": _damage,
    "-damage": _damage,
    "heal": _heal,
    "-heal": _heal,
    "boost": _boost,
    "-boost": _boost,
    "unboost": _unboost,
    "-unboost": _unboost,
    "status": _status,
    "-status": _status,
    "curestatus": _curestatus,
    "-curestatus": _curestatus,
    "faint": _faint,
    "-faint": _faint,
    "weather": _weather,
    "-weather": _weather,
    "fieldstart": _fieldstart,
    "-fieldstart": _fieldstart,
    "fieldend": _fieldend,
    "-fieldend": _fieldend,
    "sidestart": _sidestart,
    "-sidestart": _sidestart,
    "sideend": _sideend,
    "-sideend": _sideend,
    "win": _win,
    "tie": _tie,
    "turn": _turn,
    "request": _request,
    "": _no_op,
    "raw": _no_op,
    "html": _no_op,
    "uhtml": _no_op,
    "uhtmlchange": _no_op,
    "c": _no_op,
    "chat": _no_op,
    "j": _no_op,
    "l": _no_op,
    "n": _no_op,
    "join": _no_op,
    "leave": _no_op,
    "player-battle": _no_op,
    "player-battle-finalized": _no_op,
    "battle": _no_op,
    "b": _no_op,
    "callback": _no_op,
    "deinit": _no_op,
    "noinit": _no_op,
    "error": _unknown,
    "warning": _unknown,
    "message": _unknown,
    "crit": _no_op,
    "supereffective": _no_op,
    "resisted": _no_op,
    "immune": _no_op,
    "item": _no_op,
    "enditem": _no_op,
    "ability": _no_op,
    "endability": _no_op,
    "transform": _no_op,
    "mega": _no_op,
    "primal": _no_op,
    "burst": _no_op,
    "zmove": _no_op,
    "dynamax": _no_op,
    "terastallize": _no_op,
}


def parse_stream(stream: Iterable[str]) -> list[Event]:
    """Parse a sequence of protocol lines into a list of events."""
    out: list[Event] = []
    turn = 0
    for line in stream:
        ev = parse_line(line, turn=turn)
        if ev is None:
            continue
        if ev.kind == EventKind.TURN_START and ev.detail is None:
            turn = ev.turn
        out.append(ev)
    return out


_ = Any
