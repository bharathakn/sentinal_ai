# FILE: docs/16_DATA/CANONICAL_TRANSACTION_SCHEMA.md

# Sentinel AI — Canonical Transaction Schema

## 1. Purpose

Sentinel AI ingests transactions from three datasets with entirely different schemas:

| Dataset | Primary Format | Currency | Has Timestamps |
|---|---|---|---|
| IEEE-CIS | Card-based e-commerce, 400+ features | USD | No (relative delta only) |
| PaySim | Simulated mobile-money transactions | USD (synthetic) | No (simulation step only) |
| India Synthetic | Indian payment rails (UPI/NEFT/RTGS) | INR | Yes (ISO-8601 offset-aware) |

Rather than have every agent understand each dataset's raw column names, Sentinel AI defines a **canonical internal transaction representation** (`CanonicalTransaction`) that all datasets are normalized into before entering the agent pipeline.

---

## 2. Design Principles

- Agents consume `CanonicalTransaction`, never raw dataset-specific column names.
- Every canonical record preserves `source_dataset` and `raw_record_id` for full provenance.
- All optional fields are explicitly `Optional` to accommodate dataset gaps gracefully.
- Business rules (non-negative amount, valid currency, non-empty ID) are enforced at ingestion via Pydantic v2 validators.
- The schema is intentionally broad to accommodate future datasets and live banking data.

---

## 3. Canonical Schema — Field Reference

### 3.1 CanonicalTransaction (root model)

| Field | Type | Required | Description |
|---|---|---|---|
| `canonical_id` | `UUID` | Auto-generated | Stable internal UUID assigned at canonicalization time |
| `raw_record_id` | `str` | ✅ | Primary identifier from the originating dataset |
| `source_dataset` | `DataSource` | ✅ | Originating dataset enum value |
| `amount` | `Decimal` | ✅ | Transaction amount (≥ 0) in the stated currency |
| `currency` | `str` (ISO-4217, 3 chars) | Default: `"USD"` | Currency code, always uppercased |
| `timestamp` | `datetime` (optional) | ❌ | Transaction initiation timestamp (offset-aware) |
| `channel` | `TransactionChannel` | Default: `UNKNOWN` | Payment channel used |
| `status` | `TransactionStatus` | Default: `UNKNOWN` | Settlement / outcome status |
| `sender` | `AccountInfo` | Default: empty | Originating account (sender / payor) |
| `receiver` | `AccountInfo` | Default: empty | Destination account (receiver / payee) |
| `device` | `DeviceInfo` | Default: empty | Device and session metadata |
| `location` | `GeoLocation` | Default: empty | Geographic location metadata |
| `is_fraud` | `bool` (optional) | ❌ | Ground-truth fraud label (labelled datasets only) |
| `metadata` | `TransactionMetadata` | Default: empty | Dataset-specific supplementary features |

### 3.2 TransactionChannel (enum)

```
UPI, NEFT, RTGS, IMPS, CARD, WIRE, ACH, MOBILE, ONLINE,
CASH, PAYMENT, TRANSFER, CASH_OUT, CASH_IN, DEBIT, UNKNOWN
```

### 3.3 TransactionStatus (enum)

```
SUCCESS, FAILED, PENDING, REVERSED, UNKNOWN
```

### 3.4 DataSource (enum)

```
IEEE_CIS, PAYSIM, INDIA_SYNTHETIC, LIVE_BANKING, MOCK_BANKING, UNKNOWN
```

### 3.5 AccountInfo (sub-model)

| Field | Type | Description |
|---|---|---|
| `account_id` | `str` (optional) | Account identifier |
| `customer_id` | `str` (optional) | Customer identifier |
| `vpa` | `str` (optional) | UPI Virtual Payment Address |
| `ifsc_code` | `str` (optional) | Indian bank branch IFSC code |
| `email_domain` | `str` (optional) | E-mail domain (IEEE-CIS) |
| `balance_before` | `Decimal` (optional) | Account balance before transaction |
| `balance_after` | `Decimal` (optional) | Account balance after transaction |
| `account_name` | `str` (optional) | Account name string (PaySim) |

### 3.6 DeviceInfo (sub-model)

| Field | Type | Description |
|---|---|---|
| `device_id` | `str` (optional) | Device identifier |
| `device_type` | `str` (optional) | e.g. "mobile", "desktop" |
| `device_info` | `str` (optional) | Raw device-info string (IEEE-CIS) |
| `ip_address` | `str` (optional) | IP address at transaction time |
| `is_new_device` | `bool` (optional) | Whether device was newly registered |

### 3.7 GeoLocation (sub-model)

| Field | Type | Description |
|---|---|---|
| `city` | `str` (optional) | City name |
| `state` | `str` (optional) | State/province |
| `country` | `str` (optional) | Country code |
| `latitude` | `float` (optional) | Latitude in [-90, 90] |
| `longitude` | `float` (optional) | Longitude in [-180, 180] |
| `zip_code` | `str` (optional) | Postal/ZIP code |

