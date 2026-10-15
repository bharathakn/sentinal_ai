"""
Sentinel AI — CanonicalTransaction to ML model feature mapper.

Responsibility
--------------
Convert a CanonicalTransaction (the internal agent schema) into the feature
dictionaries expected by the XGBoost FraudPredictor and the Isolation Forest
AnomalyPredictor.

Design constraints
------------------
* Both ML models were trained on IEEE-CIS features (432 columns after preprocessing).
  Most of these columns have no equivalent in the CanonicalTransaction schema.
* This mapper only populates the fields that CAN be reliably derived from the
  canonical schema. All other fields are left as NaN and handled by the fitted
  imputer in the preprocessing pipeline.
* The mapper is NOT a shortcut to bypass the preprocessing pipeline.
  Its output must still be passed through the predictor.predict_transaction() or
  predictor.score_transaction() interface, which applies the full pipeline.
* Missing features do NOT cause errors — the pipeline's MedianImputer fills
  numeric NaNs and OrdinalEncoder handles unseen categoricals (with 'use_encoded_value').
* This mapper is a BEST-EFFORT translation. The model's performance on
  CanonicalTransaction inputs is expected to be lower than on full IEEE-CIS rows
  because most features will be imputed.
* Provenance and model version are preserved in the output.

Supported field mappings (IEEE-CIS column ← CanonicalTransaction field)
------------------------------------------------------------------------
    TransactionAmt    ← float(amount)
    card4             ← sender.bank_name (card network approximation, optional)
    addr1             ← location.region_code (optional)
    P_emaildomain     ← sender.email_domain (optional)
    R_emaildomain     ← receiver.email_domain (optional)

All other IEEE-CIS features are left as NaN.

Usage
-----
    from src.ml.feature_mapper import canonical_to_xgb_features
    from src.ml.predictor import FraudPredictor

    predictor = FraudPredictor()
    features = canonical_to_xgb_features(canonical_tx)
    result = predictor.predict_transaction(features)

Integration with Agent 1
------------------------
See src/ml/agent1_scorer.py for the full Agent 1 integration entry point
that combines XGBoost and Isolation Forest signals.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas.canonical_transaction import CanonicalTransaction

logger = logging.getLogger(__name__)

# Columns that can be derived from CanonicalTransaction fields.
# These are a tiny subset of the 432 IEEE-CIS features.
_MAPPED_COLUMNS: list[str] = [
    "TransactionAmt",  # float — always available
    "card4",           # card network / bank name — optional
    "addr1",           # billing region — optional
    "P_emaildomain",   # payer email domain — optional
    "R_emaildomain",   # receiver email domain — optional
]


def canonical_to_xgb_features(transaction: Any) -> dict[str, Any]:
    """Map a CanonicalTransaction to an IEEE-CIS-compatible feature dict.

    Parameters
    ----------
    transaction : CanonicalTransaction instance or any object with the fields:
        .amount (Decimal | float)
        .sender.bank_name (str | None)
        .location.region_code (str | None)
        .sender.email_domain (str | None)         — optional attribute
        .receiver.email_domain (str | None)       — optional attribute

    Returns
    -------
    dict[str, Any]
        Sparse feature dict with only the mappable fields populated.
        All other IEEE-CIS columns are absent (will become NaN after reindex
        in the predictor).

    Notes
    -----
    The returned dict must be passed to FraudPredictor.predict_transaction()
    or AnomalyPredictor.score_transaction(). Do not pass it to
    pipeline.transform() directly.
    """
    features: dict[str, Any] = {}

    # --- TransactionAmt (mandatory; always available) ---
    try:
        features["TransactionAmt"] = float(transaction.amount)
    except (AttributeError, TypeError, ValueError) as exc:
        logger.warning("Could not convert amount to float: %s. Setting to NaN.", exc)
        features["TransactionAmt"] = float("nan")

    # --- card4 (bank/card network — approximation) ---
    try:
        card_net = None
        if hasattr(transaction, "metadata") and transaction.metadata is not None:
            card_net = getattr(transaction.metadata, "card_network", None)
        if not card_net and hasattr(transaction, "sender") and transaction.sender is not None:
            card_net = getattr(transaction.sender, "bank_name", None)
        if card_net:
            features["card4"] = str(card_net).lower()[:20]
    except (AttributeError, TypeError):
        pass

    # --- addr1 (billing region / zip code) ---
    try:
        region = None
        if hasattr(transaction, "location") and transaction.location is not None:
            region = (
                getattr(transaction.location, "zip_code", None)
                or getattr(transaction.location, "region_code", None)
                or getattr(transaction.location, "state", None)
            )
        if region is not None:
            try:
                features["addr1"] = float(region)
            except (ValueError, TypeError):
                features["addr1"] = region
    except (AttributeError, TypeError):
        pass

    # --- P_emaildomain (payer email domain) ---
    try:
        p_email = getattr(transaction.sender, "email_domain", None)
        if p_email:
            features["P_emaildomain"] = str(p_email).lower()
    except AttributeError:
        pass

    # --- R_emaildomain (receiver email domain) ---
    try:
        r_email = getattr(transaction.receiver, "email_domain", None)
        if r_email:
            features["R_emaildomain"] = str(r_email).lower()
    except AttributeError:
        pass

    unmapped = 432 - len(features)
    logger.debug(
        "canonical_to_xgb_features: %d fields mapped, %d fields will be NaN-imputed.",
        len(features), unmapped,
    )
    return features


def canonical_to_if_features(transaction: Any) -> dict[str, Any]:
    """Map a CanonicalTransaction to feature dict for Isolation Forest.

    The IF model uses the same preprocessing pipeline as XGBoost.
    This function is an alias for canonical_to_xgb_features — both models
    share the same feature space.

    See canonical_to_xgb_features for full documentation.
    """
    return canonical_to_xgb_features(transaction)


def describe_mapping() -> dict[str, Any]:
    """Return a human-readable description of the active field mapping."""
    return {
        "mapped_columns": _MAPPED_COLUMNS,
        "total_ieee_cis_features": 432,
        "n_mapped": len(_MAPPED_COLUMNS),
        "n_nan_imputed": 432 - len(_MAPPED_COLUMNS),
        "mapping_note": (
            "Most IEEE-CIS features have no equivalent in CanonicalTransaction. "
            "Unmapped features are NaN-imputed by the preprocessing pipeline. "
            "Model performance on CanonicalTransaction inputs is expected to be "
            "lower than on full IEEE-CIS rows. This mapper is best-effort only."
        ),
        "field_map": {
            "TransactionAmt": "float(transaction.amount)  [always available]",
            "card4": "transaction.sender.bank_name  [optional]",
            "addr1": "transaction.location.region_code  [optional]",
            "P_emaildomain": "transaction.sender.email_domain  [optional]",
            "R_emaildomain": "transaction.receiver.email_domain  [optional]",
        },
    }
