"""RL-compatible poke-env player.

Bridges the async poke-env battle loop with a synchronous Gymnasium
environment. The player puts battle states into a queue and blocks
until the environment pushes an action back.

Requires: ``poke-env``, ``gymnasium`` (available with ``[train]`` extra).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from queue import Empty, Queue
from typing import Any

from poke_env.battle.abstract_battle import AbstractBattle
from poke_env.battle.double_battle import DoubleBattle
from poke_env.player.battle_order import BattleOrder
from poke_env.player.player import Player
from poke_env.ps_client.account_configuration import AccountConfiguration
from poke_env.ps_client.server_configuration import ServerConfiguration

from pokerl.encoder import encode_battle

logger = logging.getLogger(__name__)

# Sentinel for shutdown
_STOP = object()

# Max actions: 4 moves + 5 switches
NUM_ACTIONS: int = 9

# Max consecutive 60s action-timeouts before the player gives up and
# returns a random move (prevents an infinite retry hang on a dead env).
MAX_ACTION_WAITS: int = 5


class RLPlayer(Player):
    """A poke-env player driven by external action selection (Gymnasium env).

    On each turn, ``choose_move`` encodes the battle state and puts it
    into ``obs_queue``. It then blocks on ``action_queue`` waiting for
    the environment to provide an action index. The action is mapped to
    a legal BattleOrder and returned to poke-env.

    Parameters
    ----------
    obs_queue:
        Queue where (observation, action_mask, battle) tuples are placed.
    action_queue:
        Queue where integer action indices are received.
    reward_queue:
        Queue where (reward, done, info) tuples are placed after each turn.
    """

    def __init__(
        self,
        obs_queue: Queue[Any],
        action_queue: Queue[int | object],
        *,
        account_configuration: AccountConfiguration | None = None,
        server_configuration: ServerConfiguration | None = None,
        battle_format: str = "gen9randombattle",
        **kwargs: Any,
    ) -> None:
        self._obs_queue = obs_queue
        self._action_queue = action_queue
        acct = account_configuration or AccountConfiguration("RLPlayer", "")
        server_cfg = server_configuration or ServerConfiguration(
            "ws://localhost:8000/showdown/websocket",
            "http://localhost:8000/action.php?",
        )
        super().__init__(
            account_configuration=acct,
            server_configuration=server_cfg,
            battle_format=battle_format,
            **kwargs,
        )

    def choose_move(self, battle: AbstractBattle) -> Awaitable[BattleOrder]:
        """Encode state, wait for action, return order."""
        return self._choose_move_async(battle)

    async def _choose_move_async(self, battle: AbstractBattle) -> BattleOrder:
        """Async implementation of move choice."""
        if isinstance(battle, DoubleBattle):
            logger.warning("RLPlayer does not support doubles; using a legal random order")
            return self.choose_random_move(battle)
        # Encode observation
        obs = encode_battle(battle)

        # Compute action mask (which actions are legal)
        action_mask = self._compute_action_mask(battle)

        # Put observation into queue for the env to read
        self._obs_queue.put((obs, action_mask, battle))

        # Wait for action from the environment
        # Use a polling loop to avoid blocking the event loop forever
        action: int | object = await asyncio.get_event_loop().run_in_executor(
            None, self._wait_for_action
        )

        if action is _STOP:
            # Graceful shutdown — pick random
            return self.choose_random_move(battle)

        # sb3's Discrete env.step passes a numpy int (np.int64) which is not
        # a subclass of Python int. Cast defensively so the queue bridge
        # works for both raw gym envs and sb3's VecEnv wrappers.
        return self._action_to_order(int(action), battle)  # type: ignore[arg-type]

    def _wait_for_action(self) -> int | object:
        """Block until an action is available (called in executor).

        Bounds the total wait so a dead env (e.g. a dropped websocket that
        left the battle thread unable to resume) cannot hang the player
        forever and deadlock the training/eval loop. After
        ``MAX_ACTION_WAITS`` timeouts we give up and return a random move,
        letting poke-env resolve the battle instead of stalling.
        """
        for _ in range(MAX_ACTION_WAITS):
            try:
                return self._action_queue.get(timeout=60.0)
            except Empty:
                logger.warning("RLPlayer: Timeout waiting for action, retrying...")
                continue
        logger.error(
            "RLPlayer: gave up waiting for action after %d timeouts; "
            "returning a random move to avoid a hang",
            MAX_ACTION_WAITS,
        )
        return _STOP

    def _compute_action_mask(self, battle: AbstractBattle) -> list[bool]:
        """Compute which of the 9 actions are legal.

        Actions 0-3: moves[0..3]
        Actions 4-8: switches[0..4]
        """
        mask = [False] * NUM_ACTIONS

        # Available moves
        available_moves = battle.available_moves
        for i in range(min(len(available_moves), 4)):
            mask[i] = True

        # Available switches
        available_switches = battle.available_switches
        for i in range(min(len(available_switches), 5)):
            mask[4 + i] = True

        # If nothing is legal (force switch with no options), allow first move
        if not any(mask):
            # Struggle case or forced action
            if available_moves:
                mask[0] = True
            elif available_switches:
                mask[4] = True

        return mask

    def _action_to_order(self, action: int, battle: AbstractBattle) -> BattleOrder:
        """Convert a discrete action index to a poke-env BattleOrder.

        Falls back to random if the action is somehow invalid.
        """
        available_moves = battle.available_moves
        available_switches = battle.available_switches

        if action < 4:
            # Move action
            move_idx = action
            if move_idx < len(available_moves):
                return self.create_order(available_moves[move_idx])
        else:
            # Switch action
            switch_idx = action - 4
            if switch_idx < len(available_switches):
                return self.create_order(available_switches[switch_idx])

        # Fallback: pick any legal action
        if available_moves:
            return self.create_order(available_moves[0])
        if available_switches:
            return self.create_order(available_switches[0])
        return self.choose_random_move(battle)
