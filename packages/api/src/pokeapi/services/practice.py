"""Practice battle helpers for user-vs-AI battles."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unicodedata import normalize

from poke_env.battle.battle import Battle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.player.battle_order import (
    BattleOrder,
    DefaultBattleOrder,
    DoubleBattleOrder,
    ForfeitBattleOrder,
)

from pokecore.teams import sprite_id as _sprite_id


@dataclass(frozen=True, slots=True)
class PracticeActionOption:
    id: str
    label: str
    message: str
    kind: str = "double"
    move: dict[str, object] | None = None
    pokemon: dict[str, object] | None = None
    first: dict[str, object] | None = None
    second: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PracticeActionRequest:
    request_id: str
    battle_id: str
    expires_at: datetime
    options: tuple[PracticeActionOption, ...]
    phase: str = "move"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "practice_action_required",
            "request_id": self.request_id,
            "battle_id": self.battle_id,
            "expires_at": self.expires_at.isoformat(),
            "phase": self.phase,
            "options": [
                {
                    "id": option.id,
                    "label": option.label,
                    "message": option.message,
                    "kind": option.kind,
                    "move": option.move,
                    "pokemon": option.pokemon,
                    "first": option.first,
                    "second": option.second,
                }
                for option in self.options
            ],
        }


@dataclass(frozen=True, slots=True)
class PracticeTeamPreviewOption:
    id: str
    label: str
    message: str
    pokemon: dict[str, object]


@dataclass(frozen=True, slots=True)
class PracticeTeamPreviewRequest:
    request_id: str
    battle_id: str
    expires_at: datetime
    pick: int
    options: tuple[PracticeTeamPreviewOption, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "practice_team_preview",
            "request_id": self.request_id,
            "battle_id": self.battle_id,
            "expires_at": self.expires_at.isoformat(),
            "pick": self.pick,
            "options": [
                {
                    "id": opt.id,
                    "label": opt.label,
                    "message": opt.message,
                    "pokemon": opt.pokemon,
                }
                for opt in self.options
            ],
        }


@dataclass(slots=True)
class _PendingTeamPreview:
    request: PracticeTeamPreviewRequest
    future: asyncio.Future[str]
    picks: dict[str, int]


@dataclass(slots=True)
class _PendingAction:
    request: PracticeActionRequest
    future: asyncio.Future[BattleOrder]
    orders: dict[str, BattleOrder]


@dataclass(frozen=True, slots=True)
class PracticeScore:
    remaining: int
    hp_percent_total: int


@dataclass(frozen=True, slots=True)
class PracticePointDecision:
    winner: str | None
    reason: str
    player_score: PracticeScore
    ai_score: PracticeScore


class PracticeActionController:
    """Coordinates web-submitted choices with a waiting human-controlled player."""

    def __init__(self, *, move_timeout_s: float = 30.0, broadcaster: Any = None) -> None:
        self.move_timeout_s = move_timeout_s
        self._broadcaster = broadcaster
        self._pending_by_battle: dict[str, _PendingAction] = {}
        self._pending_by_request: dict[str, _PendingAction] = {}
        self._pending_preview_by_battle: dict[str, _PendingTeamPreview] = {}
        self._pending_preview_by_request: dict[str, _PendingTeamPreview] = {}
        self._preview_index: dict[str, dict[str, set[int]]] = {}
        self._timeout_battles: set[str] = set()
        self._lock = asyncio.Lock()

    async def request_choice(self, battle_id: str, battle: Any) -> BattleOrder:
        orders = _legal_orders_for_battle(battle)
        if not orders:
            return cast("BattleOrder", DefaultBattleOrder())  # type: ignore[no-untyped-call]
        request_id = f"pa-{uuid.uuid4().hex[:8]}"
        phase = _resolve_phase(battle)
        options = tuple(
            PracticeActionOption(
                id=str(index),
                label=_order_label(order),
                message=order.message,
                kind=_order_kind(order),
                move=_order_move_payload(order),
                pokemon=_order_pokemon_payload(order),
                first=_order_slot_payload(getattr(order, "first_order", None)),
                second=_order_slot_payload(getattr(order, "second_order", None)),
            )
            for index, order in enumerate(orders)
        )
        request = PracticeActionRequest(
            request_id=request_id,
            battle_id=battle_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.move_timeout_s),
            options=options,
            phase=phase,
        )
        loop = asyncio.get_running_loop()
        pending = _PendingAction(
            request=request,
            future=loop.create_future(),
            orders={option.id: order for option, order in zip(options, orders, strict=True)},
        )
        async with self._lock:
            self._pending_by_battle[battle_id] = pending
            self._pending_by_request[request_id] = pending
        await self._broadcast(battle_id, request.to_dict())
        try:
            return await asyncio.wait_for(pending.future, timeout=self.move_timeout_s)
        except TimeoutError:
            self._timeout_battles.add(battle_id)
            await self._broadcast(
                battle_id,
                {"kind": "practice_user_timeout", "battle_id": battle_id, "request_id": request_id},
            )
            return ForfeitBattleOrder()
        finally:
            async with self._lock:
                self._pending_by_battle.pop(battle_id, None)
                self._pending_by_request.pop(request_id, None)

    async def submit_choice(self, battle_id: str, request_id: str, option_id: str) -> bool:
        async with self._lock:
            pending = self._pending_by_request.get(request_id)
            if pending is None or pending.request.battle_id != battle_id:
                return False
            order = pending.orders.get(option_id)
            if order is None:
                return False
            if pending.future.done():
                return False
            pending.future.set_result(order)
        await self._broadcast(
            battle_id,
            {"kind": "practice_action_submitted", "request_id": request_id, "option_id": option_id},
        )
        return True

    def current_request(self, battle_id: str) -> PracticeActionRequest | None:
        pending = self._pending_by_battle.get(battle_id)
        return pending.request if pending is not None else None

    def current_team_preview(self, battle_id: str) -> PracticeTeamPreviewRequest | None:
        pending = self._pending_preview_by_battle.get(battle_id)
        return pending.request if pending is not None else None

    def user_timed_out(self, battle_id: str) -> bool:
        return battle_id in self._timeout_battles

    def clear(self, battle_id: str) -> None:
        self._timeout_battles.discard(battle_id)
        pending = self._pending_by_battle.pop(battle_id, None)
        if pending is not None:
            self._pending_by_request.pop(pending.request.request_id, None)
            if not pending.future.done():
                pending.future.cancel()
        pending_preview = self._pending_preview_by_battle.pop(battle_id, None)
        if pending_preview is not None:
            self._pending_preview_by_request.pop(pending_preview.request.request_id, None)
            if not pending_preview.future.done():
                pending_preview.future.cancel()
        self._preview_index.pop(battle_id, None)

    async def request_team_preview(self, battle_id: str, battle: Any) -> str:
        members = list(battle.team.values())
        if not members:
            return _fallback_team_order(battle)
        max_team_size = int(getattr(battle, "_max_team_size", 0) or 0)
        if max_team_size <= 0:
            max_team_size = 1
        pick = min(max_team_size, len(members))
        if pick >= len(members):
            return _fallback_team_order(battle)
        request_id = f"tp-{uuid.uuid4().hex[:8]}"
        options = tuple(
            PracticeTeamPreviewOption(
                id=str(position + 1),
                label=_team_member_label(member, position),
                message=str(position + 1),
                pokemon=_team_member_payload(member, position),
            )
            for position, member in enumerate(members)
        )
        request = PracticeTeamPreviewRequest(
            request_id=request_id,
            battle_id=battle_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.move_timeout_s),
            pick=pick,
            options=options,
        )
        loop = asyncio.get_running_loop()
        pending = _PendingTeamPreview(
            request=request,
            future=loop.create_future(),
            picks={},
        )
        async with self._lock:
            self._pending_preview_by_battle[battle_id] = pending
            self._pending_preview_by_request[request_id] = pending
        await self._broadcast(battle_id, request.to_dict())
        try:
            return await asyncio.wait_for(pending.future, timeout=self.move_timeout_s)
        except TimeoutError:
            self._timeout_battles.add(battle_id)
            await self._broadcast(
                battle_id,
                {
                    "kind": "practice_user_timeout",
                    "battle_id": battle_id,
                    "request_id": request_id,
                },
            )
            return _fallback_team_order(battle)
        finally:
            async with self._lock:
                self._pending_preview_by_battle.pop(battle_id, None)
                self._pending_preview_by_request.pop(request_id, None)
                self._preview_index.pop(battle_id, None)

    async def submit_team_preview(
        self, battle_id: str, request_id: str, option_ids: list[str]
    ) -> bool:
        async with self._lock:
            pending = self._pending_preview_by_request.get(request_id)
            if pending is None or pending.request.battle_id != battle_id:
                return False
            if pending.future.done():
                return False
            positions: list[int] = []
            valid_ids: dict[str, int] = {
                opt.id: index + 1 for index, opt in enumerate(pending.request.options)
            }
            seen: set[int] = set()
            for option_id in option_ids:
                pos = valid_ids.get(option_id)
                if pos is None or pos in seen:
                    return False
                seen.add(pos)
                positions.append(pos)
            target_pick = pending.request.pick
            if target_pick <= 0 or len(positions) != target_pick:
                return False
            ordered = _order_team_preview(positions, len(pending.request.options))
        if not ordered:
            return False
        if not pending.future.done():
            pending.future.set_result(ordered)
        await self._broadcast(
            battle_id,
            {
                "kind": "practice_team_preview_submitted",
                "battle_id": battle_id,
                "request_id": request_id,
                "picks": positions,
            },
        )
        return True

    def record_team_preview_pick(
        self, battle_id: str, request_id: str, option_id: str
    ) -> list[int] | None:
        pending = self._pending_preview_by_request.get(request_id)
        if pending is None or pending.request.battle_id != battle_id:
            return None
        try:
            picked = int(option_id)
        except ValueError:
            return None
        valid_ids = {opt.id for opt in pending.request.options}
        if option_id not in valid_ids:
            return None
        index = self._preview_index.setdefault(battle_id, {})
        picks = index.setdefault(request_id, set())
        picks.add(picked)
        return sorted(picks)

    async def _broadcast(self, battle_id: str, payload: dict[str, object]) -> None:
        if self._broadcaster is not None:
            await self._broadcaster.broadcast(battle_id, payload)


def decide_points(
    *,
    player_name: str,
    ai_name: str,
    player_raw_log: str,
    ai_raw_log: str,
) -> PracticePointDecision:
    player_score = score_from_raw_log(player_raw_log)
    ai_score = score_from_raw_log(ai_raw_log)
    if player_score.remaining > ai_score.remaining:
        return PracticePointDecision(player_name, "remaining_pokemon", player_score, ai_score)
    if ai_score.remaining > player_score.remaining:
        return PracticePointDecision(ai_name, "remaining_pokemon", player_score, ai_score)
    if player_score.hp_percent_total > ai_score.hp_percent_total:
        return PracticePointDecision(player_name, "remaining_hp", player_score, ai_score)
    if ai_score.hp_percent_total > player_score.hp_percent_total:
        return PracticePointDecision(ai_name, "remaining_hp", player_score, ai_score)
    return PracticePointDecision(None, "draw", player_score, ai_score)


def score_from_raw_log(raw_log: str) -> PracticeScore:
    pokemon = _latest_side_pokemon(raw_log)
    remaining = 0
    hp_total = 0
    for mon in pokemon:
        condition = str(mon.get("condition") or "")
        hp = _condition_hp_percent(condition)
        if hp > 0:
            remaining += 1
            hp_total += hp
    return PracticeScore(remaining=remaining, hp_percent_total=hp_total)


def _legal_orders_for_battle(battle: Any) -> list[BattleOrder]:
    if isinstance(battle, DoubleBattle):
        return list(_compact_double_orders(battle))
    if isinstance(battle, Battle):
        return list(battle.valid_orders)
    valid_orders = getattr(battle, "valid_orders", None)
    if isinstance(valid_orders, list):
        return list(valid_orders)
    return []


def _compact_double_orders(battle: DoubleBattle) -> list[DoubleBattleOrder]:
    per_slot = battle.valid_orders
    if len(per_slot) != 2:
        return list(DoubleBattleOrder.join_orders(*per_slot))
    slot_orders = [_dedupe_slot_orders(slot) for slot in per_slot]
    return list(DoubleBattleOrder.join_orders(*slot_orders))


def _dedupe_slot_orders(orders: list[Any]) -> list[Any]:
    by_signature: dict[tuple[Any, ...], Any] = {}
    for order in orders:
        signature = _single_order_signature(order)
        if signature is None:
            by_signature[(id(order),)] = order
            continue
        if signature not in by_signature:
            by_signature[signature] = order
    return list(by_signature.values())


def _single_order_signature(order: Any) -> tuple[Any, ...] | None:
    message = getattr(order, "message", None)
    if not isinstance(message, str):
        return None
    # Target choices and mechanics (such as Terastallization) are encoded in
    # the message, while the move id alone is not enough to distinguish them.
    return (message,)


def _order_label(order: BattleOrder) -> str:
    message = order.message.removeprefix("/choose ")
    return message.replace(", ", " + ").replace("move ", "Move ").replace("switch ", "Switch ")


def _resolve_phase(battle: Any) -> str:
    force_switch = getattr(battle, "_force_switch", None)
    if isinstance(force_switch, list) and any(force_switch):
        return "switch"
    if isinstance(force_switch, bool) and force_switch:
        return "switch"
    wait = getattr(battle, "wait", False)
    if wait:
        return "free"
    return "move"


def _order_kind(order: BattleOrder) -> str:
    if hasattr(order, "first_order") and hasattr(order, "second_order"):
        first_kind = _single_kind(getattr(order, "first_order", None))
        second_kind = _single_kind(getattr(order, "second_order", None))
        kinds = {k for k in (first_kind, second_kind) if k}
        if kinds == {"move"}:
            return "move"
        if kinds == {"switch"}:
            return "switch"
        if kinds:
            return "double"
        return "double"
    return _single_kind(order) or "move"


def _single_kind(order: Any) -> str | None:
    if order is None:
        return None
    inner = getattr(order, "order", None)
    if inner is None:
        return None
    if _is_pokemon(inner):
        return "switch"
    if _is_move(inner):
        return "move"
    return None


def _is_move(obj: Any) -> bool:
    from poke_env.battle.move import Move

    return isinstance(obj, Move)


def _is_pokemon(obj: Any) -> bool:
    from poke_env.battle.pokemon import Pokemon

    return isinstance(obj, Pokemon)


def _order_move_payload(order: BattleOrder) -> dict[str, object] | None:
    if hasattr(order, "first_order") and hasattr(order, "second_order"):
        return None
    inner = getattr(order, "order", None)
    if inner is None or _is_pokemon(inner):
        return None
    move_id = str(getattr(inner, "id", "") or "")
    move_type = str(getattr(inner, "type", "") or "").split(" ")[0].lower()
    pp_current = getattr(inner, "current_pp", None)
    pp_max = getattr(inner, "max_pp", None)
    if pp_current is None and pp_max is None:
        try:
            pp_current = int(getattr(inner, "pp", 0) or 0)
            pp_max = int(getattr(inner, "maxpp", 0) or 0)
        except (TypeError, ValueError):
            pp_current, pp_max = 0, 0
    target = getattr(inner, "target", None)
    disabled = bool(getattr(inner, "disabled", False))
    return {
        "id": move_id,
        "label": move_id.replace(" ", " ").title() if move_id else "",
        "type": move_type,
        "pp": {"current": int(pp_current or 0), "max": int(pp_max or 0)},
        "target": str(target).split(" ")[0].lower() if target else None,
        "disabled": disabled,
    }


def _order_pokemon_payload(order: BattleOrder) -> dict[str, object] | None:
    if hasattr(order, "first_order") and hasattr(order, "second_order"):
        return None
    inner = getattr(order, "order", None)
    if not _is_pokemon(inner):
        return None
    return _pokemon_payload(inner)


def _order_slot_payload(order: Any) -> dict[str, object] | None:
    if order is None:
        return None
    inner = getattr(order, "order", None)
    if _is_pokemon(inner):
        return {"kind": "switch", "pokemon": _pokemon_payload(inner)}
    if _is_move(inner):
        move_id = str(getattr(inner, "id", "") or "")
        return {
            "kind": "move",
            "move": {
                "id": move_id,
                "label": move_id.replace(" ", " ").title() if move_id else "",
                "type": str(getattr(inner, "type", "") or "").split(" ")[0].lower(),
            },
        }
    return None


def _pokemon_payload(mon: Any) -> dict[str, object]:
    display_species, display_nickname = _display_species_and_nickname(mon)
    types = _normalize_types(getattr(mon, "types", None))
    hp = getattr(mon, "current_hp_fraction", None)
    hp_percent = 100 if hp is None else max(0, min(100, round(hp * 100)))
    fainted = bool(getattr(mon, "fainted", False))
    status_name = getattr(mon, "status", None)
    if status_name is None:
        status: str = "active"
    else:
        status = status_name.value if hasattr(status_name, "value") else str(status_name).lower()
    return {
        "name": display_nickname,
        "species": display_species,
        "species_id": _species_id(display_species),
        "sprite_id": _sprite_id(display_species),
        "types": types,
        "hp_percent": hp_percent,
        "status": status,
        "position": -1,
        "fainted": fainted,
    }


def _normalize_types(types: Any) -> list[str]:
    out: list[str] = []
    for t in types or []:
        name = getattr(t, "name", None) or getattr(t, "value", None) or str(t)
        out.append(str(name).lower())
    return out


def _team_member_label(member: Any, position: int) -> str:
    display_species, display_nickname = _display_species_and_nickname(member)
    species = display_species or f"Slot {position + 1}"
    if display_nickname and display_nickname != display_species:
        return f"{display_nickname} ({species})"
    return str(species)


def _team_member_payload(member: Any, position: int) -> dict[str, object]:
    display_species, display_nickname = _display_species_and_nickname(member)
    species = display_species or f"slot-{position + 1}"
    types = [str(t) for t in (getattr(member, "types", None) or [])]
    hp = getattr(member, "current_hp_fraction", None)
    hp_percent = 100 if hp is None else max(0, min(100, round(hp * 100)))
    fainted = bool(getattr(member, "fainted", False))
    status_name = getattr(member, "status", None)
    if status_name is None:
        status: str = "active"
    else:
        status = status_name.value if hasattr(status_name, "value") else str(status_name).lower()
    item = getattr(member, "item", None)
    ability = getattr(member, "ability", None)
    return {
        "name": display_nickname or species,
        "species": species,
        "species_id": _species_id(species),
        "sprite_id": _sprite_id(species),
        "types": types,
        "hp_percent": hp_percent,
        "status": status,
        "position": position,
        "fainted": fainted,
        "item": str(item) if item else None,
        "ability": str(ability) if ability else None,
    }


def _display_species_and_nickname(mon: Any) -> tuple[str, str | None]:
    """Return the species name the user expects to see plus the nickname.

    The Showdown server strips the form suffix from a Pokemon's display
    name whenever the nickname matches the species (``sim/pokemon.ts``
    rewrites ``set.name`` to ``baseSpecies.baseSpecies`` in that case).
    That means for ``Slowking-Galar`` with no custom nickname the
    server's ``|ident|`` arrives as ``p1: Slowking`` and poke-env's
    ``Pokemon.name`` returns ``"Slowking"`` — even though the
    ``|details|`` field correctly says ``"Slowking-Galar, L50"``.

    We prefer the species from ``_last_details`` (which the server
    fills with the full form name) and fall back to the teambuilder
    species / id-form species when the details haven't arrived yet.
    """
    details = getattr(mon, "_last_details", None) or ""
    if details:
        first = details.split(",", 1)[0].strip()
        if first:
            species = first
            return species, getattr(mon, "name", None)
    species_id = getattr(mon, "species", None) or "unknown"
    nickname = getattr(mon, "name", None)
    if nickname and nickname != species_id:
        return species_id, nickname
    return species_id, None


def _species_id(species: str) -> str:
    folded = normalize("NFKD", str(species)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", folded.lower())


def _fallback_team_order(battle: Any) -> str:
    members = len(getattr(battle, "team", {}) or {})
    max_team_size = int(getattr(battle, "_max_team_size", 0) or members)
    size = min(max(1, max_team_size), members)
    return "/team " + ",".join(str(i) for i in range(1, size + 1))


def _order_team_preview(picks: list[int], total: int) -> str | None:
    if total <= 0:
        return None
    if not picks:
        return None
    seen: set[int] = set()
    ordered: list[int] = []
    for pick in picks:
        if pick < 1 or pick > total:
            return None
        if pick in seen:
            return None
        seen.add(pick)
        ordered.append(pick)
    return "/team " + ",".join(str(i) for i in ordered)


def _latest_side_pokemon(raw_log: str) -> list[dict[str, object]]:
    latest: list[dict[str, object]] = []
    for line in raw_log.splitlines():
        if not line.startswith("|request|"):
            continue
        try:
            body = json.loads(line.removeprefix("|request|"))
        except json.JSONDecodeError:
            continue
        side = body.get("side")
        if isinstance(side, dict) and isinstance(side.get("pokemon"), list):
            latest = [mon for mon in side["pokemon"] if isinstance(mon, dict)]
    return latest


def _condition_hp_percent(condition: str) -> int:
    if "fnt" in condition:
        return 0
    hp_text = condition.split()[0] if condition else ""
    if "/" in hp_text:
        left, _, right = hp_text.partition("/")
        if left.isdigit() and right.isdigit():
            total = int(right)
            return int((int(left) / total) * 100) if total else 0
    if hp_text.endswith("%") and hp_text[:-1].isdigit():
        return int(hp_text[:-1])
    if hp_text.isdigit():
        return int(hp_text)
    return 100 if condition else 0


def monotonic_deadline(seconds: float | None) -> float | None:
    return time.monotonic() + seconds if seconds is not None else None
