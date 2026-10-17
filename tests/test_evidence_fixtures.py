"""
Tests for the centralised synthetic evidence fixture data.

Verifies internal consistency of the single source of truth before
individual provider tests run.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.evidence.fixture_data import (
    ACCOUNTS,
    ACCOUNT_DEVICES,
    ACCOUNT_SANCTIONS_KEY,
    ACCOUNT_STATS,
    DEVICES,
    SANCTIONS_SUBJECTS,
    TRANSACTION_HISTORY,
    SYNTHETIC_DATA_NOTICE,
    get_account,
    get_account_devices,
    get_account_stats,
    get_device,
    get_news_articles,
    get_sanctions_result,
    get_transaction_history,
    is_device_registered_to_account,
)


class TestFixtureIntegrity:
    """Verify the fixture data is internally self-consistent."""

    def test_all_known_accounts_present(self):
        for acc_id in ("ACC001", "ACC002", "ACC003", "ACC004"):
            assert acc_id in ACCOUNTS, f"{acc_id} missing from ACCOUNTS fixture."

    def test_all_known_devices_present(self):
        for dev_id in ("DEV001", "DEV002", "DEV003"):
            assert dev_id in DEVICES, f"{dev_id} missing from DEVICES fixture."

    def test_account_stats_match_accounts(self):
        for acc_id in ACCOUNTS:
            stats = get_account_stats(acc_id)
            assert stats is not None, f"No stats for {acc_id}."

    def test_transaction_history_counterparties_are_consistent(self):
        """ACC001 debits to ACC002 should match ACC002 credits from ACC001."""
        acc001_to_acc002 = [
            tx for tx in get_transaction_history("ACC001")
            if tx["counterparty_id"] == "ACC002" and tx["direction"] == "DEBIT"
        ]
        acc002_from_acc001 = [
            tx for tx in get_transaction_history("ACC002")
            if tx["counterparty_id"] == "ACC001" and tx["direction"] == "CREDIT"
        ]
        # Same number of mirrored transactions
        assert len(acc001_to_acc002) == len(acc002_from_acc001)
        # Amounts match between the two sides
        debit_amounts = sorted(float(tx["amount_inr"]) for tx in acc001_to_acc002)
        credit_amounts = sorted(float(tx["amount_inr"]) for tx in acc002_from_acc001)
        assert debit_amounts == credit_amounts

    def test_avg_debit_agrees_with_history(self):
        """ACCOUNT_STATS avg_debit_amount_inr must agree with actual debit transactions."""
        history = get_transaction_history("ACC001")
        debits = [tx for tx in history if tx["direction"] == "DEBIT"]
        assert len(debits) > 0
        actual_avg = sum(float(tx["amount_inr"]) for tx in debits) / len(debits)
        stats = get_account_stats("ACC001")
        assert stats is not None
        recorded_avg = stats["avg_debit_amount_inr"]
        assert abs(float(recorded_avg) - actual_avg) < 1.0, (
            f"avg_debit mismatch: fixture={recorded_avg}, computed={actual_avg}"
        )

    def test_acc003_is_recently_created(self):
        """ACC003 is the 'new account' scenario — must be very recently created."""
        from datetime import datetime, timezone
        acc003 = get_account("ACC003")
        opening = acc003["account_opening_date"]
        ref = datetime(2024, 1, 15, tzinfo=timezone.utc)
        age_days = (ref - opening).days
        assert age_days <= 5, f"ACC003 should be a new account (< 5 days), got {age_days}."

    def test_dev001_registered_to_acc001_only(self):
        dev = get_device("DEV001")
        assert "ACC001" in dev["associated_accounts"]
        assert dev["num_associated_accounts"] == 1

    def test_dev002_is_new_unregistered(self):
        dev = get_device("DEV002")
        assert dev["registration_status"] == "NOT_REGISTERED"
        assert dev["associated_accounts"] == []
        assert dev["first_seen"] is None

    def test_dev003_is_shared(self):
        dev = get_device("DEV003")
        assert dev["num_associated_accounts"] == 3
        assert len(dev["associated_accounts"]) == 3

    def test_account_devices_match_device_fixture(self):
        """ACCOUNT_DEVICES must agree with DEVICES.associated_accounts."""
        for acc_id, device_ids in ACCOUNT_DEVICES.items():
            for dev_id in device_ids:
                dev = get_device(dev_id)
                assert dev is not None
                assert acc_id in dev["associated_accounts"], (
                    f"ACCOUNT_DEVICES says {acc_id} has {dev_id}, "
                    f"but DEVICES[{dev_id}].associated_accounts does not list it."
                )

    def test_sanctions_acc004_is_matched(self):
        key = ACCOUNT_SANCTIONS_KEY.get("ACC004")
        assert key is not None
        fixture = get_sanctions_result(key)
        assert fixture is not None
        assert fixture["matched"] is True

    def test_sanctions_acc001_is_clean(self):
        key = ACCOUNT_SANCTIONS_KEY.get("ACC001")
        assert key is not None
        fixture = get_sanctions_result(key)
        assert fixture is not None
        assert fixture["matched"] is False

    def test_synthetic_notice_present_in_all_accounts(self):
        for acc_id, acc in ACCOUNTS.items():
            assert "synthetic_notice" in acc, f"No synthetic_notice on {acc_id}."
            assert "SYNTHETIC" in acc["synthetic_notice"].upper()

    def test_no_real_pan_numbers(self):
        """No account should contain real PAN patterns (XXXXX9999X format)."""
        import re
        pan_pattern = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
        for acc_id, acc in ACCOUNTS.items():
            for field, value in acc.items():
                if isinstance(value, str):
                    assert not pan_pattern.search(value), (
                        f"Possible real PAN number found in {acc_id}.{field}: {value}"
                    )

    def test_get_account_unknown_returns_none(self):
        assert get_account("DOES_NOT_EXIST") is None

    def test_get_transaction_history_unknown_returns_empty(self):
        assert get_transaction_history("DOES_NOT_EXIST") == []

    def test_get_account_stats_unknown_returns_none(self):
        assert get_account_stats("DOES_NOT_EXIST") is None

    def test_is_device_registered_consistency(self):
        assert is_device_registered_to_account("ACC001", "DEV001") is True
        assert is_device_registered_to_account("ACC001", "DEV002") is False
        assert is_device_registered_to_account("ACC002", "DEV001") is False

    def test_news_fixture_for_sanctions_subject_has_articles(self):
        articles = get_news_articles("Synthetic Fraudster One")
        assert len(articles) >= 1

    def test_news_fixture_for_normal_account_is_empty(self):
        articles = get_news_articles("Arjun Sharma (SYNTHETIC)")
        assert articles == []
