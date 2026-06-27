"""Metadata routes consumed by the web UI."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pokeapi.schemas import (
    FormatResponse,
    ModelResponse,
    PokedexEntry,
    PokedexResponse,
)
from pokecore.formats import SUPPORTED_FORMATS
from pokecore.pokedex import load_pokedex

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


@router.get("/pokedex", response_model=PokedexResponse)
async def list_pokedex() -> PokedexResponse:
    """Return the canonical Pokémon Showdown Pokédex as a flat list.

    Sourced from the same ``pokedex.js`` that ships with the engine
    package, so ``species_id`` is exactly the lookup key the Showdown
    client and CDN use. The web UI uses this to:
      * populate autocomplete for the team paste field,
      * discover which Pokémon have a sprite on the Showdown CDN,
      * any other feature that needs the canonical species list.
    """
    entries = load_pokedex()
    return PokedexResponse(
        count=len(entries),
        pokemon=[
            PokedexEntry(
                species_id=entry.species_id,
                name=entry.name,
                num=entry.num,
                types=list(entry.types),
                base_stats=entry.base_stats,
                abilities=entry.abilities,
            )
            for entry in entries
        ],
    )


__all__ = ["router"]
