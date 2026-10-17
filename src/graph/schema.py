"""
Sentinel AI — Neo4j Graph Schema Management

Sets up the graph schema required for network analysis:
- Account uniqueness constraint on account_id
- Index on Account.source_dataset for dataset-scoped queries
- Idempotent schema initialisation (safe to call repeatedly)

Design notes
------------
* All operations are idempotent — running init_schema() multiple times
  must not raise errors or produce duplicate constraints.
* Uses IF NOT EXISTS syntax supported by Neo4j 4.1.3+ and 5.x.
* Keeps only justified constraints and indexes.
* No fraud-detection logic belongs here — this is infrastructure only.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cypher statements
# ---------------------------------------------------------------------------

# Uniqueness constraint ensures each account_id maps to exactly one node.
# Also implicitly creates a backing index on Account.account_id.
_CONSTRAINT_ACCOUNT_ID = """
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account)
REQUIRE a.account_id IS UNIQUE
"""

# Explicit composite index to support queries that filter by source_dataset
# while traversing accounts — justified by expected Agent 3 query patterns.
_INDEX_ACCOUNT_SOURCE = """
CREATE INDEX account_source_dataset IF NOT EXISTS
FOR (a:Account)
ON (a.source_dataset)
"""

# List all constraints for reporting
_LIST_CONSTRAINTS = "SHOW CONSTRAINTS"

# List all indexes for reporting
_LIST_INDEXES = "SHOW INDEXES"


# ---------------------------------------------------------------------------
# Schema manager
# ---------------------------------------------------------------------------

class GraphSchemaManager:
    """
    Initialises and verifies the Neo4j graph schema for Sentinel AI.

    Parameters
    ----------
    session_factory:
        A callable that returns a neo4j.Session (or compatible context manager).
        Typically ``Neo4jConnectionManager.session``.

    Example
    -------
    ::

        with Neo4jConnectionManager() as mgr:
            schema = GraphSchemaManager(mgr.session)
            schema.init_schema()
            info = schema.schema_info()
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def init_schema(self) -> None:
        """
        Apply all required constraints and indexes idempotently.

        Safe to call on every application startup; uses IF NOT EXISTS so
        existing constraints/indexes are left unchanged.

        Raises
        ------
        neo4j.exceptions.Neo4jError
            On query failure (e.g. Enterprise-only features on Community).
        """
        statements = [
            ("Account ID uniqueness constraint", _CONSTRAINT_ACCOUNT_ID),
            ("Account source_dataset index", _INDEX_ACCOUNT_SOURCE),
        ]

        with self._session_factory() as session:
            for name, cypher in statements:
                try:
                    session.run(cypher)
                    logger.info("Schema: applied — %s.", name)
                except Exception as exc:  # noqa: BLE001
                    # Log and re-raise so callers know something failed.
                    logger.error(
                        "Schema: failed to apply '%s': %s: %s",
                        name,
                        type(exc).__name__,
                        exc,
                    )
                    raise

        logger.info("Neo4j graph schema initialisation complete.")

    def schema_info(self) -> dict:
        """
        Return current constraint and index counts as a summary dict.

        Does not return constraint or index definitions verbatim to avoid
        leaking schema internals unnecessarily.

        Returns
        -------
        dict
            {
              "constraints": <int>,
              "indexes": <int>,
            }
        """
        with self._session_factory() as session:
            constraints = session.run(_LIST_CONSTRAINTS).data()
            indexes = session.run(_LIST_INDEXES).data()

        return {
            "constraints": len(constraints),
            "indexes": len(indexes),
        }

    def constraint_exists(self, constraint_name: str) -> bool:
        """
        Check whether a named constraint exists in the graph.

        Parameters
        ----------
        constraint_name:
            The name used in the CREATE CONSTRAINT statement.
        """
        with self._session_factory() as session:
            result = session.run(_LIST_CONSTRAINTS).data()

        names = [row.get("name", "") for row in result]
        return constraint_name in names
