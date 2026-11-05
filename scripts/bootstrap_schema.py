#!/usr/bin/env python3
"""Inspect or explicitly create missing AI HUB SQLAlchemy tables.

This is an additive bootstrap helper, not a replacement for versioned migrations.
It never drops tables or alters existing columns.
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import inspect

# Import the application so every account-scoped model is registered on Base.
import web_app  # noqa: F401
from accounts import Base, _engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create missing tables (requires AI_HUB_SCHEMA_BOOTSTRAP=1).",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL", "").strip():
        print("ERROR: DATABASE_URL is not configured.", file=sys.stderr)
        return 2

    engine = _engine()
    expected = set(Base.metadata.tables)
    with engine.connect() as connection:
        existing = set(inspect(connection).get_table_names())
    missing = sorted(expected - existing)

    print(f"Existing tables: {len(existing)}")
    print(f"Application tables expected: {len(expected)}")
    if not missing:
        print("Schema check: complete; no missing tables.")
        return 0

    print("Missing tables:")
    for table in missing:
        print(f" - {table}")

    if not args.apply:
        print("Check only. No database changes were made.")
        print("After a verified backup, set AI_HUB_SCHEMA_BOOTSTRAP=1 and rerun with --apply.")
        return 1

    if os.getenv("AI_HUB_SCHEMA_BOOTSTRAP") != "1":
        print("ERROR: --apply also requires AI_HUB_SCHEMA_BOOTSTRAP=1.", file=sys.stderr)
        return 2

    # SQLAlchemy create_all is additive: it creates absent tables and does not
    # drop tables or modify existing columns.
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        remaining = sorted(expected - set(inspect(connection).get_table_names()))
    if remaining:
        print("ERROR: Some tables are still missing:", ", ".join(remaining), file=sys.stderr)
        return 3

    print("Schema bootstrap complete. No existing tables or rows were intentionally modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
