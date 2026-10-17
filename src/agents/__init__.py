"""
Sentinel AI — Agents package.

This package contains LangGraph-ready agent implementations for the
Sentinel AI investigation pipeline.

Agents
------
agent1 : Anomaly Detector — XGBoost fraud scoring + Isolation Forest anomaly
         detection + SHAP explainability. First stage of the investigation
         pipeline.
agent2 : Evidence Gatherer — asyncio concurrent evidence collection across
         8 provider categories. Second stage.
agent3 : Network Analyser — Neo4j graph pattern detection across 7 network
         pattern types. Third stage.
"""
