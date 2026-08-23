from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class NoiseTrader(Agent):
    """Zero-intelligence trader (Gode & Sunder 1993 style): submits one random
    limit order within a band around the current mid price (falling back to a
    reference price if the book is empty) at Poisson-process arrival times,
    cancelling its own previous order first. No view on value beyond "wherever
    the market currently is" -- this is the baseline liquidity/order-flow
    generator.

    One live order per trader, replaced each wake, matters for more than
    tidiness: without it, old resting orders never expire, so book depth grows
    unboundedly, and as the market drifts a trader's own new order can end up
    priced on the wrong side of its own stale one -- self-trade prevention then
    correctly refuses to match them, but leaves both resting, which can make
    best_bid/best_ask momentarily report a "locked" price from one agent's own
    crossed quotes (see DECISIONS.md).
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
        self._resting_order_id: Optional[int] = None

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return sim_time + self.rng.expovariate(self.arrival_rate)

    def act(self, sim_time: float, market: MarketAccess) -> None:
        if self._resting_order_id is not None:
            market.cancel(self._resting_order_id)
            self._resting_order_id = None

        mid = market.book.mid_price
        center = round(mid) if mid is not None else self.reference_price

        side = self.rng.choice([Side.BUY, Side.SELL])
        offset = self.rng.randint(-self.price_band_ticks, self.price_band_ticks)
        price = max(1, center + offset)
        quantity = self.rng.randint(self.min_quantity, self.max_quantity)
        order, _ = market.submit_limit(self.agent_id, side, price, quantity)
        if order.remaining > 0:
            self._resting_order_id = order.order_id
