"""Sentinel AI — Evidence providers package."""
from .core_banking import get_account_history
from .kyc import get_kyc_data
from .device_registry import check_device
from .beneficiary import get_beneficiary
from .sanctions import screen_subject, screen_account
from .geolocation import check_geolocation
from .news.mock_provider import MockNewsProvider
from .news.newsapi_provider import NewsAPIProvider
from .news.base import BaseNewsProvider

__all__ = [
    "get_account_history",
    "get_kyc_data",
    "check_device",
    "get_beneficiary",
    "screen_subject",
    "screen_account",
    "check_geolocation",
    "MockNewsProvider",
    "NewsAPIProvider",
    "BaseNewsProvider",
]
