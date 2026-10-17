"""Sentinel AI — Mock Device Registry provider."""

from __future__ import annotations

from ..fixture_data import (
    get_account,
    get_device,
    is_device_registered_to_account,
    SYNTHETIC_DATA_NOTICE,
)
from ..schemas import (
    DeviceRegistryData,
    DeviceRegistryResponse,
    EvidenceStatus,
    SourceMode,
)

_SOURCE = "MOCK_DEVICE_REGISTRY"


def check_device(account_id: str, device_id: str) -> DeviceRegistryResponse:
    """Return the device's relationship to the given account.

    Parameters
    ----------
    account_id : The account to check against.
    device_id  : The device identifier to look up.

    Returns
    -------
    DeviceRegistryResponse
        - FOUND with is_registered_to_account=True if device is known and registered.
        - FOUND with is_registered_to_account=False if device exists but not for this account.
        - NOT_FOUND if neither device nor account is in the fixture.
    """
    account = get_account(account_id)
    if account is None:
        return DeviceRegistryResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.NOT_FOUND,
            requested_entity_id=f"{account_id}:{device_id}",
            warnings=[f"Account '{account_id}' not found in mock device registry."],
        )

    device = get_device(device_id)
    registered = is_device_registered_to_account(account_id, device_id)

    if device is None:
        # Device is genuinely unknown — not previously seen
        data = DeviceRegistryData(
            device_id=device_id,
            account_id=account_id,
            registration_status="NOT_REGISTERED",
            is_registered_to_account=False,
            num_associated_accounts=0,
            associated_accounts=[],
            synthetic_notice=SYNTHETIC_DATA_NOTICE,
        )
        return DeviceRegistryResponse(
            source=_SOURCE,
            source_mode=SourceMode.MOCK,
            status=EvidenceStatus.FOUND,
            requested_entity_id=f"{account_id}:{device_id}",
            data=data,
            warnings=[f"Device '{device_id}' has no registration record in mock fixture."],
        )

    data = DeviceRegistryData(
        device_id=device_id,
        account_id=account_id,
        registration_status=device["registration_status"],
        device_type=device.get("device_type"),
        device_info=device.get("device_info"),
        device_fingerprint=device.get("device_fingerprint"),
        associated_accounts=list(device.get("associated_accounts", [])),
        first_seen=device.get("first_seen"),
        num_associated_accounts=device.get("num_associated_accounts", 0),
        is_registered_to_account=registered,
        synthetic_notice=SYNTHETIC_DATA_NOTICE,
    )

    return DeviceRegistryResponse(
        source=_SOURCE,
        source_mode=SourceMode.MOCK,
        status=EvidenceStatus.FOUND,
        requested_entity_id=f"{account_id}:{device_id}",
        data=data,
    )
