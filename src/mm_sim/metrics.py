from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from mm_sim.models import OrderType, Side, Trade


@dataclass(frozen=True)
class BookSnapshot:
    """Book state at one instant. Recorded automatically by EventLoop after every
    order-book-touching action, giving spread/depth a real time series to plot
    rather than only being readable at whatever moment someone happens to ask.
    """

    timestamp: float
    best_bid: Optional[int]
    best_ask: Optional[int]
    spread: Optional[int]
    mid_price: Optional[float]
    bid_depth: int
    ask_depth: int


@dataclass(frozen=True)
class OrderImpact:
    """How much the mid price moved because of one order submission -- covers both
    trade-driven impact (a fill swept through resting liquidity) and quote-driven
    impact (a new best price was posted without necessarily trading), since both
    genuinely move the market in real order books.
    """

    timestamp: float
    agent_id: int
    side: Side
    order_type: OrderType
    requested_quantity: int
    filled_quantity: int
    mid_price_before: Optional[float]
    mid_price_after: Optional[float]

    @property
    def price_impact(self) -> Optional[float]:
        """Signed mid-price change. None if either side of the book was empty
        before or after (mid price undefined), which happens early in a run.
        """
        if self.mid_price_before is None or self.mid_price_after is None:
            return None
        return self.mid_price_after - self.mid_price_before


@dataclass(frozen=True)
class PnL:
    """Mark-to-market P&L for one agent: realized cash flow from fills, plus
    ending inventory valued at a mark price (typically the final mid price).
    Combines realized and unrealized P&L into one number without needing
    FIFO lot-cost tracking -- the standard simplification for this kind of
    aggregate view.
    """

    agent_id: int
    cash: float
    inventory: int
    mark_price: float

    @property
    def total(self) -> float:
        return self.cash + self.inventory * self.mark_price


def compute_pnl(trades: list[Trade], mark_price: float) -> dict[int, PnL]:
    """P&L for every agent that appears in `trades`, marked to `mark_price`
    (pass the final mid price of the book, in the same integer-tick units as
    Trade.price, for consistent units throughout).
    """
    cash: dict[int, float] = defaultdict(float)
    inventory: dict[int, int] = defaultdict(int)

    for trade in trades:
        maker_side = Side.SELL if trade.aggressor_side is Side.BUY else Side.BUY
        _apply_fill(cash, inventory, trade.maker_agent_id, maker_side, trade.price, trade.quantity)
        _apply_fill(cash, inventory, trade.taker_agent_id, trade.aggressor_side, trade.price, trade.quantity)

    agent_ids = set(cash) | set(inventory)
    return {
        agent_id: PnL(agent_id, cash[agent_id], inventory[agent_id], mark_price)
        for agent_id in agent_ids
    }


def _apply_fill(
    cash: dict[int, float], inventory: dict[int, int], agent_id: int, side: Side, price: int, quantity: int
) -> None:
    if side is Side.BUY:
        cash[agent_id] -= price * quantity
        inventory[agent_id] += quantity
    else:
        cash[agent_id] += price * quantity
        inventory[agent_id] -= quantity
