import json
from pathlib import Path
from typing import Optional

from mm_sim.agents.quoting_base import QuotingAgent
from mm_sim.market_access import MarketAccess


class QLearningMarketMaker(QuotingAgent):
    """Tabular Q-learning market maker (per the brief: start simple, no
    PyTorch/deep RL needed for a state space this small).

    State = (inventory bucket, time-remaining bucket). Action = (half-spread
    choice, skew choice) from a small discrete grid, deliberately mirroring
    Avellaneda-Stoikov's own two decision variables -- spread driven by
    time-to-horizon, reservation-price-style skew driven by inventory -- so
    the eventual comparison between what this agent learns and AS's closed
    form is apples-to-apples (see examples/compare_rl_vs_avellaneda_stoikov.py).

    Reward each wake is the change in mark-to-market P&L since the last
    decision: cash flow from any fills, plus any change in the value of
    inventory already held, from mid-price movement. Using mark-to-market
    (not just realized cash) is what makes inventory risk show up as a real,
    learnable cost -- an agent that lets inventory balloon and then the price
    moves against it actually experiences that as negative reward, without
    needing a hand-tuned penalty term.
    """

    HALF_SPREAD_CHOICES = (5, 10, 15, 20, 30)
    SKEW_CHOICES = (-10, -5, 0, 5, 10)
    N_INVENTORY_BUCKETS = 5
    N_TIME_BUCKETS = 3
    _INVENTORY_BUCKET_EDGES = (-0.6, -0.2, 0.2, 0.6)  # as a fraction of max_inventory

    def __init__(
        self,
        agent_id: int,
        reference_price: int,
        horizon: float,
        quote_size: int,
        max_inventory: int,
        requote_interval: float,
        learning_rate: float = 0.1,
        discount_factor: float = 0.95,
        epsilon: float = 0.1,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, quote_size, max_inventory, requote_interval, seed)
        self.reference_price = reference_price
        self.horizon = horizon
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.q_table: dict[tuple[int, int], list[float]] = {}
        self.visit_counts: dict[tuple[int, int], int] = {}
        self._last_state: Optional[tuple[int, int]] = None
        self._last_action: Optional[int] = None
        self._last_mark_to_market: Optional[float] = None

    @property
    def n_actions(self) -> int:
        return len(self.HALF_SPREAD_CHOICES) * len(self.SKEW_CHOICES)

    def _decode_action(self, action: int) -> tuple[int, int]:
        spread_idx, skew_idx = divmod(action, len(self.SKEW_CHOICES))
        return self.HALF_SPREAD_CHOICES[spread_idx], self.SKEW_CHOICES[skew_idx]

    def _bucket_inventory(self, inventory: int) -> int:
        frac = inventory / self.max_inventory if self.max_inventory else 0.0
        bucket = 0
        for edge in self._INVENTORY_BUCKET_EDGES:
            if frac > edge:
                bucket += 1
        return bucket

    def _bucket_time(self, sim_time: float) -> int:
        frac_remaining = max(0.0, (self.horizon - sim_time) / self.horizon) if self.horizon > 0 else 0.0
        if frac_remaining > 0.66:
            return 0
        if frac_remaining > 0.33:
            return 1
        return 2

    def _state(self, sim_time: float) -> tuple[int, int]:
        return self._bucket_inventory(self.inventory), self._bucket_time(sim_time)

    def _q_values(self, state: tuple[int, int]) -> list[float]:
        if state not in self.q_table:
            self.q_table[state] = [0.0] * self.n_actions
        return self.q_table[state]

    def _select_action(self, state: tuple[int, int]) -> int:
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(self.n_actions)
        q_values = self._q_values(state)
        best = max(q_values)
        best_actions = [a for a, v in enumerate(q_values) if v == best]
        return self.rng.choice(best_actions)  # break ties randomly, not always the first

    def _quotes_for_action(self, center: float, action: int) -> tuple[int, int]:
        half_spread, skew = self._decode_action(action)
        bid_price = max(1, round(center - half_spread - skew))
        ask_price = max(bid_price + 1, round(center + half_spread - skew))
        return bid_price, ask_price

    def _choose_quotes(self, sim_time: float, market: MarketAccess) -> tuple[int, int]:
        mid = market.book.mid_price
        center = mid if mid is not None else float(self.reference_price)
        current_mtm = self.mark_to_market(center)
        state = self._state(sim_time)
        self.visit_counts[state] = self.visit_counts.get(state, 0) + 1

        if self._last_state is not None:
            reward = current_mtm - self._last_mark_to_market
            q_values = self._q_values(self._last_state)
            best_next = max(self._q_values(state))
            td_target = reward + self.discount_factor * best_next
            q_values[self._last_action] += self.learning_rate * (td_target - q_values[self._last_action])

        action = self._select_action(state)
        self._last_state = state
        self._last_action = action
        self._last_mark_to_market = current_mtm

        return self._quotes_for_action(center, action)

    def greedy_quotes(self, mid_price: float, inventory: int, sim_time: float) -> tuple[int, int]:
        """This agent's learned quotes for a given (inventory, time), greedy
        (no exploration) and with no side effects on training state -- used for
        the Avellaneda-Stoikov comparison, not live trading.
        """
        state = (self._bucket_inventory(inventory), self._bucket_time(sim_time))
        q_values = self.q_table.get(state, [0.0] * self.n_actions)
        best_action = max(range(self.n_actions), key=lambda a: q_values[a])
        return self._quotes_for_action(mid_price, best_action)

    def reset_episode(self) -> None:
        """Clear per-episode state (inventory, cash, resting order ids, the
        pending (state, action) waiting for a reward) WITHOUT touching the
        learned Q-table. Call between training episodes -- learning carries
        over, but stale order ids/inventory from the previous episode's now-
        defunct book must not.
        """
        self.inventory = 0
        self.cash = 0.0
        self._bid_order_id = None
        self._ask_order_id = None
        self._trade_log_cursor = 0
        self._last_state = None
        self._last_action = None
        self._last_mark_to_market = None

    def save(self, path: Path) -> None:
        serializable_q = {f"{inv},{t}": values for (inv, t), values in self.q_table.items()}
        serializable_counts = {f"{inv},{t}": n for (inv, t), n in self.visit_counts.items()}
        payload = {
            "q_table": serializable_q,
            "visit_counts": serializable_counts,
            "half_spread_choices": list(self.HALF_SPREAD_CHOICES),
            "skew_choices": list(self.SKEW_CHOICES),
        }
        Path(path).write_text(json.dumps(payload, indent=2))

    def load(self, path: Path) -> None:
        payload = json.loads(Path(path).read_text())
        self.q_table = {
            tuple(int(x) for x in key.split(",")): values for key, values in payload["q_table"].items()
        }
        self.visit_counts = {
            tuple(int(x) for x in key.split(",")): n for key, n in payload.get("visit_counts", {}).items()
        }
