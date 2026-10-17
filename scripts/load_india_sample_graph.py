"""
Sentinel AI — India Synthetic Sample Graph Loader (Phase 7)

Loads a bounded sample of India Synthetic transactions into Neo4j for
initial graph verification and Agent 3 development.

Scope
-----
* Loads at most MAX_SAMPLE_ROWS rows from the India Synthetic dataset.
* Requires both transactions_features.csv and transactions_targets.csv
  to be present at the expected dataset paths (they are git-ignored).
* Reports loading statistics without exposing credentials.
* Designed to be run manually from the project root:

    python -m scripts.load_india_sample_graph

Environment variables required
-------------------------------
  NEO4J_URI
  NEO4J_USERNAME
  NEO4J_PASSWORD
  NEO4J_DATABASE   (default: neo4j)

Do NOT run this script against a production database containing real data.
This script uses the India Synthetic dataset (100% synthetic data).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("sentinel.graph.sample_loader")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_SAMPLE_ROWS = 500  # Hard upper bound for Phase 7 initial load
FEATURES_PATH = Path("dataset/processed/custom_india/transactions_features.csv")
TARGETS_PATH = Path("dataset/processed/custom_india/transactions_targets.csv")


def load_sample() -> None:
    """Load a bounded sample of India Synthetic transactions into Neo4j."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required. Install with: pip install pandas")
        sys.exit(1)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv is optional; env vars may be set externally

    # Import graph infrastructure (config errors reported cleanly)
    from src.graph.connection import Neo4jConnectionManager, Neo4jConfigError
    from src.graph.schema import GraphSchemaManager
    from src.graph.loader import TransactionGraphLoader
    from src.schemas.adapters.india_adapter import IndiaSyntheticAdapter

    # ------------------------------------------------------------------
    # Load dataset files
    # ------------------------------------------------------------------
    if not FEATURES_PATH.exists():
        logger.error(
            "Features file not found: %s\n"
            "Generate the India Synthetic dataset first.",
            FEATURES_PATH,
        )
        sys.exit(1)

    logger.info("Loading India Synthetic features from: %s", FEATURES_PATH)
    features_df = pd.read_csv(FEATURES_PATH, nrows=MAX_SAMPLE_ROWS)
    logger.info("Loaded %d feature rows (max %d).", len(features_df), MAX_SAMPLE_ROWS)

    if TARGETS_PATH.exists():
        logger.info("Loading targets from: %s", TARGETS_PATH)
        targets_df = pd.read_csv(TARGETS_PATH)
        merged_df = features_df.merge(targets_df, on="transaction_id", how="left")
        logger.info("Merged features + targets: %d rows.", len(merged_df))
    else:
        logger.warning(
            "Targets file not found at %s — loading features only.", TARGETS_PATH
        )
        merged_df = features_df

    # ------------------------------------------------------------------
    # Convert to CanonicalTransaction
    # ------------------------------------------------------------------
    logger.info("Converting rows to CanonicalTransaction records …")
    canonical_transactions = []
    skipped = 0

    for _, row in merged_df.iterrows():
        try:
            tx = IndiaSyntheticAdapter.from_row(row.to_dict())
            # Only include transactions with both sender and receiver account IDs
            if tx.sender.account_id and tx.receiver.account_id:
                canonical_transactions.append(tx)
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            logger.debug("Skipped row: %s", exc)

    logger.info(
        "Converted %d transactions (%d skipped — missing account IDs).",
        len(canonical_transactions),
        skipped,
    )

    if not canonical_transactions:
        logger.error("No valid transactions to load. Exiting.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Connect and load
    # ------------------------------------------------------------------
    try:
        with Neo4jConnectionManager() as mgr:
            mgr.verify_connectivity()
            logger.info("Neo4j connectivity verified.")

            # Initialise schema (idempotent)
            schema_mgr = GraphSchemaManager(mgr.session)
            schema_mgr.init_schema()
            logger.info("Graph schema initialised.")

            # Load transactions
            loader = TransactionGraphLoader(mgr.session, batch_size=50)
            result = loader.load_batch(canonical_transactions)

            logger.info(
                "Load complete: total=%d, succeeded=%d, failed=%d, "
                "nodes_created=%d, relationships_created=%d.",
                result.total,
                result.succeeded,
                result.failed,
                result.nodes_created,
                result.relationships_created,
            )

            if result.errors:
                logger.warning("%d loading errors:", len(result.errors))
                for err in result.errors[:10]:
                    logger.warning("  %s", err)
                if len(result.errors) > 10:
                    logger.warning("  … and %d more.", len(result.errors) - 10)

    except Neo4jConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error during graph loading: %s: %s", type(exc).__name__, exc)
        sys.exit(1)


if __name__ == "__main__":
    load_sample()
