# Market Microstructure Simulator

A limit-order-book market built from scratch, populated with multiple types of trading
agents (noise traders, an informed trader, market makers), used to study emergent
microstructure dynamics — spreads, price impact, adverse selection — and to train a
reinforcement-learning market-making agent inside the simulated market.

See [DESIGN.md](DESIGN.md) for the core data model and event-loop design, and
[DECISIONS.md](DECISIONS.md) for a running log of non-trivial design choices and why
they were made.

## Status

Phase 0 (research & design) complete. Phase 1 (core matching engine) in progress.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

## Architecture

_To be filled in as the matching engine, agent population, and simulation framework
are built out — see DESIGN.md in the meantime._

## Results

_To be filled in during Phase 3/4 (metrics pipeline and emergent-behaviour analysis)._
