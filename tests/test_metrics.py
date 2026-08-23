from mm_sim.metrics import compute_pnl
from mm_sim.models import Side, Trade


def make_trade(trade_id, price, quantity, maker_agent_id, taker_agent_id, aggressor_side):
    return Trade(
        trade_id=trade_id, timestamp=0.0, price=price, quantity=quantity,
        maker_order_id=trade_id * 10, taker_order_id=trade_id * 10 + 1,
        maker_agent_id=maker_agent_id, taker_agent_id=taker_agent_id, aggressor_side=aggressor_side,
    )


class TestSingleTrade:
    def test_taker_buy_debits_cash_and_adds_inventory(self):
        trades = [make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.BUY)]
        pnl = compute_pnl(trades, mark_price=100)

        assert pnl[2].cash == -1000
        assert pnl[2].inventory == 10

    def test_maker_of_a_buy_is_the_seller(self):
        trades = [make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.BUY)]
        pnl = compute_pnl(trades, mark_price=100)

        assert pnl[1].cash == 1000
        assert pnl[1].inventory == -10

    def test_taker_sell_credits_cash_and_reduces_inventory(self):
        trades = [make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.SELL)]
        pnl = compute_pnl(trades, mark_price=100)

        assert pnl[2].cash == 1000
        assert pnl[2].inventory == -10
        # maker of a sell is the buyer
        assert pnl[1].cash == -1000
        assert pnl[1].inventory == 10


class TestMarkToMarket:
    def test_total_combines_cash_and_inventory_at_mark_price(self):
        trades = [make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.BUY)]
        pnl = compute_pnl(trades, mark_price=105)

        # agent 1 sold at 100, now marked at 105 while short 10 -- down 50
        assert pnl[1].total == 1000 + (-10 * 105)
        assert pnl[1].total == -50
        # agent 2 bought at 100, now marked at 105 while long 10 -- up 50
        assert pnl[2].total == -1000 + (10 * 105)
        assert pnl[2].total == 50

    def test_pnl_is_zero_sum_across_all_agents(self):
        trades = [
            make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.BUY),
            make_trade(2, price=102, quantity=5, maker_agent_id=2, taker_agent_id=3, aggressor_side=Side.SELL),
        ]
        pnl = compute_pnl(trades, mark_price=101)

        assert sum(p.total for p in pnl.values()) == 0


class TestAccumulatesAcrossMultipleTrades:
    def test_same_agent_across_multiple_trades_nets_correctly(self):
        trades = [
            make_trade(1, price=100, quantity=10, maker_agent_id=1, taker_agent_id=2, aggressor_side=Side.BUY),
            make_trade(2, price=110, quantity=4, maker_agent_id=1, taker_agent_id=3, aggressor_side=Side.BUY),
        ]
        # agent 1 sold 10 @ 100 then 4 @ 110 -- both as maker/seller
        pnl = compute_pnl(trades, mark_price=100)

        assert pnl[1].cash == 1000 + 440
        assert pnl[1].inventory == -14


class TestEmptyTradeLog:
    def test_no_trades_means_no_agents_in_result(self):
        assert compute_pnl([], mark_price=100) == {}
