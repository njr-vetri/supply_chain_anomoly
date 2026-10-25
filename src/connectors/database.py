"""SQLAlchemy read-only database import adapter."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, create_engine, select

from src.connectors.base import ConnectorHealth, RecordBatch


class DatabaseImportConnector:
    def __init__(self, *, url_env: str, table_name: str, chunksize: int = 1000,
                 engine_factory=create_engine):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", table_name):
            raise ValueError("table_name must be a simple SQL identifier")
        if chunksize <= 0:
            raise ValueError("chunksize must be positive")
        self.url_env, self.table_name, self.chunksize = url_env, table_name, chunksize
        self.engine_factory = engine_factory

    def _engine(self):
        url = os.getenv(self.url_env)
        if not url:
            raise RuntimeError("Database URL environment variable is not configured")
        return self.engine_factory(url, future=True, pool_pre_ping=True)

    def health_check(self) -> ConnectorHealth:
        try:
            engine = self._engine()
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
                exists = self.table_name in __import__("sqlalchemy").inspect(connection).get_table_names()
            status = "HEALTHY" if exists else "UNAVAILABLE"
            detail = "database connection and source table are available" if exists else "configured source table was not found"
        except Exception as exc:
            status, detail = "UNAVAILABLE", f"database check failed ({type(exc).__name__})"
        return ConnectorHealth("database_import", status, datetime.now(timezone.utc).isoformat(), detail)

    def read_batches(self):
        engine = self._engine()
        metadata = MetaData()
        table = Table(self.table_name, metadata, autoload_with=engine)
        with engine.connect() as connection:
            result = connection.execution_options(stream_results=True).execute(select(table))
            while True:
                rows = result.fetchmany(self.chunksize)
                if not rows:
                    break
                yield RecordBatch("database_import", f"{self.table_name}", None,
                    [{key: value for key, value in row._mapping.items()} for row in rows])
