from typing import Protocol

from mm_sim.models import Order, Side, Trade
from mm_sim.order_book import OrderBook


class MarketAccess(Protocol):
    """What an Agent can see and do when it wakes up.

    A separate Protocol (rather than agents importing EventLoop directly) so
    agents.py and event_loop.py don't need to import each other -- EventLoop just
    happens to satisfy this structurally.
    """

    time: float
    book: OrderBook

    def submit_limit(self, agent_id: int, side: Side, price: int, quantity: int) -> tuple[Order, list[Trade]]: ...

    def submit_market(self, agent_id: int, side: Side, quantity: int) -> tuple[Order, list[Trade]]: ...

    def cancel(self, order_id: int) -> bool: ...
