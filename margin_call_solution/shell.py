# ==========================================
# IMPERATIVE SHELL (IO, Orchestration, Side Effects)
# ==========================================

from infra.database import db
from infra.email_service import email_service
from infra.market_data_api import market_data_api

from core import (
    AccountState,
    MarginCallContinues,
    MarginCallTriggered,
    NoChange,
    Position,
    Recovered,
    evaluate_margin,
)

def process_margin_call(account_id: str) -> None:
    """
    The shell coordinates IO. It gathers inputs, delegates to the core, 
    and applies the resulting decisions back to the outside world.
    """
    # STEP 1: Gather (Read IO)
    account_record = db.accounts.find_by_id(account_id)
    if not account_record:
        raise ValueError("Account not found")

    # Map mutable ORM object to immutable dataclass for the core
    account_state = AccountState(
        status=account_record.status,
        positions=[Position(p.asset_id, p.quantity, p.margin_rate) for p in account_record.positions]
    )

    asset_ids = [p.asset_id for p in account_state.positions]
    market_prices = market_data_api.get_latest_prices(asset_ids)

    # STEP 2: Decide (Functional Core)
    decision = evaluate_margin(account_state, market_prices)

    # STEP 3: Act (Write IO)
    match decision:
        case NoChange():
            pass
        case MarginCallTriggered(margin_shortfall=shortfall):
            save_account(account_record, 'MARGIN_CALL', shortfall)
            email_service.send_margin_call_alert(account_record.email, shortfall)
        case MarginCallContinues(margin_shortfall=shortfall):
            save_account(account_record, 'MARGIN_CALL', shortfall)
        case Recovered():
            save_account(account_record, 'HEALTHY', 0.0)

def save_account(account_record, status: str, margin_shortfall: float) -> None:
    account_record.status = status
    account_record.margin_shortfall = margin_shortfall
    db.accounts.save(account_record)
