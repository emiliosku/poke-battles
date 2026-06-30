"""Reinforcement learning training for poke-battles agents.

Core modules (encoder, rewards, config) are importable without torch.
Training modules (env, player, train) require the ``[train]`` extra.
"""

from pokerl.encoder import OBSERVATION_SIZE, encode_battle
from pokerl.rewards import RewardConfig, compute_reward

__all__ = [
    "OBSERVATION_SIZE",
    "RewardConfig",
    "compute_reward",
    "encode_battle",
]
