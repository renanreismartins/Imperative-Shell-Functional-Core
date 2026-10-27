from margin_call.models import AccountSnapshot, AccountStatus, Position
from margin_call.tests.factories import make_account


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


# Pure core: the boundary mapping from entity to immutable snapshot.
class TestAccountSnapshot:

    def test_snapshot_captures_status_and_positions(self):
        account = make_account(status=AccountStatus.MARGIN_CALL, positions=[
            Position(asset_id="AAPL", quantity=10, margin_rate=0.5),
        ])

        snapshot = AccountSnapshot.of(account)

        assert snapshot.status is AccountStatus.MARGIN_CALL
        assert snapshot.in_margin_call
        assert snapshot.positions == tuple(account.positions)

    def test_snapshot_is_detached_from_later_mutation(self):
        account = make_account()
        snapshot = AccountSnapshot.of(account)

        account.enter_margin_call(500.0)
        account.positions.append(
            Position(asset_id="TSLA", quantity=1, margin_rate=0.5)
        )

        assert snapshot.status is AccountStatus.HEALTHY
        assert snapshot.positions == ()
