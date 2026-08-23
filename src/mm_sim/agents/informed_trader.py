from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class InformedTrader(Agent):
    """Has noisy access to a private random-walk "true price" -- something the rest
    of the market can't see -- and trades aggressively (market orders) whenever the
    book's best quotes have drifted far enough from it. This is the source of
    adverse selection: it systematically picks off stale quotes.

    The true-price process lives inside this agent for now (Phase 2 baseline). Once
    Phase 4 wants to measure adverse selection against a *known* ground truth, this
    should move to a process the simulation owns and can compare against -- see
    DECISIONS.md.
    """

    def __init__(
        self,
        agent_id: int,
        initial_true_price: int,
        true_price_volatility: float,
        signal_noise_std: float,
        edge_threshold: int,
        quantity: int,
        arrival_rate: float,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, seed)
        self.true_price = initial_true_price
        self.true_price_volatility = true_price_volatility
        self.signal_noise_std = signal_noise_std
        self.edge_threshold = edge_threshold
        self.quantity = quantity
        self.arrival_rate = arrival_rate

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return sim_time + self.rng.expovariate(self.arrival_rate)

    def _step_true_price(self) -> int:
        self.true_price = max(1, self.true_price + round(self.rng.gauss(0, self.true_price_volatility)))
        return self.true_price

    def act(self, sim_time: float, market: MarketAccess) -> None:
        true_price = self._step_true_price()
        signal = true_price + round(self.rng.gauss(0, self.signal_noise_std))

        best_ask = market.book.best_ask
        best_bid = market.book.best_bid

        if best_ask is not None and signal - best_ask >= self.edge_threshold:
            market.submit_market(self.agent_id, Side.BUY, self.quantity)
        elif best_bid is not None and best_bid - signal >= self.edge_threshold:
            market.submit_market(self.agent_id, Side.SELL, self.quantity)
