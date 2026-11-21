"""
Sentinel AI — Mock Geolocation provider.

Compares transaction location with the registered account location and
calculates approximate distance using the Haversine formula.

All location data comes from the active evidence data store (data_store.py).
"""

from __future__ import annotations

import math
from typing import Optional

from ..data_store import get_store
from ..schemas import (
    EvidenceStatus,
    GeolocationData,
    GeolocationResponse,
    SourceMode,
)

_SOURCE_SUFFIX = "GEOLOCATION"

# Distance threshold (km) above which a transaction is flagged as anomalous.
_ANOMALY_DISTANCE_KM = 500.0


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate great-circle distance in km using the Haversine formula."""
    r = 6371.0  # Earth radius km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def check_geolocation(
    account_id: str,
    transaction_latitude: Optional[float],
    transaction_longitude: Optional[float],
    transaction_city: Optional[str] = None,
    transaction_country: Optional[str] = None,
) -> GeolocationResponse:
    """Compare transaction location with the account's registered location.

    Parameters
    ----------
    account_id              : Account to look up.
    transaction_latitude    : Latitude of the transaction origin (None if unavailable).
    transaction_longitude   : Longitude of the transaction origin (None if unavailable).
    transaction_city        : Human-readable city name (optional).
    transaction_country     : Human-readable country name (optional).

    Returns
    -------
    GeolocationResponse
        - FOUND when account is known.
        - NOT_FOUND when account is unknown.
        - is_anomalous=True when distance exceeds _ANOMALY_DISTANCE_KM.
        - is_anomalous=None when coordinates are unavailable (distinct from False).
    """
    store = get_store()
    _SOURCE = f"{store.source_prefix}_{_SOURCE_SUFFIX}"
    account = store.get_account(account_id)
    if account is None:
        return GeolocationResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=account_id,
            warnings=[f"Account '{account_id}' not found in geolocation records."],
        )

    reg_lat = account.get("registered_latitude")
    reg_lon = account.get("registered_longitude")
    reg_city = account.get("registered_city")
    reg_country = account.get("registered_country")

    # Compute distance only when both coordinate pairs are available
    distance_km: Optional[float] = None
    is_anomalous: Optional[bool] = None
    anomaly_reason: Optional[str] = None
    location_available = transaction_latitude is not None and transaction_longitude is not None

    if location_available and reg_lat is not None and reg_lon is not None:
        distance_km = _haversine_km(reg_lat, reg_lon, transaction_latitude, transaction_longitude)
        is_anomalous = distance_km >= _ANOMALY_DISTANCE_KM
        if is_anomalous:
            anomaly_reason = (
                f"Transaction location is {distance_km:.0f} km from registered location "
                f"(threshold: {_ANOMALY_DISTANCE_KM:.0f} km)."
            )
    elif not location_available:
        is_anomalous = None   # Cannot determine — not the same as False
        anomaly_reason = "Transaction coordinates not available; location check not possible."

    data = GeolocationData(
        account_id=account_id,
        transaction_city=transaction_city,
        transaction_country=transaction_country,
        transaction_latitude=transaction_latitude,
        transaction_longitude=transaction_longitude,
        registered_city=reg_city,
        registered_country=reg_country,
        registered_latitude=reg_lat,
        registered_longitude=reg_lon,
        distance_km=round(distance_km, 2) if distance_km is not None else None,
        is_anomalous=is_anomalous,
        anomaly_reason=anomaly_reason,
        location_data_available=location_available,
        synthetic_notice=store.synthetic_notice,
    )

    warnings = []
    if not location_available:
        warnings.append(
            "Transaction coordinates not provided. is_anomalous is None — "
            "this is not the same as confirming a normal location."
        )

    return GeolocationResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=account_id,
        data=data,
        warnings=warnings,
    )
