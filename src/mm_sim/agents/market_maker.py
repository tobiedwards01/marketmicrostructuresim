from typing import Optional

from mm_sim.agents.quoting_base import QuotingAgent
from mm_sim.market_access import MarketAccess


class NaiveMarketMaker(QuotingAgent):
    """Quotes a fixed spread around the current mid price (falling back to a
    reference price if the book is empty). Stops quoting a side once its
    inventory limit on that side is hit -- no inventory skewing, that's
    Avellaneda-Stoikov/Q-learning territory (Phase 5).
    """

    def __init__(
        self,
        agent_id: int,
        reference_price: int,
        half_spread_ticks: int,
        quote_size: int,
        max_inventory: int,
        requote_interval: float,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, quote_size, max_inventory, requote_interval, seed)
        self.reference_price = reference_price
        self.half_spread_ticks = half_spread_ticks

    def _choose_quotes(self, sim_time: float, market: MarketAccess) -> tuple[int, int]:
        mid = market.book.mid_price
        center = round(mid) if mid is not None else self.reference_price
        bid_price = max(1, center - self.half_spread_ticks)
        ask_price = center + self.half_spread_ticks
        return bid_price, ask_price
