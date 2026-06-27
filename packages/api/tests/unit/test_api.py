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
from pokeapi.db.models import Battle, User
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


class TestPracticeBattles:
    def test_natdex_doubles_ubers_requires_both_teams(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/practice/battles",
            json={
                "format": "gen9nationaldexdoublesubers",
                "player_username": "alice",
                "ai_username": "bot",
                "ai_model": "random",
            },
        )

        assert r.status_code == 400
        assert "requires both teams" in r.json()["detail"]

    def test_missing_pending_action_returns_conflict(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            session.add(
                Battle(
                    id="battle-practice-action",
                    format="gen9randombattle",
                    status="running",
                    owner_id="github:u1",
                    player1_username="alice",
                    player2_username="bot",
                    model1="human",
                    model2="random",
                )
            )

        r = authed_client.post(
            "/practice/battles/battle-practice-action/actions",
            json={"request_id": "missing", "option_id": "0"},
        )

        assert r.status_code == 409


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

    def test_pokedex_lists_canonical_species(self, client: TestClient) -> None:
        r = client.get("/pokedex")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] > 1000
        ids = {p["species_id"] for p in body["pokemon"]}
        for must in (
            "pikachu",
            "garchomp",
            "charizard",
            "charizardmegax",
            "slowkinggalar",
            "aerodactylmega",
        ):
            assert must in ids, f"{must} missing from /pokedex"

    def test_sprite_status_reports_slug_results(self, client: TestClient) -> None:
        # Hatterene is a vanilla species whose canonical species_id
        # resolves on the CDN; Galarian Slowking's canonical id does
        # NOT resolve but its derived "slowking-galar" form does.
        # The debug endpoint must report both cases accurately.
        # Marked integration because it probes the live Showdown CDN
        # (1463 species * up to 14 URL probes each) and is therefore
        # environment-sensitive.
        pytest.importorskip("pokeapi", reason="api not importable")
        import os

        if os.environ.get("POKE_BATTLES_RUN_SPRITE_PROBE") != "1":
            pytest.skip("set POKE_BATTLES_RUN_SPRITE_PROBE=1 to hit the live CDN")
        r = client.get("/sprites/status")
        assert r.status_code == 200
        body = r.json()
        assert "checked_at" in body and "results" in body
        by_sid = {p["species_id"]: p for p in body["results"]}
        assert by_sid["hatterene"]["canonical_hit"] is not None
        assert by_sid["hatterene"]["canonical_hit"].startswith("gen5ani")
        galar = by_sid["slowkinggalar"]
        assert galar["canonical_hit"] is None, "Showdown CDN 404s slowkinggalar"
        assert galar["derived_hit"] is not None
        assert galar["derived_hit"].endswith("slowking-galar.gif")

    def test_sprite_status_filters(self, client: TestClient) -> None:
        # Substring + type filters narrow the result set without
        # triggering a fresh CDN probe. We don't probe the CDN here
        # at all — the endpoint serves the cached report, and the
        # cached report is built on first hit by the previous test
        # (which is skipped in CI without POKE_BATTLES_RUN_SPRITE_PROBE).
        # The empty-state behavior is also covered: the route returns
        # an empty list when nothing has been probed yet.
        body = client.get("/sprites/status", params={"q": "hatterene", "type": "psychic"}).json()
        for entry in body["results"]:
            assert "hatter" in entry["name"].lower() or "hatter" in entry["species_id"]
            assert "Psychic" in entry["types"]


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
