from unittest.mock import patch

import pytest

from margin_call.margin_call import (
    decide_margin_action,
    process_margin_call,
    value_portfolio,
)
from margin_call.models import (
    Account,
    AccountStatus,
    NoAction,
    Position,
    Recover,
    TriggerMarginCall,
)


def make_account(status=AccountStatus.HEALTHY, positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


# Pure core: the model's state transitions, no mocks.
class TestAccountTransitions:

    def test_new_account_is_healthy(self):
        account = make_account()

        assert account.status is AccountStatus.HEALTHY
        assert not account.in_margin_call

    def test_enter_margin_call(self):
        account = make_account()

        account.enter_margin_call(500.0)

        assert account.status is AccountStatus.MARGIN_CALL
        assert account.in_margin_call
        assert account.margin_shortfall == 500.0

    def test_recover(self):
        account = make_account(status=AccountStatus.MARGIN_CALL)
        account.margin_shortfall = 500.0

        account.recover()

        assert account.status is AccountStatus.HEALTHY
        assert not account.in_margin_call
        assert account.margin_shortfall == 0.0


# Pure core: no mocks, no patches — data in, data out.
class TestValuePortfolio:

    def test_values_single_position(self):
        positions = [Position(asset_id="AAPL", quantity=10, margin_rate=0.25)]

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.total_value == pytest.approx(1000.0)
        assert valuation.margin_requirement == pytest.approx(250.0)
        assert valuation.margin_level == pytest.approx(4.0)

    def test_sums_multiple_positions(self):
        positions = [
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
            Position(asset_id="TSLA", quantity=5, margin_rate=0.5),
        ]

        valuation = value_portfolio(positions, {"AAPL": 100.0, "TSLA": 200.0})

        # AAPL: 1000 (req 250), TSLA: 1000 (req 500)
        assert valuation.total_value == pytest.approx(2000.0)
        assert valuation.margin_requirement == pytest.approx(750.0)

    def test_missing_price_defaults_to_zero(self):
        positions = [Position(asset_id="UNKNOWN", quantity=10, margin_rate=0.5)]

        valuation = value_portfolio(positions, {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_no_positions(self):
        valuation = value_portfolio([], {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_margin_level_is_none_when_no_requirement(self):
        positions = [Position(asset_id="AAPL", quantity=10, margin_rate=0.0)]

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.margin_level is None


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


# The "not found" case belongs to the shell, so it keeps its db patch.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")
