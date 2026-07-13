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
from pokeapi.db.models import Battle, Simulation, Team, User
from pokeapi.main import create_app
from pokeapi.services.team_validation import TeamValidationResult


class _StubTeamValidator:
    """In-memory stand-in for :class:`ShowdownTeamValidator`.

    Tests register a list of ``(paste, format) -> result`` answers before
    the request runs. The stub records the calls so tests can assert on
    what the API actually sent to the validator.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str]] = []
        self.answers: list[TeamValidationResult] = []
        self._default = TeamValidationResult(ok=True, reason="")
        self.stop_calls = 0

    async def validate(self, team_paste: str | None, battle_format: str) -> TeamValidationResult:
        self.calls.append((team_paste, battle_format))
        if self.answers:
            return self.answers.pop(0)
        return self._default

    async def stop(self) -> None:
        self.stop_calls += 1


class _StubBattleService:
    async def run_simulation(self, **_: object) -> dict[str, object]:
        return {}


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


@pytest.fixture
def stub_validator(client: TestClient) -> _StubTeamValidator:
    """Inject a stub team validator on the app so routes never hit Showdown."""
    stub = _StubTeamValidator()
    client.app.state.team_validator = stub  # type: ignore[attr-defined]
    return stub


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

    def test_create_and_get(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
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
        assert stub_validator.calls == [
            (
                body["paste"],
                "gen9ou",
            )
        ]

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

    def test_create_rejects_illegal_team_for_format(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        # Validator says "this team isn't legal for the requested format" —
        # the route must return 400 with the same Showdown message format
        # used by /battles.
        stub_validator.answers.append(
            TeamValidationResult(
                ok=False,
                reason=(
                    "Hatterene is level 50, but this format allows level 100 Pokémon. "
                    "(If this was intentional, add exactly 1 to one of your EVs, "
                    "which won't change its stats but will tell us that it wasn't a mistake)."
                ),
            )
        )
        r = authed_client.post(
            "/teams",
            json={
                "name": "VGC team",
                "paste": (
                    "Hatterene @ Life Orb\n"
                    "Ability: Magic Bounce\n"
                    "Level: 50\n"
                    "Tera Type: Psychic\n"
                    "EVs: 252 HP / 252 SpA / 4 SpD\n"
                    "Quiet Nature\n"
                    "- Expanding Force\n"
                ),
                "format": "gen9anythinggoes",
            },
        )
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        assert detail.startswith("Team rejected by Showdown:")
        assert "Hatterene is level 50" in detail

    def test_create_skips_validator_when_format_omitted(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        r = authed_client.post(
            "/teams",
            json={
                "name": "Formatless",
                "paste": (
                    "Garchomp @ Choice Scarf\n"
                    "Ability: Rough Skin\n"
                    "EVs: 252 Atk / 4 SpD / 252 Spe\n"
                    "Jolly Nature\n"
                    "- Earthquake\n"
                ),
            },
        )
        assert r.status_code == 201, r.text
        assert stub_validator.calls == []

    def test_update_team(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            team = Team(
                owner_id="github:u1",
                name="Old team",
                paste="Garchomp @ Choice Scarf\nAbility: Rough Skin\n- Earthquake",
                format="gen9ou",
                is_public=False,
            )
            session.add(team)
            session.flush()
            team_id = team.id

        new_paste = "Gengar @ Life Orb\nAbility: Cursed Body\nTimid Nature\n- Shadow Ball"
        r = authed_client.put(
            f"/teams/{team_id}",
            json={
                "name": "Edited team",
                "paste": new_paste,
                "format": "gen9anythinggoes",
                "is_public": True,
            },
        )

        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == team_id
        assert body["name"] == "Edited team"
        assert body["paste"] == new_paste
        assert body["format"] == "gen9anythinggoes"
        assert body["is_public"] is True
        assert body["pokemon_count"] == 1
        assert stub_validator.calls == [(new_paste, "gen9anythinggoes")]

    def test_update_requires_owner(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            team = Team(
                owner_id="github:other",
                name="Other team",
                paste="Garchomp @ Choice Scarf\nAbility: Rough Skin\n- Earthquake",
                format="gen9ou",
                is_public=False,
            )
            session.add(team)
            session.flush()
            team_id = team.id

        r = authed_client.put(
            f"/teams/{team_id}",
            json={
                "name": "Stolen team",
                "paste": "Gengar @ Life Orb\nAbility: Cursed Body\nTimid Nature\n- Shadow Ball",
                "format": "gen9ou",
                "is_public": True,
            },
        )

        assert r.status_code == 404

        with session_scope(factory) as session:
            team = session.get(Team, team_id)
            assert team is not None
            assert team.name == "Other team"
            assert team.is_public is False

    def test_validate_route_returns_validator_result(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        stub_validator.answers.append(TeamValidationResult(ok=True, reason=""))
        r = authed_client.post(
            "/teams/validate",
            json={
                "paste": (
                    "Garchomp @ Choice Scarf\n"
                    "Ability: Rough Skin\n"
                    "EVs: 252 Atk / 4 SpD / 252 Spe\n"
                    "Jolly Nature\n"
                    "- Earthquake\n"
                ),
                "format": "gen9ou",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["detail"] == ""
        assert stub_validator.calls == [
            (
                (
                    "Garchomp @ Choice Scarf\n"
                    "Ability: Rough Skin\n"
                    "EVs: 252 Atk / 4 SpD / 252 Spe\n"
                    "Jolly Nature\n"
                    "- Earthquake\n"
                ),
                "gen9ou",
            )
        ]

    def test_validate_route_surfaces_rejection(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        stub_validator.answers.append(
            TeamValidationResult(ok=False, reason="Aerodactyl-Mega is illegal in this format.")
        )
        r = authed_client.post(
            "/teams/validate",
            json={
                "paste": (
                    "Aerodactyl-Mega @ Aerodactylite\n"
                    "Ability: Unnerve\n"
                    "EVs: 248 HP / 252 Atk / 8 SpD\n"
                    "Adamant Nature\n"
                    "- Stone Edge\n"
                ),
                "format": "gen9ou",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "Aerodactyl-Mega is illegal" in body["detail"]

    def test_validate_route_rejects_unparseable_paste(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        r = authed_client.post(
            "/teams/validate",
            json={"paste": "garbage", "format": "gen9ou"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["detail"].startswith("Invalid paste:")
        # Validator must not be consulted when the paste doesn't even parse.
        assert stub_validator.calls == []

    def test_get_missing(self, client: TestClient) -> None:
        r = client.get("/teams/9999")
        assert r.status_code == 404

    def test_delete_clears_history_references(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            team = Team(
                owner_id="github:u1",
                name="History team",
                paste="Garchomp @ Choice Scarf\nAbility: Rough Skin\n- Earthquake",
                format="gen9ou",
                is_public=False,
            )
            session.add(team)
            session.flush()
            team_id = team.id
            session.add(
                Battle(
                    id="battle-with-team",
                    format="gen9ou",
                    status="finished",
                    player1_username="alice",
                    player2_username="bob",
                    model1="random",
                    model2="random",
                    owner_id="github:u1",
                    team1_id=team_id,
                    team2_id=team_id,
                )
            )
            session.add(
                Simulation(
                    id="sim-with-team",
                    owner_id="github:u1",
                    mode="team_vs_team",
                    format="gen9ou",
                    team_a_id=team_id,
                    team_b_id=team_id,
                    n_battles=1,
                )
            )

        r = authed_client.delete(f"/teams/{team_id}")
        assert r.status_code == 204, r.text

        with session_scope(factory) as session:
            assert session.get(Team, team_id) is None
            battle = session.get(Battle, "battle-with-team")
            assert battle is not None
            assert battle.team1_id is None
            assert battle.team2_id is None
            simulation = session.get(Simulation, "sim-with-team")
            assert simulation is not None
            assert simulation.team_a_id is None
            assert simulation.team_b_id is None


class TestBattles:
    @pytest.mark.integration
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
    @pytest.mark.integration
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

    def test_create_named_simulation_rejects_duplicate_name(
        self, authed_client: TestClient, stub_validator: _StubTeamValidator
    ) -> None:
        authed_client.app.state.bservice = _StubBattleService()
        payload = {
            "name": "Benchmark",
            "mode": "round_robin",
            "models": ["random", "random"],
            "n_battles": 4,
        }
        first = authed_client.post("/simulations", json=payload)
        second = authed_client.post("/simulations", json=payload)

        assert first.status_code == 202
        assert first.json()["name"] == "Benchmark"
        assert second.status_code == 409
        assert second.json()["detail"] == "Simulation name already exists"

    @pytest.mark.integration
    def test_create_named_simulation(self, authed_client: TestClient) -> None:
        r = authed_client.post(
            "/simulations",
            json={
                "name": "Benchmark",
                "mode": "round_robin",
                "models": ["random", "random"],
                "n_battles": 4,
            },
        )
        assert r.status_code == 202
        assert r.json()["name"] == "Benchmark"

    def test_lookup_simulation_by_name(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            session.add(
                Simulation(
                    id="sim-named",
                    owner_id="github:u1",
                    name="Benchmark",
                    mode="ladder",
                    n_battles=20,
                )
            )

        r = authed_client.get("/simulations/lookup", params={"query": "Benchmark"})

        assert r.status_code == 200
        assert r.json()["id"] == "sim-named"
        assert r.json()["name"] == "Benchmark"

    def test_lookup_does_not_return_another_users_simulation(
        self, authed_client: TestClient
    ) -> None:
        factory = authed_client.app.state.session_factory
        with session_scope(factory) as session:
            session.add(User(id="github:u2"))
            session.add(
                Simulation(
                    id="sim-private",
                    owner_id="github:u2",
                    name="Private benchmark",
                    mode="ladder",
                    n_battles=20,
                )
            )

        r = authed_client.get("/simulations/lookup", params={"query": "Private benchmark"})

        assert r.status_code == 404

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
        # The /pokedex endpoint serves the local Showdown dex file. If
        # that file isn't shipped with the engine wheel in this
        # environment, the endpoint returns an empty list — skip the
        # test rather than fail (the unit-test asset is at
        # tests/integration, the engine wheel package is a separate
        # concern).
        r = client.get("/pokedex")
        assert r.status_code == 200
        body = r.json()
        if body["count"] == 0:
            pytest.skip("Showdown dex data not bundled with this engine wheel")
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
        assert by_sid["hatterene"]["canonical_hits"]
        assert by_sid["hatterene"]["canonical_hits"][0].startswith("gen5ani")
        galar = by_sid["slowkinggalar"]
        assert galar["canonical_hits"] == [], "Showdown CDN 404s slowkinggalar"
        assert galar["derived_hits"]
        assert any(h.endswith("slowking-galar.gif") for h in galar["derived_hits"])

    def test_sprite_status_filters(self, client: TestClient) -> None:
        # Substring + type filters narrow the result set without
        # triggering a fresh CDN probe. We don't probe the CDN here
        # at all — the endpoint serves the cached report, and the
        # cached report is built on first hit by the previous test
        # (which is skipped in CI without POKE_BATTLES_RUN_SPRITE_PROBE).
        # The empty-state behavior is also covered: the route returns
        # an empty list when nothing has been probed yet.
        if os.environ.get("POKE_BATTLES_RUN_SPRITE_PROBE") != "1":
            pytest.skip("set POKE_BATTLES_RUN_SPRITE_PROBE=1 to exercise the filter test")
        body = client.get("/sprites/status", params={"q": "hatterene", "type": "psychic"}).json()
        assert body["count"] >= 1
        for entry in body["results"]:
            assert "hatter" in entry["name"].lower() or "hatter" in entry["species_id"]
            assert "Psychic" in entry["types"]


class TestSpriteStatusNonBlocking:
    """Regression: the sprite probe used to be invoked inline from an
    ``async def`` route, which froze the single-worker uvicorn event
    loop for the full ~60-80s probe. Other tabs (teams, leaderboard,
    health) would hang behind it. The fix pushes the probe into the
    default threadpool via :func:`asyncio.to_thread`. These tests
    pin that behavior without touching the live CDN.
    """

    async def test_probe_does_not_block_concurrent_requests(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio
        import threading
        import time as _time

        import httpx
        from httpx import ASGITransport

        from pokeapi.routes import sprites as sprites_route
        from pokeapi.schemas import SpriteStatusResponse
        from pokecore.sprite_status import SpriteStatusReport

        probe_delay_s = 0.4
        main_thread = threading.get_ident()
        recorded: dict[str, int | float] = {}

        def slow_stub(*, refresh: bool = False) -> SpriteStatusReport:
            _ = refresh
            recorded["thread"] = threading.get_ident()
            recorded["started"] = _time.monotonic()
            # Simulate the long CDN probe: a blocking sleep inside a
            # threadpool thread is fine; inside the event loop it
            # would freeze every other coroutine.
            import time as _t

            _t.sleep(probe_delay_s)
            return SpriteStatusReport(
                checked_at=0.0,
                count=0,
                duration_s=probe_delay_s,
                results=[],
            )

        monkeypatch.setattr(sprites_route, "get_status", slow_stub)

        # Build a fresh app *without* running the lifespan — the
        # startup warmup would otherwise hit the real CDN and dwarf
        # our timing assertions.
        db_path = tmp_path / "nonblocking.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["SESSION_SECRET"] = "test-session-secret"  # noqa: S105
        import pokeapi.settings as settings_module

        settings_module._settings = None
        from pokeapi.main import create_app

        app = create_app()

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            started = _time.monotonic()
            status_resp, health_resp = await asyncio.gather(
                ac.get("/sprites/status"),
                ac.get("/health"),
            )
            elapsed = _time.monotonic() - started

        assert status_resp.status_code == 200, status_resp.text
        assert health_resp.status_code == 200, health_resp.text
        # Both routes share a single event loop. If the probe ran
        # inline, total time would be >= probe_delay_s + health cost
        # (serialized). With asyncio.to_thread, the health request
        # piggybacks on the probe and we stay comfortably under 2x.
        assert elapsed < probe_delay_s * 2, (
            f"event loop appears blocked: {elapsed:.3f}s for "
            f"probe={probe_delay_s}s + concurrent /health"
        )
        # The probe should have run on a worker thread, not the
        # asyncio thread that drove the request.
        assert recorded["thread"] != main_thread, (
            "get_status ran on the asyncio thread; asyncio.to_thread missing"
        )
        # Sanity: the response shape is the documented schema.
        body = SpriteStatusResponse.model_validate(status_resp.json())
        assert body.results == []


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
