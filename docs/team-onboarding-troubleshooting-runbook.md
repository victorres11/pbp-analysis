# Team Onboarding And Troubleshooting Runbook

## Purpose

Use this runbook when the selected-matchup operator command blocks because a
team-season is missing, stale, or not trusted for a client deliverable.

This is the onboarding mode. The goal is to make one requested team-season safe
to use, then return to the selected-matchup delivery flow.

## When To Enter Onboarding Mode

Enter this flow when preflight reports any of these blockers:

- team missing from the PBP bundle
- zero games found
- found games do not match expected completed games
- team missing from CFBStats snapshot
- CFBStats conference scope is missing or wrong
- team missing from verification report
- verification has fail metrics
- enrichment is missing when PFF is required
- core PFF fields are missing
- rendered brief has blank core sections

Do not work around these by forcing a render for a client deliverable. Use
`--allow-blocked` only for local diagnosis.

## Inputs To Record

Create or update the team readiness entry with:

- season
- requested client-facing team name
- canonical slug
- expected completed games
- expected CFBStats conference scope
- CollegePressBox schedule URL, if known
- StatBroadcast group id, if known
- known aliases and abbreviations
- PFF slug
- source exceptions or fallback decisions

Expected completed games should come from a schedule check or operator input,
not from the week number.

## Source Discovery Order

Use this order:

1. Existing ready artifacts.
2. CollegePressBox logged-in team schedule page.
3. StatBroadcast archive XML discovery for completed games.
4. Saved CollegePressBox HTML when automation cannot access the page.
5. Manual schedule repair when links are wrong.
6. SIDEARM boxscore fallback for isolated missing games.

SIDEARM is a fallback, not the default source. Use it when the primary
StatBroadcast source is missing, wrong, or unavailable for a specific game.

## CollegePressBox Notes

CollegePressBox is the normal discovery starting point:

```text
https://collegepressbox.com/teams/<team-slug>/team-schedule/
```

You must be logged in. The team schedule page usually contains links to the
StatBroadcast game pages or `statmonitr/?id=...` event IDs.

Sometimes the CollegePressBox links are wrong. In that case:

- extract the IDs
- inspect whether each event is the right game
- repair the schedule JSON manually
- document the source issue in the readiness notes

The parser-side source runbook has the lower-level details:

```text
../pbp-parser/docs/team-onboarding-statbroadcast.md
```

## Backfill Completed Games From Archive XML

For completed 2025 games, archive XML is often the fastest path.

From `pbp-parser`:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/discover_statbroadcast_archive_xml.py \
  --year 2025 \
  --team-name "Utah" \
  --team-groupid utah \
  --out data/statbroadcast_cache/schedule_utah_2025_manual.json
```

Review the schedule file before backfill:

- expected game count matches
- opponents are correct
- dates are correct
- neutral/bowl rows use the correct `xmlfile`
- no duplicate or wrong events

Then backfill normalized game briefs:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/backfill_statbroadcast_archive_xml.py \
  --schedule-file data/statbroadcast_cache/schedule_utah_2025_manual.json \
  --team-output utah \
  --out-dir data/statbroadcast_game_briefs
```

If the default archive ranges miss a cluster, rerun discovery with an explicit
ID range:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/discover_statbroadcast_archive_xml.py \
  --year 2025 \
  --team-name "Team Name" \
  --team-groupid team-slug \
  --id-range 626000-628000 \
  --out data/statbroadcast_cache/schedule_team-slug_2025_manual.json
```

## SIDEARM Fallback

Use SIDEARM only for isolated games where StatBroadcast discovery/backfill does
not produce a usable game brief.

From `pbp-parser`:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/build_game_brief_from_sidearm_boxscore.py \
  --url "https://example.sidearmsports.com/sports/football/stats/2025/opponent/boxscore/12345" \
  --out data/statbroadcast_game_briefs/team-slug/game_12345.json
```

After adding a SIDEARM fallback:

- confirm the game count
- inspect penalties and scoring zones in the rendered brief
- note the fallback source in readiness
- add or update parser tests when the fallback reveals a parser contract issue

