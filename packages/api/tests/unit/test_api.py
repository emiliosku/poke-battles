"""Unit tests for the FastAPI app via TestClient."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pokeapi.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    app = create_app()
    with TestClient(app) as c:
        yield c


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
    def test_create_and_get(self, client: TestClient) -> None:
        r = client.post(
            "/teams?owner_id=u1",
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

        r2 = client.get(f"/teams/{team_id}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "My team"

    def test_create_invalid_paste(self, client: TestClient) -> None:
        r = client.post(
            "/teams?owner_id=u1",
            json={"name": "bad", "paste": "not a team"},
        )
        assert r.status_code == 400
        assert "Invalid paste" in r.json()["detail"]

    def test_get_missing(self, client: TestClient) -> None:
        r = client.get("/teams/9999")
        assert r.status_code == 404


class TestBattles:
    def test_create_battle(self, client: TestClient) -> None:
        r = client.post(
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
    def test_create_round_robin(self, client: TestClient) -> None:
        r = client.post(
            "/simulations",
            json={
                "mode": "round_robin",
                "models": ["random", "random"],
                "n_battles": 4,
            },
        )
        assert r.status_code == 202
        assert r.json()["status"] == "queued"

    def test_invalid_mode(self, client: TestClient) -> None:
        r = client.post(
            "/simulations",
            json={"mode": "invalid", "n_battles": 10},
        )
        assert r.status_code == 400


class TestLeaderboard:
    def test_empty(self, client: TestClient) -> None:
        r = client.get("/leaderboard")
        assert r.status_code == 200
        assert r.json() == []
