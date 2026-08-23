from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class NoiseTrader(Agent):
    """Zero-intelligence trader: submits random limit orders within a band around a
    fixed reference price, at Poisson-process arrival times. No view on value, no
    reaction to the book -- this is the baseline liquidity/order-flow generator.
    """

    def __init__(
        self,
        agent_id: int,
        reference_price: int,
        price_band_ticks: int,
        min_quantity: int,
        max_quantity: int,
        arrival_rate: float,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, seed)
        self.reference_price = reference_price
        self.price_band_ticks = price_band_ticks
        self.min_quantity = min_quantity
        self.max_quantity = max_quantity
        self.arrival_rate = arrival_rate

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return sim_time + self.rng.expovariate(self.arrival_rate)

    def act(self, sim_time: float, market: MarketAccess) -> None:
        side = self.rng.choice([Side.BUY, Side.SELL])
        offset = self.rng.randint(-self.price_band_ticks, self.price_band_ticks)
        price = max(1, self.reference_price + offset)
        quantity = self.rng.randint(self.min_quantity, self.max_quantity)
        market.submit_limit(self.agent_id, side, price, quantity)
