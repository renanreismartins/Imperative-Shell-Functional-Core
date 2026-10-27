import pytest

from core import (
    AccountState,
    MarginCallContinues,
    MarginCallTriggered,
    NoChange,
    Position,
    Recovered,
    evaluate_margin,
)


def account(status="HEALTHY", positions=None):
    return AccountState(status=status, positions=positions or [])


class TestNoChange:
    def test_no_positions(self):
        assert evaluate_margin(account(), {}) == NoChange()

    def test_zero_margin_requirement(self):
        acc = account(positions=[Position("AAPL", 10, margin_rate=0.0)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()

    def test_missing_price_defaults_to_zero(self):
        acc = account(positions=[Position("UNKNOWN", 10, margin_rate=0.5)])
        assert evaluate_margin(acc, {}) == NoChange()

    def test_healthy_account_stays_healthy(self):
        # value = 1000; requirement = 250; margin_level = 4.0
        acc = account(positions=[Position("AAPL", 10, margin_rate=0.25)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()

    def test_margin_level_exactly_one_is_not_a_margin_call(self):
        # value = 1000; requirement = 1000; margin_level = 1.0
        acc = account(positions=[Position("AAPL", 10, margin_rate=1.0)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()


class TestMarginCall:
    def test_triggered_from_healthy(self):
        # value = 1000; requirement = 1500; shortfall = 500
        acc = account(positions=[Position("TSLA", 10, margin_rate=1.5)])
        decision = evaluate_margin(acc, {"TSLA": 100.0})
        assert decision == MarginCallTriggered(margin_shortfall=pytest.approx(500.0))

    def test_continues_when_already_in_margin_call(self):
        acc = account(status="MARGIN_CALL", positions=[Position("TSLA", 10, margin_rate=1.5)])
        decision = evaluate_margin(acc, {"TSLA": 100.0})
        assert decision == MarginCallContinues(margin_shortfall=pytest.approx(500.0))

    def test_shortfall_aggregates_across_positions(self):
        # AAPL: value 1000, req 500; TSLA: value 500, req 1500
        # total value = 1500; total req = 2000; shortfall = 500
        acc = account(positions=[
            Position("AAPL", 10, margin_rate=0.5),
            Position("TSLA", 5, margin_rate=3.0),
        ])
        decision = evaluate_margin(acc, {"AAPL": 100.0, "TSLA": 100.0})
        assert decision == MarginCallTriggered(margin_shortfall=pytest.approx(500.0))


class TestRecovery:
    def test_recovers_above_buffer(self):
        # value = 1000; requirement = 500; margin_level = 2.0 > 1.5
        acc = account(status="MARGIN_CALL", positions=[Position("AAPL", 10, margin_rate=0.5)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == Recovered()

    def test_no_recovery_at_exactly_buffer_level(self):
        # value = 1500; requirement = 1000; margin_level = 1.5 (not > 1.5)
        acc = account(status="MARGIN_CALL", positions=[Position("AAPL", 15, margin_rate=2 / 3)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()

    def test_no_recovery_in_hysteresis_band(self):
        # value = 1200; requirement = 1000; margin_level = 1.2 (between 1.0 and 1.5)
        acc = account(status="MARGIN_CALL", positions=[Position("AAPL", 12, margin_rate=1 / 1.2)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()

    def test_healthy_account_above_buffer_is_no_change(self):
        acc = account(status="HEALTHY", positions=[Position("AAPL", 10, margin_rate=0.5)])
        assert evaluate_margin(acc, {"AAPL": 100.0}) == NoChange()
