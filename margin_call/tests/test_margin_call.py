from unittest.mock import patch, MagicMock

import pytest

from margin_call.margin_call import process_margin_call
from margin_call.models import Account, Position


def make_account(status="HEALTHY", positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


# Every single test needs all three patches, even the ones that are
# "really" about pure arithmetic.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")

    def test_healthy_account_does_nothing(self, mock_db, mock_api, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"AAPL": 100.0}

        process_margin_call("ACC-1")

        # Behavior assertions: we can only "see" the result by spying
        # on what was (not) called.
        mock_db.accounts.save.assert_not_called()
        mock_email.send_margin_call_alert.assert_not_called()

    def test_margin_call_triggered(self, mock_db, mock_api, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 1.5 = 1500
        # margin_level = 1000 / 1500 < 1.0 -> shortfall = 500
        account = make_account(positions=[
            Position(asset_id="TSLA", quantity=10, margin_rate=1.5),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"TSLA": 100.0}

        process_margin_call("ACC-1")

        assert account.status == "MARGIN_CALL"
        assert account.margin_shortfall == pytest.approx(500.0)
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_called_once_with(
            "trader@example.com", pytest.approx(500.0)
        )

    def test_recovery_back_to_healthy(self, mock_db, mock_api, mock_email):
        # value = 10 * 100 = 1000; requirement = 1000 * 0.5 = 500
        # margin_level = 2.0 > 1.5 and status is MARGIN_CALL -> recover
        account = make_account(status="MARGIN_CALL", positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"AAPL": 100.0}

        process_margin_call("ACC-1")

        assert account.status == "HEALTHY"
        assert account.margin_shortfall == 0.0
        mock_db.accounts.save.assert_called_once_with(account)
        mock_email.send_margin_call_alert.assert_not_called()

    def test_zero_margin_requirement_returns_early(self, mock_db, mock_api, mock_email):
        account = make_account(positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.0),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {"AAPL": 100.0}

        process_margin_call("ACC-1")

        mock_db.accounts.save.assert_not_called()

    def test_missing_price_defaults_to_zero(self, mock_db, mock_api, mock_email):
        # Price missing from API response -> value 0, requirement 0 -> early return
        account = make_account(positions=[
            Position(asset_id="UNKNOWN", quantity=10, margin_rate=0.5),
        ])
        mock_db.accounts.find_by_id.return_value = account
        mock_api.get_latest_prices.return_value = {}

        process_margin_call("ACC-1")

        mock_db.accounts.save.assert_not_called()
