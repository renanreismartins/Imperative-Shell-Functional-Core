from margin_call.models import Account, AccountSnapshot, AccountStatus


def make_account(status=AccountStatus.HEALTHY, positions=None):
    return Account(
        id="ACC-1",
        email="trader@example.com",
        status=status,
        positions=positions or [],
    )


def make_snapshot(status=AccountStatus.HEALTHY, positions=()):
    return AccountSnapshot(status=status, positions=tuple(positions))
