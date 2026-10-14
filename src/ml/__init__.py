"""
Sentinel AI — ML pipeline package.

Submodules
----------
ieee_cis_loader   : Dataset loading and merging for IEEE-CIS.
preprocessor      : Feature engineering and sklearn preprocessing pipeline.
trainer           : XGBoost training and model-artifact persistence.
predictor         : XGBoost inference from saved artifacts.
evaluator         : XGBoost metrics calculation and reporting.
explainer         : SHAP-based feature attribution (XGBoost).
if_trainer        : Isolation Forest unsupervised anomaly detection training.
if_predictor      : Isolation Forest inference from saved artifacts.
if_evaluator      : Isolation Forest anomaly detection evaluation metrics.
"""
