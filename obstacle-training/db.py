"""Minimal READ-ONLY Postgres access through the psql command in config.PSQL_COMMAND (no Python DB driver needed).

This pipeline never writes to the application database: it only reads what customers did with detections. Anything that is not a SELECT/WITH
query is refused before it is sent.
"""
import json
import re
import shlex
import subprocess

import config

_READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def run_sql(sql: str) -> str:
    """Runs a read-only query and returns stdout; raises with psql's message on failure."""
    if not _READ_ONLY.match(sql):
        raise ValueError("db.run_sql only accepts SELECT / WITH queries (this pipeline never writes to the application database)")
    proc = subprocess.run(shlex.split(config.PSQL_COMMAND), input=sql, text=True, encoding="utf-8", capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def query_json(select_sql: str):
    """select_sql must be a SELECT that returns one jsonb value (e.g. jsonb_agg(...)); returns it parsed, or None."""
    out = run_sql(select_sql).strip()
    return json.loads(out) if out else None
