from margin_call.models import Account, AccountStatus


def make_account(status=AccountStatus.HEALTHY, positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )
