from collections import deque
from typing import Optional

from sortedcontainers import SortedDict

from mm_sim.models import Order, Side


class OrderBook:
    """Two-sided limit order book: price -> FIFO deque of resting orders per side."""

    def __init__(self) -> None:
        self.bids: SortedDict[int, deque[Order]] = SortedDict()  # ascending; best bid = max key
        self.asks: SortedDict[int, deque[Order]] = SortedDict()  # ascending; best ask = min key
        self.orders_by_id: dict[int, Order] = {}

    @property
    def best_bid(self) -> Optional[int]:
        if not self.bids:
            return None
        return self.bids.peekitem(-1)[0]

    @property
    def best_ask(self) -> Optional[int]:
        if not self.asks:
            return None
        return self.asks.peekitem(0)[0]

    @property
    def spread(self) -> Optional[int]:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        return ask - bid

    @property
    def mid_price(self) -> Optional[float]:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def _book_for(self, side: Side) -> "SortedDict[int, deque[Order]]":
        return self.bids if side is Side.BUY else self.asks

    def _rest(self, order: Order) -> None:
        """Insert a resting order into the book at its own price level. No matching."""
        book = self._book_for(order.side)
        if order.price not in book:
            book[order.price] = deque()
        book[order.price].append(order)
        self.orders_by_id[order.order_id] = order
