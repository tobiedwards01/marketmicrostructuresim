import pytest

from mm_sim.agents.rl_market_maker import QLearningMarketMaker
from mm_sim.event_loop import EventLoop
from mm_sim.models import Side


def make_agent(**overrides):
    defaults = dict(
        agent_id=1,
        reference_price=10_000,
        horizon=100.0,
        quote_size=10,
        max_inventory=20,
        requote_interval=0.5,
        learning_rate=0.5,
        discount_factor=0.9,
        epsilon=0.0,
        seed=1,
    )
    defaults.update(overrides)
    return QLearningMarketMaker(**defaults)


class TestInventoryBucketing:
    def test_boundaries(self):
        agent = make_agent(max_inventory=20)
        # edges at fractions -0.6, -0.2, 0.2, 0.6 of max_inventory=20 -> -12, -4, 4, 12
        assert agent._bucket_inventory(-20) == 0
        assert agent._bucket_inventory(-13) == 0
        assert agent._bucket_inventory(-10) == 1
        assert agent._bucket_inventory(0) == 2
        assert agent._bucket_inventory(10) == 3
        assert agent._bucket_inventory(13) == 4
        assert agent._bucket_inventory(20) == 4


class TestTimeBucketing:
    def test_boundaries(self):
        agent = make_agent(horizon=100.0)
        assert agent._bucket_time(0.0) == 0  # 100% remaining
        assert agent._bucket_time(30.0) == 0  # 70% remaining
        assert agent._bucket_time(40.0) == 1  # 60% remaining
        assert agent._bucket_time(70.0) == 2  # 30% remaining
        assert agent._bucket_time(99.0) == 2  # 1% remaining


class TestActionDecoding:
    def test_all_actions_decode_to_distinct_pairs_within_the_configured_grid(self):
        agent = make_agent()
        pairs = {agent._decode_action(a) for a in range(agent.n_actions)}

        assert len(pairs) == agent.n_actions
        for half_spread, skew in pairs:
            assert half_spread in agent.HALF_SPREAD_CHOICES
            assert skew in agent.SKEW_CHOICES


class TestActionSelection:
    def test_epsilon_zero_always_picks_the_single_best_action(self):
        agent = make_agent(epsilon=0.0, seed=1)
        state = (2, 0)
        agent.q_table[state] = [0.0] * agent.n_actions
        agent.q_table[state][7] = 5.0

        chosen = {agent._select_action(state) for _ in range(20)}
        assert chosen == {7}

    def test_epsilon_one_explores_and_visits_multiple_actions(self):
        agent = make_agent(epsilon=1.0, seed=1)
        state = (2, 0)
        agent.q_table[state] = [0.0] * agent.n_actions
        agent.q_table[state][7] = 5.0

        chosen = {agent._select_action(state) for _ in range(50)}
        assert len(chosen) > 1  # not always exploiting the single best action


class TestQTableUpdate:
    def test_update_matches_hand_computed_td_target(self):
        agent = make_agent(
            reference_price=10_000, horizon=100.0, max_inventory=20,
            quote_size=10, requote_interval=0.5, learning_rate=0.5, discount_factor=0.9, epsilon=0.0,
        )
        state0 = (2, 0)  # inventory=0 -> bucket 2, sim_time=0 -> bucket 0
        state1 = (3, 0)  # inventory=10 (of max 20) -> bucket 3, sim_time=0.5 -> still bucket 0
        agent.q_table[state0] = [0.0] * agent.n_actions
        agent.q_table[state0][12] = 1.0  # half_spread=15, skew=0 -- the unique best action at state0
        agent.q_table[state1] = [0.0] * agent.n_actions
        agent.q_table[state1][5] = 2.0  # unique best action at state1

        loop = EventLoop([agent])
        agent.act(loop.time, loop)  # t=0: no previous state yet, just picks action 12 and quotes 9985/10015

        assert agent._last_state == state0
        assert agent._last_action == 12

        # another agent sells into our bid at 9985, filling it fully
        loop.submit_limit(agent_id=2, side=Side.SELL, price=1, quantity=10)

        loop.time = 0.5
        agent.act(loop.time, loop)  # t=0.5: syncs the fill, updates q_table[state0][12], picks new action at state1

        assert agent.inventory == 10
        assert agent.cash == pytest.approx(-9985 * 10)

        # mid is undefined after this call (both sides empty/cancelled), so mark-to-market
        # falls back to reference_price=10_000: mtm = cash + inventory*10_000
        expected_mtm = -9985 * 10 + 10 * 10_000
        reward = expected_mtm - 0.0  # previous mtm was 0 (flat, no cash)
        expected_best_next = 2.0  # max(q_table[state1])
        expected_td_target = reward + 0.9 * expected_best_next
        expected_q = 1.0 + 0.5 * (expected_td_target - 1.0)

        assert agent.q_table[state0][12] == pytest.approx(expected_q)
        assert agent._last_state == state1

    def test_visiting_a_state_increments_its_visit_count(self):
        agent = make_agent()
        agent.q_table[(2, 0)] = [0.0] * agent.n_actions
        loop = EventLoop([agent])

        agent.act(loop.time, loop)
        loop.time = 0.5
        agent.act(loop.time, loop)

        assert agent.visit_counts[(2, 0)] == 2


class TestResetEpisode:
    def test_clears_episode_state_but_not_the_q_table_or_visit_counts(self):
        agent = make_agent()
        agent.q_table[(2, 0)] = [1.0] * agent.n_actions
        agent.visit_counts[(2, 0)] = 5
        agent.inventory = 15
        agent.cash = -500.0
        agent._bid_order_id = 42
        agent._ask_order_id = 43
        agent._trade_log_cursor = 7
        agent._last_state = (2, 0)
        agent._last_action = 3
        agent._last_mark_to_market = 12.5

        agent.reset_episode()

        assert agent.inventory == 0
        assert agent.cash == 0.0
        assert agent._bid_order_id is None
        assert agent._ask_order_id is None
        assert agent._trade_log_cursor == 0
        assert agent._last_state is None
        assert agent._last_action is None
        assert agent._last_mark_to_market is None
        assert agent.q_table[(2, 0)] == [1.0] * agent.n_actions  # untouched
        assert agent.visit_counts[(2, 0)] == 5  # untouched


class TestSaveLoad:
    def test_round_trips_the_q_table_and_visit_counts(self, tmp_path):
        agent = make_agent()
        agent.q_table[(0, 0)] = [1.0, 2.0, 3.0] + [0.0] * (agent.n_actions - 3)
        agent.q_table[(4, 2)] = [0.5] * agent.n_actions
        agent.visit_counts[(0, 0)] = 12
        agent.visit_counts[(4, 2)] = 3

        path = tmp_path / "model.json"
        agent.save(path)

        loaded = make_agent()
        loaded.load(path)

        assert loaded.q_table == agent.q_table
        assert loaded.visit_counts == agent.visit_counts


class TestGreedyQuotes:
    def test_uses_learned_action_without_mutating_state(self):
        agent = make_agent()
        state = (agent._bucket_inventory(0), agent._bucket_time(10.0))
        agent.q_table[state] = [0.0] * agent.n_actions
        agent.q_table[state][0] = 10.0  # HALF_SPREAD_CHOICES[0]=5, SKEW_CHOICES[0]=-10

        bid, ask = agent.greedy_quotes(mid_price=10_000, inventory=0, sim_time=10.0)

        assert bid == 10_000 - 5 - (-10)
        assert ask == 10_000 + 5 - (-10)
        assert agent._last_state is None  # no side effects
        assert agent.inventory == 0
