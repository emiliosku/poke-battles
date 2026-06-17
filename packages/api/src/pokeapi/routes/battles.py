"""Battle create + status routes."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status

from pokeapi.db import session_scope
from pokeapi.db.models import Battle
from pokeapi.orchestrator import BattleJob
from pokeapi.schemas import BattleCreate, BattleResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/battles", tags=["battles"])


@router.post("", response_model=BattleResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_battle(body: BattleCreate, request: Request) -> BattleResponse:
    factory = request.app.state.session_factory
    orch = request.app.state.orchestrator
    battle_id = f"battle-{int(time.time() * 1000)}"
    with session_scope(factory) as session:
        battle = Battle(
            id=battle_id,
            format=body.format,
            status="queued",
            player1_username=body.player1.username,
            player2_username=body.player2.username,
            model1=body.player1.model_name,
            model2=body.player2.model_name,
            team1_id=body.team1_id,
            team2_id=body.team2_id,
        )
        session.add(battle)

    async def on_complete(job: BattleJob, winner: str | None, turns: int) -> None:
        with session_scope(factory) as sess:
            b = sess.get(Battle, job.id)
            if b is not None:
                b.status = "finished"
                b.winner = winner
                b.turns = turns
                b.finished_at = b.finished_at or b.created_at

    job = BattleJob(
        id=battle_id,
        format=body.format,
        player1=body.player1.username,
        player2=body.player2.username,
        model1=body.player1.model_name,
        model2=body.player2.model_name,
        on_complete=on_complete,
    )
    await orch.submit(job)
    with session_scope(factory) as session:
        battle_opt = session.get(Battle, battle_id)
        if battle_opt is None:
            raise HTTPException(status_code=500, detail="Battle vanished after submit")
        return _to_response(battle_opt)


@router.get("/{battle_id}", response_model=BattleResponse)
async def get_battle(battle_id: str, request: Request) -> BattleResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        battle = session.get(Battle, battle_id)
        if battle is None:
            raise HTTPException(status_code=404, detail="Battle not found")
        return _to_response(battle)


def _to_response(b: Battle) -> BattleResponse:
    started = b.started_at
    finished = b.finished_at
    duration = (finished - started).total_seconds() if started and finished else None
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
        duration_s=duration,
        created_at=b.created_at,
        started_at=started,
        finished_at=finished,
    )


_ = asyncio
