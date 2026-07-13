"""SQLAlchemy ORM models for the API service.

Postgres for production, SQLite for dev/test. Models cover:
- User (auth, profile metadata)
- Team (Showdown paste + parsed team)
- Battle (one match between two participants)
- Tournament (bracket of battles)
- Simulation (N battles to compute win-rates)
- Replay (event log of a finished battle)
- Rating (Glicko-2 ratings per (subject, format) pair)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    teams: Mapped[list[Team]] = relationship(back_populates="owner")


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column()

    user: Mapped[User] = relationship()


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(64))
    paste: Mapped[str] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(String(64))
    is_public: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="teams")


class Battle(Base):
    __tablename__ = "battles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    format: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    player1_username: Mapped[str] = mapped_column(String(64))
    player2_username: Mapped[str] = mapped_column(String(64))
    model1: Mapped[str] = mapped_column(String(64))
    model2: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    team1_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    team2_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    team1_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON)
    team2_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(32), default="battle")
    winner: Mapped[str | None] = mapped_column(String(64))
    turns: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


class Tournament(Base):
    __tablename__ = "tournaments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    format: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    bracket_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column()


class Simulation(Base):
    __tablename__ = "simulations"
    __table_args__ = (Index("uq_simulation_owner_name", "owner_id", "name", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str | None] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(32))
    format: Mapped[str] = mapped_column(String(64), default="gen9randombattle")
    team_a_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    models_json: Mapped[list[str] | None] = mapped_column(JSON)
    n_battles: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    wins: Mapped[int | None] = mapped_column(Integer)
    losses: Mapped[int | None] = mapped_column(Integer)
    draws: Mapped[int | None] = mapped_column(Integer)
    win_rate: Mapped[float | None] = mapped_column(Float)
    ci_95: Mapped[float | None] = mapped_column(Float)
    results_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column()


class Replay(Base):
    __tablename__ = "replays"
    battle_id: Mapped[str] = mapped_column(ForeignKey("battles.id"), primary_key=True)
    events: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    raw_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict[str, object] | None] = mapped_column(JSON)


class ReplayShare(Base):
    __tablename__ = "replay_shares"

    battle_id: Mapped[str] = mapped_column(ForeignKey("battles.id"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column()


class ReplayStudy(Base):
    __tablename__ = "replay_studies"

    battle_id: Mapped[str] = mapped_column(
        ForeignKey("battles.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    is_favorite: Mapped[bool] = mapped_column(default=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class ReplayAnnotation(Base):
    __tablename__ = "replay_annotations"
    __table_args__ = (Index("ix_replay_annotations_owner_battle", "owner_id", "battle_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    battle_id: Mapped[str] = mapped_column(ForeignKey("battles.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    turn: Mapped[int | None] = mapped_column(Integer)
    event_index: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    is_highlight: Mapped[bool] = mapped_column(default=False)
    is_shared: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Rating(Base):
    __tablename__ = "ratings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(64))
    rating: Mapped[float] = mapped_column(Float, default=1500.0)
    rd: Mapped[float] = mapped_column(Float, default=350.0)
    vol: Mapped[float] = mapped_column(Float, default=0.06)
    games: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow)

    __table_args__ = (UniqueConstraint("subject", "format", name="uq_rating_subject_format"),)


__all__ = [
    "Base",
    "Battle",
    "Rating",
    "Replay",
    "ReplayAnnotation",
    "ReplayShare",
    "ReplayStudy",
    "Simulation",
    "Team",
    "Tournament",
    "User",
    "UserSession",
]
