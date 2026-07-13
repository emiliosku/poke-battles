"""Private replay, download, and share-link routes."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from html import escape
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from pokeapi.auth import require_current_user, token_hash
from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Replay, ReplayAnnotation, ReplayShare, ReplayStudy, User
from pokeapi.schemas import (
    ReplayAnnotationCreate,
    ReplayAnnotationResponse,
    ReplayAnnotationUpdate,
    ReplayKeyMoment,
    ReplayListResponse,
    ReplayParticipant,
    ReplayRationale,
    ReplayResponse,
    ReplayShareCreate,
    ReplayShareResponse,
    ReplayStudyResponse,
    ReplayTagsUpdate,
    ReplayTeamMember,
    ReplayTeamSnapshot,
)
from pokeapi.settings import get_settings

router = APIRouter(prefix="/replays", tags=["replays"])


@router.get("", response_model=ReplayListResponse)
async def list_replays(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = None,
    format: str | None = None,
    outcome: str | None = None,
    source: str | None = None,
    participant: str | None = None,
    sort: Literal["newest", "oldest", "shortest", "longest"] = "newest",
    user: User = Depends(require_current_user),
) -> ReplayListResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        rows = (
            session.query(Battle, Replay)
            .outerjoin(Replay, Replay.battle_id == Battle.id)
            .filter(Battle.owner_id == user.id)
            .all()
        )
        filtered = [
            (battle, replay)
            for battle, replay in rows
            if _matches_filters(battle, replay, search, format, outcome, source, participant)
        ]
        _sort_rows(filtered, sort)
        total = len(filtered)
        start = (page - 1) * page_size
        page_rows = filtered[start : start + page_size]
        studies, annotations = _private_study_data(
            session, user.id, [battle.id for battle, _ in page_rows]
        )
        return ReplayListResponse(
            items=[
                _to_response(
                    battle,
                    replay,
                    study=studies.get(battle.id),
                    annotations=annotations.get(battle.id, []),
                )
                for battle, replay in page_rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )


@router.post("/{battle_id}/favorite", response_model=ReplayStudyResponse)
async def toggle_replay_favorite(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayStudyResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _owned_battle_and_replay(session, battle_id, user.id)
        study = _study_for(session, battle_id, user.id)
        study.is_favorite = not study.is_favorite
        return _study_response(study)


@router.put("/{battle_id}/tags", response_model=ReplayStudyResponse)
async def set_replay_tags(
    battle_id: str,
    body: ReplayTagsUpdate,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayStudyResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _owned_battle_and_replay(session, battle_id, user.id)
        study = _study_for(session, battle_id, user.id)
        study.tags = body.tags
        return _study_response(study)


@router.get("/{battle_id}/annotations", response_model=list[ReplayAnnotationResponse])
async def list_replay_annotations(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> list[ReplayAnnotationResponse]:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _, replay = _owned_battle_and_replay(session, battle_id, user.id)
        _require_available_replay(replay)
        return _annotations_for_battle(session, battle_id, user.id)


@router.post("/{battle_id}/annotations", response_model=ReplayAnnotationResponse)
async def create_replay_annotation(
    battle_id: str,
    body: ReplayAnnotationCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayAnnotationResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _, replay = _owned_battle_and_replay(session, battle_id, user.id)
        replay = _require_available_replay(replay)
        _validate_annotation_location(replay, body.turn, body.event_index)
        annotation = ReplayAnnotation(
            battle_id=battle_id,
            owner_id=user.id,
            turn=body.turn,
            event_index=body.event_index,
            title=body.title,
            note=body.note,
            is_highlight=body.is_highlight,
            is_shared=body.is_shared,
        )
        session.add(annotation)
        session.flush()
        return _annotation_response(annotation)


@router.patch("/{battle_id}/annotations/{annotation_id}", response_model=ReplayAnnotationResponse)
async def update_replay_annotation(
    battle_id: str,
    annotation_id: int,
    body: ReplayAnnotationUpdate,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayAnnotationResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _, replay = _owned_battle_and_replay(session, battle_id, user.id)
        replay = _require_available_replay(replay)
        annotation = (
            session.query(ReplayAnnotation)
            .filter_by(id=annotation_id, battle_id=battle_id, owner_id=user.id)
            .first()
        )
        if annotation is None:
            raise HTTPException(status_code=404, detail="Replay annotation not found")
        values = body.model_dump(exclude_unset=True)
        turn = values.get("turn", annotation.turn)
        event_index = values.get("event_index", annotation.event_index)
        if turn is None and event_index is None:
            raise HTTPException(status_code=422, detail="turn or event_index is required")
        _validate_annotation_location(replay, turn, event_index)
        for field, value in values.items():
            setattr(annotation, field, value)
        return _annotation_response(annotation)


@router.delete("/{battle_id}/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_replay_annotation(
    battle_id: str,
    annotation_id: int,
    request: Request,
    user: User = Depends(require_current_user),
) -> None:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _owned_battle_and_replay(session, battle_id, user.id)
        annotation = (
            session.query(ReplayAnnotation)
            .filter_by(id=annotation_id, battle_id=battle_id, owner_id=user.id)
            .first()
        )
        if annotation is None:
            raise HTTPException(status_code=404, detail="Replay annotation not found")
        session.delete(annotation)


@router.post("/{battle_id}/share", response_model=ReplayShareResponse)
async def create_share_link(
    battle_id: str,
    body: ReplayShareCreate,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayShareResponse:
    factory = request.app.state.session_factory
    token = secrets.token_urlsafe(32)
    with session_scope(factory) as session:
        battle, replay = _owned_battle_and_replay(session, battle_id, user.id)
        if replay is None:
            raise HTTPException(status_code=409, detail="Replay is unavailable")
        share = session.get(ReplayShare, battle.id)
        if share is None:
            share = ReplayShare(
                battle_id=battle.id,
                token_hash=token_hash(token),
                scope=body.scope,
                revoked_at=None,
            )
            session.add(share)
        else:
            share.token_hash = token_hash(token)
            share.scope = body.scope
            share.created_at = datetime.now(UTC)
            share.revoked_at = None
        return ReplayShareResponse(battle_id=battle.id, token=token, scope=body.scope)


@router.delete("/{battle_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share_link(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> None:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _owned_battle_and_replay(session, battle_id, user.id)
        share = session.get(ReplayShare, battle_id)
        if share is not None:
            share.revoked_at = datetime.now(UTC)


@router.get("/share/{token}", response_model=ReplayResponse)
async def get_shared_replay(token: str, request: Request) -> ReplayResponse | JSONResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        share = session.query(ReplayShare).filter_by(token_hash=token_hash(token)).first()
        if share is None or share.revoked_at is not None:
            raise HTTPException(status_code=404, detail="Shared replay not found")
        battle = session.get(Battle, share.battle_id)
        replay = session.get(Replay, share.battle_id)
        if battle is None or replay is None:
            raise HTTPException(status_code=404, detail="Shared replay not found")
        annotations = _shared_annotations(
            session, battle.id, battle.owner_id, share.scope == "standard"
        )
        response = _to_response(
            battle,
            replay,
            include_raw=share.scope == "full_study",
            public=share.scope != "full_study",
            annotations=annotations,
            include_study=False,
        )
        return JSONResponse(response.model_dump(mode="json", exclude={"is_favorite", "tags"}))


@router.get("/share/{token}/preview", response_class=HTMLResponse, include_in_schema=False)
async def preview_shared_replay(token: str, request: Request) -> HTMLResponse:
    """Serve crawler-readable, spoiler-free metadata before opening the SPA player."""
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        share = session.query(ReplayShare).filter_by(token_hash=token_hash(token)).first()
        if share is None or share.revoked_at is not None:
            raise HTTPException(status_code=404, detail="Shared replay not found")
        battle = session.get(Battle, share.battle_id)
        replay = session.get(Replay, share.battle_id)
        if battle is None or replay is None:
            raise HTTPException(status_code=404, detail="Shared replay not found")
        target = f"{get_settings().frontend_base_url.rstrip('/')}/shared/{token}"
        turns = (
            battle.turns
            if battle.turns is not None
            else _summary_int(replay.summary_json or {}, "turns")
        )
        title = f"Poké Battles replay · {battle.format}"
        description = (
            f"{battle.player1_username} ({battle.model1}) vs "
            f"{battle.player2_username} ({battle.model2}) · {turns if turns is not None else '?'} turns"
        )
        return HTMLResponse(
            "<!doctype html><html><head>"
            f"<title>{escape(title)}</title>"
            '<meta name="robots" content="noindex,nofollow">'
            f'<meta name="description" content="{escape(description, quote=True)}">'
            f'<meta property="og:title" content="{escape(title, quote=True)}">'
            f'<meta property="og:description" content="{escape(description, quote=True)}">'
            '<meta property="og:type" content="website">'
            f'<meta http-equiv="refresh" content="0;url={escape(target, quote=True)}">'
            "</head><body>Opening shared replay...</body></html>"
        )


@router.get("/{battle_id}.log", response_class=PlainTextResponse)
async def download_replay_log(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> PlainTextResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _, replay = _owned_battle_and_replay(session, battle_id, user.id)
        if replay is None:
            raise HTTPException(status_code=404, detail="Replay is unavailable")
        return PlainTextResponse(
            replay.raw_log or "",
            headers={"Content-Disposition": f'attachment; filename="{battle_id}.log"'},
        )


@router.get("/{battle_id}.json")
async def download_replay_json(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> JSONResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        battle, replay = _owned_battle_and_replay(session, battle_id, user.id)
        if replay is None:
            raise HTTPException(status_code=404, detail="Replay is unavailable")
        studies, annotations = _private_study_data(session, user.id, [battle_id])
        response = _to_response(
            battle,
            replay,
            include_raw=True,
            study=studies.get(battle_id),
            annotations=annotations.get(battle_id, []),
        )
        return JSONResponse(
            response.model_dump(mode="json"),
            headers={"Content-Disposition": f'attachment; filename="{battle_id}.json"'},
        )


@router.delete("/{battle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_replay(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> None:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        _, replay = _owned_battle_and_replay(session, battle_id, user.id)
        if replay is None:
            raise HTTPException(status_code=404, detail="Replay not found")
        share = session.get(ReplayShare, battle_id)
        if share is not None:
            session.delete(share)
        session.query(ReplayAnnotation).filter_by(battle_id=battle_id, owner_id=user.id).delete()
        session.query(ReplayStudy).filter_by(battle_id=battle_id, owner_id=user.id).delete()
        session.delete(replay)


@router.get("/{battle_id}", response_model=ReplayResponse)
async def get_replay(
    battle_id: str,
    request: Request,
    user: User = Depends(require_current_user),
) -> ReplayResponse:
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        battle, replay = _owned_battle_and_replay(session, battle_id, user.id)
        studies, annotations = _private_study_data(session, user.id, [battle_id])
        return _to_response(
            battle,
            replay,
            study=studies.get(battle_id),
            annotations=annotations.get(battle_id, []),
        )


def _owned_battle_and_replay(
    session: Session, battle_id: str, user_id: str
) -> tuple[Battle, Replay | None]:
    battle = session.get(Battle, battle_id)
    if battle is None or battle.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Replay not found")
    return battle, session.get(Replay, battle_id)


def _require_available_replay(replay: Replay | None) -> Replay:
    if replay is None:
        raise HTTPException(status_code=409, detail="Replay is unavailable")
    return replay


def _study_for(session: Session, battle_id: str, user_id: str) -> ReplayStudy:
    study = session.get(ReplayStudy, {"battle_id": battle_id, "owner_id": user_id})
    if study is None:
        study = ReplayStudy(battle_id=battle_id, owner_id=user_id, tags=[])
        session.add(study)
    return study


def _study_response(study: ReplayStudy | None) -> ReplayStudyResponse:
    if study is None:
        return ReplayStudyResponse(is_favorite=False, tags=[])
    return ReplayStudyResponse(is_favorite=study.is_favorite, tags=list(study.tags or []))


def _private_study_data(
    session: Session, user_id: str, battle_ids: list[str]
) -> tuple[dict[str, ReplayStudy], dict[str, list[ReplayAnnotationResponse]]]:
    if not battle_ids:
        return {}, {}
    studies = (
        session.query(ReplayStudy)
        .filter(ReplayStudy.owner_id == user_id, ReplayStudy.battle_id.in_(battle_ids))
        .all()
    )
    annotations = (
        session.query(ReplayAnnotation)
        .filter(ReplayAnnotation.owner_id == user_id, ReplayAnnotation.battle_id.in_(battle_ids))
        .order_by(ReplayAnnotation.id)
        .all()
    )
    annotations_by_battle: dict[str, list[ReplayAnnotationResponse]] = {}
    for annotation in annotations:
        annotations_by_battle.setdefault(annotation.battle_id, []).append(
            _annotation_response(annotation)
        )
    return {study.battle_id: study for study in studies}, annotations_by_battle


def _annotations_for_battle(
    session: Session, battle_id: str, user_id: str
) -> list[ReplayAnnotationResponse]:
    annotations = (
        session.query(ReplayAnnotation)
        .filter_by(battle_id=battle_id, owner_id=user_id)
        .order_by(ReplayAnnotation.id)
        .all()
    )
    return [_annotation_response(annotation) for annotation in annotations]


def _shared_annotations(
    session: Session, battle_id: str, owner_id: str | None, standard_scope: bool
) -> list[ReplayAnnotationResponse]:
    if owner_id is None:
        return []
    query = session.query(ReplayAnnotation).filter_by(battle_id=battle_id, owner_id=owner_id)
    if standard_scope:
        query = query.filter(ReplayAnnotation.is_shared.is_(True))
    return [
        _annotation_response(annotation) for annotation in query.order_by(ReplayAnnotation.id).all()
    ]


def _annotation_response(annotation: ReplayAnnotation) -> ReplayAnnotationResponse:
    return ReplayAnnotationResponse.model_validate(annotation)


def _validate_annotation_location(
    replay: Replay, turn: int | None, event_index: int | None
) -> None:
    if event_index is None:
        return
    events = replay.events or []
    if event_index >= len(events):
        raise HTTPException(
            status_code=422, detail="event_index is outside the replay event stream"
        )
    event_turn = events[event_index].get("turn")
    if turn is not None and type(event_turn) is int and event_turn != turn:
        raise HTTPException(status_code=422, detail="turn does not match event_index")


def _to_response(
    battle: Battle,
    replay: Replay | None,
    *,
    include_raw: bool = True,
    public: bool = False,
    study: ReplayStudy | None = None,
    annotations: list[ReplayAnnotationResponse] | None = None,
    include_study: bool = True,
) -> ReplayResponse:
    study_data = _study_response(study) if include_study else None
    response_annotations = annotations or []
    if replay is None:
        return ReplayResponse(
            battle_id=battle.id,
            format=battle.format,
            source=battle.source,
            status=battle.status,
            winner=battle.winner,
            player1=ReplayParticipant(username=battle.player1_username, model=battle.model1),
            player2=ReplayParticipant(username=battle.player2_username, model=battle.model2),
            created_at=battle.created_at,
            finished_at=battle.finished_at,
            availability="unavailable",
            legacy=False,
            duration_s=_duration(battle),
            turns=battle.turns,
            is_favorite=study_data.is_favorite if study_data is not None else None,
            tags=study_data.tags if study_data is not None else None,
            annotations=response_annotations,
            rationales=[],
        )

    summary = replay.summary_json or {}
    source = "practice" if summary.get("practice") else battle.source or "battle"
    snapshots_missing = battle.team1_snapshot is None and battle.team2_snapshot is None
    return ReplayResponse(
        battle_id=battle.id,
        format=battle.format,
        source=source,
        status=battle.status,
        winner=battle.winner,
        player1=ReplayParticipant(username=battle.player1_username, model=battle.model1),
        player2=ReplayParticipant(username=battle.player2_username, model=battle.model2),
        created_at=battle.created_at,
        finished_at=battle.finished_at,
        team1_snapshot=_team_snapshot(battle.team1_snapshot, public),
        team2_snapshot=_team_snapshot(battle.team2_snapshot, public),
        availability="available",
        legacy=snapshots_missing,
        events=replay.events or [],
        raw_log=replay.raw_log if include_raw else None,
        duration_s=_duration(battle, summary),
        turns=battle.turns if battle.turns is not None else _summary_int(summary, "turns"),
        is_favorite=study_data.is_favorite if study_data is not None else None,
        tags=study_data.tags if study_data is not None else None,
        annotations=response_annotations,
        key_moments=_key_moments(replay.events or []),
        rationales=_rationales(summary),
    )


def _rationales(summary: dict[str, object]) -> list[ReplayRationale]:
    values = summary.get("rationales")
    if not isinstance(values, list):
        return []
    rationales: list[ReplayRationale] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        turn = value.get("turn")
        model = value.get("model")
        action = value.get("action")
        commentary = value.get("commentary")
        target = value.get("target")
        if (
            not isinstance(turn, int)
            or not isinstance(model, str)
            or not isinstance(action, str)
            or not isinstance(commentary, str)
        ):
            continue
        rationales.append(
            ReplayRationale(
                turn=turn,
                model=model,
                action=action,
                target=target if isinstance(target, str) else None,
                commentary=commentary,
            )
        )
    return rationales


def _key_moments(events: list[dict[str, object]]) -> list[ReplayKeyMoment]:
    moment_kinds = {
        "faint",
        "status",
        "weather_start",
        "weather_end",
        "field_start",
        "field_end",
    }
    moments: list[ReplayKeyMoment] = []
    saw_faint = False
    for event_index, event in enumerate(events):
        kind = event.get("kind")
        turn = event.get("turn")
        if kind not in moment_kinds or type(turn) is not int:
            continue
        is_first_faint = kind == "faint" and not saw_faint
        if is_first_faint:
            saw_faint = True
        target = event.get("target")
        detail = event.get("detail")
        moments.append(
            ReplayKeyMoment(
                turn=turn,
                event_index=event_index,
                kind=kind,
                target=target if isinstance(target, str) else None,
                detail=detail if isinstance(detail, str) else None,
                is_first_faint=is_first_faint,
            )
        )
    return moments


def _team_snapshot(snapshot: dict[str, object] | None, public: bool) -> ReplayTeamSnapshot | None:
    if snapshot is None:
        return None
    roster_value = snapshot.get("roster")
    roster = (
        [
            ReplayTeamMember(
                species=str(member["species"]),
                species_id=str(member["species_id"]),
                sprite_id=str(member["sprite_id"]),
            )
            for member in roster_value
            if isinstance(member, dict)
            and all(key in member for key in ("species", "species_id", "sprite_id"))
        ]
        if isinstance(roster_value, list)
        else []
    )
    name = None if public else snapshot.get("name")
    paste = None if public else snapshot.get("paste")
    return ReplayTeamSnapshot(
        name=str(name) if isinstance(name, str) else None,
        roster=roster,
        paste=str(paste) if isinstance(paste, str) else None,
    )


def _duration(battle: Battle, summary: dict[str, object] | None = None) -> float | None:
    if battle.duration_s is not None:
        return battle.duration_s
    if battle.started_at is not None and battle.finished_at is not None:
        return (battle.finished_at - battle.started_at).total_seconds()
    if summary is not None:
        duration = summary.get("duration_s")
        if isinstance(duration, int | float):
            return float(duration)
    return None


def _summary_int(summary: dict[str, object], key: str) -> int | None:
    value = summary.get(key)
    return int(value) if isinstance(value, int | float) else None


def _matches_filters(
    battle: Battle,
    replay: Replay | None,
    search: str | None,
    format: str | None,
    outcome: str | None,
    source: str | None,
    participant: str | None,
) -> bool:
    summary = replay.summary_json if replay is not None and replay.summary_json is not None else {}
    row_source = "practice" if summary.get("practice") else battle.source or "battle"
    if format is not None and battle.format != format:
        return False
    if source is not None and row_source != source:
        return False
    if participant is not None and participant not in {
        battle.player1_username,
        battle.player2_username,
    }:
        return False
    if outcome is not None:
        if outcome == "draw":
            if battle.winner is not None:
                return False
        elif battle.winner != outcome:
            return False
    if search is None or not search.strip():
        return True
    needle = search.casefold()
    values = [
        battle.player1_username,
        battle.player2_username,
        battle.model1,
        battle.model2,
        battle.format,
    ]
    values.extend(_snapshot_names(battle.team1_snapshot))
    values.extend(_snapshot_names(battle.team2_snapshot))
    return any(needle in value.casefold() for value in values)


def _snapshot_names(snapshot: dict[str, object] | None) -> list[str]:
    if snapshot is None:
        return []
    name = snapshot.get("name")
    return [name] if isinstance(name, str) else []


def _sort_rows(rows: list[tuple[Battle, Replay | None]], sort: str) -> None:
    if sort == "oldest":
        rows.sort(key=lambda row: row[0].created_at)
    elif sort == "shortest":
        rows.sort(
            key=lambda row: (
                _duration(row[0], row[1].summary_json if row[1] else {}) is None,
                _duration(row[0], row[1].summary_json if row[1] else {}) or 0.0,
            )
        )
    elif sort == "longest":
        rows.sort(
            key=lambda row: (
                _duration(row[0], row[1].summary_json if row[1] else {}) is not None,
                _duration(row[0], row[1].summary_json if row[1] else {}) or 0.0,
            ),
            reverse=True,
        )
    else:
        rows.sort(key=lambda row: row[0].created_at, reverse=True)
