# FILE: docs/12_TESTING/TESTING_STRATEGY.md

# Testing Strategy

## Goal

Verify that Sentinel AI produces correct, traceable and validated investigation results.

## Testing Layers

### Unit Tests

Test individual components and deterministic logic.

### Agent Tests

Test each agent independently using controlled inputs.

### Pipeline Tests

Test the complete LangGraph sequence.

### ML Evaluation

Evaluate the anomaly-detection models using defined metrics.

### Validation Tests

Verify that unsupported or inconsistent report content is rejected.

### Integration Tests

Test interactions between:

- FastAPI
- LangGraph
- databases
- evidence sources
- report generation
- dashboard API

### End-to-End Tests

Run complete investigation cases through the system.

## Required Demonstration Cases

The project plan identifies:

- two clear fraud cases
- two clear legitimate cases
- one borderline case

## Success

Each test case should produce a case result with the expected investigation behavior and validation outcome.