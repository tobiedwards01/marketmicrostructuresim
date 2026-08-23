import random
from abc import ABC, abstractmethod
from typing import Optional

from mm_sim.market_access import MarketAccess


class Agent(ABC):
    """Base class for anything that wakes up on the event loop and can act on the
    market. Each agent owns its own RNG stream (seeded independently) so a whole
    simulation run is reproducible given a fixed set of per-agent seeds.
    """

    def __init__(self, agent_id: int, seed: Optional[int] = None) -> None:
        self.agent_id = agent_id
        self.rng = random.Random(seed)

    @abstractmethod
    def act(self, sim_time: float, market: MarketAccess) -> None:
        """Called when this agent wakes up. May submit/cancel orders via `market`."""

    @abstractmethod
    def next_wake_time(self, sim_time: float) -> Optional[float]:
        """Simulation time of this agent's next wake, or None to stop waking it."""