### 3.8 TransactionMetadata (sub-model)

Holds dataset-specific supplementary features that do not fit the canonical core but must be preserved for downstream ML agents.

| Field | Type | Source |
|---|---|---|
| `anomaly_score` | `float` (optional) | Any |
| `amount_ratio_vs_30d_avg` | `float` (optional) | India Synthetic |
| `tx_frequency_24h` | `int` (optional) | India Synthetic |
| `time_since_last_tx_sec` | `int` (optional) | India Synthetic |
| `distance_from_home_km` | `float` (optional) | India Synthetic |
| `is_new_beneficiary` | `bool` (optional) | India Synthetic |
| `time_since_beneficiary_added_min` | `int` (optional) | India Synthetic |
| `product_code` | `str` (optional) | IEEE-CIS (ProductCD) |
| `card_type` | `str` (optional) | IEEE-CIS (card6) |
| `card_network` | `str` (optional) | IEEE-CIS (card4) |
| `paysim_step` | `int` (optional) | PaySim (simulation hour) |
| `is_flagged_fraud` | `bool` (optional) | PaySim / India Synthetic |
| `scenario_id` | `str` (optional) | India Synthetic |
| `risk_label` | `str` (optional) | India Synthetic |
| `alert_id` | `str` (optional) | India Synthetic |
| `transaction_type` | `str` (optional) | India Synthetic (P2P, C2B) |
| `extra` | `dict` (optional) | Carry-all for adapter-specific extras |

---

## 4. Pydantic Validation Rules

The following rules are enforced at model instantiation time:

| Rule | Field | Validator |
|---|---|---|
| Amount must be ≥ 0 | `amount` | `@model_validator` |
| Amount must be numeric | `amount` | `@field_validator` (before) |
| `raw_record_id` must not be empty or whitespace-only | `raw_record_id` | `@model_validator` |
| Currency must be exactly 3 characters (ISO-4217) | `currency` | Pydantic `min_length=3, max_length=3` |
| Currency is always uppercased | `currency` | `@field_validator` |
| Latitude must be in [-90, 90] | `location.latitude` | `@field_validator` |
| Longitude must be in [-180, 180] | `location.longitude` | `@field_validator` |

---

## 5. Dataset Adapter Mapping

### 5.1 IEEE-CIS Adapter (`IEEECISAdapter`)

**Source file:** `src/schemas/adapters/ieee_cis_adapter.py`

| Canonical Field | IEEE-CIS Source | Notes |
|---|---|---|
| `raw_record_id` | `TransactionID` | Cast to string |
| `amount` | `TransactionAmt` | USD |
| `currency` | — | Hardcoded `"USD"` |
| `timestamp` | — | `None` — `TransactionDT` is a relative offset; stored in `metadata.extra` |
| `channel` | `ProductCD` | All IEEE-CIS → `CARD` |
| `status` | — | `UNKNOWN` (no settlement status in dataset) |
| `sender.account_id` | `card1` | Hashed proxy identifier |
| `sender.email_domain` | `P_emaildomain` | |
| `receiver.email_domain` | `R_emaildomain` | |
| `device.device_type` | `DeviceType` | From merged identity file |
| `device.device_info` | `DeviceInfo` | From merged identity file |
| `location.zip_code` | `addr1` | Billing ZIP (hashed) |
| `location.country` | `addr2` | Country code |
| `is_fraud` | `isFraud` | 0/1 → bool |
| `metadata.product_code` | `ProductCD` | |
| `metadata.card_type` | `card6` | e.g. "credit", "debit" |
| `metadata.card_network` | `card4` | e.g. "VISA", "MASTERCARD" |
| `metadata.is_flagged_fraud` | `isFlaggedFraud` | |
| `metadata.extra.TransactionDT` | `TransactionDT` | Preserved for ML use |

### 5.2 PaySim Adapter (`PaySimAdapter`)

**Source file:** `src/schemas/adapters/paysim_adapter.py`

| Canonical Field | PaySim Source | Notes |
|---|---|---|
| `raw_record_id` | Synthesised | `PAYSIM_S{step}_{nameOrig}_{index}` |
| `amount` | `amount` | USD (synthetic) |
| `currency` | — | Hardcoded `"USD"` |
| `timestamp` | — | `None` — `step` is simulation hour; stored in `metadata.paysim_step` |
| `channel` | `type` | PAYMENT/TRANSFER/CASH_OUT/CASH_IN/DEBIT |
| `status` | — | `UNKNOWN` (no settlement status) |
| `sender.account_id` | `nameOrig` | |
| `sender.balance_before` | `oldbalanceOrg` | |
| `sender.balance_after` | `newbalanceOrig` | |
| `receiver.account_id` | `nameDest` | |
| `receiver.balance_before` | `oldbalanceDest` | |
| `receiver.balance_after` | `newbalanceDest` | |
| `device` | — | All `None` (no device data) |
| `location` | — | All `None` (no location data) |
| `is_fraud` | `isFraud` | 0/1 → bool |
| `metadata.paysim_step` | `step` | Simulation time-step (hours) |
| `metadata.is_flagged_fraud` | `isFlaggedFraud` | System flag for > 200,000 transfers |

