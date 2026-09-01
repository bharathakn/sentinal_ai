# FILE: docs/15_FEATURES/CASE_INGESTION.md

# Feature — Case Ingestion

## Purpose

Receive a suspicious transaction alert and create an investigation case.

## Input

The alert must contain the transaction information required by the project.

The project plan identifies:

- transaction ID
- sender account
- receiver account
- amount
- timestamp
- device ID

## Processing

1. Receive alert.
2. Validate input.
3. Generate case ID.
4. Record creation timestamp.
5. Initialize investigation state.
6. Start the investigation pipeline.

## Output

The system returns case identification/status information.

## Dependencies

- FastAPI
- Pydantic
- LangGraph

## Testing

Verify:

- valid alert
- invalid alert
- case creation
- unique case ID
- pipeline initiation