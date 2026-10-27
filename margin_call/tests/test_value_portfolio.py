import pytest

from margin_call.core import value_portfolio
from margin_call.models import Position


# Pure core: no mocks, no patches — data in, data out.
class TestValuePortfolio:

    def test_values_single_position(self):
        positions = (Position(asset_id="AAPL", quantity=10, margin_rate=0.25),)

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.total_value == pytest.approx(1000.0)
        assert valuation.margin_requirement == pytest.approx(250.0)
        assert valuation.margin_level == pytest.approx(4.0)

    def test_sums_multiple_positions(self):
        positions = (
            Position(asset_id="AAPL", quantity=10, margin_rate=0.25),
            Position(asset_id="TSLA", quantity=5, margin_rate=0.5),
        )

        valuation = value_portfolio(positions, {"AAPL": 100.0, "TSLA": 200.0})

        # AAPL: 1000 (req 250), TSLA: 1000 (req 500)
        assert valuation.total_value == pytest.approx(2000.0)
        assert valuation.margin_requirement == pytest.approx(750.0)

    def test_missing_price_defaults_to_zero(self):
        positions = (Position(asset_id="UNKNOWN", quantity=10, margin_rate=0.5),)

        valuation = value_portfolio(positions, {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_no_positions(self):
        valuation = value_portfolio((), {})

        assert valuation.total_value == 0.0
        assert valuation.margin_requirement == 0.0

    def test_margin_level_is_none_when_no_requirement(self):
        positions = (Position(asset_id="AAPL", quantity=10, margin_rate=0.0),)

        valuation = value_portfolio(positions, {"AAPL": 100.0})

        assert valuation.margin_level is None
