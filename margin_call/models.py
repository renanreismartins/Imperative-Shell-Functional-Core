from dataclasses import dataclass, field
from enum import Enum


class AccountStatus(Enum):
    HEALTHY = "HEALTHY"
    MARGIN_CALL = "MARGIN_CALL"


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


@dataclass(frozen=True)
class TriggerMarginCall:
    shortfall: float


@dataclass(frozen=True)
class Recover:
    pass


@dataclass(frozen=True)
class NoAction:
    pass


MarginDecision = TriggerMarginCall | Recover | NoAction


@dataclass
class Account:
    id: str
    email: str
    status: AccountStatus = AccountStatus.HEALTHY
    margin_shortfall: float = 0.0
    positions: list[Position] = field(default_factory=list)

    def enter_margin_call(self, shortfall: float) -> None:
        self.status = AccountStatus.MARGIN_CALL
        self.margin_shortfall = shortfall

    def recover(self) -> None:
        self.status = AccountStatus.HEALTHY
        self.margin_shortfall = 0.0

    @property
    def in_margin_call(self) -> bool:
        return self.status is AccountStatus.MARGIN_CALL
