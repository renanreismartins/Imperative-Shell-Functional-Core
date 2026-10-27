import logging

logger = logging.getLogger("email_service")


class _EmailService:
    def send_margin_call_alert(self, email: str, shortfall: float) -> None:
        logger.info("EMAIL SEND: margin call alert to %s, shortfall=%.2f", email, shortfall)


email_service = _EmailService()
