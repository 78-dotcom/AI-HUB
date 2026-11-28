# Match-Factor source registry — research-first mode

**Policy:** this project is not bulk-downloading or importing third-party archives at this stage. We consult sources when analysing a match, record only the observations needed for reproducible analysis, and later move curated records into our own database. Every provider must pass a terms/licence review before persistent ingestion or commercial use.

## Source assessment

| Sport | Candidate source | What it can provide | Current status | Restrictions / cautions |
|---|---|---|---|---|
| Tennis | [Valuebetennis](https://www.valuebetennis.com/en/donnees.htm) | ATP/WTA singles history since 2021; results, surface, round, player identities, opening and last pre-match odds | **Best documented historical candidate** | Published under CC BY 4.0; preserve attribution. No rich point-by-point/statistical match data. Do not bulk import until user approves. |
| NHL | [NHL public web feeds](https://api-web.nhle.com/) | Schedules, game results, boxscores, play-by-play and player/team statistics | **Candidate for on-demand research** | Public endpoints are not the same as an explicit commercial data licence. Review NHL terms before persistent storage or commercial product use. |
| NHL | [Sportradar NHL historical API](https://developer.sportradar.com/ice-hockey/docs/nhl-ig-historical-data) | Historical stats from 2013, including schedules, team/player stats and game feeds | **Documented fallback, not assumed free** | Commercial provider; trial access is not a permanent free archive. Check contract and field coverage before use. |
| KHL | [KHL site REST / webcaster feeds via sportsdataverse-py](https://sportsdataverse-py.sportsdataverse.org/docs/intro) | Schedules, results and selected KHL data through community-maintained wrappers | **Discovery candidate** | Wrapper documentation is not a licence from KHL. Validate endpoint stability, completeness, and terms before collection or redistribution. |
| NBA | [NBA Stats endpoints via nba_api](https://github.com/swar/nba_api) | Game logs, boxscores, team/player stats and some advanced statistics | **Candidate for on-demand research** | Community wrapper over unofficial NBA.com endpoints; endpoints can change or block requests. No assumption of commercial redistribution rights. |
| Football | [Football-Data.co.uk](https://www.football-data.co.uk/data.php) | Historical results, match statistics and bookmaker odds for many European leagues | **Personal/academic analysis only unless permission obtained** | Its stated terms restrict commercial use and automated bots/scrapers/AI-training use. Do not ingest into a commercial AI product without written permission. |
| Football | [sportsdataverse-py soccer sources](https://sportsdataverse-py.sportsdataverse.org/docs/intro) | Discovery layer for ESPN, OpenLigaDB, UEFA/FIFA and other feeds | **Source-by-source review required** | Wrapper availability does not grant upstream data rights. Check the original provider's terms for each competition and field. |

## Operating procedure — no bulk import yet

1. **Before a match:** query the relevant primary/public sources and retrieve only the data needed for that fixture.
2. **Verify:** cross-check important facts (starting lineups, confirmed NHL goalie, injuries/suspensions, match status and recent results) against a second independent source where possible.
3. **Record provenance:** for every observation, retain provider, original URL/endpoint, retrieval timestamp (UTC), event ID, field, value, and confidence/status (confirmed, probable, unknown).
4. **Respect the pre-match cutoff:** never use information published after the scheduled start when reconstructing a historical prediction.
5. **Keep raw facts separate from derived metrics:** preserve source values; calculate rolling form, opponent-adjusted performance, fatigue and model features in our own code.
6. **No silent assumptions:** missing or unverified historical lineups/injuries remain unknown; do not backfill them from current pages.
7. **Build our archive gradually:** persist curated, rights-cleared records after the schema and source terms are validated. No mass copying of entire third-party databases.

## Data quality rules

- Canonical participant identity must use provider IDs and an alias map; names alone are not reliable identifiers.
- Match keys must include sport, competition, season/date, participants and provider event ID where available.
- Store UTC timestamps and original local date/time separately when supplied.
- Preserve corrections and source snapshots rather than overwriting history without an audit trail.
- Separate regular season, playoffs, exhibitions and cancelled/postponed events.
- For each sport, maintain its own feature definitions and model calibration.
- Market odds are optional external observations, not the label or the model's truth.

## First implementation sequence

1. Validate source endpoints and terms for the next fixture in each sport.
2. Create small, documented on-demand collectors (no bulk archive).
3. Store only curated observations with provenance once user approves database persistence.
4. Build sport-specific recent-form and opponent-strength calculations.
5. Add historical replay only when reliable pre-match snapshots exist.
6. Compare model predictions with settled results and report calibration, Brier score, log loss, flat-stake ROI, drawdown and uncertainty intervals.

**Important:** this registry is a research map, not a claim that every source is licensed for commercial use or that all feeds have been tested end-to-end.
