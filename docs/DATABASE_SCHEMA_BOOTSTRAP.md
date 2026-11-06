# AI HUB database schema bootstrap

The application currently uses SQLAlchemy metadata and does not yet have a versioned
Alembic migration history. The helper `scripts/bootstrap_schema.py` provides a
controlled, additive way to inspect/create tables required by the current application.

## Safety rules

1. Confirm the Render PostgreSQL database is reachable from the execution environment.
2. Take and verify a database backup before applying schema changes.
3. Run the script without flags first. This is check-only and lists missing tables.
4. Apply only when the target database and backup have been verified:
   ```bash
   AI_HUB_SCHEMA_BOOTSTRAP=1 python scripts/bootstrap_schema.py --apply
   ```
5. Re-run the check-only command and verify that no tables are missing.

The script uses SQLAlchemy `MetaData.create_all`: it creates absent tables only. It does
not drop tables, delete rows, or alter existing columns. It is therefore suitable only
for initial/additive table creation. It is **not** a substitute for versioned migrations
when an existing table's columns, indexes, constraints, or data need to change.

Do not run against production until a backup has been completed and the database URL
has been verified without exposing it in chat, logs, or source control.
