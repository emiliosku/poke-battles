"""Helpers for accessing shared application state from request handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from pokeapi.services.team_validation import (
    ShowdownTeamValidator,
    TeamValidationResult,
)

if TYPE_CHECKING:
    from pokeapi.services import BattleService


def get_team_validator(request: Request) -> ShowdownTeamValidator:
    validator = getattr(request.app.state, "team_validator", None)
    if validator is None:
        bservice: BattleService = request.app.state.bservice
        websocket_url = bservice.websocket_url()
        if websocket_url is None:
            bservice.start()
            websocket_url = bservice.websocket_url()
        if websocket_url is None:
            raise RuntimeError("Showdown server is not available for team validation")
        validator = ShowdownTeamValidator(websocket_url=websocket_url)
        request.app.state.team_validator = validator
    return validator


async def shutdown_team_validator(request: Request) -> None:
    validator = getattr(request.app.state, "team_validator", None)
    if validator is None:
        return
    await validator.stop()
    request.app.state.team_validator = None


__all__ = [
    "TeamValidationResult",
    "get_team_validator",
    "shutdown_team_validator",
]
