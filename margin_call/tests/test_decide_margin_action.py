import pytest

from margin_call.margin_call import decide_margin_action, value_portfolio
from margin_call.models import (
    AccountStatus,
    NoAction,
    Position,
    Recover,
    TriggerMarginCall,
)
from margin_call.tests.factories import make_account


# Pure core: the decision policy, no mocks.
class TestDecideMarginAction:

    def test_healthy_account_no_action(self):
        # level = 1000 / 250 = 4.0
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_below_requirement_triggers_margin_call(self):
        # value 1000, requirement 1500 -> shortfall 500
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])
        valuation = value_portfolio(account.positions, {"TSLA": 100.0})

        decision = decide_margin_action(account, valuation)

        assert decision == TriggerMarginCall(shortfall=pytest.approx(500.0))

    def test_recovers_above_threshold_when_in_margin_call(self):
        # level = 1000 / 500 = 2.0 > 1.5
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == Recover()

    def test_high_level_but_already_healthy_no_action(self):
        # Same valuation as recovery, but status is HEALTHY
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_in_hysteresis_band_no_action(self):
        # level = 1000 / 800 = 1.25: above 1.0, below 1.5 -> stay put
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.8),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()

    def test_no_margin_requirement_no_action(self):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])
        valuation = value_portfolio(account.positions, {"AAPL": 100.0})

        assert decide_margin_action(account, valuation) == NoAction()
