from mm_sim.agents.informed_trader import InformedTrader
from mm_sim.event_loop import EventLoop
from mm_sim.models import Side


def make_informed(true_price=10_000, edge_threshold=20, quantity=10, seed=1, volatility=0.0, noise_std=0.0):
    # volatility=0 and noise_std=0 make the true-price walk and signal noise
    # deterministic (random.gauss(mu, 0) == mu exactly), so the tests below can
    # assert on exact threshold-crossing behavior instead of statistical outcomes.
    return InformedTrader(
        agent_id=99,
        initial_true_price=true_price,
        true_price_volatility=volatility,
        signal_noise_std=noise_std,
        edge_threshold=edge_threshold,
        quantity=quantity,
        arrival_rate=1.0,
        seed=seed,
    )


class TestNoActionWhenBookIsEmpty:
    def test_does_nothing_against_an_empty_book(self):
        trader = make_informed()
        loop = EventLoop([trader])

        trader.act(loop.time, loop)

        assert loop.trade_log == []
        assert loop.book.best_bid is None
        assert loop.book.best_ask is None


class TestBuysWhenSignalAboveAsk:
    def test_buys_when_signal_exceeds_best_ask_by_the_edge_threshold(self):
        trader = make_informed(true_price=10_000, edge_threshold=20)
        loop = EventLoop([trader])
        # resting ask well below the trader's "true" price of 10_000
        loop.submit_limit(agent_id=1, side=Side.SELL, price=9_970, quantity=10)

        trader.act(loop.time, loop)

        assert len(loop.trade_log) == 1
        assert loop.trade_log[0].price == 9_970
        assert loop.trade_log[0].taker_agent_id == 99

    def test_does_not_trade_when_edge_is_below_threshold(self):
        trader = make_informed(true_price=10_000, edge_threshold=50)
        loop = EventLoop([trader])
        loop.submit_limit(agent_id=1, side=Side.SELL, price=9_990, quantity=10)  # only 10 ticks of edge

        trader.act(loop.time, loop)

        assert loop.trade_log == []


class TestSellsWhenSignalBelowBid:
    def test_sells_when_best_bid_exceeds_signal_by_the_edge_threshold(self):
        trader = make_informed(true_price=10_000, edge_threshold=20)
        loop = EventLoop([trader])
        loop.submit_limit(agent_id=1, side=Side.BUY, price=10_030, quantity=10)

        trader.act(loop.time, loop)

        assert len(loop.trade_log) == 1
        assert loop.trade_log[0].price == 10_030
        assert loop.trade_log[0].aggressor_side is Side.SELL


class TestTruePriceRandomWalk:
    def test_true_price_changes_over_successive_acts_when_volatility_is_nonzero(self):
        trader = make_informed(volatility=5.0)
        loop = EventLoop([trader])

        seen = set()
        for _ in range(20):
            trader.act(loop.time, loop)
            seen.add(trader.true_price)

        assert len(seen) > 1  # it actually moved, not stuck at the initial value

    def test_true_price_is_static_when_volatility_is_zero(self):
        trader = make_informed(true_price=10_000, volatility=0.0)
        loop = EventLoop([trader])

        for _ in range(10):
            trader.act(loop.time, loop)

        assert trader.true_price == 10_000
