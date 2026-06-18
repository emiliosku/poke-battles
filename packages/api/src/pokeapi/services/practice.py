"""Practice battle helpers for user-vs-AI battles."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from poke_env.battle.battle import Battle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.player.battle_order import (
    BattleOrder,
    DefaultBattleOrder,
    DoubleBattleOrder,
    ForfeitBattleOrder,
)


@dataclass(frozen=True, slots=True)
class PracticeActionOption:
    id: str
    label: str
    message: str


@dataclass(frozen=True, slots=True)
class PracticeActionRequest:
    request_id: str
    battle_id: str
    expires_at: datetime
    options: tuple[PracticeActionOption, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "practice_action_required",
            "request_id": self.request_id,
            "battle_id": self.battle_id,
            "expires_at": self.expires_at.isoformat(),
            "options": [
                {"id": option.id, "label": option.label, "message": option.message}
                for option in self.options
            ],
        }


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
        self._timeout_battles: set[str] = set()
        self._lock = asyncio.Lock()

    async def request_choice(self, battle_id: str, battle: Any) -> BattleOrder:
        orders = _legal_orders_for_battle(battle)
        if not orders:
            return cast("BattleOrder", DefaultBattleOrder())  # type: ignore[no-untyped-call]
        request_id = f"pa-{uuid.uuid4().hex[:8]}"
        options = tuple(
            PracticeActionOption(
                id=str(index),
                label=_order_label(order),
                message=order.message,
            )
            for index, order in enumerate(orders)
        )
        request = PracticeActionRequest(
            request_id=request_id,
            battle_id=battle_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.move_timeout_s),
            options=options,
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

    def user_timed_out(self, battle_id: str) -> bool:
        return battle_id in self._timeout_battles

    def clear(self, battle_id: str) -> None:
        self._timeout_battles.discard(battle_id)
        pending = self._pending_by_battle.pop(battle_id, None)
        if pending is not None:
            self._pending_by_request.pop(pending.request.request_id, None)
            if not pending.future.done():
                pending.future.cancel()

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
        return list(DoubleBattleOrder.join_orders(*battle.valid_orders))
    if isinstance(battle, Battle):
        return list(battle.valid_orders)
    valid_orders = getattr(battle, "valid_orders", None)
    if isinstance(valid_orders, list):
        return list(valid_orders)
    return []


def _order_label(order: BattleOrder) -> str:
    message = order.message.removeprefix("/choose ")
    return message.replace(", ", " + ").replace("move ", "Move ").replace("switch ", "Switch ")


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
