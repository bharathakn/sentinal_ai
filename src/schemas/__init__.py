"""
Sentinel AI — Canonical Schema Package

Exports the canonical CanonicalTransaction model and dataset adapters.
"""

from .canonical_transaction import (
    CanonicalTransaction,
    TransactionChannel,
    TransactionStatus,
    DataSource,
    GeoLocation,
    DeviceInfo,
    AccountInfo,
    TransactionMetadata,
)
from .adapters.ieee_cis_adapter import IEEECISAdapter
from .adapters.paysim_adapter import PaySimAdapter
from .adapters.india_adapter import IndiaSyntheticAdapter

__all__ = [
    "CanonicalTransaction",
    "TransactionChannel",
    "TransactionStatus",
    "DataSource",
    "GeoLocation",
    "DeviceInfo",
    "AccountInfo",
    "TransactionMetadata",
    "IEEECISAdapter",
    "PaySimAdapter",
    "IndiaSyntheticAdapter",
]
