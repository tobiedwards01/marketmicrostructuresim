from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class NaiveMarketMaker(Agent):
    """Quotes a fixed spread around the current mid price (falling back to a
    reference price if the book is empty), re-quoting both sides at a fixed
    interval. Stops quoting a side once its inventory limit on that side is hit --
    no inventory skewing yet, that's Avellaneda-Stoikov territory (Phase 5).
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
        super().__init__(agent_id, seed)
        self.reference_price = reference_price
        self.half_spread_ticks = half_spread_ticks
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.requote_interval = requote_interval
        self.inventory = 0
        self._bid_order_id: Optional[int] = None
        self._ask_order_id: Optional[int] = None
        self._trade_log_cursor = 0  # how far into market.trade_log we've already reconciled

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return sim_time + self.requote_interval

    def act(self, sim_time: float, market: MarketAccess) -> None:
        self._cancel_stale_quotes(market)
        # Reconcile fills from other agents trading against our resting quotes since
        # last wake BEFORE deciding whether to quote -- otherwise the inventory limit
        # below is checked against a stale number and only takes effect one cycle late.
        self._sync_inventory(market)

        mid = market.book.mid_price
        center = round(mid) if mid is not None else self.reference_price

        if self.inventory < self.max_inventory:
            bid_price = max(1, center - self.half_spread_ticks)
            order, _ = market.submit_limit(self.agent_id, Side.BUY, bid_price, self.quote_size)
            if order.remaining > 0:
                self._bid_order_id = order.order_id

        if self.inventory > -self.max_inventory:
            ask_price = center + self.half_spread_ticks
            order, _ = market.submit_limit(self.agent_id, Side.SELL, ask_price, self.quote_size)
            if order.remaining > 0:
                self._ask_order_id = order.order_id

        self._sync_inventory(market)  # catch any fill from the submissions just above

    def _cancel_stale_quotes(self, market: MarketAccess) -> None:
        if self._bid_order_id is not None:
            market.cancel(self._bid_order_id)
            self._bid_order_id = None
        if self._ask_order_id is not None:
            market.cancel(self._ask_order_id)
            self._ask_order_id = None

    def _sync_inventory(self, market: MarketAccess) -> None:
        """Reconcile inventory against every trade since we last checked -- not just
        ones from this agent's own submissions above, but also fills that happened
        to our resting quotes because some OTHER agent traded against them between
        wakes. The trade's own return value only tells you about the former; the
        shared trade log is the only place that captures both.
        """
        trade_log = market.trade_log
        for trade in trade_log[self._trade_log_cursor :]:
            if trade.maker_agent_id == self.agent_id:
                self.inventory += trade.quantity if trade.aggressor_side is Side.SELL else -trade.quantity
            elif trade.taker_agent_id == self.agent_id:
                self.inventory += trade.quantity if trade.aggressor_side is Side.BUY else -trade.quantity
        self._trade_log_cursor = len(trade_log)
