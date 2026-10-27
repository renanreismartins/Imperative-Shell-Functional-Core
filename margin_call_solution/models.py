from dataclasses import dataclass, field


@dataclass
class Position:
    asset_id: str
    quantity: float
    margin_rate: float


@dataclass
class Account:
    id: str
    email: str
    status: str = "HEALTHY"
    margin_shortfall: float = 0.0
    positions: list[Position] = field(default_factory=list)
