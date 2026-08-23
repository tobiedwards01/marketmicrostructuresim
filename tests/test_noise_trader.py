from mm_sim.agents.noise_trader import NoiseTrader
from mm_sim.event_loop import EventLoop
from mm_sim.models import Side


def make_loop(trader: NoiseTrader) -> EventLoop:
    return EventLoop([trader])


class TestOrderStaysWithinConfiguredBounds:
    def test_price_and_quantity_stay_within_configured_bands_over_many_draws(self):
        trader = NoiseTrader(
            agent_id=1,
            reference_price=10_000,
            price_band_ticks=50,
            min_quantity=1,
            max_quantity=20,
            arrival_rate=1.0,
            seed=42,
        )
        loop = make_loop(trader)

        for _ in range(200):
            trader.act(loop.time, loop)

        submitted = [o for o in loop.book.orders_by_id.values()]
        assert len(submitted) > 0
        for order in submitted:
            assert 9_950 <= order.price <= 10_050
            assert 1 <= order.quantity <= 20

    def test_both_sides_appear_over_many_draws(self):
        trader = NoiseTrader(
            agent_id=1, reference_price=10_000, price_band_ticks=50,
            min_quantity=1, max_quantity=5, arrival_rate=1.0, seed=1,
        )
        loop = make_loop(trader)

        for _ in range(100):
            trader.act(loop.time, loop)

        sides_seen = {order.side for order in loop.book.orders_by_id.values()}
        assert sides_seen == {Side.BUY, Side.SELL}


class TestReproducibility:
    def test_same_seed_produces_same_sequence_of_orders(self):
        trader_a = NoiseTrader(
            agent_id=1, reference_price=10_000, price_band_ticks=50,
            min_quantity=1, max_quantity=20, arrival_rate=1.0, seed=7,
        )
        trader_b = NoiseTrader(
            agent_id=1, reference_price=10_000, price_band_ticks=50,
            min_quantity=1, max_quantity=20, arrival_rate=1.0, seed=7,
        )
        loop_a, loop_b = make_loop(trader_a), make_loop(trader_b)

        for _ in range(20):
            trader_a.act(loop_a.time, loop_a)
            trader_b.act(loop_b.time, loop_b)

        orders_a = [(o.side, o.price, o.quantity) for o in loop_a.book.orders_by_id.values()]
        orders_b = [(o.side, o.price, o.quantity) for o in loop_b.book.orders_by_id.values()]
        assert orders_a == orders_b


class TestWakeSchedule:
    def test_next_wake_time_always_moves_forward(self):
        trader = NoiseTrader(
            agent_id=1, reference_price=10_000, price_band_ticks=50,
            min_quantity=1, max_quantity=20, arrival_rate=2.0, seed=3,
        )
        t = 0.0
        for _ in range(50):
            next_t = trader.next_wake_time(t)
            assert next_t > t
            t = next_t
