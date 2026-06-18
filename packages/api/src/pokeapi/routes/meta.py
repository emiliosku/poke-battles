"""Metadata routes consumed by the web UI."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pokeapi.schemas import FormatResponse, ModelResponse
from pokecore.formats import SUPPORTED_FORMATS

router = APIRouter(tags=["meta"])


@router.get("/formats", response_model=list[FormatResponse])
async def list_formats() -> list[FormatResponse]:
    return [
        FormatResponse(
            id=fmt.id,
            name=fmt.name,
            generation=fmt.generation.value,
            kind=fmt.kind.value,
                team_size=fmt.team_size,
                level=fmt.level,
                random_team=fmt.random_team,
                requires_team=fmt.requires_team,
                active_slots=fmt.active_slots,
                practice_supported=fmt.practice_supported,
                experimental=fmt.experimental,
            )
        for fmt in SUPPORTED_FORMATS
    ]


@router.get("/models", response_model=list[ModelResponse])
async def list_models(request: Request) -> list[ModelResponse]:
    models = getattr(request.app.state, "models", {})
    out = [
        ModelResponse(
            name=config.name,
            provider=config.provider,
            tier=config.tier.value,
            supports_tools=config.supports_tools,
            rate_limit_rpm=config.rate_limit_rpm,
            notes=config.notes,
        )
        for config in models.values()
    ]
    if not any(model.name == "random" for model in out):
        out.insert(
            0,
            ModelResponse(
                name="random",
                provider="local",
                tier="mock",
                supports_tools=False,
                notes="Local random move chooser",
            ),
        )
    return sorted(out, key=lambda model: (model.tier != "mock", model.name))


__all__ = ["router"]
