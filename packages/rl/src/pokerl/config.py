"""Training hyperparameters and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TrainConfig:
    """PPO training configuration.

    Defaults are tuned for Pokémon battles — moderate batch size,
    relatively high entropy coefficient to encourage exploration of
    moves/switches, and a generous learning rate.
    """

    # Environment
    battle_format: str = "gen9randombattle"
    opponent: str = "random"  # "random", "heuristic", "self-play", or model path
    num_envs: int = 4  # parallel environments for vectorized training

    # PPO hyperparameters
    total_timesteps: int = 500_000
    learning_rate: float = 3e-4
    n_steps: int = 2048  # steps per env before update
    batch_size: int = 256
    n_epochs: int = 10
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.01  # entropy bonus for exploration
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5

    # Network architecture
    net_arch: list[int] = field(default_factory=lambda: [256, 256])
    activation: str = "relu"  # "relu" or "tanh"

    # Training schedule
    eval_freq: int = 10_000  # evaluate every N steps
    eval_episodes: int = 50  # battles per evaluation
    save_freq: int = 50_000  # save checkpoint every N steps
    log_interval: int = 10  # log every N updates

    # Paths
    save_dir: str = "models/rl"
    log_dir: str = "logs/rl"
    tensorboard_log: str = "logs/rl/tensorboard"

    # Showdown server
    server_host: str = "localhost"
    server_port: int = 8000

    # Episode limits
    max_turns: int = 200  # force-end a battle after this many turns (anti-stall)

    # Self-play
    self_play_update_freq: int = 50_000  # update opponent model every N steps
    self_play_pool_size: int = 5  # keep N past versions for opponent sampling

    # Fine-tuning
    resume_path: str | None = None  # load a saved .zip and continue training
