from margin_call.models import (
    AccountSnapshot,
    MarginDecision,
    NoAction,
    PortfolioValuation,
    Position,
    Recover,
    TriggerMarginCall,
)


def value_portfolio(
    positions: tuple[Position, ...], market_prices: dict[str, float]
) -> PortfolioValuation:
    total_value = 0.0
    margin_requirement = 0.0

    for position in positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_value += position_value
        margin_requirement += position_value * position.margin_rate

    return PortfolioValuation(total_value, margin_requirement)


def decide_margin_action(
    snapshot: AccountSnapshot, valuation: PortfolioValuation
) -> MarginDecision:
    if valuation.margin_level is None:
        return NoAction()

    if valuation.margin_level < 1.0:
        return TriggerMarginCall(
            shortfall=valuation.margin_requirement - valuation.total_value
        )

    if valuation.margin_level > 1.5 and snapshot.in_margin_call:
        return Recover()

    return NoAction()
