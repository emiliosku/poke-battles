"""Database session and engine setup."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from pokeapi.db.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

DEFAULT_DATABASE_URL = "sqlite:///./pokeapi.db"


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: str | None = None) -> Engine:
    db_url = url or get_database_url()
    connect_args: dict[str, object] = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(db_url, future=True, connect_args=connect_args)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        _ensure_postgres_columns(engine)


def _ensure_postgres_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    table_columns = {
        table: {column["name"]: column for column in inspector.get_columns(table)}
        for table in ("battles", "simulations", "replays")
        if inspector.has_table(table)
    }
    statements = []
    battle_columns = table_columns.get("battles", {})
    simulation_columns = table_columns.get("simulations", {})
    replay_columns = table_columns.get("replays", {})

    if "owner_id" not in battle_columns:
        statements.append("ALTER TABLE battles ADD COLUMN owner_id VARCHAR(64)")
    if "status" in battle_columns and _varchar_length(battle_columns["status"]) < 32:
        statements.append("ALTER TABLE battles ALTER COLUMN status TYPE VARCHAR(32)")
    if "owner_id" not in simulation_columns:
        statements.append("ALTER TABLE simulations ADD COLUMN owner_id VARCHAR(64)")
    if "format" not in simulation_columns:
        statements.append(
            "ALTER TABLE simulations ADD COLUMN format VARCHAR(64) DEFAULT 'gen9randombattle'"
        )
    if "status" in simulation_columns and _varchar_length(simulation_columns["status"]) < 32:
        statements.append("ALTER TABLE simulations ALTER COLUMN status TYPE VARCHAR(32)")
    if "raw_log" not in replay_columns:
        statements.append("ALTER TABLE replays ADD COLUMN raw_log TEXT")

    if statements:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))


def _varchar_length(column: Mapping[str, object]) -> int:
    length = getattr(column["type"], "length", None)
    return int(length) if length is not None else 32


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "DEFAULT_DATABASE_URL",
    "get_database_url",
    "init_db",
    "make_engine",
    "make_session_factory",
    "session_scope",
]
