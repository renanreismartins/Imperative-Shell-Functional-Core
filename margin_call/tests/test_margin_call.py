from unittest.mock import patch

import pytest

from margin_call.margin_call import (
    evaluate_margin,
    process_margin_call,
    value_portfolio,
)
from margin_call.models import Account, Position


def make_account(status="HEALTHY", positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


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


# Only the writes need patching now.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.db")
class TestEvaluateMargin:

    def test_healthy_account_does_nothing(self, mock_db, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        assert account.status == "HEALTHY"
        mock_db.accounts.save.assert_not_called()
        mock_email.send_margin_call_alert.assert_not_called()

    def test_margin_call_triggered(self, mock_db, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 1.5 = 1500
        # margin_level = 1000 / 1500 < 1.0 -> shortfall = 500
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])

        evaluate_margin(account, {"TSLA": 100.0})

        assert account.status == "MARGIN_CALL"
        assert account.margin_shortfall == pytest.approx(500.0)
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_called_once_with(
            "trader@example.com", pytest.approx(500.0)
        )

    def test_recovery_back_to_healthy(self, mock_db, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 0.5 = 500
        # margin_level = 2.0 > 1.5 and status is MARGIN_CALL -> recover
        account = make_account(status="MARGIN_CALL", positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        assert account.status == "HEALTHY"
        assert account.margin_shortfall == 0.0
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_not_called()

    def test_zero_margin_requirement_does_nothing(self, mock_db, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])

        evaluate_margin(account, {"AAPL": 100.0})

        mock_db.accounts.save.assert_not_called()


# The "not found" case belongs to the shell, so it keeps its db patch.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")
