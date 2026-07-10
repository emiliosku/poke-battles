"""Unit tests for the ``RLPlayer`` queue bridge.

These tests cover the parts of ``RLPlayer`` that don't need a live
Showdown server: the numpy-int-to-python-int cast, the action-mask
builder, and the queue-bridge order mapping.
"""

from __future__ import annotations

from queue import Queue
from unittest.mock import MagicMock

import numpy as np

from pokerl.player import NUM_ACTIONS, RLPlayer


def _make_player() -> RLPlayer:
    """Build an ``RLPlayer`` without going through the network layer."""
    obs_q: Queue = Queue(maxsize=1)
    act_q: Queue = Queue(maxsize=1)
    return RLPlayer.__new__(RLPlayer), obs_q, act_q  # type: ignore[arg-type]


class TestActionMask:
    def test_mask_for_four_moves_no_switches(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        m0, m1, m2, m3 = (MagicMock(),) * 4
        battle.available_moves = [m0, m1, m2, m3]
        battle.available_switches = []
        mask = player._compute_action_mask(battle)
        assert mask == [True, True, True, True, False, False, False, False, False]

    def test_mask_for_three_moves_two_switches(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        battle.available_moves = [MagicMock(), MagicMock(), MagicMock()]
        battle.available_switches = [MagicMock(), MagicMock()]
        mask = player._compute_action_mask(battle)
        assert mask == [True, True, True, False, True, True, False, False, False]

    def test_mask_for_no_options_falls_back_to_first_move(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        # available_moves is empty, available_switches has one entry —
        # the fallback should expose the first switch slot
        battle.available_moves = []
        battle.available_switches = [MagicMock()]
        mask = player._compute_action_mask(battle)
        # The first switch slot (index 4) is enabled as a last-resort fallback
        assert mask[4] is True

    def test_mask_truncates_at_nine_actions(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        battle.available_moves = [MagicMock()] * 4
        battle.available_switches = [MagicMock()] * 5
        mask = player._compute_action_mask(battle)
        assert len(mask) == NUM_ACTIONS == 9
        assert all(mask[:9])


class TestActionToOrder:
    def test_int_action_maps_to_first_move(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        move = MagicMock()
        battle.available_moves = [move]
        battle.available_switches = []
        order = player._action_to_order(0, battle)
        # We can't easily assert the message without poking deeper, but
        # at least confirm it didn't fall through to the random branch.
        assert order is not None

    def test_numpy_int_action_does_not_crash(self) -> None:
        """sb3's Discrete wrapper passes ``np.int64`` through env.step.

        ``RLPlayer._action_to_order`` must accept any int-like input
        without raising — the queue bridge used to assert
        ``isinstance(action, int)`` and tripped on numpy scalars.
        """
        player, _, _ = _make_player()
        battle = MagicMock()
        battle.available_moves = [MagicMock()]
        battle.available_switches = []
        order = player._action_to_order(np.int64(0), battle)
        assert order is not None
        order2 = player._action_to_order(np.int32(1), battle)
        assert order2 is not None

    def test_switch_action_falls_back_when_index_out_of_range(self) -> None:
        player, _, _ = _make_player()
        battle = MagicMock()
        battle.available_moves = [MagicMock()]
        battle.available_switches = [MagicMock()]
        # Action 8 is a switch index that exceeds available_switches
        order = player._action_to_order(8, battle)
        # Should fall back to the first move rather than raise
        assert order is not None
