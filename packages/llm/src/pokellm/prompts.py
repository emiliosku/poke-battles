"""Prompt rendering.

We use plain ``str.format`` instead of Jinja2 to keep the wheel small (no
templating dep). Prompts are versioned via the ``PROMPT_VERSION`` constant;
bump it when you change the templates.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROMPT_VERSION: str = "v1"

_SYSTEM_TEMPLATE = """\
You are an elite Pokémon battle AI playing on Pokémon Showdown (Gen 9).
Goal: win the current 6v6 battle.

# Rules you must follow
1. You MUST respond by calling exactly one of the provided tools: `choose_move` or `choose_switch`.
2. NEVER reply with plain text, explanations, or commentary outside a tool call.
3. The `move_name` or `pokemon_name` you provide MUST exactly match one of the available options in the battle state.
4. Do NOT exceed 30 words in the `commentary` field.

# Reasoning tools
Before deciding, you MAY call:
- `lookup_type_chart(move_type, defender_primary, defender_secondary?)` to check effectiveness.
- `estimate_damage(...)` to compare move options.
- `evaluate_switch(...)` to weigh a pivot.
You have only a few tool calls per turn — use them wisely.

# Strategy principles
- Prioritize type matchup. A resisted or immune move should almost never be used.
- Consider switching when your active Pokémon is at <30% HP AND a teammate has a better matchup.
- Stealth Rock, Spikes, Sticky Web, and weather setters are high value on the field.
- Watch for opponent's setup (Swords Dance, Nasty Plot, Calm Mind) — pressure or pivot immediately.
- Preserve your win condition: don't sack a sweeper for a support Pokémon unless the position is lost.

# Output format
Call exactly one `choose_move` or `choose_switch` tool. No prose.
"""


_USER_TEMPLATE = """\
Current Battle State:
{battle_state}

---

{opponent_profile}

{short_term_memory}

Choose the best action. Call either `choose_move` or `choose_switch`. Do NOT reply with text.
"""


def render_system_prompt(
    profile: str | None = None,
    *,
    extras: Mapping[str, str] | None = None,
) -> str:
    """Render the system prompt.

    Parameters
    ----------
    profile:
        Optional strategy profile block (e.g. "aggressive", "stall"). Appended
        after the main template.
    extras:
        Additional named blocks to append.
    """
    parts: list[str] = [_SYSTEM_TEMPLATE]
    if profile:
        parts.append(f"\n# Strategy profile\n{profile.strip()}\n")
    if extras:
        for key, value in extras.items():
            parts.append(f"\n# {key}\n{value.strip()}\n")
    return "".join(parts)


def render_user_prompt(
    battle_state: str,
    *,
    opponent_profile: str = "",
    short_term_memory: str = "",
) -> str:
    """Render the user (turn) prompt."""
    return _USER_TEMPLATE.format(
        battle_state=battle_state,
        opponent_profile=opponent_profile or "Opponent profile: (no prior data)",
        short_term_memory=short_term_memory or "Your recent actions: (none yet)",
    )


def strategy_profile(name: str) -> str:
    """Return a named strategy profile block (used as ``profile`` argument)."""
    profiles: dict[str, str] = {
        "aggressive": (
            "Play aggressively. Look for KO opportunities, set up sweepers when the "
            "opponent is weakened, and pivot only when the active is at <25% HP."
        ),
        "stall": (
            "Play defensively. Prioritize status, hazards, and recovery. Switch in "
            "walls when your active is pressured, and chip the opponent with safe moves."
        ),
        "hazard_stack": (
            "Lead with hazard setters (Stealth Rock, Spikes). Keep the field control, "
            "and use Defog/Rapid Spin only when you have a clear advantage."
        ),
        "setup_sweeper": (
            "Find setup opportunities: free turns, slow opponents, or after a KO. "
            "Once sweeping, avoid switching out."
        ),
        "balanced": (
            "Play a balanced game. Apply pressure when ahead, switch to better "
            "matchups when behind. Use hazards and status to control pace."
        ),
    }
    return profiles.get(name, profiles["balanced"])


__all__ = [
    "PROMPT_VERSION",
    "render_system_prompt",
    "render_user_prompt",
    "strategy_profile",
]
_ = (Any,)
