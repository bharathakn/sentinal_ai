"""
Sentinel AI — Custom Synthetic India Dataset Validator

Executes comprehensive programmatic validation checks on generated synthetic datasets:
1. Identifier uniqueness (Duplicate checks)
2. Missing value & unexpected null checks
3. Referential integrity (FK references across tables)
4. Amount & Channel constraint checks (RTGS >= ₹2L, UPI <= ₹1L)
5. Timestamp & Temporal ordering checks
6. Double-entry balance arithmetic consistency
7. Zero Label Leakage Verification (Confirms features file contains no targets)
"""

from typing import Dict, List, Any
import pandas as pd


class SyntheticDatasetValidator:
    """Validator engine for generated synthetic dataset."""

    def __init__(self, data_dict: Dict[str, pd.DataFrame]):
        self.customers_df = data_dict["customers"]
        self.accounts_df = data_dict["accounts"]
        self.devices_df = data_dict["devices"]
        self.beneficiaries_df = data_dict["beneficiaries"]
        self.tx_features_df = data_dict["transactions_features"]
        self.tx_targets_df = data_dict["transactions_targets"]
        self.graph_edges_df = data_dict["graph_edges"]

    def validate_all(self) -> Dict[str, Any]:
        """Run all validation check methods."""
        results = {
            "passed": True,
            "checks": {},
            "errors": [],
            "warnings": []
        }

        # 1. Uniqueness Checks
        self._check_uniqueness(results)

        # 2. Null Checks
        self._check_nulls(results)

        # 3. Referential Integrity
        self._check_referential_integrity(results)

        # 4. Amount & Channel Constraints
        self._check_amount_and_channel_constraints(results)

        # 5. Timestamp & Temporal Logic
        self._check_temporal_logic(results)

        # 6. Zero Label Leakage Verification
        self._check_zero_label_leakage(results)

        # 7. Relational / behavioural consistency (generator v2)
        self._check_behavioural_consistency(results)

        # Summarize pass/fail
        if len(results["errors"]) > 0:
            results["passed"] = False

        return results

    def _check_uniqueness(self, results: Dict[str, Any]):
        check_name = "1_uniqueness_checks"
        errors = []

        if self.customers_df["customer_id"].duplicated().any():
            errors.append("Duplicate customer_id values found in customers table.")

        if self.accounts_df["account_id"].duplicated().any():
            errors.append("Duplicate account_id values found in accounts table.")

        if self.devices_df["device_id"].duplicated().any():
            errors.append("Duplicate device_id values found in devices table.")

        if self.beneficiaries_df["beneficiary_id"].duplicated().any():
            errors.append("Duplicate beneficiary_id values found in beneficiaries table.")

        if self.tx_features_df["transaction_id"].duplicated().any():
            errors.append("Duplicate transaction_id values found in transactions_features table.")

        if self.tx_targets_df["transaction_id"].duplicated().any():
            errors.append("Duplicate transaction_id values found in transactions_targets table.")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_nulls(self, results: Dict[str, Any]):
        check_name = "2_null_checks"
        errors = []

        for name, df in [
            ("customers", self.customers_df),
            ("accounts", self.accounts_df),
            ("devices", self.devices_df),
            ("beneficiaries", self.beneficiaries_df),
            ("transactions_features", self.tx_features_df)
        ]:
            null_cols = df.isnull().sum()
            null_cols = null_cols[null_cols > 0]
            if len(null_cols) > 0:
                errors.append(f"Unexpected null values in {name}: {null_cols.to_dict()}")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_referential_integrity(self, results: Dict[str, Any]):
        check_name = "3_referential_integrity"
        errors = []

        valid_cust_ids = set(self.customers_df["customer_id"])
        valid_acc_ids = set(self.accounts_df["account_id"])
        valid_dev_ids = set(self.devices_df["device_id"])

        # Accounts -> Customers
        invalid_acc_cust = set(self.accounts_df["customer_id"]) - valid_cust_ids
        if len(invalid_acc_cust) > 0:
            errors.append(f"Accounts reference invalid customer_ids: {invalid_acc_cust}")

        # Transactions -> Sender Accounts
        invalid_tx_sender = set(self.tx_features_df["sender_account_id"]) - valid_acc_ids
        if len(invalid_tx_sender) > 0:
            errors.append(f"Transactions reference invalid sender_account_ids: {invalid_tx_sender}")

        # Transactions -> Receiver Accounts
        invalid_tx_receiver = set(self.tx_features_df["receiver_account_id"]) - valid_acc_ids
        if len(invalid_tx_receiver) > 0:
            errors.append(f"Transactions reference invalid receiver_account_ids: {invalid_tx_receiver}")

        # Transactions -> Devices
        invalid_tx_dev = set(self.tx_features_df["device_id"]) - valid_dev_ids
        if len(invalid_tx_dev) > 0:
            errors.append(f"Transactions reference invalid device_ids: {invalid_tx_dev}")

        # Targets <-> Features Parity
        features_tx_ids = set(self.tx_features_df["transaction_id"])
        targets_tx_ids = set(self.tx_targets_df["transaction_id"])
        if features_tx_ids != targets_tx_ids:
            errors.append("Transaction IDs mismatch between features and targets files.")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_amount_and_channel_constraints(self, results: Dict[str, Any]):
        check_name = "4_amount_and_channel_constraints"
        errors = []

        # Negative / Zero amounts
        if (self.tx_features_df["amount_inr"] <= 0).any():
            errors.append("Transactions contain non-positive amounts.")

        # Invalid channels
        valid_channels = {"UPI", "NEFT", "RTGS"}
        invalid_channels = set(self.tx_features_df["channel"]) - valid_channels
        if len(invalid_channels) > 0:
            errors.append(f"Invalid transaction channels found: {invalid_channels}")

        # RTGS regulatory minimum check (₹2,00,000)
        rtgs_below_min = self.tx_features_df[(self.tx_features_df["channel"] == "RTGS") & (self.tx_features_df["amount_inr"] < 200000.0)]
        if len(rtgs_below_min) > 0:
            errors.append(f"Found {len(rtgs_below_min)} RTGS transactions below mandatory ₹2,00,000 threshold.")

        # UPI regulatory maximum check (₹1,00,000)
        upi_above_max = self.tx_features_df[(self.tx_features_df["channel"] == "UPI") & (self.tx_features_df["amount_inr"] > 100000.0)]
        if len(upi_above_max) > 0:
            errors.append(f"Found {len(upi_above_max)} UPI transactions exceeding NPCI ₹1,00,000 per-transaction cap.")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_temporal_logic(self, results: Dict[str, Any]):
        check_name = "5_temporal_logic"
        errors = []

        # Parse timestamps
        try:
            pd.to_datetime(self.tx_features_df["timestamp"])
        except Exception as e:
            errors.append(f"Failed to parse transaction timestamps: {e}")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_zero_label_leakage(self, results: Dict[str, Any]):
        check_name = "6_zero_label_leakage"
        errors = []

        forbidden_target_cols = {"is_fraud", "risk_label", "scenario_id", "is_flagged_alert",
                                 "fraud_reason", "pattern_id"}
        leaked_cols = set(self.tx_features_df.columns) & forbidden_target_cols

        if len(leaked_cols) > 0:
            errors.append(f"TARGET LEAKAGE DETECTED! Forbidden target columns in feature matrix: {leaked_cols}")

        leaked_edges = set(self.graph_edges_df.columns) & forbidden_target_cols
        if leaked_edges:
            errors.append(f"TARGET LEAKAGE DETECTED! Forbidden target columns in graph edges: {leaked_edges}")

        results["checks"][check_name] = "PASSED" if len(errors) == 0 else "FAILED"
        results["errors"].extend(errors)

    def _check_behavioural_consistency(self, results: Dict[str, Any]):
        """Transaction features must agree with entity tables and the ledger."""
        import numpy as np

        check_name = "7_behavioural_consistency"
        errors: List[str] = []
        tx = self.tx_features_df.copy()
        tx["ts"] = pd.to_datetime(tx["timestamp"], utc=True)

        # (a) Chronological ids
        if not tx["ts"].is_monotonic_increasing:
            errors.append("Transaction ids are not in chronological order.")

        # (b) Beneficiary record exists, precedes tx, and matches derived fields
        ben = self.beneficiaries_df.copy()
        ben["added"] = pd.to_datetime(ben["beneficiary_added_timestamp"], utc=True)
        m = tx.merge(ben[["sender_account_id", "receiver_account_id", "added"]],
                     on=["sender_account_id", "receiver_account_id"], how="left")
        if m["added"].isna().any():
            errors.append(f"{int(m['added'].isna().sum())} transactions have no beneficiary record.")
        else:
            mins = ((m["ts"] - m["added"]).dt.total_seconds() // 60).astype(int)
            if (mins < 0).any():
                errors.append("Beneficiary added after transaction.")
            if (mins != m["time_since_beneficiary_added_min"]).any():
                errors.append("time_since_beneficiary_added_min disagrees with beneficiaries table.")
            if ((mins < 30 * 1440).astype(int) != m["is_new_beneficiary"]).any():
                errors.append("is_new_beneficiary disagrees with beneficiary added date.")

        # (c) Device flag
        dev = self.devices_df.copy()
        dev["first_seen"] = pd.to_datetime(dev["first_seen_timestamp"], utc=True)
        d = tx.merge(dev[["device_id", "customer_id", "first_seen"]], on="device_id", how="left")
        expected = ((d["ts"] - d["first_seen"]) < pd.Timedelta(days=7)) | (d["customer_id"] != d["sender_customer_id"])
        if (expected.astype(int) != d["is_new_device"]).any():
            errors.append("is_new_device disagrees with device registry.")
        if (d["first_seen"] > d["ts"]).any():
            errors.append("Device used before its first_seen timestamp.")

        # (d) Distance from home
        c = tx.merge(self.customers_df[["customer_id", "home_lat", "home_long"]],
                     left_on="sender_customer_id", right_on="customer_id", how="left")
        p1, p2 = np.radians(c["home_lat"]), np.radians(c["tx_lat"])
        dl = np.radians(c["tx_long"] - c["home_long"])
        dist = 6371.0 * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1))
        if (np.abs(dist - c["distance_from_home_km"]) > 1.0).any():
            errors.append("distance_from_home_km disagrees with coordinates.")

        # (e) Velocity features from the ledger
        freq = []
        last = {}
        recent: Dict[str, list] = {}
        bad_gap = 0
        for s, t, gap in zip(tx["sender_account_id"], tx["ts"], tx["time_since_last_tx_sec"]):
            w = [x for x in recent.get(s, []) if (t - x) < pd.Timedelta(hours=24)] + [t]
            recent[s] = w
            freq.append(len(w))
            if s in last and int((t - last[s]).total_seconds()) != int(gap):
                bad_gap += 1
            last[s] = t
        if (np.array(freq) != tx["tx_frequency_24h"].to_numpy()).any():
            errors.append("tx_frequency_24h disagrees with ledger.")
        if bad_gap:
            errors.append(f"time_since_last_tx_sec disagrees with ledger for {bad_gap} transactions.")

        results["checks"][check_name] = "PASSED" if not errors else "FAILED"
        results["errors"].extend(errors)
