"""
Sentinel AI — India Synthetic Graph Loader

Loads India Synthetic transactions into Neo4j for Agent 3.

Scope
-----
* Loads ALL rows by default (Phase 9.5); ``--limit N`` loads the first N.
* Reads ONLY transactions_features.csv. Ground-truth labels
  (transactions_targets.csv) are never loaded (label firewall).
* ``--reset-india`` first deletes existing INDIA_SYNTHETIC relationships and
  orphaned accounts (use after regenerating the dataset).
* Reports loading statistics without exposing credentials.
* Run from the project root:

    PYTHONPATH=. python scripts/load_india_sample_graph.py [--limit N] [--reset-india]

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

FEATURES_PATH = Path("dataset/processed/custom_india/transactions_features.csv")


def load_sample(limit: int | None = None, reset_india: bool = False) -> None:
    """Load India Synthetic transactions (features only) into Neo4j."""
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
    features_df = pd.read_csv(FEATURES_PATH, nrows=limit)
    logger.info("Loaded %d feature rows (limit=%s).", len(features_df), limit)
    merged_df = features_df  # features only — labels never enter the graph

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

            if reset_india:
                with mgr.session() as s:
                    s.run("MATCH ()-[r:TRANSFERRED_TO {source_dataset: 'INDIA_SYNTHETIC'}]->() DELETE r")
                    s.run("MATCH (a:Account {source_dataset: 'INDIA_SYNTHETIC'}) "
                          "WHERE NOT (a)--() DELETE a")
                logger.info("Removed existing INDIA_SYNTHETIC graph data.")

            # Initialise schema (idempotent)
            schema_mgr = GraphSchemaManager(mgr.session)
            schema_mgr.init_schema()
            logger.info("Graph schema initialised.")

            # Load transactions
            loader = TransactionGraphLoader(mgr.session, batch_size=500)
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
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--limit", type=int, default=None, help="Load only the first N transactions.")
    ap.add_argument("--reset-india", action="store_true",
                    help="Delete existing INDIA_SYNTHETIC graph data before loading.")
    a = ap.parse_args()
    load_sample(limit=a.limit, reset_india=a.reset_india)
