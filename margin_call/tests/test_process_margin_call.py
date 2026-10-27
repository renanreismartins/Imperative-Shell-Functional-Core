from unittest.mock import patch

import pytest

from margin_call.margin_call import process_margin_call


# The "not found" case belongs to the shell, so it keeps its db patch.
@patch("margin_call.margin_call.email_service")
@patch("margin_call.margin_call.market_data_api")
@patch("margin_call.margin_call.db")
class TestProcessMarginCall:

    def test_account_not_found_raises(self, mock_db, mock_api, mock_email):
        mock_db.accounts.find_by_id.return_value = None

        with pytest.raises(ValueError, match="Account not found"):
            process_margin_call("MISSING")
