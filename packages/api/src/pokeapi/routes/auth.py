"""Authentication routes for direct Google/GitHub OAuth."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from pokeapi.auth import (
    Provider,
    authorize_url,
    build_state,
    create_session,
    delete_session,
    fetch_oauth_profile,
    optional_current_user,
    provider_configured,
    upsert_user,
    verify_state,
)
from pokeapi.db import session_scope
from pokeapi.schemas import AuthMeResponse, UserResponse
from pokeapi.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user_id: str, display_name: str | None, avatar_url: str | None) -> UserResponse:
    return UserResponse(id=user_id, display_name=display_name, avatar_url=avatar_url)


@router.get("/providers")
async def providers() -> dict[str, bool]:
    return {
        "github": provider_configured("github"),
        "google": provider_configured("google"),
    }


@router.get("/me", response_model=AuthMeResponse)
async def me(request: Request) -> AuthMeResponse:
    user = optional_current_user(request)
    if user is None:
        return AuthMeResponse(authenticated=False)
    return AuthMeResponse(
        authenticated=True,
        user=_user_response(user.id, user.display_name, user.avatar_url),
    )


@router.get("/{provider}/login")
async def login(provider: Provider) -> RedirectResponse:
    state = build_state()
    response = RedirectResponse(authorize_url(provider, state))
    response.set_cookie(
        "poke_battles_oauth_state",
        state,
        path="/",
        httponly=True,
        secure=get_settings().external_base_url.startswith("https://"),
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/{provider}/callback")
async def callback(
    provider: Provider,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if error:
        raise HTTPException(status_code=401, detail=error)
    stored_state = request.cookies.get("poke_battles_oauth_state")
    if (
        not code
        or not state
        or not stored_state
        or state != stored_state
        or not verify_state(state)
    ):
        raise HTTPException(status_code=401, detail="Invalid OAuth state")

    profile = await fetch_oauth_profile(provider, code, settings)
    factory = request.app.state.session_factory
    with session_scope(factory) as session:
        user = upsert_user(session, profile)
        session_token = create_session(session, user.id, settings)

    response = RedirectResponse(settings.frontend_base_url.rstrip("/") + "/")
    response.delete_cookie("poke_battles_oauth_state", path="/")
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        path="/",
        httponly=True,
        secure=settings.external_base_url.startswith("https://"),
        samesite="lax",
        max_age=settings.session_days * 24 * 60 * 60,
    )
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        factory = request.app.state.session_factory
        with session_scope(factory) as session:
            delete_session(session, token)
    response.delete_cookie(settings.session_cookie_name, path="/")


__all__ = ["router"]
