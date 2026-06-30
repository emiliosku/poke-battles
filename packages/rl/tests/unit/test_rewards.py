"""Unit tests for the reward shaping module."""

from __future__ import annotations

from types import SimpleNamespace

from pokerl.rewards import RewardConfig, RewardTracker, compute_reward


def _make_mon(hp: float = 1.0, fainted: bool = False) -> SimpleNamespace:
    return SimpleNamespace(current_hp_fraction=hp, fainted=fainted)


def _make_battle(
    *,
    team_hp: list[float] | None = None,
    opp_hp: list[float] | None = None,
    finished: bool = False,
    won: bool = False,
) -> SimpleNamespace:
    team_hp = team_hp or [1.0] * 6
    opp_hp = opp_hp or [1.0] * 6

    team = {f"mon{i}": _make_mon(hp=hp, fainted=(hp <= 0.0)) for i, hp in enumerate(team_hp)}
    opp_team = {f"opp{i}": _make_mon(hp=hp, fainted=(hp <= 0.0)) for i, hp in enumerate(opp_hp)}
    return SimpleNamespace(
        team=team,
        opponent_team=opp_team,
        finished=finished,
        won=won,
    )


class TestRewardTracker:
    """Test RewardTracker step-by-step reward computation."""

    def test_no_change_gives_turn_penalty(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=6.0,
            opponent_hp_sum=6.0,
            player_fainted=0,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )
        # Only turn penalty
        assert abs(reward - config.turn_penalty) < 1e-7

    def test_dealing_damage_gives_positive_reward(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=6.0,
            opponent_hp_sum=5.0,  # opponent lost 1.0 HP
            player_fainted=0,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )
        expected = config.hp_damage_reward * 1.0 + config.turn_penalty
        assert abs(reward - expected) < 1e-7

    def test_taking_damage_gives_negative_reward(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=5.5,  # lost 0.5 HP
            opponent_hp_sum=6.0,
            player_fainted=0,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )
        expected = config.hp_loss_penalty * 0.5 + config.turn_penalty
        assert abs(reward - expected) < 1e-7

    def test_ko_gives_bonus(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=6.0,
            opponent_hp_sum=5.0,
            player_fainted=0,
            opponent_fainted=1,  # KO'd one opponent
            battle_finished=False,
            won=None,
        )
        expected = config.hp_damage_reward * 1.0 + config.ko_reward * 1 + config.turn_penalty
        assert abs(reward - expected) < 1e-7

    def test_own_faint_gives_penalty(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=5.0,
            opponent_hp_sum=6.0,
            player_fainted=1,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )
        expected = config.hp_loss_penalty * 1.0 + config.faint_reward * 1 + config.turn_penalty
        assert abs(reward - expected) < 1e-7

    def test_win_terminal_reward(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=3.0,
            opponent_hp_sum=0.0,
            player_fainted=3,
            opponent_fainted=6,
            battle_finished=True,
            won=True,
        )
        assert reward == config.win_reward

    def test_loss_terminal_reward(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        reward = tracker.step(
            player_hp_sum=0.0,
            opponent_hp_sum=3.0,
            player_fainted=6,
            opponent_fainted=3,
            battle_finished=True,
            won=False,
        )
        assert reward == config.loss_reward

    def test_multi_step_accumulation(self):
        """Rewards accumulate correctly over multiple steps."""
        config = RewardConfig()
        tracker = RewardTracker(config=config)

        # Step 1: deal some damage
        r1 = tracker.step(
            player_hp_sum=6.0,
            opponent_hp_sum=5.5,
            player_fainted=0,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )

        # Step 2: deal more damage
        r2 = tracker.step(
            player_hp_sum=5.8,
            opponent_hp_sum=4.5,
            player_fainted=0,
            opponent_fainted=0,
            battle_finished=False,
            won=None,
        )

        # r2 should account for delta from step1 state
        assert r1 > 0  # dealt damage
        # r2: dealt 1.0 damage, took 0.2 damage
        expected_r2 = (
            config.hp_damage_reward * 1.0 + config.hp_loss_penalty * 0.2 + config.turn_penalty
        )
        assert abs(r2 - expected_r2) < 1e-7


class TestComputeReward:
    """Test the convenience compute_reward function."""

    def test_full_hp_no_change(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        battle = _make_battle()
        reward = compute_reward(battle, tracker)
        assert abs(reward - config.turn_penalty) < 1e-7

    def test_win_detection(self):
        config = RewardConfig()
        tracker = RewardTracker(config=config)
        battle = _make_battle(
            team_hp=[0.5, 1.0, 0.0, 0.0, 0.0, 0.0],
            opp_hp=[0.0] * 6,
            finished=True,
            won=True,
        )
        reward = compute_reward(battle, tracker)
        assert reward == config.win_reward


class TestRewardConfig:
    """Test reward config defaults and customization."""

    def test_defaults(self):
        config = RewardConfig()
        assert config.win_reward == 1.0
        assert config.loss_reward == -1.0
        assert config.faint_reward < 0
        assert config.ko_reward > 0

    def test_custom_values(self):
        config = RewardConfig(win_reward=10.0, ko_reward=2.0)
        assert config.win_reward == 10.0
        assert config.ko_reward == 2.0
