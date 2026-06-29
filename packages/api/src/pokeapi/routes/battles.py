"""Battle create + status routes."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from pokeapi.auth import require_current_user
from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Rating, Replay, Team, User
from pokeapi.orchestrator import BattleJob, JobResult
from pokeapi.schemas import BattleCreate, BattleResponse
from pokeapi.state import get_team_validator
from pokecore.elo import MIN_VOLATILITY, GlickoRating, rate_pair

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/battles", tags=["battles"])


@router.post("", response_model=BattleResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_battle(
    body: BattleCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> BattleResponse:
    factory = request.app.state.session_factory
    orch = request.app.state.orchestrator
    team1_paste: str | None = None
    team2_paste: str | None = None
    with session_scope(factory) as session:
        if body.team1_id is not None:
            team = session.get(Team, body.team1_id)
            if team is None or team.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Team 1 not found")
            team1_paste = team.paste
        if body.team2_id is not None:
            team = session.get(Team, body.team2_id)
            if team is None or team.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Team 2 not found")
            team2_paste = team.paste
    validator = get_team_validator(request)
    check1 = await validator.validate(team1_paste, body.format)
    if not check1.ok:
        raise HTTPException(status_code=400, detail=check1.to_detail("Team 1"))
    check2 = await validator.validate(team2_paste, body.format)
    if not check2.ok:
        raise HTTPException(status_code=400, detail=check2.to_detail("Team 2"))
    job = BattleJob(
        format=body.format,
        player1=body.player1.username,
        player2=body.player2.username,
        model1=body.player1.model_name,
        model2=body.player2.model_name,
        team1_paste=team1_paste,
        team2_paste=team2_paste,
    )
    battle_id = job.id
    with session_scope(factory) as session:
        battle = Battle(
            id=battle_id,
            format=body.format,
            status="queued",
            owner_id=user.id,
            player1_username=body.player1.username,
            player2_username=body.player2.username,
            model1=body.player1.model_name,
            model2=body.player2.model_name,
            team1_id=body.team1_id,
            team2_id=body.team2_id,
        )
        session.add(battle)

    async def on_start(started_job: BattleJob) -> None:
        with session_scope(factory) as sess:
            b = sess.get(Battle, started_job.id)
            if b is not None:
                b.status = "running"
                b.started_at = datetime.now(UTC)

    async def on_complete(job: BattleJob, result: JobResult) -> None:
        with session_scope(factory) as sess:
            b = sess.get(Battle, job.id)
            if b is not None:
                b.status = "finished" if result.winner is not None or result.events else "failed"
                b.winner = result.winner
                b.turns = result.turns
                b.duration_s = result.duration_s
                b.finished_at = datetime.now(UTC)
            if result.events or result.raw_log:
                replay = Replay(
                    battle_id=job.id,
                    events=[e.to_dict() if hasattr(e, "to_dict") else e for e in result.events],
                    raw_log=result.raw_log or "",
                    summary_json={
                        "format": job.format,
                        "turns": result.turns,
                        "duration_s": result.duration_s,
                        "winner": result.winner,
                    },
                )
                sess.add(replay)
            if result.winner is not None:
                _update_ratings(sess, job, result.winner)

    job.on_start = on_start
    job.on_complete = on_complete
    await orch.submit(job)
    with session_scope(factory) as session:
        battle_opt = session.get(Battle, battle_id)
        if battle_opt is None:
            raise HTTPException(status_code=500, detail="Battle vanished after submit")
        return _to_response(battle_opt)


@router.get("", response_model=list[BattleResponse])
async def list_battles(
    request: Request,
    limit: int = 25,
    user: User = Depends(require_current_user),
) -> list[BattleResponse]:
    factory = request.app.state.session_factory
    capped_limit = min(max(limit, 1), 100)
    with session_scope(factory) as session:
        battles = (
            session.query(Battle)
            .filter(Battle.owner_id == user.id)
            .order_by(Battle.created_at.desc())
            .limit(capped_limit)
            .all()
        )
        return [_to_response(battle) for battle in battles]


@router.get("/{battle_id}", response_model=BattleResponse)
async def get_battle(battle_id: str, request: Request) -> BattleResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        battle = session.get(Battle, battle_id)
        if battle is None:
            raise HTTPException(status_code=404, detail="Battle not found")
        return _to_response(battle)


def _update_ratings(sess: Any, job: BattleJob, winner: str) -> None:
    fmt = job.format
    for player in (job.player1, job.player2):
        rating = sess.query(Rating).filter_by(subject=player, format=fmt).first()
        if rating is None:
            rating = Rating(subject=player, format=fmt)
            sess.add(rating)
            sess.flush()
    r1 = sess.query(Rating).filter_by(subject=job.player1, format=fmt).first()
    r2 = sess.query(Rating).filter_by(subject=job.player2, format=fmt).first()
    if r1 is None or r2 is None:
        return
    # Defensive: a Rating row written by a previous (buggy) code
    # path can have vol == 0.0 if the Glicko-2 Illinois iteration
    # underflowed ``math.exp`` to 0.0. ``GlickoRating``'s
    # ``__post_init__`` rejects vol <= 0, which would crash the
    # on_complete callback and orphan the battle. Clamp to the
    # algorithm's minimum volatility so the rating can recover.
    g1 = GlickoRating(
        rating=r1.rating,
        rd=r1.rd,
        vol=max(r1.vol, MIN_VOLATILITY),
    )
    g2 = GlickoRating(
        rating=r2.rating,
        rd=r2.rd,
        vol=max(r2.vol, MIN_VOLATILITY),
    )
    score_a = 1.0 if winner == job.player1 else 0.0
    new_g1, new_g2 = rate_pair(g1, g2, score_a)
    r1.rating = new_g1.rating
    r1.rd = new_g1.rd
    r1.vol = new_g1.vol
    r1.games += 1
    r2.rating = new_g2.rating
    r2.rd = new_g2.rd
    r2.vol = new_g2.vol
    r2.games += 1


def _to_response(b: Battle) -> BattleResponse:
    started = b.started_at
    finished = b.finished_at
    duration = b.duration_s
    if duration is None and started and finished:
        duration = (finished - started).total_seconds()
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
