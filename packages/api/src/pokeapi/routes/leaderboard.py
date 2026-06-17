"""Leaderboard routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pokeapi.db import session_scope
from pokeapi.db.models import Rating
from pokeapi.schemas import LeaderboardEntry

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("", response_model=list[LeaderboardEntry])
async def leaderboard(
    request: Request,
    format: str = "gen9randombattle",
    limit: int = 25,
) -> list[LeaderboardEntry]:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        rows = (
            session.query(Rating)
            .filter(Rating.format == format)
            .order_by(Rating.rating.desc())
            .limit(limit)
            .all()
        )
        return [
            LeaderboardEntry(
                subject=r.subject,
                format=r.format,
                rating=r.rating,
                rd=r.rd,
                games=r.games,
            )
            for r in rows
        ]
