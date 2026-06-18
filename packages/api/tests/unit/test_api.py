"""Unit tests for the FastAPI app via TestClient."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pokeapi.settings as settings_module
from pokeapi.auth import create_session
from pokeapi.db import session_scope
from pokeapi.db.models import User
from pokeapi.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SESSION_SECRET"] = "test-session-secret"  # noqa: S105
    settings_module._settings = None
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed_client(client: TestClient) -> TestClient:
    factory = client.app.state.session_factory
    with session_scope(factory) as session:
        user = User(id="github:u1", display_name="Alice", avatar_url="https://example.test/a.png")
        session.add(user)
        token = create_session(session, user.id)
    client.cookies.set("poke_battles_session", token)
    return client


class TestHealth:
    def test_health(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"

    def test_root(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"


class TestTeams:
    def test_requires_auth(self, client: TestClient) -> None:
        r = client.get("/teams")
        assert r.status_code == 401

    def test_create_and_get(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/teams",
            json={
                "name": "My team",
                "paste": (
                    "Garchomp @ Choice Scarf\n"
                    "Ability: Rough Skin\n"
                    "EVs: 252 Atk / 4 SpD / 252 Spe\n"
                    "Jolly Nature\n"
                    "- Earthquake\n"
                    "- Outrage\n"
                    "- Stone Edge\n"
                    "- Stealth Rock\n"
                ),
                "format": "gen9ou",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        team_id = body["id"]
        assert body["name"] == "My team"
        assert body["pokemon_count"] == 1

        r2 = authed_client.get(f"/teams/{team_id}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "My team"

    def test_create_invalid_paste(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/teams",
            json={"name": "bad", "paste": "not a team"},
        )
        assert r.status_code == 400
        assert "Invalid paste" in r.json()["detail"]

    def test_get_missing(self, client: TestClient) -> None:
        r = client.get("/teams/9999")
        assert r.status_code == 404


class TestBattles:
    def test_create_battle(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/battles",
            json={
                "format": "gen9randombattle",
                "player1": {"model_name": "random", "username": "alice"},
                "player2": {"model_name": "random", "username": "bob"},
            },
        )
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert body["format"] == "gen9randombattle"


class TestSimulations:
    def test_create_round_robin(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/simulations",
            json={
                "mode": "round_robin",
                "models": ["random", "random"],
                "n_battles": 4,
            },
        )
        assert r.status_code == 202
        assert r.json()["status"] == "queued"

    def test_invalid_mode(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/simulations",
            json={"mode": "invalid", "n_battles": 10},
        )
        assert r.status_code == 400


class TestMeta:
    def test_formats_and_models(self, client: TestClient) -> None:
        formats = client.get("/formats")
        assert formats.status_code == 200
        format_map = {fmt["id"]: fmt for fmt in formats.json()}
        assert "gen9randombattle" in format_map
        natdex_doubles_ubers = format_map["gen9nationaldexdoublesubers"]
        assert natdex_doubles_ubers["kind"] == "doubles"
        assert natdex_doubles_ubers["requires_team"] is True
        assert natdex_doubles_ubers["active_slots"] == 2

        models = client.get("/models")
        assert models.status_code == 200
        assert any(model["name"] == "random" for model in models.json())


class TestAuth:
    def test_me_anonymous(self, client: TestClient) -> None:
        r = client.get("/auth/me")
        assert r.status_code == 200
        assert r.json() == {"authenticated": False, "user": None}

    def test_me_authenticated(self, authed_client: TestClient) -> None:
        r = authed_client.get("/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["authenticated"] is True
        assert body["user"]["id"] == "github:u1"


class TestLeaderboard:
    def test_empty(self, client: TestClient) -> None:
        r = client.get("/leaderboard")
        assert r.status_code == 200
        assert r.json() == []
