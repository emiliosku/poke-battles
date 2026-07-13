"""Regression tests for battle Glicko-2 updates."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from pokeapi.db.models import Base, Rating
from pokeapi.orchestrator import BattleJob
from pokeapi.routes.battles import _update_ratings


@pytest.fixture
def session() -> Iterator[Session]:
    engine: Engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


@pytest.mark.parametrize(
    ("winner_side", "expected_p1_rating", "expected_p2_rating"),
    [("p1", 1500.0, 1500.0), ("p2", 1500.0, 1500.0)],
)
def test_update_ratings_uses_showdown_winner_side(
    session: Session,
    winner_side: str,
    expected_p1_rating: float,
    expected_p2_rating: float,
) -> None:
    job = BattleJob(format="gen9randombattle", player1="Alice Smith", player2="Bob Jones")

    _update_ratings(session, job, winner_side)
    session.flush()

    p1 = session.query(Rating).filter_by(subject=job.player1, format=job.format).one()
    p2 = session.query(Rating).filter_by(subject=job.player2, format=job.format).one()

    assert p1.games == p2.games == 1
    if winner_side == "p1":
        assert p1.rating > expected_p1_rating
        assert p2.rating < expected_p2_rating
    else:
        assert p1.rating < expected_p1_rating
        assert p2.rating > expected_p2_rating
