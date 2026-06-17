"""FastAPI application entry point."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pokeapi.db import init_db, make_engine, make_session_factory
from pokeapi.orchestrator import Orchestrator
from pokeapi.routes import battles, health, leaderboard, replays, simulations, teams, ws
from pokeapi.schemas import HealthResponse
from pokeapi.settings import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    orchestrator = Orchestrator(max_concurrent=settings.max_concurrent_showdown)
    await orchestrator.start()
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.orchestrator = orchestrator
    app.state.start_time = time.monotonic()
    logger.info("pokeapi ready on %s", settings.database_url)
    try:
        yield
    finally:
        await orchestrator.stop()
        engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Pokémon AI Agents",
        version="0.1.0",
        description="LLM-powered Pokémon Showdown agent battles.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(teams.router)
    app.include_router(battles.router)
    app.include_router(simulations.router)
    app.include_router(leaderboard.router)
    app.include_router(replays.router)
    app.include_router(ws.router)

    @app.get("/", response_model=HealthResponse, tags=["meta"])
    async def root() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version="0.1.0",
            uptime_s=time.monotonic() - getattr(app.state, "start_time", time.monotonic()),
        )

    return app


app = create_app()
