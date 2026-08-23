# Decisions

Running log of non-trivial design choices: what was picked, why, and what alternative was considered. Most recent first.

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
