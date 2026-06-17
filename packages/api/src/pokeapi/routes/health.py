"""Health check routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from pokeapi.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version="0.1.0",
        uptime_s=time.monotonic() - getattr(request.app.state, "start_time", time.monotonic()),
    )
