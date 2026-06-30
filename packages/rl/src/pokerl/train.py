"""PPO training script for Pokémon battle RL agent.

Usage:
    pokerl-train [--timesteps N] [--format FORMAT] [--opponent TYPE]

Requires a running Pokémon Showdown server (see ``pokeengine.runner``).
Install with: ``uv pip install -e "packages/rl[train]"``

Requires: torch, stable-baselines3, sb3-contrib, gymnasium, tensorboard.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pokerl.config import TrainConfig
    from pokerl.env import PokemonBattleEnv

logger = logging.getLogger(__name__)


def _check_deps() -> bool:
    """Verify training dependencies are installed."""
    missing: list[str] = []
    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")
    try:
        import stable_baselines3  # noqa: F401
    except ImportError:
        missing.append("stable-baselines3")
    try:
        import sb3_contrib  # noqa: F401
    except ImportError:
        missing.append("sb3-contrib")
    try:
        import gymnasium  # noqa: F401
    except ImportError:
        missing.append("gymnasium")

    if missing:
        print(
            f"Missing training dependencies: {', '.join(missing)}\n"
            f"Install with: uv pip install -e 'packages/rl[train]'",
            file=sys.stderr,
        )
        return False
    return True


def make_env(config: TrainConfig, env_id: int = 0) -> PokemonBattleEnv:
    """Create a single battle environment instance."""
    from pokerl.env import PokemonBattleEnv
    from pokerl.rewards import RewardConfig

    return PokemonBattleEnv(
        config=config,
        env_id=env_id,
        reward_config=RewardConfig(),
    )


def train(config: TrainConfig) -> None:
    """Run PPO training loop.

    Parameters
    ----------
    config:
        Training configuration with hyperparameters and paths.
    """
    from sb3_contrib import MaskablePPO
    from sb3_contrib.common.wrappers import ActionMasker
    from stable_baselines3.common.callbacks import (
        CheckpointCallback,
        EvalCallback,
    )


    # Create output directories
    save_path = Path(config.save_dir)
    log_path = Path(config.log_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.info("Starting PPO training")
    logger.info("  Format: %s", config.battle_format)
    logger.info("  Opponent: %s", config.opponent)
    logger.info("  Timesteps: %d", config.total_timesteps)
    logger.info("  Save dir: %s", config.save_dir)

    # Create environment with action masking wrapper
    def _make_wrapped_env(env_id: int = 0) -> ActionMasker:
        env = make_env(config, env_id=env_id)
        return ActionMasker(env, action_mask_fn=lambda e: e.action_masks())

    env = _make_wrapped_env(env_id=0)

    # Create eval environment
    eval_env = _make_wrapped_env(env_id=100)

    # Build MaskablePPO model
    model = MaskablePPO(
        "MlpPolicy",
        env,
        learning_rate=config.learning_rate,
        n_steps=config.n_steps,
        batch_size=config.batch_size,
        n_epochs=config.n_epochs,
        gamma=config.gamma,
        gae_lambda=config.gae_lambda,
        clip_range=config.clip_range,
        ent_coef=config.ent_coef,
        vf_coef=config.vf_coef,
        max_grad_norm=config.max_grad_norm,
        policy_kwargs={
            "net_arch": config.net_arch,
        },
        tensorboard_log=config.tensorboard_log,
        verbose=1,
    )

    logger.info("Model architecture: %s", config.net_arch)
    logger.info("Total parameters: %d", sum(p.numel() for p in model.policy.parameters()))

    # Callbacks
    callbacks = [
        CheckpointCallback(
            save_freq=config.save_freq,
            save_path=str(save_path / "checkpoints"),
            name_prefix="poke_rl",
        ),
        EvalCallback(
            eval_env,
            best_model_save_path=str(save_path / "best"),
            log_path=str(log_path / "eval"),
            eval_freq=config.eval_freq,
            n_eval_episodes=config.eval_episodes,
            deterministic=True,
        ),
    ]

    # Train
    model.learn(
        total_timesteps=config.total_timesteps,
        callback=callbacks,
        log_interval=config.log_interval,
        progress_bar=True,
    )

    # Save final model
    final_path = str(save_path / "final_model")
    model.save(final_path)
    logger.info("Training complete. Model saved to %s", final_path)

    # Cleanup
    env.close()
    eval_env.close()


def main() -> None:
    """CLI entry point for training."""
    parser = argparse.ArgumentParser(
        description="Train a PPO agent for Pokémon Showdown battles",
    )
    parser.add_argument(
        "--timesteps", type=int, default=500_000,
        help="Total training timesteps (default: 500000)",
    )
    parser.add_argument(
        "--format", type=str, default="gen9randombattle",
        help="Battle format (default: gen9randombattle)",
    )
    parser.add_argument(
        "--opponent", type=str, default="random",
        choices=["random", "heuristic", "self-play"],
        help="Opponent type (default: random)",
    )
    parser.add_argument(
        "--lr", type=float, default=3e-4,
        help="Learning rate (default: 3e-4)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=256,
        help="Batch size (default: 256)",
    )
    parser.add_argument(
        "--save-dir", type=str, default="models/rl",
        help="Directory to save models (default: models/rl)",
    )
    parser.add_argument(
        "--server-host", type=str, default="localhost",
        help="Showdown server host (default: localhost)",
    )
    parser.add_argument(
        "--server-port", type=int, default=8000,
        help="Showdown server port (default: 8000)",
    )
    parser.add_argument(
        "--net-arch", type=str, default="256,256",
        help="Network layer sizes, comma-separated (default: 256,256)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not _check_deps():
        sys.exit(1)

    from pokerl.config import TrainConfig

    config = TrainConfig(
        total_timesteps=args.timesteps,
        battle_format=args.format,
        opponent=args.opponent,
        learning_rate=args.lr,
        batch_size=args.batch_size,
        save_dir=args.save_dir,
        server_host=args.server_host,
        server_port=args.server_port,
        net_arch=[int(x) for x in args.net_arch.split(",")],
    )

    # Ensure server is reachable
    logger.info(
        "Connecting to Showdown server at %s:%d",
        config.server_host,
        config.server_port,
    )

    train(config)


if __name__ == "__main__":
    main()
