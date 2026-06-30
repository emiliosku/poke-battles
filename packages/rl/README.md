# pokerl — Reinforcement Learning for Pokémon Showdown

PPO-based RL training for the poke-battles agent. Trains a policy
network to play Gen 9 Random Battles by self-play or against
heuristic/random baselines.

## Quick start

```bash
# Install with training deps
uv pip install -e "packages/rl[train]"

# Start a local Showdown server (requires packages/engine setup)
make demo  # or manually: uv run python -m pokeengine.runner

# Train against random opponent
pokerl-train --timesteps 500000 --opponent random

# Train against heuristic
pokerl-train --timesteps 1000000 --opponent heuristic

# Monitor training
tensorboard --logdir logs/rl/tensorboard
```

## Architecture

```
encoder.py   → Battle state → 360-dim float32 observation vector
rewards.py   → Shaped reward (HP delta + KO bonus + win/loss terminal)
player.py    → RL-compatible poke-env Player (queue-based sync bridge)
env.py       → Gymnasium environment wrapper
train.py     → PPO training CLI (MaskablePPO from sb3-contrib)
inference.py → Load trained model → MoveChooser for AgentPlayer
config.py    → Training hyperparameters
```

## Using a trained model

```python
from pokeengine.player import AgentPlayer
from pokerl.inference import make_rl_chooser

chooser = make_rl_chooser("models/rl/final_model")
player = AgentPlayer.from_config("RLBot", choose_move_for_turn=chooser)
```

## Dependencies

Core (always): `numpy`, `pokecore`, `pokeengine`
Training (`[train]` extra): `torch`, `stable-baselines3`, `sb3-contrib`, `gymnasium`, `tensorboard`
