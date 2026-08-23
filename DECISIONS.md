# Decisions

Running log of non-trivial design choices: what was picked, why, and what alternative was considered. Most recent first.

---

## Phase 3

### NoiseTrader holds one live order, cancelled and replaced each wake
**Decision:** `NoiseTrader` now cancels its own previous resting order (if any) before submitting a new one, matching the classic Gode & Sunder (1993) zero-intelligence trader -- one outstanding order per trader, replaced each period.
**Why:** Building the Phase 3 metrics dashboard immediately surfaced two artifacts from the old "never cancel" behavior: (1) the spread chart showed genuine negative values -- a trader's own new order, quoted around a drifting mid price, could end up priced on the wrong side of an old resting order it never cancelled; self-trade prevention correctly refuses to match the same agent against itself, but per the Phase 0 STP decision it leaves both resting rather than cancelling one, so best_bid/best_ask briefly reported a "locked" price from one agent's own crossed quotes. (2) order book depth grew unboundedly over the run instead of settling into a steady state, since nothing ever expired. Both are downstream of the same root cause and both are fixed by this one change -- confirmed by re-running the dashboard before/after.
**Alternative considered:** Filter negative spreads out at the metrics/plotting layer instead of fixing the agent. Rejected -- that would hide a real (if minor) modeling gap rather than fix it, and the unbounded depth growth would still be there; fixing the agent's behavior is more correct and happens to match the actual textbook model this agent type is based on.

## Phase 2

### NoiseTrader anchors to the live mid price, not a fixed reference price
**Decision:** `NoiseTrader.act()` centers its random price offset on `market.book.mid_price` when available, falling back to its configured `reference_price` only when the book is empty -- same pattern `NaiveMarketMaker` already used.
**Why:** Found during a design review before starting Phase 3. A noise trader anchored to a static price doesn't track where the market actually is; over a long enough run (or with enough informed/market-maker activity moving the price), it would end up quoting a growing distance from the live book, which would quietly distort exactly the metrics Phase 3 is about to measure -- spread and depth would partly reflect "how far the market has drifted from noise traders' fixed anchor" rather than genuine liquidity dynamics.
**Alternative considered:** Leave it anchored to the fixed reference price, since it's simpler and the Phase 2 demo run didn't drift far in 200 time units. Rejected -- the distortion risk grows with simulation length and Phase 3+ will run longer, more varied scenarios, and this was a one-line fix consistent with how the market maker already worked.

### best_bid/best_ask purge cancelled orders from the front on access
**Decision:** `OrderBook.best_bid`/`best_ask` now walk past (and delete) any cancelled order sitting at the front of the best price level before reporting a price, rather than trusting whatever `SortedDict.peekitem` returns.
**Why:** Lazy deletion (see Phase 0) means a cancelled order can sit in its deque until matching happens to walk past it. That's fine for matching itself, which already skips cancelled orders -- but `best_bid`/`best_ask` were reading the raw price key regardless of whether anything live was actually resting there. Discovered via `NaiveMarketMaker`: it cancels its old quote and immediately reads `mid_price` to decide where to re-quote, and was getting a stale price back for a level with nothing tradeable left in it. Since these are read properties used for decisions (not just display), a stale answer is a real correctness bug, not a cosmetic one.
**Alternative considered:** Track a separate live-quantity counter per price level, decremented on cancel, so reads never need to touch the deque. More bookkeeping for the same result; purging on read is simpler and keeps the "cleaned up on next touch" lazy-deletion contract in one place.

### Agents reconcile fills via the shared trade log, not just their own submission's return value
**Decision:** `NaiveMarketMaker` (and any future agent that needs to track its own position) tracks a cursor into `EventLoop.trade_log` and reconciles inventory from every trade since it last checked -- both trades where it was the maker (resting order got hit by someone else) and where it was the taker (its own order crossed on submission) -- rather than relying only on the trades returned directly from its own `submit_limit`/`submit_market` calls.
**Why:** An agent's resting order can be filled by *any other agent* at *any later wake*, not just at the instant it was submitted. The MM's own `market.submit_limit(...)` call only returns trades that happened synchronously during that call; a fill that happens later, when some other agent's incoming order crosses the MM's resting quote, has no way to reach the MM through that return value. Also matters where in `act()` this runs: reconciling must happen *before* the inventory-limit check that decides whether to quote, not just after, or the limit is enforced one wake-cycle late.
**Alternative considered:** Push-based fill notification -- have the matching engine call back into affected agents directly when a trade happens. More real-time, but adds a dependency from `OrderBook`/`EventLoop` back into agent code and a lot more plumbing for a baseline agent that only checks its position once per requote cycle anyway. Worth reconsidering if a future agent (e.g. the Phase 5 RL market maker) needs to react to fills faster than its own polling interval.

---

## Phase 0

### Tick size: $0.01, prices stored as integer cents
**Decision:** `Order.price` and `Trade.price` are integers representing whole cents (`price_ticks = round(price_dollars * 100)`). All internal comparisons, sorting, and matching use these integers; conversion to a dollar float happens only at the display/reporting boundary (metrics, plots, logs).
**Why:** Matches real US equity tick size for stocks trading above $1, and — more importantly — avoids float equality/comparison bugs in the matching engine (`0.1 + 0.2 != 0.3` is exactly the kind of bug that silently corrupts price-level bucketing). Cheap to decide now; expensive to retrofit once agents in Phase 2 are generating prices.
**Alternative considered:** `Decimal` prices. Also avoids float bugs, but slower and heavier for no real benefit at this scale — rejected in favor of plain integers.

### Market orders on an empty book: IOC, cancel the unfilled remainder
**Decision:** A market order fills against whatever liquidity is available on the opposite side; any unfilled remainder is cancelled immediately rather than resting in the book.
**Why:** This is what "market order" means at essentially every real venue — immediate execution against available liquidity, nothing more. It also produces a useful signal for later phases: the fraction of a market order that goes unfilled during a liquidity shortage is worth tracking as its own metric, and it's exactly what Phase 6's stress test wants to observe — does the book have enough depth to absorb the shock, or do market orders start getting partially cancelled.
**Alternative considered:** Convert the unfilled remainder into a resting limit order at the last trade price. More forgiving, but blurs the line between order types and produces less realistic dynamics — rejected.

### Self-trade prevention: required
**Decision:** The matching engine must not let an agent's incoming order match against that same agent's own resting order.
**Why:** Matches real-exchange behavior, and prevents an agent from generating fake volume/trades against itself, which would quietly pollute every downstream metric (traded volume, price impact, spread) with self-generated noise.
**Alternative considered:** No STP check. Simpler, but rejected — any self-trades would need to be filtered out of every metric anyway, so it's cheaper to prevent them at the source.
**Implementation note:** when matching, skip past a resting order belonging to the same `agent_id` as the incoming order rather than matching it (continue to the next resting order at that price level, or the next price level if none remain).

### Order cancellation: lazy deletion
**Decision:** Cancelled orders are marked `CANCELLED` in place and skipped during matching, rather than removed from their price-level deque immediately.
**Why:** Simpler to implement correctly for Phase 1; cancellation becomes an O(1) status write instead of requiring a doubly-linked list for O(1) mid-deque removal.
**Alternative considered:** Doubly-linked list per price level for eager O(1) removal — closer to how real matching engines behave, since cancel-replace is extremely common in practice. Revisit if Phase 3's order-book-depth metric needs exact live depth (lazy deletion needs a maintained running total per level instead of trusting deque contents), or if profiling shows lazy deletion causing real matching-loop overhead.
