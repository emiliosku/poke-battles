"""Simulation routes (round-robin, team-vs-team)."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, status

from pokeapi.db import session_scope
from pokeapi.db.models import Simulation
from pokeapi.schemas import SimulationCreate, SimulationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=SimulationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_simulation(body: SimulationCreate, request: Request) -> SimulationResponse:
    if body.mode not in {"round_robin", "team_vs_team"}:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}")
    factory = request.app.state.session_factory
    sim_id = f"sim-{uuid.uuid4().hex[:8]}"
    with session_scope(factory) as session:
        sim = Simulation(
            id=sim_id,
            mode=body.mode,
            team_a_id=body.team_a_id,
            team_b_id=body.team_b_id,
            models_json=body.models,
            n_battles=body.n_battles,
            status="queued",
        )
        session.add(sim)
    return _to_response(sim)


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
