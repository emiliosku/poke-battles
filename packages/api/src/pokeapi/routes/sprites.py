"""Routes for the dev/debug sprite coverage tool.

``GET /api/sprites/status`` reports, for every species in the bundled
Pokédex, whether the canonical ``species_id`` and the derived
``sprite_id`` slug resolve to a real image on the Showdown CDN.

Used by the ``/debug/sprites`` page in the web UI to find missing
sprites without a manual probe. Results are cached in memory for an
hour; pass ``?refresh=true`` to bust the cache.

Not auth-gated — this is a developer tool, not user data.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from pokeapi.schemas import SpriteResultEntry, SpriteStatusResponse
from pokecore.sprite_status import get_status

router = APIRouter(prefix="/sprites", tags=["sprites"])


@router.get("/status", response_model=SpriteStatusResponse)
async def sprite_status(
    refresh: bool = Query(
        False,
        description="Bust the in-memory cache and re-probe the CDN.",
    ),
    q: str | None = Query(
        None,
        description="Optional substring filter against ``species_id`` or name.",
    ),
    type: str | None = Query(
        None,
        description="Optional filter by Pokémon type (e.g. ``fire``).",
    ),
) -> SpriteStatusResponse:
    # The probe walks ~1.5k species x 7 CDN URLs and is fully
    # synchronous. Running it inline would block the single uvicorn
    # worker's event loop for ~60-80s, freezing every other tab on the
    # site (teams/leaderboard/health/etc.). Push it to the default
    # threadpool so the loop keeps handling requests; the probe
    # itself already uses a ThreadPoolExecutor internally, so we
    # simply wrap the *outer* call. Filters are applied on the
    # in-memory report after the probe returns.
    report = await asyncio.to_thread(get_status, refresh=refresh)
    results = report.results
    if q:
        needle = q.lower()
        results = [r for r in results if needle in r.species_id or needle in r.name.lower()]
    if type:
        needle = type.lower()
        results = [r for r in results if any(t.lower() == needle for t in r.types)]
    return SpriteStatusResponse(
        checked_at=report.checked_at,
        count=len(results),
        duration_s=report.duration_s,
        results=[
            SpriteResultEntry(
                species_id=r.species_id,
                name=r.name,
                types=list(r.types),
                canonical_slug=r.canonical_slug,
                derived_slug=r.derived_slug,
                canonical_hits=list(r.canonical_hits),
                derived_hits=list(r.derived_hits),
                is_cap=r.is_cap,
            )
            for r in results
        ],
    )


__all__ = ["router"]
