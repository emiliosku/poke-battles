"""Gymnasium environment wrapping poke-env battles.

Provides a standard ``gymnasium.Env`` interface for training RL agents
on Pokémon Showdown battles. Internally manages the async poke-env
player and opponent in a background thread.

Requires: ``gymnasium``, ``poke-env`` (available with ``[train]`` extra).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from queue import Empty, Queue
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import numpy.typing as npt
from gymnasium import spaces
from poke_env.battle.double_battle import DoubleBattle
from poke_env.player.player import Player
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import ServerConfiguration

try:
    from poke_env.player import RandomPlayer, SimpleHeuristicsPlayer
except ImportError:  # pragma: no cover - older poke_env layout
    from poke_env.player.random_player import RandomPlayer  # type: ignore[no-redef]
    from poke_env.player.simple_heuristics_player import (  # type: ignore[no-redef]
        SimpleHeuristicsPlayer,
    )

from pokerl.config import TrainConfig
from pokerl.encoder import OBSERVATION_SIZE, encode_battle
from pokerl.player import NUM_ACTIONS, RLPlayer
from pokerl.rewards import RewardConfig, RewardTracker, compute_reward

logger = logging.getLogger(__name__)


class PokemonBattleEnv(gym.Env[npt.NDArray[np.float32], int]):
    """Gymnasium environment for Pokémon Showdown battles.

    Each episode is one complete battle. The agent receives encoded
    battle state observations and selects from discrete actions
    (moves + switches). Invalid actions are masked.

    Parameters
    ----------
    config:
        Training configuration (server, format, opponent type).
    env_id:
        Unique ID for this environment instance (for parallel envs).
    reward_config:
        Reward shaping configuration.
    """

    metadata: ClassVar[dict[str, Any]] = {"render_modes": ["ansi"]}  # type: ignore[misc]

    def __init__(
        self,
        config: TrainConfig | None = None,
        env_id: int = 0,
        reward_config: RewardConfig | None = None,
    ) -> None:
        super().__init__()
        self._config = config or TrainConfig()
        if _is_doubles_format(self._config.battle_format):
            raise ValueError("RL training supports singles formats only")
        self._env_id = env_id
        self._reward_config = reward_config or RewardConfig()

        # Gymnasium spaces
        self.observation_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(OBSERVATION_SIZE,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(NUM_ACTIONS)

        # Communication queues between env (sync) and player (async)
        self._obs_queue: Queue[Any] = Queue(maxsize=1)
        self._action_queue: Queue[int | object] = Queue(maxsize=1)

        # State
        self._current_battle: Any | None = None
        self._reward_tracker: RewardTracker | None = None
        self._action_mask: list[bool] = [True] * NUM_ACTIONS
        self._battle_count: int = 0
        self._turn_count: int = 0
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._player: RLPlayer | None = None
        self._opponent: Player | None = None
        self._started = False
        self._battle_over = threading.Event()

    @property
    def action_mask(self) -> list[bool]:
        """Current action mask (for MaskablePPO)."""
        return self._action_mask

    def action_masks(self) -> npt.NDArray[np.bool_]:
        """Action masks as numpy array (sb3-contrib interface)."""
        return np.array(self._action_mask, dtype=np.bool_)

    def _make_server_config(self) -> ServerConfiguration:
        """Build server configuration from training config."""
        return ServerConfiguration(
            f"ws://{self._config.server_host}:{self._config.server_port}/showdown/websocket",
            f"http://{self._config.server_host}:{self._config.server_port}/action.php?",
        )

    def _start_background(self) -> None:
        """Start the background event loop and players."""
        if self._started:
            return

        server_config = self._make_server_config()

        # Create RL player
        self._player = RLPlayer(
            self._obs_queue,
            self._action_queue,
            account_configuration=AccountConfiguration(f"RLAgent-{self._env_id}", ""),
            server_configuration=server_config,
            battle_format=self._config.battle_format,
        )

        # Create opponent
        self._opponent = self._make_opponent(server_config)

        self._started = True

    def _restart_background(self) -> None:
        """Tear down and recreate the player connections.

        Called when a battle thread has died (e.g. the Showdown websocket
        dropped mid-battle with ``no close frame received or sent``). The
        old poke-env players keep the dead connection, so a fresh pair must
        be created and reconnected before the next battle can start —
        otherwise ``reset()`` blocks forever waiting for an observation that
        will never arrive.
        """
        logger.warning("Restarting background players (reconnecting to Showdown)")
        for player in (self._player, self._opponent):
            if player is not None:
                try:
                    # poke-env players expose connection teardown via the
                    # underlying PSClient (there is no Player.close()).
                    player.ps_client.stop_listening()  # type: ignore[no-untyped-call]
                except Exception as e:  # pragma: no cover - best effort
                    logger.debug("Error stopping player listener on restart: %s", e)
        self._player = None
        self._opponent = None
        self._started = False
        self._start_background()

    def _make_opponent(self, server_config: ServerConfiguration) -> Player:
        """Create the opponent player based on config.

        Supported opponent types (set via ``config.opponent``):
        - ``"random"`` — uniform-random move chooser.
        - ``"heuristic"`` — poke-env's built-in ``SimpleHeuristicsPlayer``,
          a deterministic hand-crafted baseline. This is a much stronger
          opponent than random and is the recommended first step of the
          Random → Heuristic → Self-play curriculum.
        - ``"self-play"`` — same as ``"random"`` for now; the real self-play
          loop (frozen opponent snapshot from the replay pool) lands in
          a follow-up.
        - any other string is treated as a path to a saved MaskablePPO
          model (``.zip``) that gets loaded as the opponent policy.
        """
        acct = AccountConfiguration(f"Opponent-{self._env_id}", "")
        kind = self._config.opponent

        if kind == "random" or kind == "self-play":
            return RandomPlayer(
                account_configuration=acct,
                server_configuration=server_config,
                battle_format=self._config.battle_format,
            )
        if kind == "heuristic":
            return SimpleHeuristicsPlayer(
                account_configuration=acct,
                server_configuration=server_config,
                battle_format=self._config.battle_format,
            )
        # Anything else: treat as a path to a trained opponent policy.
        from pathlib import Path

        from sb3_contrib import MaskablePPO

        model_path = Path(kind)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Opponent model not found at {model_path}. Use 'random', "
                f"'heuristic', 'self-play', or an absolute path to a .zip."
            )
        logger.info("Loading opponent policy from %s", model_path)
        opponent_model = MaskablePPO.load(str(model_path))
        return _LoadedPolicyOpponent(
            account_configuration=acct,
            server_configuration=server_config,
            battle_format=self._config.battle_format,
            model=opponent_model,
        )

    def _run_battle_background(self) -> None:
        """Run a single battle in background thread."""
        assert self._player is not None
        assert self._opponent is not None

        loop = asyncio.new_event_loop()
        self._loop = loop

        async def _wait_for_login(player: Player, timeout: float = 30.0) -> None:
            """Block until ``player.ps_client.logged_in`` is set.

            poke-env 0.15's ``Player.challenge``/``accept_challenge`` assert
            ``self.logged_in.is_set()``; without this wait a fast env reset
            can race the WebSocket login handshake and the very first battle
            of every episode explodes with ``AssertionError``.
            """
            try:
                logged_in = player.ps_client.logged_in
                await asyncio.wait_for(logged_in.wait(), timeout=timeout)
            except TimeoutError:
                logger.warning(
                    "Timed out after %.1fs waiting for %s to log in",
                    timeout,
                    getattr(player, "username", "?"),
                )

        async def _battle() -> None:
            assert self._player is not None
            assert self._opponent is not None
            await asyncio.gather(
                _wait_for_login(self._player),
                _wait_for_login(self._opponent),
            )
            await self._player.battle_against(self._opponent, n_battles=1)

        try:
            loop.run_until_complete(_battle())
        except Exception as e:
            logger.error("Battle error: %s", e)
        finally:
            loop.close()
            self._battle_over.set()

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[npt.NDArray[np.float32], dict[str, Any]]:
        """Start a new battle episode.

        Returns the initial observation and info dict.
        """
        super().reset(seed=seed)

        # If the previous battle thread died (e.g. websocket dropped),
        # the old players hold a dead connection — recreate them so the
        # next battle can actually connect.
        if self._thread is not None and not self._thread.is_alive():
            self._restart_background()

        # Ensure background system is ready
        self._start_background()

        # Reset reward tracker
        self._reward_tracker = RewardTracker(config=self._reward_config)

        # Start a new battle in background thread
        self._battle_over.clear()

        # Drain any stale action from the previous battle (the last
        # ``step()`` puts an action but returns ``truncated=True`` when
        # it detects ``_battle_over``, leaving the action in the queue).
        # If not drained, the new battle's first ``_choose_move_async``
        # picks up the stale action and processes it as if it were the
        # current battle's first action.
        while not self._action_queue.empty():
            try:
                self._action_queue.get_nowait()
            except Empty:
                break

        self._thread = threading.Thread(target=self._run_battle_background, daemon=True)
        self._thread.start()

        # Wait for first observation from the player
        try:
            obs, mask, battle = self._obs_queue.get(timeout=120.0)
        except Empty:
            logger.error(
                "Reset timed out waiting for first observation — battle thread may be stuck"
            )
            obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
            mask = [True] * NUM_ACTIONS
            battle = None

        if battle is not None:
            self._current_battle = battle
        self._action_mask = mask
        self._battle_count += 1
        self._turn_count = 0

        info: dict[str, Any] = {
            "action_mask": np.array(mask, dtype=np.bool_),
            "battle_count": self._battle_count,
        }
        return obs, info

    def step(
        self, action: int
    ) -> tuple[npt.NDArray[np.float32], float, bool, bool, dict[str, Any]]:
        """Execute an action and return the next observation.

        Parameters
        ----------
        action:
            Discrete action index (0-3: moves, 4-8: switches).

        Returns
        -------
        observation, reward, terminated, truncated, info
        """
        assert self._player is not None
        assert self._reward_tracker is not None

        # Send action to the player
        self._action_queue.put(action)

        # Wait for next observation or battle end.
        # Use a polling loop so we can detect the battle-over event
        # instead of blocking 120s on the queue for an obs that will
        # never arrive (the last action finished the battle).
        try:
            while True:
                try:
                    obs, mask, battle = self._obs_queue.get(timeout=0.5)
                except Empty:
                    if self._battle_over.is_set():
                        return self._terminal_result(reason="battle_over")
                    continue

                # Got an observation
                self._current_battle = battle
                self._action_mask = mask

                reward = compute_reward(battle, self._reward_tracker)
                self._turn_count += 1

                terminated = bool(getattr(battle, "finished", False))
                truncated = False

                # Anti-stall: force-end battles that run past max_turns.
                # Heuristic/random battles can occasionally drag on (or the
                # websocket drops mid-battle); without this cap a single
                # episode can stall the whole training/eval run.
                if not terminated and self._turn_count >= self._config.max_turns:
                    logger.warning(
                        "Battle exceeded max_turns=%d — force-terminating as loss",
                        self._config.max_turns,
                    )
                    return self._terminal_result(reason="max_turns")

                update_info: dict[str, Any] = {
                    "action_mask": np.array(mask, dtype=np.bool_),
                }

                if terminated:
                    won = bool(getattr(battle, "won", False))
                    update_info["won"] = won
                    reward = self._reward_tracker.step(
                        player_hp_sum=0.0,
                        opponent_hp_sum=0.0,
                        player_fainted=6,
                        opponent_fainted=6,
                        battle_finished=True,
                        won=won,
                    )
                    if self._thread is not None:
                        self._thread.join(timeout=10.0)

                return obs, reward, terminated, truncated, update_info

        except Empty:
            logger.warning("Battle timed out waiting for observation")
            return self._terminal_result(reason="timeout")

    def _terminal_result(
        self, *, reason: str
    ) -> tuple[npt.NDArray[np.float32], float, bool, bool, dict[str, Any]]:
        """Build the (obs, reward, terminated, truncated, info) tuple for an
        episode that ended without a fresh observation.

        This happens when the player's last action ended the battle: poke-env
        does not call ``choose_move`` again, so no terminal observation is ever
        queued. The true outcome must be read from ``self._current_battle``,
        which poke-env has already updated to ``finished``/``won``.

        Previously this path hardcoded ``loss_reward`` regardless of the
        actual result, which taught the agent it always lost and prevented
        any learning.
        """
        assert self._reward_tracker is not None
        obs = np.zeros(OBSERVATION_SIZE, dtype=np.float32)
        info: dict[str, Any] = {
            "action_mask": np.array([True] * NUM_ACTIONS, dtype=np.bool_),
            "terminal_reason": reason,
        }

        battle = self._current_battle
        finished = bool(getattr(battle, "finished", False))
        if finished:
            won = bool(getattr(battle, "won", False))
            info["won"] = won
            reward = self._reward_config.win_reward if won else self._reward_config.loss_reward
            # Make sure the reward tracker is advanced to the terminal state so
            # a subsequent reset starts from a clean slate.
            self._reward_tracker.step(
                player_hp_sum=0.0,
                opponent_hp_sum=0.0,
                player_fainted=6,
                opponent_fainted=6,
                battle_finished=True,
                won=won,
            )
        else:
            # Battle did not actually finish (genuine hang) — treat as a loss.
            info["won"] = False
            reward = self._reward_config.loss_reward

        if self._thread is not None:
            self._thread.join(timeout=10.0)

        return obs, reward, True, True, info

    def close(self) -> None:
        """Clean up resources."""
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        for player in (self._player, self._opponent):
            if player is not None:
                try:
                    player.ps_client.stop_listening()  # type: ignore[no-untyped-call]
                except Exception:
                    pass
        super().close()

    def render(self) -> str | None:
        """Render current battle state as text."""
        if self._current_battle is None:
            return None
        battle = self._current_battle
        active = getattr(battle, "active_pokemon", None)
        opp = getattr(battle, "opponent_active_pokemon", None)
        lines = [
            f"Turn {getattr(battle, 'turn', '?')}",
            f"  Player: {getattr(active, 'species', '?')} "
            f"HP={getattr(active, 'current_hp_fraction', 0):.0%}",
            f"  Opponent: {getattr(opp, 'species', '?')} "
            f"HP={getattr(opp, 'current_hp_fraction', 0):.0%}",
        ]
        return "\n".join(lines)


class _LoadedPolicyOpponent(Player):
    """A poke-env player driven by a loaded MaskablePPO policy.

    Used as an opponent in self-play or when comparing a freshly-trained
    policy against a frozen snapshot of a previous run. Falls back to
    a random move if the policy predict call raises.
    """

    def __init__(
        self,
        *,
        account_configuration: AccountConfiguration,
        server_configuration: ServerConfiguration,
        battle_format: str,
        model: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            battle_format=battle_format,
            **kwargs,
        )
        self._model = model

    def choose_move(self, battle: Any) -> Any:
        if isinstance(battle, DoubleBattle):
            logger.warning(
                "Opponent RL policy does not support doubles; using a legal random order"
            )
            return self.choose_random_move(battle)
        obs = encode_battle(battle)
        mask = _battle_action_mask(battle)
        try:
            action, _ = self._model.predict(obs, action_masks=mask, deterministic=True)
        except Exception:
            logger.exception("Opponent policy predict failed; using random move")
            return self.choose_random_move(battle)
        action = int(action)
        available_moves = battle.available_moves
        available_switches = battle.available_switches
        if action < 4 and action < len(available_moves):
            return self.create_order(available_moves[action])
        switch_idx = action - 4
        if switch_idx < len(available_switches):
            return self.create_order(available_switches[switch_idx])
        if available_moves:
            return self.create_order(available_moves[0])
        if available_switches:
            return self.create_order(available_switches[0])
        return self.choose_random_move(battle)


def _battle_action_mask(battle: Any) -> npt.NDArray[np.bool_]:
    """Standalone action-mask builder (mirrors RLPlayer._compute_action_mask)."""
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


def _is_doubles_format(format_id: str) -> bool:
    from pokecore.formats import get_format

    try:
        return get_format(format_id).active_slots > 1
    except KeyError:
        return False
