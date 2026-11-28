"""Import Valuebetennis season CSV files into the Match-Factor PostgreSQL store.

Usage:
  DATABASE_URL=... python -m match_factor.ingest.valuebetennis path/to/file.csv
  DATABASE_URL=... python -m match_factor.ingest.valuebetennis --init-schema path/to/file.csv

The source is licensed CC BY 4.0; retain attribution when redistributing derived data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_KEY = "valuebetennis"
SOURCE_URL = "https://www.valuebetennis.com/en/donnees.htm"
SOURCE_NAME = "Valuebetennis — Tennis results and odds since 2021"
ATTRIBUTION = "Valuebetennis, Tennis results and odds since 2021, https://www.valuebetennis.com/en/donnees.htm"


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and value.strip():
            return value.strip()
    return ""


def _decimal(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip().replace(",", "."))
    except ValueError:
        return None


def normalize_row(row: dict[str, str]) -> dict[str, Any]:
    """Normalize one source row; keep source fields untouched in raw_record."""
    external_id = _first(row, "match_id", "id_match")
    if not external_id:
        raise ValueError("missing match_id")

    raw_date = _first(row, "date", "datetime")
    if not raw_date:
        raise ValueError("missing date")
    event_start = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    if event_start.tzinfo is None:
        event_start = event_start.replace(tzinfo=timezone.utc)
    event_start = event_start.astimezone(timezone.utc)

    player1 = _first(row, "joueur1", "player1")
    player2 = _first(row, "joueur2", "player2")
    if not player1 or not player2:
        raise ValueError("missing player name")

    winner_id = _first(row, "vainqueur_id", "winner_id")
    player1_id = _first(row, "joueur1_id", "player1_id")
    player2_id = _first(row, "joueur2_id", "player2_id")
    winner_role = "player1" if winner_id and winner_id == player1_id else (
        "player2" if winner_id and winner_id == player2_id else None
    )

    season = str(event_start.year)
    return {
        "external_id": external_id,
        "event_start_utc": event_start,
        "competition": _first(row, "tournoi", "tournament") or None,
        "season": season,
        "surface": _first(row, "surface") or None,
        "round_name": _first(row, "tour", "round") or None,
        "player1": player1,
        "player2": player2,
        "player1_external_id": player1_id or None,
        "player2_external_id": player2_id or None,
        "winner_role": winner_role,
        "winner_external_id": winner_id or None,
        "score": _first(row, "score") or None,
        "duration_minutes": int(_first(row, "duree_min", "duration_minutes")) if _first(row, "duree_min", "duration_minutes").isdigit() else None,
        "opening": {
            "player1": _decimal(_first(row, "cote1_ouverture", "odds1_open")),
            "player2": _decimal(_first(row, "cote2_ouverture", "odds2_open")),
        },
        "closing": {
            "player1": _decimal(_first(row, "cote1_cloture", "odds1_close")),
            "player2": _decimal(_first(row, "cote2_cloture", "odds2_close")),
        },
        "raw_record": row,
    }


def _connect(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install project dependencies, including psycopg[binary].") from exc
    return psycopg.connect(database_url)


def import_csv(csv_path: Path, database_url: str, init_schema: bool = False) -> dict[str, int]:
    from psycopg.types.json import Jsonb

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    counts = {"seen": 0, "inserted": 0, "rejected": 0}
    with _connect(database_url) as conn:
        with conn.cursor() as cur:
            if init_schema:
                schema_path = Path(__file__).resolve().parents[1] / "schema.sql"
                cur.execute(schema_path.read_text(encoding="utf-8"))
            cur.execute(
                """INSERT INTO mf_sources
                   (source_key, name, source_url, licence, attribution, commercial_use_allowed, notes)
                   VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                   ON CONFLICT (source_key) DO NOTHING""",
                (SOURCE_KEY, SOURCE_NAME, SOURCE_URL, "CC BY 4.0", ATTRIBUTION,
                 "Season CSV; source records include opening and last pre-match odds."),
            )
            cur.execute(
                """INSERT INTO mf_ingestion_runs (source_key, file_name, file_sha256)
                   VALUES (%s, %s, %s) RETURNING id""",
                (SOURCE_KEY, csv_path.name, digest),
            )
            run_id = cur.fetchone()[0]
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\\t")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(handle, dialect=dialect)
                for source_row in reader:
                    counts["seen"] += 1
                    try:
                        item = normalize_row(source_row)
                        cur.execute(
                            """INSERT INTO mf_events
                               (sport, competition, season, event_start_utc, status, surface,
                                round_name, source_key, external_id, raw_record)
                               VALUES ('tennis', %s, %s, %s, 'finished', %s, %s, %s, %s, %s)
                               ON CONFLICT (source_key, external_id) DO UPDATE SET
                                 competition=EXCLUDED.competition, season=EXCLUDED.season,
                                 event_start_utc=EXCLUDED.event_start_utc, surface=EXCLUDED.surface,
                                 round_name=EXCLUDED.round_name, raw_record=EXCLUDED.raw_record,
                                 updated_at=now()
                               RETURNING id""",
                            (item["competition"], item["season"], item["event_start_utc"],
                             item["surface"], item["round_name"], SOURCE_KEY,
                             item["external_id"], Jsonb(item["raw_record"])),
                        )
                        event_id = cur.fetchone()[0]
                        participant_ids: dict[str, int] = {}
                        for role in ("player1", "player2"):
                            name = item[role]
                            cur.execute(
                                """INSERT INTO mf_participants (sport, participant_type, canonical_name)
                                   VALUES ('tennis', 'player', %s)
                                   ON CONFLICT (sport, participant_type, canonical_name)
                                   DO UPDATE SET canonical_name=EXCLUDED.canonical_name
                                   RETURNING id""", (name,),
                            )
                            participant_ids[role] = cur.fetchone()[0]
                            cur.execute(
                                """INSERT INTO mf_event_participants
                                   (event_id, participant_id, role, source_external_id)
                                   VALUES (%s, %s, %s, %s)
                                   ON CONFLICT (event_id, role) DO UPDATE SET
                                     participant_id=EXCLUDED.participant_id,
                                     source_external_id=EXCLUDED.source_external_id""",
                                (event_id, participant_ids[role], role, item[f"{role}_external_id"]),
                            )
                        winner_participant_id = participant_ids.get(item["winner_role"]) if item["winner_role"] else None
                        cur.execute(
                            """INSERT INTO mf_results
                               (event_id, winner_participant_id, final_score, duration_minutes, settled_at, source_key, raw_record)
                               VALUES (%s, %s, %s, %s, now(), %s, %s)
                               ON CONFLICT (event_id) DO UPDATE SET
                                 winner_participant_id=EXCLUDED.winner_participant_id,
                                 final_score=EXCLUDED.final_score,
                                 duration_minutes=EXCLUDED.duration_minutes,
                                 settled_at=EXCLUDED.settled_at,
                                 raw_record=EXCLUDED.raw_record""",
                            (event_id, winner_participant_id, item["score"], item["duration_minutes"],
                             SOURCE_KEY, Jsonb(item["raw_record"])),
                        )
                        for timing in ("opening", "closing"):
                            for role in ("player1", "player2"):
                                odds = item[timing][role]
                                if odds and odds > 1:
                                    cur.execute(
                                        """INSERT INTO mf_odds_snapshots
                                           (event_id, source_key, bookmaker, market, selection,
                                            decimal_odds, captured_at, is_opening, is_closing, raw_record)
                                           VALUES (%s, %s, 'Pinnacle (source-recorded)', 'h2h', %s,
                                                   %s, %s, %s, %s, %s)
                                           ON CONFLICT DO NOTHING""",
                                        (event_id, SOURCE_KEY, role, odds, item["event_start_utc"],
                                         timing == "opening", timing == "closing", Jsonb(item["raw_record"])),
                                    )
                        raw_json = json.dumps(item["raw_record"], ensure_ascii=False, sort_keys=True)
                        row_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
                        cur.execute(
                            """INSERT INTO mf_raw_records
                               (source_key, external_id, payload, payload_sha256, ingestion_run_id)
                               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                            (SOURCE_KEY, item["external_id"], Jsonb(item["raw_record"]), row_hash, run_id),
                        )
                        counts["inserted"] += 1
                    except (ValueError, TypeError, KeyError) as exc:
                        counts["rejected"] += 1
                        # Preserve the run and continue; bad source rows are counted, not silently discarded.
                        continue
            cur.execute(
                """UPDATE mf_ingestion_runs SET finished_at=now(), rows_seen=%s,
                   rows_inserted=%s, rows_rejected=%s, status=%s WHERE id=%s""",
                (counts["seen"], counts["inserted"], counts["rejected"],
                 "completed" if counts["rejected"] == 0 else "completed_with_rejections", run_id),
            )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Valuebetennis CSV into Match-Factor.")
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--init-schema", action="store_true", help="Apply match_factor/schema.sql before import.")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required; no database was changed.")
    if not args.csv_file.is_file():
        raise SystemExit(f"CSV file not found: {args.csv_file}")
    print(import_csv(args.csv_file, database_url, init_schema=args.init_schema))


if __name__ == "__main__":
    main()
