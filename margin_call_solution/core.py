from dataclasses import dataclass
from typing import List, Dict

# ==========================================
# FUNCTIONAL CORE (Pure, Deterministic, Testable)
# ==========================================

@dataclass(frozen=True)
class Position:
    asset_id: str
    quantity: float
    margin_rate: float

@dataclass(frozen=True)
class AccountState:
    status: str
    positions: List[Position]

@dataclass(frozen=True)
class NoChange:
    pass

@dataclass(frozen=True)
class MarginCallTriggered:
    margin_shortfall: float

@dataclass(frozen=True)
class MarginCallContinues:
    margin_shortfall: float

@dataclass(frozen=True)
class Recovered:
    pass

MarginDecision = NoChange | MarginCallTriggered | MarginCallContinues | Recovered

def evaluate_margin(account: AccountState, market_prices: Dict[str, float]) -> MarginDecision:
    """
    Pure function. Computes margin health given current state and market data.
    Returns a decision of what *should* happen, without mutating anything.
    """
    total_portfolio_value = 0.0
    maintenance_margin_requirement = 0.0

    for position in account.positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_portfolio_value += position_value
        maintenance_margin_requirement += position_value * position.margin_rate
        
    if maintenance_margin_requirement == 0:
        return NoChange()

    margin_level = total_portfolio_value / maintenance_margin_requirement

    if margin_level < 1.0:
        shortfall = maintenance_margin_requirement - total_portfolio_value
        # Determine if this is a newly triggered call to avoid spamming emails
        if account.status != 'MARGIN_CALL':
            return MarginCallTriggered(margin_shortfall=shortfall)
        return MarginCallContinues(margin_shortfall=shortfall)

    if margin_level > 1.5 and account.status == 'MARGIN_CALL':
        return Recovered()

    # No state change required
    return NoChange()
