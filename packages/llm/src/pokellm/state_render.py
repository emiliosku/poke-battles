"""Render :class:`pokecore.state.BattleState` for the LLM prompt.

The renderer is pure-Python (no poke-env dependency) so it can be unit-tested
in isolation. The output is a compact, human-readable block that fits in the
``{battle_state}`` slot of the user prompt.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from typing import Any

from pokecore.state import BattleState, FieldState, KnownMove, PokemonState

_REVEALED_MOVE_LIMIT = 6


def format_battle_state(state: BattleState) -> str:
    """Format a :class:`BattleState` as a prompt-friendly string."""
    parts: list[str] = [
        f"Turn {state.turn} of {state.format} ({state.player_username} vs {state.opponent_username})",
    ]
    parts.append("")
    parts.extend(_format_side("Your side", state.player, can_tera=state.can_tera))
    parts.append("")
    parts.extend(_format_side("Opponent", state.opponent, can_tera=False))
    parts.append("")
    parts.append(_format_field(state.field))
    return "\n".join(parts)


def _format_side(label: str, side: tuple[PokemonState, ...], *, can_tera: bool) -> list[str]:
    lines: list[str] = [f"{label}:"]
    if not side:
        lines.append("  (no Pokémon)")
        return lines
    for _index, mon in enumerate(side):
        prefix = "  > " if mon.is_active else "    "
        marker = " [active]" if mon.is_active else (" [fainted]" if mon.is_fainted else " [bench]")
        types = "/".join(mon.types) if mon.types else "?"
        tera = (
            f" tera={mon.tera_type}{'!' if mon.is_terastallized else ''}"
            if mon.tera_type or mon.is_terastallized
            else ""
        )
        lines.append(
            f"{prefix}{mon.nickname} ({mon.species}) L{mon.level} "
            f"{types} {mon.hp_fraction * 100:.0f}% HP{tera}{marker}"
        )
        if mon.status:
            lines.append(f"      status: {mon.status}")
        if mon.ability:
            lines.append(f"      ability: {mon.ability}")
        if mon.item:
            lines.append(f"      item: {mon.item}")
        if mon.boosts:
            boosts = ", ".join(f"{k}+{v}" if v > 0 else f"{k}{v}" for k, v in mon.boosts.items())
            lines.append(f"      boosts: {boosts}")
        for mv in mon.moves:
            lines.append(
                f"      - {mv.id} {mv.type} {mv.category} BP{mv.base_power} Acc{mv.accuracy} PP{mv.pp}/{mv.max_pp}"
            )
    if can_tera and any(not mon.is_terastallized and not mon.is_fainted for mon in side):
        lines.append("  (tera available)")
    return lines


def _format_field(field: FieldState) -> str:
    bits: list[str] = ["Field:"]
    if field.weather:
        bits.append(f"weather={field.weather}")
    if field.terrain:
        bits.append(f"terrain={field.terrain}")
    if field.trick_room:
        bits.append("trick_room")
    if field.player_hazards:
        haz = ", ".join(f"{k}:{v}" for k, v in field.player_hazards.items() if v)
        if haz:
            bits.append(f"your_hazards={haz}")
    if field.opponent_hazards:
        haz = ", ".join(f"{k}:{v}" for k, v in field.opponent_hazards.items() if v)
        if haz:
            bits.append(f"opp_hazards={haz}")
    if len(bits) == 1:
        bits.append("(no field effects)")
    return " ".join(bits)


def default_state_formatter(state: Any) -> str:
    """Format any state value the agent may receive.

    - ``str`` → returned as-is.
    - ``dict`` with a ``"formatted"`` key → that value.
    - ``BattleState`` → rendered via :func:`format_battle_state`.
    - other ``dict`` → ``k: v`` per key, joined by newlines.
    - anything else → ``str(state)``.
    """
    if isinstance(state, str):
        return state
    if isinstance(state, BattleState):
        return format_battle_state(state)
    if isinstance(state, dict):
        if "formatted" in state:
            return str(state["formatted"])
        return "\n".join(f"{k}: {v}" for k, v in state.items())
    return str(state)


__all__ = ["default_state_formatter", "format_battle_state"]
_ = (KnownMove, _REVEALED_MOVE_LIMIT)
