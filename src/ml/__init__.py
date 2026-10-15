"""
Sentinel AI — ML pipeline package.

Submodules
----------
ieee_cis_loader       : Dataset loading and merging for IEEE-CIS.
preprocessor          : Feature engineering and sklearn preprocessing pipeline.
trainer               : XGBoost training and model-artifact persistence.
predictor             : XGBoost inference from saved artifacts.
evaluator             : XGBoost metrics: accuracy, precision, recall, F1, ROC-AUC,
                        PR-AUC, FPR, FNR, confusion matrix, metadata.
explainer             : SHAP-based feature attribution (XGBoost).
if_trainer            : Isolation Forest unsupervised anomaly detection training.
if_predictor          : Isolation Forest inference from saved artifacts.
if_evaluator          : Isolation Forest anomaly detection evaluation metrics.
threshold_calibration : Sweep and select classification thresholds on validation data.
feature_mapper        : CanonicalTransaction → IEEE-CIS feature mapping.
agent1_scorer         : Agent 1 ML scoring integration (XGBoost + IF).
"""
