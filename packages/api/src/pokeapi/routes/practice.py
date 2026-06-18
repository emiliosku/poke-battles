"""Practice battle routes for user-vs-AI training."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from pokeapi.auth import require_current_user
from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Replay, Team, User
from pokeapi.schemas import (
    BattleResponse,
    PracticeActionResponse,
    PracticeActionSubmit,
    PracticeBattleCreate,
)
from pokecore.formats import Format, get_format

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("/battles", response_model=BattleResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_practice_battle(
    body: PracticeBattleCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> BattleResponse:
    factory = request.app.state.session_factory
    bservice = request.app.state.bservice
    action_controller = request.app.state.practice_controller
    fmt = _known_format(body.format)
    if (
        fmt is not None
        and fmt.requires_team
        and (body.user_team_id is None or body.ai_team_id is None)
    ):
        raise HTTPException(status_code=400, detail=f"{fmt.name} requires both teams")
    battle_id = f"battle-{uuid.uuid4().hex[:8]}"
    player_team_paste: str | None = None
    ai_team_paste: str | None = None
    with session_scope(factory) as session:
        if body.user_team_id is not None:
            player_team_paste = _team_paste(session, body.user_team_id, user.id, "User team")
        if body.ai_team_id is not None:
            ai_team_paste = _team_paste(session, body.ai_team_id, user.id, "AI team")
        battle = Battle(
            id=battle_id,
            format=body.format,
            status="queued",
            owner_id=user.id,
            player1_username=body.player_username,
            player2_username=body.ai_username,
            model1="human",
            model2=body.ai_model,
            team1_id=body.user_team_id,
            team2_id=body.ai_team_id,
        )
        session.add(battle)

    async def _run() -> None:
        try:
            with session_scope(factory) as sess:
                b = sess.get(Battle, battle_id)
                if b is not None:
                    b.status = "running"
                    b.started_at = datetime.now(UTC)
            result = await bservice.run_practice_battle(
                app_battle_id=battle_id,
                battle_format=body.format,
                player=body.player_username,
                ai_player=body.ai_username,
                ai_model=body.ai_model,
                action_controller=action_controller,
                player_team_paste=player_team_paste,
                ai_team_paste=ai_team_paste,
                total_timer_s=body.total_timer_s,
            )
            with session_scope(factory) as sess:
                b = sess.get(Battle, battle_id)
                if b is not None:
                    b.status = str(
                        result.get("status") or ("failed" if "error" in result else "finished")
                    )
                    b.winner = result.get("winner")
                    b.turns = result.get("turns", 0)
                    b.duration_s = result.get("duration_s", 0.0)
                    b.finished_at = datetime.now(UTC)
                events = result.get("events", ())
                raw_log = str(result.get("raw_log") or "")
                if events or raw_log:
                    sess.add(
                        Replay(
                            battle_id=battle_id,
                            events=[e.to_dict() if hasattr(e, "to_dict") else e for e in events],
                            raw_log=raw_log,
                            summary_json={
                                "format": body.format,
                                "turns": result.get("turns", 0),
                                "duration_s": result.get("duration_s", 0.0),
                                "winner": result.get("winner"),
                                "practice": True,
                                "status": result.get("status"),
                                **dict(result.get("summary") or {}),
                            },
                        )
                    )
        except Exception:
            logger.exception("Practice battle %s failed", battle_id)
            with session_scope(factory) as sess:
                b = sess.get(Battle, battle_id)
                if b is not None:
                    b.status = "failed"
                    b.finished_at = datetime.now(UTC)
        finally:
            action_controller.clear(battle_id)

    tasks: set[asyncio.Task[None]] = getattr(request.app.state, "practice_tasks", set())
    request.app.state.practice_tasks = tasks
    task = asyncio.create_task(_run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    with session_scope(factory) as session:
        battle_opt = session.get(Battle, battle_id)
        if battle_opt is None:
            raise HTTPException(status_code=500, detail="Practice battle vanished after create")
        return _to_response(battle_opt)


@router.get("/battles/{battle_id}/action")
async def get_practice_action(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> dict[str, object | None]:
    _require_owner(request, battle_id, user.id)
    current = request.app.state.practice_controller.current_request(battle_id)
    return {"action": current.to_dict() if current is not None else None}


@router.post("/battles/{battle_id}/actions", response_model=PracticeActionResponse)
async def submit_practice_action(
    battle_id: str,
    body: PracticeActionSubmit,
    request: Request,
    user: User = Depends(require_current_user),
) -> PracticeActionResponse:
    _require_owner(request, battle_id, user.id)
    accepted = await request.app.state.practice_controller.submit_choice(
        battle_id, body.request_id, body.option_id
    )
    if not accepted:
        raise HTTPException(status_code=409, detail="No matching pending action")
    return PracticeActionResponse(accepted=True)


def _known_format(format_id: str) -> Format | None:
    try:
        return get_format(format_id)
    except KeyError:
        return None


def _team_paste(session: Any, team_id: int, owner_id: str, label: str) -> str:
    team = session.get(Team, team_id)
    if team is None or team.owner_id != owner_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return str(team.paste)


def _require_owner(request: Request, battle_id: str, user_id: str) -> None:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        battle = session.get(Battle, battle_id)
        if battle is None or battle.owner_id != user_id:
            raise HTTPException(status_code=404, detail="Practice battle not found")


def _to_response(b: Battle) -> BattleResponse:
    return BattleResponse(
        id=b.id,
        format=b.format,
        status=b.status,
        player1_username=b.player1_username,
        player2_username=b.player2_username,
        model1=b.model1,
        model2=b.model2,
        winner=b.winner,
        turns=b.turns,
        duration_s=b.duration_s,
        created_at=b.created_at,
        started_at=b.started_at,
        finished_at=b.finished_at,
    )
