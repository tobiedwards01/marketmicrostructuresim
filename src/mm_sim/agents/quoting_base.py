from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class QuotingAgent(Agent):
    """Base for agents that maintain a two-sided quote (one resting bid + one
    resting ask), cancelled and replaced each wake, with inventory and cash
    tracked from the shared trade log. Subclasses implement `_choose_quotes()`
    to decide prices; this class owns the machinery every quoting agent needs
    regardless of pricing strategy: cancelling stale quotes, reconciling fills
    (from either side, from any counterparty, at any wake -- not just the
    agent's own submissions), and respecting inventory limits.

    Originally lived duplicated inside NaiveMarketMaker; pulled out here once a
    second and third quoting agent (Avellaneda-Stoikov, then Q-learning) were
    about to duplicate it a second and third time.
    """

    def __init__(
        self,
        agent_id: int,
        quote_size: int,
        max_inventory: int,
        requote_interval: float,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, seed)
        self.quote_size = quote_size
        self.max_inventory = max_inventory
        self.requote_interval = requote_interval
        self.inventory = 0
        self.cash = 0.0
        self._bid_order_id: Optional[int] = None
        self._ask_order_id: Optional[int] = None
        self._trade_log_cursor = 0

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return sim_time + self.requote_interval

    def mark_to_market(self, mark_price: float) -> float:
        return self.cash + self.inventory * mark_price

    def act(self, sim_time: float, market: MarketAccess) -> None:
        self._cancel_stale_quotes(market)
        self._sync_fills(market)

        bid_price, ask_price = self._choose_quotes(sim_time, market)

        if self.inventory < self.max_inventory:
            order, _ = market.submit_limit(self.agent_id, Side.BUY, bid_price, self.quote_size)
            if order.remaining > 0:
                self._bid_order_id = order.order_id

        if self.inventory > -self.max_inventory:
            order, _ = market.submit_limit(self.agent_id, Side.SELL, ask_price, self.quote_size)
            if order.remaining > 0:
                self._ask_order_id = order.order_id

        self._sync_fills(market)  # catch any fill from the submissions just above

    def _choose_quotes(self, sim_time: float, market: MarketAccess) -> tuple[int, int]:
        """Return (bid_price, ask_price). Inventory-limit gating on whether to
        actually submit each side happens in `act()` above -- subclasses just
        decide where they'd quote if allowed to.
        """
        raise NotImplementedError

    def _cancel_stale_quotes(self, market: MarketAccess) -> None:
        if self._bid_order_id is not None:
            market.cancel(self._bid_order_id)
            self._bid_order_id = None
        if self._ask_order_id is not None:
            market.cancel(self._ask_order_id)
            self._ask_order_id = None

    def _sync_fills(self, market: MarketAccess) -> None:
        """Reconcile inventory and cash against every trade since we last
        checked -- both fills from our own submissions above and fills that
        happened to our resting quotes because some OTHER agent traded against
        them between wakes (the shared trade log is the only place that
        captures both; a submission's own return value only covers the former).
        """
        trade_log = market.trade_log
        for trade in trade_log[self._trade_log_cursor :]:
            if trade.maker_agent_id == self.agent_id:
                maker_side = Side.SELL if trade.aggressor_side is Side.BUY else Side.BUY
                self._apply_fill(maker_side, trade.price, trade.quantity)
            elif trade.taker_agent_id == self.agent_id:
                self._apply_fill(trade.aggressor_side, trade.price, trade.quantity)
        self._trade_log_cursor = len(trade_log)

    def _apply_fill(self, side: Side, price: int, quantity: int) -> None:
        if side is Side.BUY:
            self.cash -= price * quantity
            self.inventory += quantity
        else:
            self.cash += price * quantity
            self.inventory -= quantity
