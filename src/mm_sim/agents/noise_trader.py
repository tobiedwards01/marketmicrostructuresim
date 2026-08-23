from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class NoiseTrader(Agent):
    """Zero-intelligence trader: submits random limit orders within a band around
    the current mid price (falling back to a reference price if the book is empty),
    at Poisson-process arrival times. No view on value beyond "wherever the market
    currently is" -- this is the baseline liquidity/order-flow generator.
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
        mid = market.book.mid_price
        center = round(mid) if mid is not None else self.reference_price

        side = self.rng.choice([Side.BUY, Side.SELL])
        offset = self.rng.randint(-self.price_band_ticks, self.price_band_ticks)
        price = max(1, center + offset)
        quantity = self.rng.randint(self.min_quantity, self.max_quantity)
        market.submit_limit(self.agent_id, side, price, quantity)
