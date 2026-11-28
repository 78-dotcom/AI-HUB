# Match-Factor data foundation

This is the first implementation layer for the independent Match-Factor database. It is intentionally separate from the live-odds endpoint and does not treat Pinnacle as the model's source of truth.

## Architecture

- PostgreSQL stores normalized events, participants, results, odds snapshots, statistics snapshots, availability snapshots, raw source records, and ingestion-run audit data.
- Every imported record retains source identity and raw payload for traceability.
- Every time-sensitive snapshot has both retrieval time and `valid_as_of`; backtests must use only information available before the event start.
- Sport-specific models will be built on top of this shared event/data layer. Do not combine raw NHL, NBA, football, and tennis features into one uncalibrated model.
- Pinnacle odds are stored as one external market observation where available, not as the model's target or training label.

## First dataset: Valuebetennis

Valuebetennis publishes ATP/WTA singles match CSVs from 2021 under CC BY 4.0. The published rows include UTC date, tournament/category/surface/round, players, opening odds, last odds before match, winner, score, and duration. Attribution is required; commercial reuse is permitted under the stated licence.

Source: https://www.valuebetennis.com/en/donnees.htm

Attribution: Valuebetennis, Tennis results and odds since 2021, https://www.valuebetennis.com/en/donnees.htm

## Import

1. Obtain a season CSV from the source page.
2. Set `DATABASE_URL` to the Render PostgreSQL **Internal Database URL** from the AI-HUB service's region.
3. Run once with schema creation:
   ```bash
   python -m match_factor.ingest.valuebetennis --init-schema valuebetennis-matchs-2026.csv
   ```
4. Import other seasons without `--init-schema`.

The importer is idempotent for event identity and raw-record hashes. It preserves source rows and records rejected rows in the ingestion-run counters. Review source terms before adding any new provider.

## Important safeguards

- No automatic production migration or deployment is triggered by these files.
- Do not expose the database publicly or change its IP allowlist to make imports work.
- Do not run a historical backtest until source coverage, duplicates, timezone handling, and pre-match cutoff rules have been validated.
- Source-recorded odds are not treated as ground truth. They are stored as observations with provenance.
- Football-Data and other non-commercial datasets must not be ingested into a commercial AI product without permission.
