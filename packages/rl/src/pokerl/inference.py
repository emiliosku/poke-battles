"""Load a trained RL model and expose it as a MoveChooser.

This module bridges the trained PPO policy back into the existing
``AgentPlayer`` infrastructure. The ``make_rl_chooser()`` function
returns an async callable compatible with ``MoveChooser`` type.

Requires: torch, stable-baselines3, sb3-contrib.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pokerl.encoder import encode_battle
from pokerl.player import NUM_ACTIONS

if TYPE_CHECKING:
    from poke_env.battle.abstract_battle import AbstractBattle
    from poke_env.player.battle_order import BattleOrder

    from pokeengine.player import AgentPlayer, MoveChooser

logger = logging.getLogger(__name__)


def _action_to_order(
    action: int,
    battle: AbstractBattle,
    player: AgentPlayer,
) -> BattleOrder:
    """Convert discrete action to BattleOrder (same logic as RLPlayer)."""
    available_moves = battle.available_moves
    available_switches = battle.available_switches

    if action < 4:
        if action < len(available_moves):
            return player.create_order(available_moves[action])
    else:
        switch_idx = action - 4
        if switch_idx < len(available_switches):
            return player.create_order(available_switches[switch_idx])

    # Fallback
    if available_moves:
        return player.create_order(available_moves[0])
    if available_switches:
        return player.create_order(available_switches[0])
    return player.choose_random_move(battle)


def _compute_action_mask(battle: AbstractBattle) -> np.ndarray:
    """Compute legal action mask for the current battle state."""
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)

    available_moves = battle.available_moves
    for i in range(min(len(available_moves), 4)):
        mask[i] = True

    available_switches = battle.available_switches
    for i in range(min(len(available_switches), 5)):
        mask[4 + i] = True

    if not mask.any():
        if available_moves:
            mask[0] = True
        elif available_switches:
            mask[4] = True

    return mask


def make_rl_chooser(
    model_path: str | Path,
    *,
    deterministic: bool = True,
) -> MoveChooser:
    """Load a trained RL model and return a MoveChooser callable.

    Parameters
    ----------
    model_path:
        Path to a saved MaskablePPO model (zip file or directory).
    deterministic:
        If True, always pick the highest-probability action.
        If False, sample from the policy distribution.

    Returns
    -------
    An async callable ``(AgentPlayer, AbstractBattle) -> BattleOrder``
    compatible with the existing ``AgentPlayer.choose_move_for_turn``.
    """
    from sb3_contrib import MaskablePPO

    model_path = Path(model_path)
    logger.info("Loading RL model from %s", model_path)
    model = MaskablePPO.load(str(model_path))
    logger.info("RL model loaded successfully")

    async def _rl_chooser(
        player: AgentPlayer,
        battle: AbstractBattle,
    ) -> BattleOrder:
        """Choose a move using the trained RL policy."""
        # Encode battle state
        obs = encode_battle(battle)

        # Get action mask
        action_mask = _compute_action_mask(battle)

        # Predict action using the trained model
        action, _states = model.predict(
            obs,
            action_masks=action_mask,
            deterministic=deterministic,
        )

        action_int = int(action)
        return _action_to_order(action_int, battle, player)

    return _rl_chooser
