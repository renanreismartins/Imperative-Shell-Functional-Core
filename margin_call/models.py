from dataclasses import dataclass, field


@dataclass
class Position:
    asset_id: str
    quantity: float
    margin_rate: float


@dataclass(frozen=True)
class PortfolioValuation:
    total_value: float
    margin_requirement: float

    @property
    def margin_level(self) -> float | None:
        if self.margin_requirement == 0:
            return None
        return self.total_value / self.margin_requirement


@dataclass
class Account:
    id: str
    email: str
    status: str = "HEALTHY"
    margin_shortfall: float = 0.0
    positions: list[Position] = field(default_factory=list)
