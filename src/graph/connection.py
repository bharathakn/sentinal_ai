"""
Sentinel AI — Neo4j Connection Management

Manages the Neo4j driver lifecycle for the Sentinel AI graph infrastructure.

Design rules
------------
* Configuration is read from environment variables; never hardcoded.
* The driver is initialised once and reused (not recreated per query).
* Sessions are always opened with the configured database name.
* All configuration errors, auth errors, and connectivity failures produce
  clear, sanitised exceptions — credentials are never included in messages.
* Import of this module succeeds even when Neo4j env-vars are absent,
  enabling offline unit tests without a live database.
* Supports both synchronous and async (asyncio) usage patterns via two
  separate manager classes sharing the same configuration logic.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level driver imports (patchable for unit tests).
# The try/except keeps this module importable in environments where the neo4j
# package is absent (offline CI without the driver installed).
# When neo4j IS installed (as required), these are real classes.
# ---------------------------------------------------------------------------
try:
    from neo4j import GraphDatabase, AsyncGraphDatabase  # type: ignore[import]
    from neo4j.exceptions import AuthError as _DriverAuthError  # type: ignore[import]
    from neo4j.exceptions import ServiceUnavailable as _DriverServiceUnavailable  # type: ignore[import]
    _NEO4J_AVAILABLE = True
except ImportError:
    GraphDatabase = None  # type: ignore[assignment,misc]
    AsyncGraphDatabase = None  # type: ignore[assignment,misc]
    _DriverAuthError = None  # type: ignore[assignment,misc]
    _DriverServiceUnavailable = None  # type: ignore[assignment,misc]
    _NEO4J_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_REQUIRED_ENV_VARS = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")


class Neo4jConfigError(Exception):
    """Raised when required Neo4j configuration is absent or invalid."""


class Neo4jConnectivityError(Exception):
    """Raised when the driver cannot reach the Neo4j instance."""


class Neo4jAuthError(Exception):
    """Raised when authentication is rejected by the Neo4j instance."""


def _read_config() -> dict[str, str]:
    """
    Read Neo4j connection settings from environment variables.

    Returns a dict with keys: uri, username, password, database.

    Raises
    ------
    Neo4jConfigError
        If any required variable is absent or empty.
    """
    uri = os.environ.get("NEO4J_URI", "").strip()
    username = os.environ.get("NEO4J_USERNAME", "").strip()
    password = os.environ.get("NEO4J_PASSWORD", "").strip()
    database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"

    missing = [
        var for var, val in [
            ("NEO4J_URI", uri),
            ("NEO4J_USERNAME", username),
            ("NEO4J_PASSWORD", password),
        ]
        if not val
    ]
    if missing:
        raise Neo4jConfigError(
            f"Missing required Neo4j environment variable(s): {', '.join(missing)}. "
            "Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD before connecting."
        )

    return {"uri": uri, "username": username, "password": password, "database": database}


# ---------------------------------------------------------------------------
# Synchronous connection manager
# ---------------------------------------------------------------------------

class Neo4jConnectionManager:
    """
    Manages a single Neo4j synchronous driver instance.

    Usage (context manager — recommended)
    --------------------------------------
    ::

        with Neo4jConnectionManager() as mgr:
            with mgr.session() as session:
                session.run("RETURN 1")

    Usage (manual lifecycle)
    ------------------------
    ::

        mgr = Neo4jConnectionManager()
        mgr.connect()
        mgr.verify_connectivity()
        # ... use mgr.session() ...
        mgr.close()

    Configuration
    -------------
    Read from environment variables:
      - NEO4J_URI
      - NEO4J_USERNAME
      - NEO4J_PASSWORD
      - NEO4J_DATABASE   (default: "neo4j")
    """

    def __init__(self) -> None:
        self._driver = None
        self._database: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Initialise the driver from environment configuration.

        Raises
        ------
        Neo4jConfigError
            If required environment variables are missing.
        Neo4jConnectivityError
            If the driver cannot be created due to an unreachable instance.
        Neo4jAuthError
            If credentials are rejected.
        """
        if self._driver is not None:
            return  # already connected — reuse existing driver

        if not _NEO4J_AVAILABLE or GraphDatabase is None:
            raise Neo4jConfigError(
                "neo4j Python driver is not installed. "
                "Add 'neo4j>=5.0.0' to requirements.txt and install."
            )

        config = _read_config()
        self._database = config["database"]

        try:
            self._driver = GraphDatabase.driver(
                config["uri"],
                auth=(config["username"], config["password"]),
            )
            logger.info(
                "Neo4j driver initialised (uri=%s, database=%s).",
                _sanitise_uri(config["uri"]),
                self._database,
            )
        except Exception as exc:
            _raise_driver_init_error(exc)

    def verify_connectivity(self) -> None:
        """
        Verify that the driver can reach the configured Neo4j instance.

        Raises
        ------
        Neo4jConnectivityError
            If the driver has not been initialised or connectivity check fails.
        Neo4jAuthError
            If authentication is rejected during verification.
        """
        if self._driver is None:
            raise Neo4jConnectivityError(
                "Driver is not initialised. Call connect() first."
            )
        try:
            self._driver.verify_connectivity()
            logger.info("Neo4j connectivity verified.")
        except Exception as exc:
            _raise_connectivity_error(exc)

    def close(self) -> None:
        """Close the driver and release all connections."""
        if self._driver is not None:
            try:
                self._driver.close()
                logger.info("Neo4j driver closed.")
            except Exception:  # noqa: BLE001
                logger.warning("Exception while closing Neo4j driver.", exc_info=True)
            finally:
                self._driver = None

    # ------------------------------------------------------------------
    # Session factory
    # ------------------------------------------------------------------

    def session(self):
        """
        Open a new session on the configured database.

        Returns
        -------
        neo4j.Session
            Caller is responsible for closing the session (use as context manager).

        Raises
        ------
        Neo4jConnectivityError
            If the driver has not been initialised.
        """
        if self._driver is None:
            raise Neo4jConnectivityError(
                "Driver is not initialised. Call connect() first."
            )
        return self._driver.session(database=self._database)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict:
        """
        Return a connectivity status dict without exposing credentials.

        Returns
        -------
        dict
            {
              "status": "ok" | "error",
              "database": "<name>",
              "detail": "<safe description>",
            }
        """
        if self._driver is None:
            return {
                "status": "error",
                "database": self._database or "unknown",
                "detail": "Driver not initialised.",
            }
        try:
            self._driver.verify_connectivity()
            return {
                "status": "ok",
                "database": self._database,
                "detail": "Connectivity verified.",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "database": self._database or "unknown",
                "detail": f"{type(exc).__name__}: connectivity check failed.",
            }

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "Neo4jConnectionManager":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Async connection manager
# ---------------------------------------------------------------------------