## Generate The Parser Bundle

After game briefs exist, generate a bundle from `pbp-parser`:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/generate_statbroadcast_bundle.py \
  --scan-dir data/statbroadcast_game_briefs \
  --out data/tmp/statbroadcast_bundle_2025_selected.json
```

Check the team entry:

```bash
python3 - <<'PY'
import json
bundle = json.load(open("data/tmp/statbroadcast_bundle_2025_selected.json"))
for slug in ["team-slug"]:
    row = bundle["teams"].get(slug)
    print(slug, row and row.get("games_parsed"))
PY
```

Do not continue if `games_parsed` does not match the expected completed games.

## Generate CFBStats Artifacts

Generate or refresh the CFBStats snapshot for the selected supported set. Include
both matchup teams and any existing supported teams needed by the current local
artifact policy.

From `pbp-parser`:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/snapshot_cfbstats.py \
  --year 2025 \
  --team "Michigan" \
  --team "Utah" \
  --output data/tmp/cfbstats_2025_selected.json
```

Verify the bundle:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.13 scripts/verify_bundle_cfbstats.py \
  --bundle data/tmp/statbroadcast_bundle_2025_selected.json \
  --year 2025 \
  --json-out data/tmp/cfbstats_verification_2025_selected.json
```

If a team is missing from CFBStats:

- confirm the CFBStats display name
- add or fix aliases in parser/analysis as needed
- rerun snapshot and verification

If the verifier has fail metrics:

- inspect whether the source is incomplete
- inspect whether aliases caused the wrong row to match
- compare normalized source totals to CFBStats totals
- classify only well-understood bounded drift as warning-level
- do not mark the team ready with unexplained fail metrics

## Promote Artifacts

Only promote after the selected team has the expected game count and verification
has no unexplained fail metrics.

Parser promotion targets:

```text
pbp-parser/data/statbroadcast_game_briefs/<team-slug>/
pbp-parser/data/statbroadcast_cache/schedule_<team>_<season>_manual.json
pbp-parser/data/cfbstats_snapshots/cfbstats_<season>.json
pbp-parser/data/cfbstats_reports/cfbstats_verification_<season>.json
```

API handoff target:

```text
yr-data-api/data/pbp_stats_bundle.json
```

API alias targets:

```text
yr-data-api/data/team_aliases.json
yr-data-api/app/services/pff_slug_aliases.json
```

Analysis targets:

```text
pbp-analysis/config/team-readiness-2025.json
pbp-analysis/scripts/game_prep_brief/loaders.py
```

Keep aliases minimal and evidence-based. Add tests for naming cases that already
failed once.

## Enrichment Triage

If PFF/enrichment is missing:

1. Smoke test Fly endpoints for both team slugs.
2. Check `fly logs -a yr-data-api`.
3. Try canonical and alias slugs, such as `uconn` and `connecticut`.
4. Confirm the PFF slug in `pff_slug_aliases.json`.
5. If auth is broken, use the Mac mini PFF cookie restore operation.
6. Rerun selected-matchup command with `--refresh-enrichment`.

Minimum PFF fields for a required-enrichment run:

- average play clock
- hurry-up rate
- offensive plays per game
- defensive plays per game

Advanced charting fields can be partial if the brief clearly labels them and
the preflight still passes.

## Return To Delivery Mode

Once artifacts are promoted, rerun:

```bash
python -m scripts.game_prep_brief.selected_matchup "Team A" "Team B" \
  --season 2025 \
  --expected-games "Team A=EXPECTED" \
  --expected-games "Team B=EXPECTED" \
  --expected-conference "Team A=CONFERENCE" \
  --expected-conference "Team B=CONFERENCE" \
  --refresh-enrichment
```

The team is ready for client delivery when:

- selected-matchup preflight has zero fail checks
- render exits 0
- operator summary status is `ready`
- brief quality review passes
- readiness registry records any remaining warnings

## Issue Log Template

Record reroutes in the readiness notes or checklist:

```text
Issue:
Impact:
Evidence:
Options:
Chosen path:
Follow-up:
```

This is what prevents one-off fixes from becoming hidden assumptions.
