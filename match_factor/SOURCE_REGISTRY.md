# Match-Factor source registry — research-first mode

**Policy:** this project is not bulk-downloading or importing third-party archives at this stage. We consult sources when analysing a match, record only the observations needed for reproducible analysis, and later move curated records into our own database. Every provider must pass a terms/licence review before persistent ingestion or commercial use.

## Source assessment

| Sport | Candidate source | What it can provide | Current status | Restrictions / cautions |
|---|---|---|---|---|
| Tennis | [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm) | ATP/WTA singles history since 2021; results, surface, round, player identities, opening and last pre-match odds | **Best documented historical candidate** | Published under CC BY 4.0; preserve attribution. No rich point-by-point/statistical match data. Do not bulk import until user approves. |
| NHL | [NHL public web feeds](https://api-web.nhle.com/) | Schedules, game results, boxscores, play-by-play and player/team statistics | **Research-only unless written permission is obtained** | Official NHL Terms of Service (last updated 2025-10-29), sections 2 and 7: access/use is limited to non-commercial, informational, personal use; unauthorized scraping/automated harvesting is prohibited; copying, entering NHL Content into a database, distribution and derivative/commercial use require written permission or another valid legal basis. Do not build a commercial collector or persist NHL feed data on the assumption that public endpoints are freely licensed. [Official terms](https://www.nhl.com/info/terms-of-service). |
| NHL | [Sportradar NHL historical API](https://developer.sportradar.com/ice-hockey/docs/nhl-ig-historical-data) | Historical stats from 2013, including schedules, team/player stats and game feeds | **Preferred licensed-provider route to evaluate** | Commercial provider; obtain a suitable contract/rights package and confirm fields, territory, retention and redistribution rights before use. |
| KHL | [KHL site REST / webcaster feeds via sportsdataverse-py](https://sportsdataverse-py.sportsdataverse.org/docs/intro) | Schedules, results and selected KHL data through community-maintained wrappers | **Discovery candidate; rights unresolved** | Wrapper documentation is not a licence from KHL. Validate endpoint stability, completeness, and terms directly with the upstream provider before collection, persistence or redistribution. |
| NBA | [NBA Stats endpoints via nba_api](https://github.com/swar/nba_api) | Game logs, boxscores, team/player stats and some advanced statistics | **Research candidate; commercial rights unresolved** | Community wrapper over unofficial NBA.com endpoints; endpoints can change or block requests. Do not assume commercial database, training, redistribution or product-use rights. Prefer a licensed provider for AI-HUB. |
| Football | [Football-Data.co.uk](https://www.football-data.co.uk/data.php) | Historical results, match statistics and bookmaker odds for many European leagues | **Personal/academic analysis only unless permission obtained** | Its stated terms restrict commercial use and automated bots/scrapers/AI-training use. Do not ingest into a commercial AI product without written permission. |
| Football | [sportsdataverse-py soccer sources](https://sportsdataverse-py.sportsdataverse.org/docs/intro) | Discovery layer for ESPN, OpenLigaDB, UEFA/FIFA and other feeds | **Source-by-source review required** | Wrapper availability does not grant upstream data rights. Check the original provider's terms for each competition and field. |

## Operating procedure — no bulk import yet

1. **Define the fixture:** sport, competition, event ID, scheduled start in UTC, and the exact pre-match cutoff.
2. **Check rights before retrieval:** distinguish a public webpage/API from permission to automate, store, train on, redistribute, or use data commercially. If unclear, mark the source as rights unresolved and do not automate or persist it.
3. **Retrieve only what is needed:** schedule/status, recent results, relevant player/team statistics, availability/lineups, rest/travel, and market observations. Do not fetch whole seasons or archives.
4. **Verify important facts:** cross-check lineups, confirmed NHL goalie, injuries/suspensions, match status and recent results against a second independent source where possible. Record disagreements rather than silently choosing one.
5. **Record provenance:** provider, original URL/endpoint, retrieval timestamp (UTC), event ID, field, value, source publication time if known, confidence/status (confirmed, probable, unverified, unknown), and rights status.
6. **Respect the pre-match cutoff:** never use information published after scheduled start when reconstructing a historical prediction. Keep retrieved_at separate from valid_as_of and published_at.
7. **Keep raw facts separate from derived metrics:** preserve only rights-cleared source values; calculate rolling form, opponent-adjusted performance, fatigue and model features in our own code.
8. **No silent assumptions:** missing or unverified historical lineups/injuries remain unknown; do not backfill them from current pages.
9. **Persist gradually:** write curated records only after source rights, schema, retention rules and backup are checked and the user explicitly approves database persistence.

## Data quality rules

- Canonical participant identity must use provider IDs and an alias map; names alone are not reliable identifiers.
- Match keys must include sport, competition, season/date, participants and provider event ID where available.
- Store UTC timestamps and original local date/time separately when supplied.
- Preserve corrections and source snapshots rather than overwriting history without an audit trail.
- Separate regular season, playoffs, exhibitions and cancelled/postponed events.
- For each sport, maintain its own feature definitions and model calibration.
- Market odds are optional external observations, not the label or the model's truth.
- A source with unresolved rights is not eligible for automated ingestion, long-term retention, model training or commercial display.

## First implementation sequence

1. Finish source/rights review for one provider per sport.
2. Validate one real upcoming fixture manually, without bulk collection or database writes.
3. Create small on-demand collectors only for providers whose terms permit the intended use.
4. Store only curated observations with provenance once the user approves database persistence.
5. Build sport-specific recent-form and opponent-strength calculations.
6. Add historical replay only when reliable pre-match snapshots exist and their use is permitted.
7. Compare model predictions with settled results and report calibration, Brier score, log loss, flat-stake ROI, drawdown and uncertainty intervals.

**Important:** this registry is a research map, not a claim that every source is licensed for commercial use or that all feeds have been tested end-to-end.
