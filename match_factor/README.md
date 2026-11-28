# Match-Factor data foundation

This is the first implementation layer for the independent Match-Factor database. It is intentionally separate from the live-odds endpoint and does not treat Pinnacle as the model's source of truth.

## Architecture

- PostgreSQL stores normalized events, participants, results, odds snapshots, statistics snapshots, availability snapshots, raw source records, and ingestion-run audit data.
- Every imported record retains source identity and raw payload for traceability.
- Every time-sensitive snapshot has both retrieval time and `valid_as_of`; backtests must use only information available before the event start.
- Sport-specific models will be built on top of this shared event/data layer. Do not combine raw NHL, NBA, football, and tennis features into one uncalibrated model.
- Pinnacle odds are stored as one external market observation where available, not as the model's target or training label.

## Initial historical reference: Valuebetennis

Valuebetennis publishes ATP/WTA singles match CSVs from 2021 under CC BY 4.0. The published rows include UTC date, tournament/category/surface/round, players, opening odds, last odds before match, winner, score, and duration. Attribution is required; commercial reuse is permitted under the stated licence.

Source: https://www.valuebetennis.com/en/donnees.htm

Attribution: Valuebetennis, Tennis results and odds since 2021, https://www.valuebetennis.com/en/donnees.htm

## Project status: non-commercial research

Match-Factor is designated a non-commercial research and model-validation project. This applies to Match-Factor only; it does not change the status or business model of the wider AI-HUB platform. No paid picks, subscriptions, advertising, sponsorship, affiliate revenue or sale/licensing of Match-Factor outputs are part of this project mode.

Non-commercial status does not override provider terms. In particular, NBA.com statistics are excluded from betting-related analysis under NBA.com Terms section 9; NHL public content must not be automatically harvested or entered into our database without permission; and Football-Data.co.uk is not eligible for AI training or automated AI collection. See [NON_COMMERCIAL_POLICY.md](./NON_COMMERCIAL_POLICY.md) for the binding source gates.

## Current operating mode: research first, no bulk import

The Valuebetennis archive is our best-documented historical reference, not an instruction to download it now. At this stage we will consult public sources on demand, validate facts, and keep a source/provenance record. We will not bulk-copy third-party archives or write to the Render database until the source terms, database backup, and persistence plan are verified and the user explicitly approves.

See [SOURCE_REGISTRY.md](./SOURCE_REGISTRY.md) for the five-sport source map and licence cautions. See [NON_COMMERCIAL_POLICY.md](./NON_COMMERCIAL_POLICY.md) for the non-commercial project rules. See [ON_DEMAND_COLLECTION.md](./ON_DEMAND_COLLECTION.md) for the one-fixture collection checklist and provenance record requirements.

The CSV importer is retained as a future implementation component; it is not part of the current operating workflow.

## Important safeguards

- No automatic production migration or deployment is triggered by these files.
- Do not expose the database publicly or change its IP allowlist to make imports work.
- Do not run a historical backtest until source coverage, duplicates, timezone handling, and pre-match cutoff rules have been validated.
- Source-recorded odds are not treated as ground truth. They are stored as observations with provenance.
- A non-commercial project designation does not grant data rights or override restrictions on gambling-related use, automated collection, storage or AI training.
