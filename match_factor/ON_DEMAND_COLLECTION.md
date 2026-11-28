# Match-Factor on-demand collection protocol

This protocol is for one fixture at a time. It does not authorize scraping, bulk retrieval, database writes, or use of a source beyond its terms.

## 1. Fixture header

Create a collection record before researching:

- sport:
- competition / season:
- home / away or player A / player B:
- provider event ID(s):
- scheduled start (UTC):
- analysis cutoff (UTC):
- collection started (UTC):
- collection status: draft / verified / blocked_by_rights / incomplete

Do not start a pre-match prediction if the fixture has already started. For historical replay, use only observations demonstrably available before the recorded cutoff.

## 2. Source observation record

Record each material fact separately. Do not combine several claims into one free-text note.

| Field | Required meaning |
|---|---|
| sport / event_id | Canonical fixture identity |
| subject_id / subject_name | Team or player the fact refers to |
| metric | Stable field name, e.g. goalie_status, injury_status, shots_for |
| value | Original observed value, not a model interpretation |
| unit / period | Unit and measurement window, where relevant |
| source_name | Publisher or data provider |
| source_url | Exact page or endpoint used |
| retrieved_at_utc | When we collected it |
| published_at_utc | When the source says it was published; null if unknown |
| valid_as_of_utc | Time the fact describes; null if unknown |
| verification | confirmed / probable / unverified / unknown |
| second_source_url | Independent corroboration, if available |
| rights_status | cleared / personal_only / permission_required / unresolved |
| notes | Conflict, missing data, caveats |

A fact is not confirmed merely because it appears on a single unofficial aggregator. If two sources disagree, preserve both observations and mark the field disputed.

## 3. Minimum pre-match checklist by sport

### NHL
- Fixture status, venue, scheduled start and rest days.
- Starting goalie: confirmed only when the source explicitly lists the starter; probable remains probable.
- Team/player availability and scratches.
- Last 10 games for each team: opponents, dates, scores, shots, special teams, goalie used and rest.
- Shot/chance profile and special teams; separate season baseline from recent sample.
- Any source rights restrictions: NHL official feed is not a commercially cleared source under the published NHL Terms of Service without written permission.

### KHL
- Fixture status, venue, start time and rest.
- Goalie confirmation and lineup/absence evidence.
- Last 10 games per team, with opponent quality and goalie context.
- Shots, power play, penalty kill and schedule density where available.
- Treat wrapper/API output as unlicensed until upstream KHL rights are checked.

### NBA
- Fixture status, venue, start time, rest and back-to-back status.
- Player availability and confirmed starting lineup, with publication time.
- Last 10 games per team: opponent, pace, offensive/defensive efficiency, rebounds, turnovers and three-point volume/accuracy.
- Key player minutes, role changes and absences; distinguish official injury report from projected lineup.
- NBA endpoint access does not itself establish commercial rights.

### Football
- Competition, venue, kickoff and fixture status.
- Starting XI, suspensions, injuries and source publication time.
- Last 10 matches per team: opponent strength, home/away, goals, shots, xG only where the provider defines it, cards and set pieces.
- Rest, travel, tactical changes and schedule congestion.
- Check league/provider terms separately; a wrapper or public page does not grant data rights.

### Tennis
- Event, round, surface, indoor/outdoor, scheduled start and match status.
- Player identity, handedness only if reliably sourced, recent form and opponent quality.
- Last 10 matches per player: surface, opponent, score, duration and rest days.
- Serve/return metrics, break points and tie-break performance only when source definitions and sample sizes are known.
- Keep odds source, bookmaker and timestamp separate from player-performance data.
- Preserve Valuebetennis attribution if using its CC BY 4.0 historical reference; do not bulk-import before explicit approval.

## 4. Analysis safeguards

- Show sample size beside every rolling statistic.
- Do not compare raw counts across different match lengths without normalization.
- Adjust recent form for opponent strength and venue/surface where relevant.
- Separate confirmed facts, model estimates and analyst judgments.
- Calculate fair probability independently from market odds; use odds only as a market observation and benchmark.
- If key inputs are missing, lower confidence or pass. Never invent a value to complete the checklist.
- Keep all feature timestamps at or before the analysis cutoff.

## 5. End-of-collection decision

Mark one outcome:

- **ready_for_analysis** — key facts are sourced, rights status permits this intended research use, and cutoff is clean.
- **incomplete** — important fields are missing or disputed.
- **blocked_by_rights** — provider terms do not permit the intended collection, storage or commercial use.
- **no_bet** — data is sufficient but no positive expected value is supported.

No records are written to the production database by this protocol. Database persistence requires a separate approval after backup and rights checks.