### 5.3 India Synthetic Adapter (`IndiaSyntheticAdapter`)

**Source file:** `src/schemas/adapters/india_adapter.py`

| Canonical Field | India Source | Notes |
|---|---|---|
| `raw_record_id` | `transaction_id` | |
| `amount` | `amount_inr` | INR |
| `currency` | — | Hardcoded `"INR"` |
| `timestamp` | `timestamp` | ISO-8601 with +05:30 offset |
| `channel` | `channel` | UPI/NEFT/RTGS → enum |
| `status` | `status` | SUCCESS/FAILED/etc → enum |
| `sender.account_id` | `sender_account_id` | |
| `sender.customer_id` | `sender_customer_id` | |
| `sender.vpa` | `sender_vpa` | |
| `sender.ifsc_code` | `sender_ifsc` | |
| `sender.balance_before` | `account_balance_before` | |
| `sender.balance_after` | `account_balance_after` | |
| `receiver.account_id` | `receiver_account_id` | |
| `receiver.customer_id` | `receiver_customer_id` | |
| `receiver.vpa` | `receiver_vpa` | |
| `receiver.ifsc_code` | `receiver_ifsc` | |
| `device.device_id` | `device_id` | |
| `device.ip_address` | `ip_address` | |
| `device.is_new_device` | `is_new_device` | 0/1 → bool |
| `location.city` | `tx_city` | |
| `location.state` | `tx_state` | |
| `location.country` | — | Hardcoded `"IN"` |
| `location.latitude` | `tx_lat` | |
| `location.longitude` | `tx_long` | |
| `is_fraud` | `is_fraud` | From targets CSV (optional) |
| `metadata.scenario_id` | `scenario_id` | |
| `metadata.risk_label` | `risk_label` | |
| `metadata.alert_id` | `alert_id` | |
| `metadata.is_flagged_fraud` | `is_flagged_alert` | |
| `metadata.transaction_type` | `transaction_type` | P2P, C2B |
| `metadata.amount_ratio_vs_30d_avg` | `amount_ratio_vs_30d_avg` | |
| `metadata.tx_frequency_24h` | `tx_frequency_24h` | |
| `metadata.time_since_last_tx_sec` | `time_since_last_tx_sec` | |
| `metadata.distance_from_home_km` | `distance_from_home_km` | |
| `metadata.is_new_beneficiary` | `is_new_beneficiary` | |
| `metadata.time_since_beneficiary_added_min` | `time_since_beneficiary_added_min` | |

---

## 6. Implementation Locations

| Artefact | Path |
|---|---|
| Canonical model | `src/schemas/canonical_transaction.py` |
| Adapters package | `src/schemas/adapters/` |
| IEEE-CIS adapter | `src/schemas/adapters/ieee_cis_adapter.py` |
| PaySim adapter | `src/schemas/adapters/paysim_adapter.py` |
| India Synthetic adapter | `src/schemas/adapters/india_adapter.py` |
| Tests | `tests/test_canonical_schema.py` |

---

## 7. Testing

Run from the project root:

```bash
python3 tests/test_canonical_schema.py
```

Or with pytest:

```bash
python3 -m pytest tests/test_canonical_schema.py -v
```

Test coverage includes:

- `TestCanonicalTransactionModel` — Pydantic model construction and validation rules (15 tests)
- `TestIEEECISAdapter` — IEEE-CIS row → CanonicalTransaction mapping (16 tests)
- `TestPaySimAdapter` — PaySim row → CanonicalTransaction mapping (15 tests)
- `TestIndiaSyntheticAdapter` — India Synthetic row → CanonicalTransaction mapping (19 tests)
- `TestCrossDatasetCompatibility` — All three sources produce schema-compatible output (17 tests)

**Total: 82 tests, all passing.**

---

## 8. Usage by Agents

Agents receive a `CanonicalTransaction` and must:

- Use `canonical_id` as the stable internal case reference.
- Use `source_dataset` + `raw_record_id` when referencing the originating record.
- Use `metadata` for dataset-specific ML features (never raw column names).
- Treat `is_fraud` as a ground-truth label only where it is non-`None`.

Agents must not:

- Re-read raw CSV files using dataset-specific column names.
- Depend on optional fields being present without `None` checks.
- Modify the `CanonicalTransaction` instance (it is frozen/immutable).

---

## 9. Future Datasets

To add a new dataset:

1. Create a new adapter module under `src/schemas/adapters/`.
2. Map raw columns to `CanonicalTransaction` fields following the pattern above.
3. Add a new value to the `DataSource` enum.
4. Add channel values to `TransactionChannel` if needed.
5. Add tests to `tests/test_canonical_schema.py`.
6. Document the mapping in this file (section 5).
7. Update `DATASET_REGISTRY.md` with the new dataset entry.
