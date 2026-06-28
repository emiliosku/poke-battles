"""Simulation routes (round-robin, team-vs-team, ladder)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from pokeapi.auth import require_current_user
from pokeapi.db import session_scope
from pokeapi.db.models import Simulation, Team, User
from pokeapi.schemas import SimulationCreate, SimulationResponse
from pokeapi.state import get_team_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=SimulationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_simulation(
    body: SimulationCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> SimulationResponse:
    if body.mode not in {"round_robin", "team_vs_team", "ladder"}:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}")
    if body.mode in {"round_robin", "ladder"} and len(body.models) < 2:
        raise HTTPException(status_code=400, detail=f"{body.mode} requires at least two models")
    factory = request.app.state.session_factory
    bservice = request.app.state.bservice
    sim_id = f"sim-{uuid.uuid4().hex[:8]}"
    team_a_paste: str | None = None
    team_b_paste: str | None = None
    with session_scope(factory) as session:
        if body.team_a_id is not None:
            team = session.get(Team, body.team_a_id)
            if team is None or team.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Team A not found")
            team_a_paste = team.paste
        if body.team_b_id is not None:
            team = session.get(Team, body.team_b_id)
            if team is None or team.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Team B not found")
            team_b_paste = team.paste
        sim = Simulation(
            id=sim_id,
            owner_id=user.id,
            mode=body.mode,
            format=body.format,
            team_a_id=body.team_a_id,
            team_b_id=body.team_b_id,
            models_json=body.models,
            n_battles=body.n_battles,
            status="queued",
        )
        session.add(sim)
    validator = get_team_validator(request)
    check_a = await validator.validate(team_a_paste, body.format)
    if not check_a.ok:
        raise HTTPException(status_code=400, detail=check_a.to_detail("Team A"))
    check_b = await validator.validate(team_b_paste, body.format)
    if not check_b.ok:
        raise HTTPException(status_code=400, detail=check_b.to_detail("Team B"))

    async def _run() -> None:
        try:
            result = await bservice.run_simulation(
                mode=body.mode,
                battle_format=body.format,
                team_a_id=body.team_a_id,
                team_b_id=body.team_b_id,
                team_a_paste=team_a_paste,
                team_b_paste=team_b_paste,
                models=body.models,
                n_battles=body.n_battles,
            )
            with session_scope(factory) as sess:
                s = sess.get(Simulation, sim_id)
                if s is not None:
                    s.status = "finished"
                    s.wins = result.get("wins", 0)
                    s.losses = result.get("losses", 0)
                    s.draws = result.get("draws", 0)
                    s.win_rate = result.get("win_rate")
                    s.results_json = result
                    s.finished_at = datetime.now(UTC)
        except Exception:
            logger.exception("Simulation %s failed", sim_id)
            with session_scope(factory) as sess:
                s = sess.get(Simulation, sim_id)
                if s is not None:
                    s.status = "failed"

    tasks: set[asyncio.Task[None]] = getattr(request.app.state, "simulation_tasks", set())
    request.app.state.simulation_tasks = tasks
    task = asyncio.create_task(_run())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return _to_response(sim)


@router.get("", response_model=list[SimulationResponse])
async def list_simulations(
    request: Request,
    limit: int = 25,
    user: User = Depends(require_current_user),
) -> list[SimulationResponse]:
    factory = request.app.state.session_factory
    capped_limit = min(max(limit, 1), 100)
    with session_scope(factory) as session:
        simulations = (
            session.query(Simulation)
            .filter(Simulation.owner_id == user.id)
            .order_by(Simulation.created_at.desc())
            .limit(capped_limit)
            .all()
        )
        return [_to_response(sim) for sim in simulations]


@router.get("/{sim_id}", response_model=SimulationResponse)
async def get_simulation(sim_id: str, request: Request) -> SimulationResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        sim = session.get(Simulation, sim_id)
        if sim is None:
            raise HTTPException(status_code=404, detail="Simulation not found")
        return _to_response(sim)


def _to_response(s: Simulation) -> SimulationResponse:
    return SimulationResponse(
        id=s.id,
        status=s.status,
        mode=s.mode,
        n_battles=s.n_battles,
        wins=s.wins,
        losses=s.losses,
        draws=s.draws,
        win_rate=s.win_rate,
        ci_95=s.ci_95,
        results_json=s.results_json,
        created_at=s.created_at,
        finished_at=s.finished_at,
    )


_ = (time, logging)
