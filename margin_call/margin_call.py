from margin_call.infra.database import db
from margin_call.infra.email_service import email_service
from margin_call.infra.market_data_api import market_data_api
from margin_call.models import Account, PortfolioValuation, Position


def process_margin_call(account_id: str) -> None:
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise ValueError("Account not found")

    asset_ids = [p.asset_id for p in account.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    evaluate_margin(account, market_prices)


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


def evaluate_margin(account: Account, market_prices: dict[str, float]) -> None:
    valuation = value_portfolio(account.positions, market_prices)

    if valuation.margin_level is None:
        return

    if valuation.margin_level < 1.0:
        shortfall = valuation.margin_requirement - valuation.total_value

        account.status = 'MARGIN_CALL'
        account.margin_shortfall = shortfall
        db.accounts.save(account)

        email_service.send_margin_call_alert(account.email, shortfall)

    elif valuation.margin_level > 1.5 and account.status == 'MARGIN_CALL':
        account.status = 'HEALTHY'
        account.margin_shortfall = 0.0
        db.accounts.save(account)
