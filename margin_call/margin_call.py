from margin_call.infra.database import db
from margin_call.infra.email_service import email_service
from margin_call.infra.market_data_api import market_data_api
from margin_call.models import Account


def process_margin_call(account_id: str) -> None:
    account = db.accounts.find_by_id(account_id)
    if not account:
        raise ValueError("Account not found")

    asset_ids = [p.asset_id for p in account.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    evaluate_margin(account, market_prices)


def evaluate_margin(account: Account, market_prices: dict[str, float]) -> None:
    total_portfolio_value = 0.0
    maintenance_margin_requirement = 0.0

    for position in account.positions:
        price = market_prices.get(position.asset_id, 0.0)
        position_value = position.quantity * price
        total_portfolio_value += position_value
        maintenance_margin_requirement += position_value * position.margin_rate

    if maintenance_margin_requirement == 0:
        return

    margin_level = total_portfolio_value / maintenance_margin_requirement

    if margin_level < 1.0:
        shortfall = maintenance_margin_requirement - total_portfolio_value

        account.status = 'MARGIN_CALL'
        account.margin_shortfall = shortfall
        db.accounts.save(account)

        email_service.send_margin_call_alert(account.email, shortfall)

    elif margin_level > 1.5 and account.status == 'MARGIN_CALL':
        account.status = 'HEALTHY'
        account.margin_shortfall = 0.0
        db.accounts.save(account)
