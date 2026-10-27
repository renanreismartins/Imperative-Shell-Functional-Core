import logging

logger = logging.getLogger("market_data_api")


class _MarketDataApi:
    def get_latest_prices(self, asset_ids: list[str]) -> dict[str, float]:
        logger.info("API READ: get_latest_prices(%s)", asset_ids)
        return {asset_id: 100.0 for asset_id in asset_ids}


market_data_api = _MarketDataApi()
