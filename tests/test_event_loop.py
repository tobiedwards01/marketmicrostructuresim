from typing import Optional

from mm_sim.agents.base import Agent
from mm_sim.event_loop import EventLoop
from mm_sim.market_access import MarketAccess
from mm_sim.models import Side


class RecordingAgent(Agent):
    """Test double: wakes at predetermined times, records every wake it receives."""

    def __init__(self, agent_id, wake_times):
        super().__init__(agent_id)
        self._wake_times = list(wake_times)
        self.wakes: list[float] = []

    def next_wake_time(self, sim_time: float) -> Optional[float]:
        return self._wake_times.pop(0) if self._wake_times else None

    def act(self, sim_time: float, market: MarketAccess) -> None:
        self.wakes.append(sim_time)


class TestWakeOrdering:
    def test_agents_wake_in_timestamp_order_across_agents(self):
        a = RecordingAgent(1, wake_times=[5.0])
        b = RecordingAgent(2, wake_times=[1.0])
        loop = EventLoop([a, b])

        loop.run_until(10.0)

        assert b.wakes == [1.0]
        assert a.wakes == [5.0]

    def test_agent_reschedules_itself_via_next_wake_time(self):
        agent = RecordingAgent(1, wake_times=[1.0, 2.0, 3.0])
        loop = EventLoop([agent])

        loop.run_until(10.0)

        assert agent.wakes == [1.0, 2.0, 3.0]

    def test_run_until_stops_at_end_time_leaving_later_events_unprocessed(self):
        agent = RecordingAgent(1, wake_times=[1.0, 5.0, 9.0])
        loop = EventLoop([agent])

        loop.run_until(6.0)
        assert agent.wakes == [1.0, 5.0]

        loop.run_until(10.0)
        assert agent.wakes == [1.0, 5.0, 9.0]

    def test_agent_stops_being_scheduled_once_next_wake_time_returns_none(self):
        agent = RecordingAgent(1, wake_times=[1.0])  # only one wake, then None
        loop = EventLoop([agent])

        loop.run_until(100.0)

        assert agent.wakes == [1.0]


class TestSubmitLimit:
    def test_assigns_increasing_order_ids_and_current_sim_time(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])
        loop.time = 42.0

        order1, _ = loop.submit_limit(agent_id=1, side=Side.BUY, price=10_000, quantity=5)
        order2, _ = loop.submit_limit(agent_id=1, side=Side.SELL, price=10_100, quantity=5)

        assert order2.order_id > order1.order_id
        assert order1.timestamp == 42.0
        assert order2.timestamp == 42.0

    def test_trades_are_appended_to_the_shared_trade_log(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])

        loop.submit_limit(agent_id=1, side=Side.SELL, price=10_000, quantity=5)
        order, trades = loop.submit_limit(agent_id=2, side=Side.BUY, price=10_000, quantity=5)

        assert len(trades) == 1
        assert loop.trade_log == trades

    def test_returns_the_order_object_for_the_caller_to_track(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])

        order, trades = loop.submit_limit(agent_id=1, side=Side.BUY, price=10_000, quantity=5)

        assert trades == []
        assert order.remaining == 5
        assert loop.book.orders_by_id[order.order_id] is order


class TestSubmitMarketAndCancel:
    def test_submit_market_forwards_to_book(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])
        loop.submit_limit(agent_id=1, side=Side.SELL, price=10_000, quantity=5)

        order, trades = loop.submit_market(agent_id=2, side=Side.BUY, quantity=5)

        assert len(trades) == 1
        assert order.remaining == 0

    def test_cancel_forwards_to_book(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])
        order, _ = loop.submit_limit(agent_id=1, side=Side.BUY, price=10_000, quantity=5)

        assert loop.cancel(order.order_id) is True
        from mm_sim.models import OrderStatus

        assert order.status is OrderStatus.CANCELLED


class TestMetricsRecording:
    def test_every_submission_and_cancel_records_a_book_snapshot(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])

        order, _ = loop.submit_limit(agent_id=1, side=Side.BUY, price=10_000, quantity=5)
        loop.submit_limit(agent_id=2, side=Side.SELL, price=10_100, quantity=5)
        loop.cancel(order.order_id)

        assert len(loop.book_snapshots) == 3

    def test_snapshot_reflects_book_state_at_that_point(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])

        loop.submit_limit(agent_id=1, side=Side.BUY, price=9_900, quantity=10)
        loop.submit_limit(agent_id=2, side=Side.SELL, price=10_100, quantity=5)

        snap = loop.book_snapshots[-1]
        assert snap.best_bid == 9_900
        assert snap.best_ask == 10_100
        assert snap.spread == 200
        assert snap.bid_depth == 10
        assert snap.ask_depth == 5

    def test_order_impact_is_zero_when_order_just_rests_without_moving_best_price(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])
        loop.submit_limit(agent_id=1, side=Side.BUY, price=9_900, quantity=10)
        loop.submit_limit(agent_id=1, side=Side.SELL, price=10_100, quantity=10)

        # a worse-priced bid than the existing best doesn't move the mid at all
        loop.submit_limit(agent_id=2, side=Side.BUY, price=9_800, quantity=5)

        impact = loop.order_impacts[-1]
        assert impact.price_impact == 0
        assert impact.filled_quantity == 0

    def test_order_impact_reflects_filled_quantity_and_mid_price_move(self):
        agent = RecordingAgent(1, wake_times=[])
        loop = EventLoop([agent])
        loop.submit_limit(agent_id=1, side=Side.BUY, price=9_900, quantity=10)
        loop.submit_limit(agent_id=1, side=Side.SELL, price=10_100, quantity=10)
        # mid is 10_000 here

        order, trades = loop.submit_market(agent_id=2, side=Side.BUY, quantity=10)

        impact = loop.order_impacts[-1]
        assert impact.filled_quantity == 10
        assert impact.mid_price_before == 10_000
        # buying wipes out the ask side entirely -- best_ask becomes None, so mid is undefined after
        assert impact.mid_price_after is None
        assert impact.price_impact is None
