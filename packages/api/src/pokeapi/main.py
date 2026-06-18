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
from pokeapi.routes import auth, battles, health, leaderboard, meta, replays, simulations, teams, ws
from pokeapi.routes.ws import manager as ws_manager
from pokeapi.schemas import HealthResponse
from pokeapi.services import BattleService
from pokeapi.settings import get_settings
from pokellm.config import find_models_yaml, load_models_yaml

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    engine = make_engine(settings.database_url)
    init_db(engine)
    factory = make_session_factory(engine)
    models_yaml = find_models_yaml()
    if models_yaml.exists():
        models = load_models_yaml(models_yaml)
        logger.info("Loaded %d models from %s", len(models), models_yaml)
    else:
        models = {}
        logger.warning("No models.yaml found; LLM agents will fall back to random")
    bservice = BattleService(
        showdown_dir=settings.showdown_server_dir,
        connection_manager=ws_manager,
        models=models,
    )
    orchestrator = Orchestrator(max_concurrent=settings.max_concurrent_showdown)
    orchestrator.set_runner(bservice.run_job)
    await orchestrator.start()
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.orchestrator = orchestrator
    app.state.bservice = bservice
    app.state.models = models
    app.state.start_time = time.monotonic()
    logger.info("pokeapi ready on %s", settings.database_url)
    try:
        yield
    finally:
        await orchestrator.stop()
        bservice.stop()
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
    app.include_router(auth.router)
    app.include_router(teams.router)
    app.include_router(battles.router)
    app.include_router(simulations.router)
    app.include_router(leaderboard.router)
    app.include_router(meta.router)
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
