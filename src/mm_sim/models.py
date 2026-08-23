from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class Side(Enum):
    BUY = auto()
    SELL = auto()


class OrderType(Enum):
    LIMIT = auto()
    MARKET = auto()


class OrderStatus(Enum):
    NEW = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()


@dataclass
class Order:
    order_id: int
    agent_id: int
    side: Side
    order_type: OrderType
    price: Optional[int]  # integer ticks (cents); None for MARKET orders
    quantity: int  # original size, immutable once set
    remaining: int  # mutable, decremented on each fill
    timestamp: float  # simulation time of submission
    seq: int  # monotonically increasing — breaks timestamp ties
    status: OrderStatus = OrderStatus.NEW

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")
        if self.remaining < 0 or self.remaining > self.quantity:
            raise ValueError(
                f"remaining ({self.remaining}) must be in [0, quantity={self.quantity}]"
            )
        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT orders must have a price")
        if self.order_type is OrderType.MARKET and self.price is not None:
            raise ValueError("MARKET orders must not have a price")
        if self.price is not None and self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")


@dataclass(frozen=True)
class Trade:
    trade_id: int
    timestamp: float
    price: int  # always the resting (maker) order's price
    quantity: int
    maker_order_id: int
    taker_order_id: int
    maker_agent_id: int
    taker_agent_id: int
    aggressor_side: Side  # side of the taker — the order that crossed the spread

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"quantity must be positive, got {self.quantity}")
        if self.price <= 0:
            raise ValueError(f"price must be positive, got {self.price}")
