"""Reward shaping for RL Pokémon battles.

Provides shaped rewards beyond simple win/loss to accelerate learning.
The reward signal combines:
- Terminal reward: +1 win, -1 loss
- HP differential: reward for dealing damage, penalty for taking it
- KO events: bonus for knocking out opponent's pokemon
- Faint penalty: penalty when own pokemon faints

All intermediate rewards are scaled to be much smaller than the terminal
reward so the agent still optimizes for winning.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Configurable reward weights."""

    win_reward: float = 1.0
    loss_reward: float = -1.0
    faint_reward: float = -0.1
    ko_reward: float = 0.15
    hp_loss_penalty: float = -0.05
    hp_damage_reward: float = 0.05
    turn_penalty: float = -0.001  # small penalty to encourage faster wins


@dataclass(slots=True)
class RewardTracker:
    """Tracks per-battle state needed to compute shaped rewards.

    Create one per battle episode. Call ``step()`` each turn with the
    current battle state to get the shaped reward for that transition.
    """

    config: RewardConfig
    prev_player_hp: float = 6.0  # sum of HP fractions across team (max 6.0)
    prev_opponent_hp: float = 6.0
    prev_player_fainted: int = 0
    prev_opponent_fainted: int = 0

    def step(
        self,
        *,
        player_hp_sum: float,
        opponent_hp_sum: float,
        player_fainted: int,
        opponent_fainted: int,
        battle_finished: bool,
        won: bool | None,
    ) -> float:
        """Compute shaped reward for a single step.

        Parameters
        ----------
        player_hp_sum:
            Sum of hp_fraction for all player pokemon (0.0–6.0).
        opponent_hp_sum:
            Sum of hp_fraction for all opponent pokemon (0.0–6.0).
        player_fainted:
            Total number of player's fainted pokemon.
        opponent_fainted:
            Total number of opponent's fainted pokemon.
        battle_finished:
            Whether the battle is over.
        won:
            True if player won, False if lost, None if not finished.

        Returns
        -------
        Float reward for this step.
        """
        reward = 0.0

        # Terminal reward
        if battle_finished and won is not None:
            reward += self.config.win_reward if won else self.config.loss_reward
            return reward

        # HP differential reward
        player_hp_delta = player_hp_sum - self.prev_player_hp
        opponent_hp_delta = opponent_hp_sum - self.prev_opponent_hp

        # Player took damage (negative delta → penalty)
        if player_hp_delta < 0:
            reward += self.config.hp_loss_penalty * abs(player_hp_delta)

        # Opponent took damage (negative delta → reward)
        if opponent_hp_delta < 0:
            reward += self.config.hp_damage_reward * abs(opponent_hp_delta)

        # KO events
        new_opponent_kos = opponent_fainted - self.prev_opponent_fainted
        if new_opponent_kos > 0:
            reward += self.config.ko_reward * new_opponent_kos

        # Faint events
        new_player_faints = player_fainted - self.prev_player_fainted
        if new_player_faints > 0:
            reward += self.config.faint_reward * new_player_faints

        # Turn penalty
        reward += self.config.turn_penalty

        # Update state
        self.prev_player_hp = player_hp_sum
        self.prev_opponent_hp = opponent_hp_sum
        self.prev_player_fainted = player_fainted
        self.prev_opponent_fainted = opponent_fainted

        return reward


def compute_reward(
    battle: object,
    tracker: RewardTracker,
) -> float:
    """Compute shaped reward from a poke-env battle object.

    Convenience function that extracts state from a poke-env AbstractBattle
    and delegates to the tracker.

    Parameters
    ----------
    battle:
        A poke-env AbstractBattle instance.
    tracker:
        The RewardTracker for this episode.

    Returns
    -------
    Float reward for the current step.
    """
    # Extract team HP sums
    team: dict[str, object] = getattr(battle, "team", {}) or {}
    opp_team: dict[str, object] = getattr(battle, "opponent_team", {}) or {}

    player_hp_sum = sum(
        float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)
        for mon in team.values()
    )
    opponent_hp_sum = sum(
        float(getattr(mon, "current_hp_fraction", 0.0) or 0.0)
        for mon in opp_team.values()
    )

    player_fainted = sum(
        1 for mon in team.values() if getattr(mon, "fainted", False)
    )
    opponent_fainted = sum(
        1 for mon in opp_team.values() if getattr(mon, "fainted", False)
    )

    # Check if battle is finished
    battle_finished = bool(getattr(battle, "finished", False))
    won: bool | None = None
    if battle_finished:
        won = bool(getattr(battle, "won", False))

    return tracker.step(
        player_hp_sum=player_hp_sum,
        opponent_hp_sum=opponent_hp_sum,
        player_fainted=player_fainted,
        opponent_fainted=opponent_fainted,
        battle_finished=battle_finished,
        won=won,
    )
