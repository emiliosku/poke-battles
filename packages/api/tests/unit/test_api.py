"""Unit tests for the FastAPI app via TestClient."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import pokeapi.settings as settings_module
from pokeapi.auth import create_session
from pokeapi.db import session_scope
from pokeapi.db.models import Battle, Replay, ReplayShare, Simulation, Team, User
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


class TestReplays:
    @staticmethod
    def _add_battle(
        factory: sessionmaker[Session], *, battle_id: str, owner_id: str = "github:u1"
    ) -> None:
        with session_scope(factory) as session:
            session.add(
                Battle(
                    id=battle_id,
                    format="gen9ou",
                    status="finished",
                    owner_id=owner_id,
                    player1_username="alice",
                    player2_username="bob",
                    model1="model-a",
                    model2="model-b",
                    winner="alice",
                    team1_snapshot={
                        "name": "Private team",
                        "paste": "Garchomp @ Leftovers\n- Earthquake",
                        "roster": [
                            {
                                "species": "Garchomp",
                                "species_id": "garchomp",
                                "sprite_id": "garchomp",
                            }
                        ],
                    },
                )
            )

    def test_replay_is_private_to_owner(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        self._add_battle(factory, battle_id="private-replay")
        with session_scope(factory) as session:
            session.add(Replay(battle_id="private-replay", events=[], raw_log="", summary_json={}))
            session.add(User(id="github:u2"))
            other_token = create_session(session, "github:u2")

        authed_client.cookies.set("poke_battles_session", other_token)
        response = authed_client.get("/replays/private-replay")

        assert response.status_code == 404
        assert authed_client.get("/battles/private-replay").status_code == 404

    def test_missing_replay_is_unavailable_not_empty(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        self._add_battle(factory, battle_id="unavailable-replay")

        response = authed_client.get("/replays/unavailable-replay")

        assert response.status_code == 200, response.text
        assert response.json()["availability"] == "unavailable"
        assert response.json()["events"] is None

    def test_share_scope_projects_private_content(self, authed_client: TestClient) -> None:
        factory = authed_client.app.state.session_factory
        self._add_battle(factory, battle_id="shareable-replay")
        with session_scope(factory) as session:
            session.add(
                Replay(
                    battle_id="shareable-replay",
                    events=[{"type": "turn"}],
                    raw_log="|turn|1",
                    summary_json={
                        "rationales": [
                            {
                                "turn": 3,
                                "model": "model-a",
                                "action": "choose_move",
                                "target": "thunderbolt",
                                "commentary": "finish the weakened target",
                            }
                        ]
                    },
                )
            )

        created = authed_client.post("/replays/shareable-replay/share", json={"scope": "standard"})
        assert created.status_code == 200, created.text
        standard_token = created.json()["token"]
        with session_scope(factory) as session:
            share = session.get(ReplayShare, "shareable-replay")
            assert share is not None
            assert share.token_hash != standard_token

        standard = authed_client.get(f"/replays/share/{standard_token}")
        assert standard.status_code == 200, standard.text
        assert standard.json()["raw_log"] is None
        assert standard.json()["team1_snapshot"]["name"] is None
        assert standard.json()["team1_snapshot"]["paste"] is None
        assert standard.json()["team1_snapshot"]["roster"][0]["species_id"] == "garchomp"
        preview = authed_client.get(f"/replays/share/{standard_token}/preview")
        assert preview.status_code == 200
        assert "noindex,nofollow" in preview.text
        assert "winner" not in preview.text.casefold()

        replacement = authed_client.post(
            "/replays/shareable-replay/share", json={"scope": "full_study"}
        )
        full_token = replacement.json()["token"]
        assert authed_client.get(f"/replays/share/{standard_token}").status_code == 404
        full = authed_client.get(f"/replays/share/{full_token}")
        assert full.status_code == 200
        assert full.json()["raw_log"] == "|turn|1"
        assert full.json()["team1_snapshot"]["name"] == "Private team"
        assert full.json()["team1_snapshot"]["paste"] == "Garchomp @ Leftovers\n- Earthquake"

        revoked = authed_client.delete("/replays/shareable-replay/share")
        assert revoked.status_code == 204
        assert authed_client.get(f"/replays/share/{full_token}").status_code == 404

    def test_study_metadata_is_owner_scoped_and_tags_are_normalized(
        self, authed_client: TestClient
    ) -> None:
        factory = authed_client.app.state.session_factory
        self._add_battle(factory, battle_id="study-replay")
        with session_scope(factory) as session:
            session.add(
                Replay(
                    battle_id="study-replay",
                    events=[
                        {"kind": "faint", "turn": 2, "target": "p2a: Gastly"},
                        {"kind": "status", "turn": 3, "target": "p1a: Abra", "detail": "par"},
                        {"kind": "weather_start", "turn": 4, "detail": "RainDance"},
                        {"kind": "field_end", "turn": 5, "detail": "Trick Room"},
                        {"kind": "faint", "turn": 6, "target": "p1a: Abra"},
                    ],
                    raw_log="",
                    summary_json={
                        "rationales": [
                            {
                                "turn": 3,
                                "model": "model-a",
                                "action": "choose_move",
                                "target": "thunderbolt",
                                "commentary": "finish the weakened target",
                            }
                        ]
                    },
                )
            )

        favorite = authed_client.post("/replays/study-replay/favorite")
        assert favorite.status_code == 200, favorite.text
        assert favorite.json() == {"is_favorite": True, "tags": []}
        tags = authed_client.put(
            "/replays/study-replay/tags", json={"tags": [" Focus ", "focus", "Tempo", "  "]}
        )
        assert tags.status_code == 200, tags.text
        assert tags.json() == {"is_favorite": True, "tags": ["focus", "tempo"]}

        replay = authed_client.get("/replays/study-replay")
        assert replay.status_code == 200, replay.text
        body = replay.json()
        assert body["is_favorite"] is True
        assert body["tags"] == ["focus", "tempo"]
        assert body["rationales"] == [
            {
                "turn": 3,
                "model": "model-a",
                "action": "choose_move",
                "target": "thunderbolt",
                "commentary": "finish the weakened target",
            }
        ]
        assert body["key_moments"] == [
            {
                "turn": 2,
                "event_index": 0,
                "kind": "faint",
                "target": "p2a: Gastly",
                "detail": None,
                "is_first_faint": True,
            },
            {
                "turn": 3,
                "event_index": 1,
                "kind": "status",
                "target": "p1a: Abra",
                "detail": "par",
                "is_first_faint": False,
            },
            {
                "turn": 4,
                "event_index": 2,
                "kind": "weather_start",
                "target": None,
                "detail": "RainDance",
                "is_first_faint": False,
            },
            {
                "turn": 5,
                "event_index": 3,
                "kind": "field_end",
                "target": None,
                "detail": "Trick Room",
                "is_first_faint": False,
            },
            {
                "turn": 6,
                "event_index": 4,
                "kind": "faint",
                "target": "p1a: Abra",
                "detail": None,
                "is_first_faint": False,
            },
        ]

        with session_scope(factory) as session:
            session.add(User(id="github:u2"))
            other_token = create_session(session, "github:u2")
        authed_client.cookies.set("poke_battles_session", other_token)
        assert (
            authed_client.put("/replays/study-replay/tags", json={"tags": ["other"]}).status_code
            == 404
        )

    def test_annotations_are_owner_only_and_projected_by_share_scope(
        self, authed_client: TestClient
    ) -> None:
        factory = authed_client.app.state.session_factory
        self._add_battle(factory, battle_id="annotated-replay")
        with session_scope(factory) as session:
            session.add(
                Replay(
                    battle_id="annotated-replay",
                    events=[
                        {"kind": "turn_start", "turn": 1},
                        {"kind": "faint", "turn": 2, "target": "p2a: Gastly"},
                    ],
                    raw_log="|turn|1",
                    summary_json={},
                )
            )

        private = authed_client.post(
            "/replays/annotated-replay/annotations",
            json={
                "turn": 1,
                "event_index": 0,
                "title": " Opening ",
                "note": " private note ",
                "is_highlight": True,
            },
        )
        assert private.status_code == 200, private.text
        private_id = private.json()["id"]
        assert private.json()["title"] == "Opening"
        assert private.json()["note"] == "private note"

        shared = authed_client.post(
            "/replays/annotated-replay/annotations",
            json={
                "turn": 2,
                "event_index": 1,
                "title": "Faint",
                "note": "shared note",
                "is_highlight": True,
                "is_shared": True,
            },
        )
        assert shared.status_code == 200, shared.text
        shared_id = shared.json()["id"]
        updated = authed_client.patch(
            f"/replays/annotated-replay/annotations/{shared_id}", json={"title": "First faint"}
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["title"] == "First faint"
        assert len(authed_client.get("/replays/annotated-replay/annotations").json()) == 2

        favorite = authed_client.post("/replays/annotated-replay/favorite")
        assert favorite.status_code == 200
        assert (
            authed_client.put(
                "/replays/annotated-replay/tags", json={"tags": ["private"]}
            ).status_code
            == 200
        )
        standard_token = authed_client.post(
            "/replays/annotated-replay/share", json={"scope": "standard"}
        ).json()["token"]
        standard = authed_client.get(f"/replays/share/{standard_token}")
        assert standard.status_code == 200, standard.text
        assert [annotation["id"] for annotation in standard.json()["annotations"]] == [shared_id]
        assert "is_favorite" not in standard.json()
        assert "tags" not in standard.json()

        full_token = authed_client.post(
            "/replays/annotated-replay/share", json={"scope": "full_study"}
        ).json()["token"]
        full = authed_client.get(f"/replays/share/{full_token}")
        assert full.status_code == 200, full.text
        assert [annotation["id"] for annotation in full.json()["annotations"]] == [
            private_id,
            shared_id,
        ]
        assert "is_favorite" not in full.json()
        assert "tags" not in full.json()
        deleted = authed_client.delete(f"/replays/annotated-replay/annotations/{shared_id}")
        assert deleted.status_code == 204
        assert [
            annotation["id"]
            for annotation in authed_client.get("/replays/annotated-replay/annotations").json()
        ] == [private_id]

        with session_scope(factory) as session:
            session.add(User(id="github:u2"))
            other_token = create_session(session, "github:u2")
        authed_client.cookies.set("poke_battles_session", other_token)
        assert (
            authed_client.patch(
                f"/replays/annotated-replay/annotations/{private_id}", json={"title": "Nope"}
            ).status_code
            == 404
        )


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
