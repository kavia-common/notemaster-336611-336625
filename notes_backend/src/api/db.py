import os
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class DbConfig:
    """Database configuration derived from environment variables.

    Expected env vars (provided by the database container):
    - POSTGRES_URL
    - POSTGRES_USER
    - POSTGRES_PASSWORD
    - POSTGRES_DB
    - POSTGRES_PORT

    Notes:
    - We intentionally accept either a full URL (preferred) or discrete parts.
    - This module is the only place that reads environment variables (keeps config from leaking).
    """

    url: str


def _build_postgres_url_from_parts() -> str:
    """Build a postgres URL from discrete env vars (fallback when POSTGRES_URL is missing)."""
    user = os.getenv("POSTGRES_USER", "")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "")
    port = os.getenv("POSTGRES_PORT", "")

    # Host is not explicitly provided by the platform contract; in container networks it's often "localhost".
    # If this turns out incorrect, prefer using POSTGRES_URL which is authoritative.
    host = os.getenv("POSTGRES_HOST", "localhost")

    auth = user
    if password:
        auth = f"{user}:{password}"
    return f"postgresql://{auth}@{host}:{port}/{db}"


# PUBLIC_INTERFACE
def get_db_config() -> DbConfig:
    """Return normalized DB configuration.

    Contract:
    - Inputs: environment variables.
    - Output: DbConfig(url=...)
    - Errors: ValueError if configuration is missing/invalid.
    - Side effects: none.
    """
    url = os.getenv("POSTGRES_URL", "").strip()
    if not url:
        # Fallback path; still requires the discrete vars to be present.
        url = _build_postgres_url_from_parts()

    # Minimal validation: must look like a PostgreSQL URL.
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        raise ValueError(
            "Invalid Postgres configuration. Provide POSTGRES_URL starting with "
            "'postgresql://' (or 'postgres://')."
        )

    return DbConfig(url=url)


# PUBLIC_INTERFACE
def get_db_connection(*, config: DbConfig | None = None) -> psycopg.Connection:
    """Create a new psycopg connection.

    Contract:
    - Inputs: optional DbConfig; if omitted, uses get_db_config().
    - Output: psycopg.Connection configured with dict_row for convenient row access.
    - Errors: raises psycopg errors on connection failures; ValueError for invalid config.
    - Side effects: opens a DB connection (caller must close).
    """
    cfg = config or get_db_config()
    return psycopg.connect(cfg.url, row_factory=dict_row)
