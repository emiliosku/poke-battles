"""Team CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from pokeapi.auth import require_current_user
from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Simulation, Team, User
from pokeapi.schemas import (
    PokemonPreview,
    TeamCreate,
    TeamPreviewRequest,
    TeamPreviewResponse,
    TeamResponse,
    TeamUpdate,
    TeamValidateRequest,
    TeamValidateResponse,
)
from pokeapi.state import get_team_validator
from pokecore import parse_team
from pokecore.teams import PokemonSet, sprite_id

router = APIRouter(prefix="/teams", tags=["teams"])


def _team_to_response(team: Team) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        name=team.name,
        format=team.format,
        is_public=team.is_public,
        created_at=team.created_at,
        paste=team.paste,
        pokemon_count=len(parse_team(team.paste).pokemon) if team.paste else 0,
    )


def _pokemon_to_preview(pkmn: PokemonSet) -> PokemonPreview:
    return PokemonPreview(
        nickname=pkmn.nickname,
        species=pkmn.species,
        species_id=pkmn.species_id,
        sprite_id=sprite_id(pkmn.species),
        item=pkmn.item,
        ability=pkmn.ability,
        types=[t.value for t in pkmn.types],
        moves=[m.name for m in pkmn.moves],
    )


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    request: Request,
    user: User = Depends(require_current_user),
) -> list[TeamResponse]:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        q = session.query(Team).filter(Team.owner_id == user.id)
        teams = q.order_by(Team.created_at.desc()).all()
        return [_team_to_response(t) for t in teams]


@router.post("/preview", response_model=TeamPreviewResponse)
async def preview_team(
    body: TeamPreviewRequest,
    user: User = Depends(require_current_user),
) -> TeamPreviewResponse:
    try:
        team = parse_team(body.paste)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid paste: {exc}") from exc
    return TeamPreviewResponse(pokemon=[_pokemon_to_preview(p) for p in team.pokemon])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> TeamResponse:
    try:
        parse_team(body.paste)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid paste: {exc}") from exc
    if body.format:
        check = await get_team_validator(request).validate(body.paste, body.format)
        if not check.ok:
            raise HTTPException(status_code=400, detail=check.to_detail("Team")) from None
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        team = Team(
            owner_id=user.id,
            name=body.name,
            paste=body.paste,
            format=body.format,
            is_public=body.is_public,
        )
        session.add(team)
        session.flush()
        return _team_to_response(team)


@router.post("/validate", response_model=TeamValidateResponse)
async def validate_team(
    body: TeamValidateRequest,
    request: Request,
    user: User = Depends(require_current_user),
) -> TeamValidateResponse:
    try:
        parse_team(body.paste)
    except ValueError as exc:
        return TeamValidateResponse(ok=False, detail=f"Invalid paste: {exc}")
    check = await get_team_validator(request).validate(body.paste, body.format)
    return TeamValidateResponse(ok=check.ok, detail=check.to_detail("Team"))


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: int, request: Request) -> TeamResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        team = session.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        if not team.is_public:
            user = require_current_user(request)
            if team.owner_id != user.id:
                raise HTTPException(status_code=404, detail="Team not found")
        return _team_to_response(team)


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    request: Request,
    user: User = Depends(require_current_user),
) -> TeamResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        team = session.get(Team, team_id)
        if team is None or team.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Team not found")

    try:
        parse_team(body.paste)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid paste: {exc}") from exc
    if body.format:
        check = await get_team_validator(request).validate(body.paste, body.format)
        if not check.ok:
            raise HTTPException(status_code=400, detail=check.to_detail("Team")) from None

    with session_scope(factory) as session:
        team = session.get(Team, team_id)
        if team is None or team.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Team not found")
        team.name = body.name
        team.paste = body.paste
        team.format = body.format
        team.is_public = body.is_public
        session.flush()
        return _team_to_response(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    request: Request,
    user: User = Depends(require_current_user),
) -> None:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        team = session.get(Team, team_id)
        if team is None or team.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Team not found")
        session.query(Battle).filter(Battle.team1_id == team_id).update(
            {Battle.team1_id: None}, synchronize_session=False
        )
        session.query(Battle).filter(Battle.team2_id == team_id).update(
            {Battle.team2_id: None}, synchronize_session=False
        )
        session.query(Simulation).filter(Simulation.team_a_id == team_id).update(
            {Simulation.team_a_id: None}, synchronize_session=False
        )
        session.query(Simulation).filter(Simulation.team_b_id == team_id).update(
            {Simulation.team_b_id: None}, synchronize_session=False
        )
        session.delete(team)
