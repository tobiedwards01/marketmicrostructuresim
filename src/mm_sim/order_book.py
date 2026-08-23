from collections import deque
from itertools import count
from typing import Callable, Optional

from sortedcontainers import SortedDict

from mm_sim.models import Order, OrderStatus, OrderType, Side, Trade


def _opposite(side: Side) -> Side:
    return Side.SELL if side is Side.BUY else Side.BUY


class OrderBook:
    """Two-sided limit order book: price -> FIFO deque of resting orders per side."""

    def __init__(self) -> None:
        self.bids: SortedDict[int, deque[Order]] = SortedDict()  # ascending; best bid = max key
        self.asks: SortedDict[int, deque[Order]] = SortedDict()  # ascending; best ask = min key
        self.orders_by_id: dict[int, Order] = {}
        self._trade_ids = count(1)
        self._submitted_order_ids: set[int] = set()

    def _register_new_order(self, order: Order) -> None:
        """Guard against a caller reusing an order_id -- checked against every order
        ever submitted, not just currently-resting ones (orders_by_id only tracks
        orders that rested at some point, so it can't be used for this on its own).
        """
        if order.order_id in self._submitted_order_ids:
            raise ValueError(f"order_id {order.order_id} has already been submitted")
        self._submitted_order_ids.add(order.order_id)

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

    def _find_match(self, level: "deque[Order]", taker_agent_id: int) -> Optional[Order]:
        """Scan a price level (oldest first) for the first order eligible to trade
        against `taker_agent_id`: purges any cancelled orders it passes over (lazy
        deletion cleanup) and skips -- without removing -- any resting order that
        belongs to the taker's own agent (self-trade prevention). Returns None if
        no eligible order remains, which can happen even if the level isn't empty
        (e.g. the only orders left there are the taker's own).
        """
        i = 0
        while i < len(level):
            candidate = level[i]
            if candidate.status is OrderStatus.CANCELLED:
                del level[i]
                continue  # next element has shifted into position i
            if candidate.agent_id == taker_agent_id:
                i += 1
                continue
            return candidate
        return None

    def _best_unskipped_price(
        self, book: "SortedDict[int, deque[Order]]", ascending: bool, skip_prices: set[int]
    ) -> Optional[int]:
        keys = book.keys()
        ordered = keys if ascending else reversed(keys)
        for price in ordered:
            if price not in skip_prices:
                return price
        return None

    def _match(self, order: Order, price_ok: Callable[[int], bool]) -> list[Trade]:
        """Sweep the opposite side, filling `order` against resting orders while
        `price_ok(level_price)` holds. Does not rest or finalize `order`'s status --
        callers do that, since limit and market orders behave differently once the
        sweep is done.
        """
        trades: list[Trade] = []
        opposite = self._book_for(_opposite(order.side))
        ascending = order.side is Side.BUY  # BUY matches asks best-first ascending; SELL matches bids best-first descending
        skip_prices: set[int] = set()  # price levels with nothing left eligible for this order (e.g. only its own resting orders)

        while order.remaining > 0:
            level_price = self._best_unskipped_price(opposite, ascending, skip_prices)
            if level_price is None or not price_ok(level_price):
                break
            level = opposite[level_price]

            resting = self._find_match(level, order.agent_id)
            if resting is None:
                if not level:
                    del opposite[level_price]
                else:
                    skip_prices.add(level_price)  # level has orders, but all belong to `order`'s own agent
                continue

            fill_qty = min(order.remaining, resting.remaining)
            order.remaining -= fill_qty
            resting.remaining -= fill_qty

            trades.append(
                Trade(
                    trade_id=next(self._trade_ids),
                    timestamp=order.timestamp,
                    price=level_price,
                    quantity=fill_qty,
                    maker_order_id=resting.order_id,
                    taker_order_id=order.order_id,
                    maker_agent_id=resting.agent_id,
                    taker_agent_id=order.agent_id,
                    aggressor_side=order.side,
                )
            )

            if resting.remaining == 0:
                resting.status = OrderStatus.FILLED
                for i, o in enumerate(level):
                    if o is resting:
                        del level[i]
                        break
                if not level:
                    del opposite[level_price]
            else:
                resting.status = OrderStatus.PARTIALLY_FILLED

        return trades

    def submit_limit_order(self, order: Order) -> list[Trade]:
        """Match `order` against the opposite side, resting any unfilled remainder."""
        if order.order_type is not OrderType.LIMIT:
            raise ValueError("submit_limit_order requires a LIMIT order")
        self._register_new_order(order)

        if order.side is Side.BUY:
            price_ok = lambda level_price: level_price <= order.price
        else:
            price_ok = lambda level_price: level_price >= order.price

        trades = self._match(order, price_ok)

        if order.remaining == 0:
            order.status = OrderStatus.FILLED
        else:
            if order.remaining < order.quantity:
                order.status = OrderStatus.PARTIALLY_FILLED
            self._rest(order)

        return trades

    def submit_market_order(self, order: Order) -> list[Trade]:
        """Sweep `order` against the opposite side ignoring price; any unfilled
        remainder is cancelled immediately rather than resting (IOC semantics).
        """
        if order.order_type is not OrderType.MARKET:
            raise ValueError("submit_market_order requires a MARKET order")
        self._register_new_order(order)

        trades = self._match(order, price_ok=lambda level_price: True)

        order.status = OrderStatus.FILLED if order.remaining == 0 else OrderStatus.CANCELLED

        return trades

    def cancel_order(self, order_id: int) -> bool:
        """Cancel a resting order (lazy deletion -- marked CANCELLED and skipped by
        the matching loop when it's next encountered, rather than removed from its
        deque immediately).

        Returns True if the order was resting and is now cancelled, False if it was
        already in a terminal state (FILLED/CANCELLED) -- a no-op either way, but
        the caller can tell the two apart. Raises KeyError for an unknown order_id.
        """
        order = self.orders_by_id[order_id]
        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return False
        order.status = OrderStatus.CANCELLED
        return True
