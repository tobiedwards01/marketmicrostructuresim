import heapq
from itertools import count
from typing import TYPE_CHECKING, Optional

from mm_sim.models import Order, OrderType, Side, Trade
from mm_sim.order_book import OrderBook

if TYPE_CHECKING:
    from mm_sim.agents.base import Agent


class EventLoop:
    """Drives the simulation: a min-heap of (timestamp, seq, agent_id) wakes agents
    in time order (seq breaks ties deterministically -- see DESIGN.md). Agents act
    through this loop's submit_limit/submit_market/cancel, which build the actual
    Order objects (assigning order_id/seq centrally) and forward to the OrderBook.
    """

    def __init__(self, agents: list["Agent"]) -> None:
        self.book = OrderBook()
        self.agents = {agent.agent_id: agent for agent in agents}
        self.trade_log: list[Trade] = []
        self.time: float = 0.0

        self._queue: list[tuple[float, int, int]] = []
        self._seq = count()  # shared tie-breaker: event ordering AND Order.seq
        self._order_ids = count(1)

        for agent in agents:
            wake_time = agent.next_wake_time(0.0)
            if wake_time is not None:
                self._schedule_wake(agent.agent_id, wake_time)

    def _schedule_wake(self, agent_id: int, timestamp: float) -> None:
        heapq.heappush(self._queue, (timestamp, next(self._seq), agent_id))

    def run_until(self, end_time: float) -> None:
        while self._queue and self._queue[0][0] <= end_time:
            timestamp, _, agent_id = heapq.heappop(self._queue)
            self.time = timestamp
            agent = self.agents[agent_id]
            agent.act(self.time, self)
            next_wake = agent.next_wake_time(self.time)
            if next_wake is not None:
                self._schedule_wake(agent_id, next_wake)

    def _new_order(
        self, agent_id: int, side: Side, order_type: OrderType, price: Optional[int], quantity: int
    ) -> Order:
        return Order(
            order_id=next(self._order_ids),
            agent_id=agent_id,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            remaining=quantity,
            timestamp=self.time,
            seq=next(self._seq),
        )

    def submit_limit(self, agent_id: int, side: Side, price: int, quantity: int) -> tuple[Order, list[Trade]]:
        order = self._new_order(agent_id, side, OrderType.LIMIT, price, quantity)
        trades = self.book.submit_limit_order(order)
        self.trade_log.extend(trades)
        return order, trades

    def submit_market(self, agent_id: int, side: Side, quantity: int) -> tuple[Order, list[Trade]]:
        order = self._new_order(agent_id, side, OrderType.MARKET, None, quantity)
        trades = self.book.submit_market_order(order)
        self.trade_log.extend(trades)
        return order, trades

    def cancel(self, order_id: int) -> bool:
        return self.book.cancel_order(order_id)
