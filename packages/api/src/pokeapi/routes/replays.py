"""Replay routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Replay
from pokeapi.schemas import ReplayResponse

router = APIRouter(prefix="/replays", tags=["replays"])


@router.get("/{battle_id}", response_model=ReplayResponse)
async def get_replay(battle_id: str, request: Request) -> ReplayResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        replay = session.get(Replay, battle_id)
        if replay is None:
            battle = session.get(Battle, battle_id)
            if battle is None:
                raise HTTPException(status_code=404, detail="Replay not found")
            return ReplayResponse(
                battle_id=battle.id,
                format=battle.format,
                events=[],
                raw_log=None,
                duration_s=None,
                turns=battle.turns,
            )
        summary = replay.summary_json or {}
        duration = summary.get("duration_s")
        turns_val = summary.get("turns")
        return ReplayResponse(
            battle_id=replay.battle_id,
            format=str(summary.get("format", "unknown")),
            events=replay.events or [],
            raw_log=replay.raw_log,
            duration_s=float(duration) if isinstance(duration, (int, float)) else None,
            turns=int(turns_val) if isinstance(turns_val, (int, float)) else None,
        )
