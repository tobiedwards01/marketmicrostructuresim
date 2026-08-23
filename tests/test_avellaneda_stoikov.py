import math

import pytest

from mm_sim.agents.avellaneda_stoikov import AvellanedaStoikovMarketMaker
from mm_sim.event_loop import EventLoop
from mm_sim.models import OrderStatus


def make_agent(gamma=0.1, sigma=2.0, k=1.5, horizon=100.0, max_inventory=50, reference_price=10_000):
    return AvellanedaStoikovMarketMaker(
        agent_id=1,
        reference_price=reference_price,
        horizon=horizon,
        gamma=gamma,
        sigma=sigma,
        k=k,
        quote_size=10,
        max_inventory=max_inventory,
        requote_interval=0.5,
    )


class TestQuoteFormula:
    def test_matches_the_documented_closed_form_at_zero_inventory(self):
        agent = make_agent(gamma=0.1, sigma=2.0, k=1.5)
        bid, ask = agent.quotes(mid_price=10_000, inventory=0, time_remaining=10.0)

        spread = 0.1 * 2.0**2 * 10.0 + (2 / 0.1) * math.log(1 + 0.1 / 1.5)
        expected_bid = 10_000 - spread / 2
        expected_ask = 10_000 + spread / 2

        assert bid == pytest.approx(expected_bid)
        assert ask == pytest.approx(expected_ask)

    def test_zero_inventory_quotes_are_symmetric_around_mid(self):
        agent = make_agent()
        bid, ask = agent.quotes(mid_price=10_000, inventory=0, time_remaining=10.0)

        assert (bid + ask) / 2 == pytest.approx(10_000)


class TestInventorySkew:
    def test_positive_inventory_shifts_reservation_price_down(self):
        agent = make_agent()
        bid_long, ask_long = agent.quotes(mid_price=10_000, inventory=20, time_remaining=10.0)
        bid_flat, ask_flat = agent.quotes(mid_price=10_000, inventory=0, time_remaining=10.0)

        # long inventory -> both quotes shift down (more eager to sell, less to buy)
        assert bid_long < bid_flat
        assert ask_long < ask_flat

    def test_negative_inventory_shifts_reservation_price_up(self):
        agent = make_agent()
        bid_short, ask_short = agent.quotes(mid_price=10_000, inventory=-20, time_remaining=10.0)
        bid_flat, ask_flat = agent.quotes(mid_price=10_000, inventory=0, time_remaining=10.0)

        assert bid_short > bid_flat
        assert ask_short > ask_flat

    def test_larger_inventory_magnitude_shifts_further(self):
        agent = make_agent()
        _, ask_small = agent.quotes(mid_price=10_000, inventory=10, time_remaining=10.0)
        _, ask_large = agent.quotes(mid_price=10_000, inventory=40, time_remaining=10.0)

        assert ask_large < ask_small


class TestSpreadNarrowsNearHorizon:
    def test_spread_is_wider_with_more_time_remaining(self):
        agent = make_agent()
        bid_far, ask_far = agent.quotes(mid_price=10_000, inventory=0, time_remaining=50.0)
        bid_near, ask_near = agent.quotes(mid_price=10_000, inventory=0, time_remaining=1.0)

        assert (ask_far - bid_far) > (ask_near - bid_near)

    def test_negative_time_remaining_is_clamped_to_zero_not_negative_spread(self):
        agent = make_agent()
        bid, ask = agent.quotes(mid_price=10_000, inventory=0, time_remaining=-5.0)
        bid_at_zero, ask_at_zero = agent.quotes(mid_price=10_000, inventory=0, time_remaining=0.0)

        assert ask > bid  # never inverted
        assert (bid, ask) == pytest.approx((bid_at_zero, ask_at_zero))


class TestIntegrationWithEventLoop:
    def test_quotes_symmetric_spread_around_reference_price_on_empty_book(self):
        agent = make_agent(reference_price=10_000)
        loop = EventLoop([agent])

        agent.act(loop.time, loop)

        assert loop.book.best_bid is not None
        assert loop.book.best_ask is not None
        mid = (loop.book.best_bid + loop.book.best_ask) / 2
        assert mid == pytest.approx(10_000, abs=1)

    def test_requote_cancels_previous_quotes(self):
        agent = make_agent()
        loop = EventLoop([agent])

        agent.act(loop.time, loop)
        first_bid_id = agent._bid_order_id

        loop.time = 1.0
        agent.act(loop.time, loop)

        assert loop.book.orders_by_id[first_bid_id].status is OrderStatus.CANCELLED
        assert agent._bid_order_id != first_bid_id

    def test_stops_quoting_a_side_once_inventory_limit_hit(self):
        from mm_sim.models import Side

        agent = make_agent(max_inventory=10)
        loop = EventLoop([agent])
        agent.act(loop.time, loop)
        # sell at a price far below any resting bid, guaranteeing a fill against it
        loop.submit_limit(agent_id=2, side=Side.SELL, price=1, quantity=10)

        loop.time = 1.0
        agent.act(loop.time, loop)

        assert agent.inventory == 10
        assert loop.book.best_bid is None
