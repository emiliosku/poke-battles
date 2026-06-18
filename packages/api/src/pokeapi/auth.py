"""Direct OAuth and server-side session helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from pokeapi.db import session_scope
from pokeapi.db.models import User, UserSession
from pokeapi.settings import Settings, get_settings

Provider = Literal["github", "google"]

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sign_state(value: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    sig = hmac.new(cfg.session_secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(sig.digest()).decode("ascii").rstrip("=")


def build_state(settings: Settings | None = None) -> str:
    value = secrets.token_urlsafe(24)
    return f"{value}.{sign_state(value, settings)}"


def verify_state(state: str, settings: Settings | None = None) -> bool:
    value, sep, signature = state.partition(".")
    if not sep or not value or not signature:
        return False
    return hmac.compare_digest(signature, sign_state(value, settings))


def callback_url(provider: Provider, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    return f"{cfg.external_base_url.rstrip('/')}/auth/{provider}/callback"


def provider_configured(provider: Provider, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    if provider == "github":
        return bool(cfg.github_oauth_client_id and cfg.github_oauth_client_secret)
    return bool(cfg.google_oauth_client_id and cfg.google_oauth_client_secret)


def authorize_url(provider: Provider, state: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    if provider == "github":
        if not cfg.github_oauth_client_id:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        query = urlencode(
            {
                "client_id": cfg.github_oauth_client_id,
                "redirect_uri": callback_url("github", cfg),
                "scope": "read:user user:email",
                "state": state,
            }
        )
        return f"{GITHUB_AUTHORIZE_URL}?{query}"
    if not cfg.google_oauth_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    query = urlencode(
        {
            "client_id": cfg.google_oauth_client_id,
            "redirect_uri": callback_url("google", cfg),
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "access_type": "online",
        }
    )
    return f"{GOOGLE_AUTHORIZE_URL}?{query}"


async def fetch_oauth_profile(provider: Provider, code: str, settings: Settings) -> dict[str, str]:
    if provider == "github":
        if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
            raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")
        token_data = {
            "client_id": settings.github_oauth_client_id,
            "client_secret": settings.github_oauth_client_secret,
            "code": code,
            "redirect_uri": callback_url("github", settings),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            token_res = await client.post(
                GITHUB_TOKEN_URL,
                json=token_data,
                headers={"Accept": "application/json"},
            )
            token_res.raise_for_status()
            access_token = str(token_res.json().get("access_token", ""))
            if not access_token:
                raise HTTPException(status_code=401, detail="GitHub OAuth did not return a token")
            user_res = await client.get(
                GITHUB_USER_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            user_res.raise_for_status()
        body = user_res.json()
        return {
            "id": f"github:{body['id']}",
            "display_name": str(body.get("name") or body.get("login") or "GitHub user"),
            "avatar_url": str(body.get("avatar_url") or ""),
        }

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    token_data = {
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": callback_url("google", settings),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data=token_data)
        token_res.raise_for_status()
        access_token = str(token_res.json().get("access_token", ""))
        if not access_token:
            raise HTTPException(status_code=401, detail="Google OAuth did not return a token")
        user_res = await client.get(GOOGLE_USER_URL, headers={"Authorization": f"Bearer {access_token}"})
        user_res.raise_for_status()
    body = user_res.json()
    return {
        "id": f"google:{body['sub']}",
        "display_name": str(body.get("name") or body.get("email") or "Google user"),
        "avatar_url": str(body.get("picture") or ""),
    }


def upsert_user(session: Session, profile: dict[str, str]) -> User:
    user = session.get(User, profile["id"])
    if user is None:
        user = User(id=profile["id"])
        session.add(user)
        session.flush()
    user.display_name = profile.get("display_name") or user.display_name
    user.avatar_url = profile.get("avatar_url") or user.avatar_url
    return user


def create_session(session: Session, user_id: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    token = secrets.token_urlsafe(48)
    expires_at = utcnow() + timedelta(days=cfg.session_days)
    session.add(UserSession(token_hash=token_hash(token), user_id=user_id, expires_at=expires_at))
    return token


def delete_session(session: Session, token: str) -> None:
    record = session.query(UserSession).filter_by(token_hash=token_hash(token)).first()
    if record is not None:
        session.delete(record)


def user_for_session_token(factory: sessionmaker[Session], token: str | None) -> User | None:
    if not token:
        return None
    with session_scope(factory) as session:
        record = session.query(UserSession).filter_by(token_hash=token_hash(token)).first()
        if record is None:
            return None
        expires_at = record.expires_at
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
        if expires_at <= utcnow():
            session.delete(record)
            return None
        user = session.get(User, record.user_id)
        if user is None:
            return None
        return User(id=user.id, display_name=user.display_name, avatar_url=user.avatar_url)


def _session_token_from_request(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def optional_current_user(request: Request) -> User | None:
    factory = request.app.state.session_factory
    return user_for_session_token(factory, _session_token_from_request(request))


def require_current_user(request: Request) -> User:
    user = optional_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def safe_profile(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(raw["id"]),
        "display_name": str(raw.get("display_name") or raw["id"]),
        "avatar_url": str(raw.get("avatar_url") or ""),
    }


__all__ = [
    "Provider",
    "authorize_url",
    "build_state",
    "create_session",
    "delete_session",
    "fetch_oauth_profile",
    "optional_current_user",
    "provider_configured",
    "require_current_user",
    "safe_profile",
    "upsert_user",
    "verify_state",
]
