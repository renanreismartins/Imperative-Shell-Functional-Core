from margin_call.core import decide_margin_action, value_portfolio
from margin_call.infra.database import db
from margin_call.infra.email_service import email_service
from margin_call.infra.market_data_api import market_data_api
from margin_call.models import NoAction, Recover, TriggerMarginCall


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
