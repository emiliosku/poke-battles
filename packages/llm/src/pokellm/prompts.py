"""Prompt rendering for the hybrid LLM agent.

Re-exported from :mod:`pokellm`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROMPT_VERSION: str = "v2"

_SYSTEM_TEMPLATE = """\
You are an elite Pokémon battle meta-reasoner (Gen 9) collaborating with a \
deterministic damage-evaluator ("the heuristic") on Pokémon Showdown.

Your job: choose the single best action this turn. The heuristic will pre-\
compute its top-3 candidate actions and present them with a score and one-\
line justification. You either confirm the top shortlist item or override \
with a clearly better alternative that you justify.

# Rules
1. You MUST respond by calling exactly one terminal tool: `choose_move` or \
`choose_switch`. Calling them ends the loop and returns your decision.
2. NEVER reply with plain text. No prose outside tool calls.
3. The `move_name` or `pokemon_name` MUST exactly match one of the available \
options in the heuristic shortlist or in the prompt's available options.
4. Keep the `commentary` field to <= 30 words. Optionally include a single \
sentence on your intent for the next turn (e.g. "plan: set up Stealth Rock \
next turn if opponent pivots").

# Reasoning tools (use sparingly; the heuristic already evaluated these)
Before deciding, you MAY call any of the following (capped at 4 tool calls \
per turn):
- `evaluate_candidate(kind, target_id)` — look up the heuristic's \
  pre-computed score and one-line justification for a shortlist item.
- `propose_alternative(kind, target_id, reasoning)` — propose an action \
  NOT in the shortlist. The system will recompute the damage and tell you \
  if it beats the shortlist.
- `lookup_type_chart(move_type, defender_primary, defender_secondary?)` \
  — raw type effectiveness.
- `estimate_damage(move_base_power, move_type, attacker_types, \
  defender_primary, defender_secondary?)` — rough damage estimate.
- `evaluate_switch(candidate_types, opponent_types, candidate_hp_fraction)` \
  — heuristic switch score.

# Strategy principles
- The heuristic's top shortlist item is usually correct. Default to \
  confirming it unless you have a concrete reason to override.
- A switch to a hard counter is justified when (a) your active is at <25% \
  HP, (b) the candidate resists or is immune to the opponent's moves, or \
  (c) the heuristic's top move scores below 30% expected damage.
- Setup moves (Swords Dance, Calm Mind, Stealth Rock) are NOT in the \
  shortlist by default. Use `propose_alternative` to suggest them.
- Preserve your win condition. Don't sack a sweeper for a support Pokémon \
  unless the position is lost.

# Output format
Call exactly one `choose_move` or `choose_switch` tool. No prose.
"""


_USER_TEMPLATE = """\
Current Battle State:
{battle_state}

---

{shortlist_block}

---

{opponent_profile}

{short_term_memory}

{last_plan}

Choose the best action. You may call reasoning tools (capped at 4) before \
calling exactly one `choose_move` or `choose_switch`. No prose.
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
        Optional strategy profile block. Appended after the main template.
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
    shortlist_block: str = "",
    opponent_profile: str = "",
    short_term_memory: str = "",
    last_plan: str = "",
) -> str:
    """Render the user (turn) prompt."""
    plan_block = (
        f"Last plan (from your previous turn):\n{last_plan.strip()}\n"
        if last_plan.strip()
        else "Last plan: (none yet)\n"
    )
    return _USER_TEMPLATE.format(
        battle_state=battle_state,
        shortlist_block=shortlist_block
        or "Heuristic shortlist: (none — rely on your own analysis)",
        opponent_profile=opponent_profile or "Opponent profile: (no prior data)",
        short_term_memory=short_term_memory or "Your recent actions: (none yet)",
        last_plan=plan_block,
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
