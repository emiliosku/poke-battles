"""Unit tests for pokeapi.db (in-memory SQLite)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, StaticPool, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from pokeapi.db import init_db
from pokeapi.db.models import Base, Battle, Rating, Simulation, Team, Tournament, User


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()


class TestUser:
    def test_create_user(self, session: Session) -> None:
        u = User(id="u1", display_name="Alice")
        session.add(u)
        session.flush()
        assert session.get(User, "u1") is not None

    def test_user_default_timestamps(self, session: Session) -> None:
        u = User(id="u1")
        session.add(u)
        session.flush()
        assert u.created_at is not None


class TestTeam:
    def test_create_team(self, session: Session) -> None:
        u = User(id="u1")
        session.add(u)
        session.flush()
        t = Team(
            owner_id="u1",
            name="My team",
            paste="Garchomp @ Scarf\nAbility: Rough Skin\n- Earthquake",
            format="gen9ou",
            is_public=True,
        )
        session.add(t)
        session.flush()
        assert t.id is not None
        assert session.get(Team, t.id) is not None


class TestBattle:
    def test_status_columns_allow_practice_terminal_statuses(self) -> None:
        assert Battle.__table__.c.status.type.length >= len("user_timeout_loss")
        assert Simulation.__table__.c.status.type.length >= len("user_timeout_loss")
        assert Tournament.__table__.c.status.type.length >= len("user_timeout_loss")

    def test_create_battle(self, session: Session) -> None:
        b = Battle(
            id="battle-1",
            format="gen9randombattle",
            status="pending",
            player1_username="alice",
            player2_username="bob",
            model1="random",
            model2="random",
        )
        session.add(b)
        session.flush()
        assert session.get(Battle, "battle-1") is not None

    def test_battle_status_transitions(self, session: Session) -> None:
        b = Battle(
            id="battle-1",
            format="gen9randombattle",
            status="queued",
            player1_username="alice",
            player2_username="bob",
            model1="random",
            model2="random",
        )
        session.add(b)
        session.flush()
        b.status = "running"
        b.winner = "alice"
        b.turns = 42
        session.flush()
        fetched = session.get(Battle, "battle-1")
        assert fetched is not None
        assert fetched.winner == "alice"
        assert fetched.turns == 42


class TestSimulation:
    def test_name_is_unique_per_owner(self, session: Session) -> None:
        session.add(User(id="u1"))
        session.add_all(
            [
                Simulation(
                    id="sim-1", owner_id="u1", name="benchmark", mode="ladder", n_battles=20
                ),
                Simulation(
                    id="sim-2", owner_id="u1", name="benchmark", mode="ladder", n_battles=20
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            session.flush()

    def test_init_db_adds_name_to_existing_simulations_table(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE simulations ("
                        "id VARCHAR(64) PRIMARY KEY, owner_id VARCHAR(64), mode VARCHAR(32), "
                        "format VARCHAR(64), n_battles INTEGER, status VARCHAR(32)"
                        ")"
                    )
                )

            init_db(engine)

            columns = {column["name"] for column in inspect(engine).get_columns("simulations")}
            indexes = inspect(engine).get_indexes("simulations")
            assert "name" in columns
            assert any(index["name"] == "uq_simulation_owner_name" for index in indexes)
        finally:
            engine.dispose()


class TestRating:
    def test_unique_subject_format(self, session: Session) -> None:
        r1 = Rating(subject="alice", format="gen9randombattle", rating=1500)
        r2 = Rating(subject="alice", format="gen9randombattle", rating=1600)
        session.add(r1)
        session.flush()
        session.add(r2)
        with pytest.raises(Exception):  # noqa: B017
            session.flush()

    def test_default_values(self, session: Session) -> None:
        r = Rating(subject="alice", format="gen9randombattle")
        session.add(r)
        session.flush()
        assert r.rating == 1500.0
        assert r.rd == 350.0
        assert r.games == 0
