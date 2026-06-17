"""Unit tests for pokeapi.db (in-memory SQLite)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from pokeapi.db.models import Base, Battle, Rating, Team, User


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
