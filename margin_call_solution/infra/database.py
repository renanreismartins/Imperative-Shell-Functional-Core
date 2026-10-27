import logging

from models import Account, Position

logger = logging.getLogger("database")


class _Accounts:
    def find_by_id(self, account_id: str) -> Account | None:
        logger.info("DB READ: accounts.find_by_id(%s)", account_id)
        return Account(
            id=account_id,
            email="trader@example.com",
            positions=[
                Position(asset_id="AAPL", quantity=100, margin_rate=0.25),
                Position(asset_id="TSLA", quantity=50, margin_rate=0.40),
            ],
        )

    def save(self, account: Account) -> None:
        logger.info(
            "DB WRITE: accounts.save(id=%s, status=%s, shortfall=%.2f)",
            account.id,
            account.status,
            account.margin_shortfall,
        )


class _Database:
    accounts = _Accounts()


db = _Database()
