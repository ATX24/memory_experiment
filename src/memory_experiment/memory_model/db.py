from __future__ import annotations

import os
import re
import uuid
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from ..eval.types import Table

DEFAULT_DSN = os.environ.get("MEMORY_EXPERIMENT_DSN", "postgresql:///memory_experiment")
_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"bad identifier: {name!r}")
    return name


class CaseDB:
    """One isolated Postgres schema per run. All backends share this helper so the
    storage is identical; only the *interface* exposed to the agent differs."""

    def __init__(self, dsn: str = DEFAULT_DSN):
        self.dsn = dsn
        self.schema = "run_" + uuid.uuid4().hex[:10]
        self.conn: psycopg.Connection | None = None

    def open(self) -> None:
        self.conn = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True)
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))

    def close(self) -> None:
        if self.conn is None:
            return
        try:
            self.conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
        finally:
            self.conn.close()
            self.conn = None

    # ---- loading -------------------------------------------------------------
    def create_tables(self, tables: list[Table]) -> None:
        assert self.conn
        for t in tables:
            self.conn.execute(f"CREATE TABLE {ident(t.name)} ({t.columns_sql})")
            if t.description:
                self.conn.execute(
                    sql.SQL("COMMENT ON TABLE {} IS {}").format(sql.Identifier(t.name), sql.Literal(t.description))
                )

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        assert self.conn
        if not rows:
            return
        cols = list(rows[0].keys())
        stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in cols),
        )
        with self.conn.cursor() as cur:
            cur.executemany(stmt, [[r.get(c) for c in cols] for r in rows])

    # ---- querying ------------------------------------------------------------
    def query(self, q: str | sql.Composed, params: tuple | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        assert self.conn
        with self.conn.cursor() as cur:
            cur.execute(q, params)
            if cur.description is None:
                return []
            return [dict(r) for r in cur.fetchmany(limit)]

    def readonly_query(self, q: str, limit: int = 200, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        """Run agent-supplied SQL inside a read-only transaction on a fresh connection."""
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
                conn.execute("SET TRANSACTION READ ONLY")
                conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                cur = conn.execute(q)
                if cur.description is None:
                    return []
                return [dict(r) for r in cur.fetchmany(limit)]

    def describe(self) -> str:
        """Human-readable schema listing for the run schema."""
        rows = self.query(
            """
            SELECT c.table_name, c.column_name, c.data_type,
                   obj_description((quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass) AS tdesc
            FROM information_schema.columns c
            WHERE c.table_schema = %s
            ORDER BY c.table_name, c.ordinal_position
            """,
            (self.schema,),
        )
        out: dict[str, list[str]] = {}
        descs: dict[str, str] = {}
        for r in rows:
            out.setdefault(r["table_name"], []).append(f"{r['column_name']} {r['data_type']}")
            descs[r["table_name"]] = r["tdesc"] or ""
        lines = []
        for t, cols in out.items():
            lines.append(f"TABLE {t}" + (f"  -- {descs[t]}" if descs[t] else ""))
            lines += [f"  {c}" for c in cols]
        return "\n".join(lines)
