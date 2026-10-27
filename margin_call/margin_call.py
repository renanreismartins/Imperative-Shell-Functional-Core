from margin_call.infra.database import db
from margin_call.infra.email_service import email_service
from margin_call.infra.market_data_api import market_data_api
from margin_call.models import (
    Account,
    MarginDecision,
    NoAction,
    PortfolioValuation,
    Position,
    Recover,
    TriggerMarginCall,
)


def process_margin_call(account_id: str) -> None:
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise ValueError("Account not found")

    asset_ids = [p.asset_id for p in account.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    valuation = value_portfolio(account.positions, market_prices)
    decision = decide_margin_action(account, valuation)

    match decision:
        case TriggerMarginCall(shortfall=shortfall):
            account.enter_margin_call(shortfall)
            db.accounts.save(account)
            email_service.send_margin_call_alert(account.email, shortfall)
        case Recover():
            account.recover()
            db.accounts.save(account)
        case NoAction():
            pass


def value_portfolio(
    positions: list[Position], market_prices: dict[str, float]
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
    account: Account, valuation: PortfolioValuation
) -> MarginDecision:
    if valuation.margin_level is None:
        return NoAction()

    if valuation.margin_level < 1.0:
        return TriggerMarginCall(
            shortfall=valuation.margin_requirement - valuation.total_value
        )

    if valuation.margin_level > 1.5 and account.in_margin_call:
        return Recover()

    return NoAction()
