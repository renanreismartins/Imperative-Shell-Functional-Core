from margin_call.models import AccountStatus
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