class AsyncNeo4jConnectionManager:
    """
    Manages a single Neo4j *async* driver instance for use in asyncio contexts.

    Usage (context manager — recommended)
    --------------------------------------
    ::

        async with AsyncNeo4jConnectionManager() as mgr:
            async with mgr.session() as session:
                await session.run("RETURN 1")

    Configuration
    -------------
    Same environment variables as Neo4jConnectionManager.
    """

    def __init__(self) -> None:
        self._driver = None
        self._database: Optional[str] = None

    async def connect(self) -> None:
        """Initialise the async driver from environment configuration."""
        if self._driver is not None:
            return

        if not _NEO4J_AVAILABLE or AsyncGraphDatabase is None:
            raise Neo4jConfigError(
                "neo4j Python driver is not installed."
            )

        config = _read_config()
        self._database = config["database"]

        try:
            self._driver = AsyncGraphDatabase.driver(
                config["uri"],
                auth=(config["username"], config["password"]),
            )
            logger.info(
                "Neo4j async driver initialised (uri=%s, database=%s).",
                _sanitise_uri(config["uri"]),
                self._database,
            )
        except Exception as exc:
            _raise_driver_init_error(exc)

    async def verify_connectivity(self) -> None:
        """Verify async connectivity."""
        if self._driver is None:
            raise Neo4jConnectivityError("Async driver is not initialised.")
        try:
            await self._driver.verify_connectivity()
            logger.info("Neo4j async connectivity verified.")
        except Exception as exc:
            _raise_connectivity_error(exc)

    async def close(self) -> None:
        """Close the async driver."""
        if self._driver is not None:
            try:
                await self._driver.close()
                logger.info("Neo4j async driver closed.")
            except Exception:  # noqa: BLE001
                logger.warning("Exception closing async Neo4j driver.", exc_info=True)
            finally:
                self._driver = None

    def session(self):
        """Return an async session context manager."""
        if self._driver is None:
            raise Neo4jConnectivityError("Async driver is not initialised.")
        return self._driver.session(database=self._database)

    async def __aenter__(self) -> "AsyncNeo4jConnectionManager":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sanitise_uri(uri: str) -> str:
    """Return the URI scheme+host only, removing any embedded credentials."""
    try:
        # Remove any user:password@ in the URI
        if "@" in uri:
            scheme_end = uri.index("://") + 3
            at_pos = uri.index("@", scheme_end)
            return uri[:scheme_end] + uri[at_pos + 1:]
    except (ValueError, IndexError):
        pass
    return uri


def _raise_driver_init_error(exc: Exception) -> None:
    """Convert a Neo4j driver init exception into a sanitised Sentinel error."""
    if _DriverAuthError is not None and isinstance(exc, _DriverAuthError):
        raise Neo4jAuthError(
            "Neo4j authentication failed. "
            "Verify NEO4J_USERNAME and NEO4J_PASSWORD."
        ) from exc
    if _DriverServiceUnavailable is not None and isinstance(exc, _DriverServiceUnavailable):
        raise Neo4jConnectivityError(
            "Neo4j instance is unreachable. "
            "Verify NEO4J_URI and network connectivity."
        ) from exc
    raise Neo4jConnectivityError(
        f"Failed to create Neo4j driver: {type(exc).__name__}. "
        "Check NEO4J_URI and driver compatibility."
    ) from exc


def _raise_connectivity_error(exc: Exception) -> None:
    """Convert a Neo4j driver exception into a sanitised Sentinel error."""
    if _DriverAuthError is not None and isinstance(exc, _DriverAuthError):
        raise Neo4jAuthError(
            "Neo4j authentication failed during connectivity check."
        ) from exc
    if _DriverServiceUnavailable is not None and isinstance(exc, _DriverServiceUnavailable):
        raise Neo4jConnectivityError(
            "Neo4j instance is unreachable during connectivity check."
        ) from exc
    raise Neo4jConnectivityError(
        f"Neo4j connectivity check failed: {type(exc).__name__}."
    ) from exc
