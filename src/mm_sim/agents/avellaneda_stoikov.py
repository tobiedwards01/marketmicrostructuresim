import math
from typing import Optional

from mm_sim.agents.quoting_base import QuotingAgent
from mm_sim.market_access import MarketAccess


class AvellanedaStoikovMarketMaker(QuotingAgent):
    """Closed-form optimal market-making quotes from Avellaneda & Stoikov (2008),
    "High-frequency trading in a limit order book". The analytical benchmark
    Phase 5's Q-learning agent gets checked against.

    r(s, t) = s - q * gamma * sigma^2 * (T - t)            [reservation price]
    spread  = gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / k)
    bid = r - spread / 2, ask = r + spread / 2

    where q is inventory, gamma is risk aversion, sigma is mid-price volatility,
    T-t is remaining time to the horizon, and k controls how fast order-arrival
    intensity decays with distance from the mid price.

    Two things this closed form does automatically that NaiveMarketMaker's fixed
    spread can't: (1) the reservation price shifts away from mid in the
    direction that reduces inventory -- long position -> quotes shift down,
    encouraging sells; (2) the spread widens with more time left on the horizon
    (more time for inventory risk to hurt) and narrows to just the
    order-flow-driven term as the horizon approaches.
    """

    def __init__(
        self,
        agent_id: int,
        reference_price: int,
        horizon: float,
        gamma: float,
        sigma: float,
        k: float,
        quote_size: int,
        max_inventory: int,
        requote_interval: float,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(agent_id, quote_size, max_inventory, requote_interval, seed)
        self.reference_price = reference_price
        self.horizon = horizon
        self.gamma = gamma
        self.sigma = sigma
        self.k = k

    def quotes(self, mid_price: float, inventory: int, time_remaining: float) -> tuple[float, float]:
        """(bid, ask) as floats, in the same price units as mid_price -- not yet
        rounded to an integer tick or inventory-limit-gated. Exposed separately
        from _choose_quotes so it can be called directly for the Phase 5
        comparison against the Q-learning agent's learned quotes, without
        needing a live market/OrderBook.
        """
        time_remaining = max(time_remaining, 0.0)
        reservation = mid_price - inventory * self.gamma * self.sigma**2 * time_remaining
        spread = self.gamma * self.sigma**2 * time_remaining + (2 / self.gamma) * math.log(1 + self.gamma / self.k)
        return reservation - spread / 2, reservation + spread / 2

    def _choose_quotes(self, sim_time: float, market: MarketAccess) -> tuple[int, int]:
        mid = market.book.mid_price
        center = mid if mid is not None else float(self.reference_price)
        time_remaining = self.horizon - sim_time

        bid_f, ask_f = self.quotes(center, self.inventory, time_remaining)
        bid_price = max(1, round(bid_f))
        ask_price = max(bid_price + 1, round(ask_f))  # guard against inversion from rounding at tiny spreads
        return bid_price, ask_price
