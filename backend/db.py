"""PostgreSQL helpers for durable OCR jobs."""

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://clipscribe:clipscribe-local@postgres:5432/clipscribe")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY,
  filename TEXT NOT NULL,
  engine TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  stage TEXT NOT NULL DEFAULT 'Queued',
  error TEXT,
  result JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs(status, created_at);
"""


@contextmanager
def connection():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def ensure_schema() -> None:
    with connection() as conn:
        conn.execute(SCHEMA)


def public_job(row: dict) -> dict:
    result = row.get("result")
    return {
        "id": str(row["id"]),
        "filename": row["filename"],
        "engine": row["engine"],
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"],
        "error": row.get("error"),
        "result": result if row["status"] == "complete" else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }
