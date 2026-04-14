# Selected Matchup Operator Runbook

## Purpose

Use this runbook when a client requests one D1 matchup brief. The goal is to
generate the requested brief from selected-matchup artifacts without allowing
unrelated team issues to block delivery.

The current command assumes the selected teams already have season artifacts:

- team readiness registry entry
- PBP bundle
- CFBStats snapshot
- CFBStats verification report
- enrichment artifact, unless explicitly disabled

If a team is missing from those artifacts, switch to onboarding/troubleshooting
mode before promising a delivery time. Use
`docs/team-onboarding-troubleshooting-runbook.md` for that path.

## Inputs To Confirm

Before running the brief, confirm:

- season
- team names exactly as the client expects them
- expected completed games for each team
- expected CFBStats conference scope for each team, when known
- whether PFF/enrichment is required
- any client-specific notes or naming preferences

Do not infer completed games from the week number. BYE weeks, Week 0 games,
postponements, neutral sites, and bowls make that unsafe.

## Standard Command

Run this from `pbp-analysis`:

```bash
python -m scripts.game_prep_brief.selected_matchup "Notre Dame" UConn \
  --season 2025 \
  --expected-games "Notre Dame=12" \
  --expected-games UConn=13 \
  --expected-conference "Notre Dame=Independents" \
  --expected-conference UConn=Independents \
  --refresh-enrichment
```

Outputs are written to `outputs/game_prep_brief/`:

- `<team1>_vs_<team2>_<season>_preflight.json`
- `<team1>_vs_<team2>_<season>_preflight.md`
- `<team1>_vs_<team2>_<season>_operator_summary.json`
- `<team1>_vs_<team2>_<season>_enrichment.json`
- `<team1>_vs_<team2>_<season>_v2.md`
- `<team1>_vs_<team2>_<season>_v2.html`

By default, the command reads:

```text
config/team-readiness-<season>.json
```

Override it only when testing a draft registry:

```bash
python -m scripts.game_prep_brief.selected_matchup Michigan Utah \
  --season 2025 \
  --readiness-registry /path/to/team-readiness-2025.json \
  --expected-games Michigan=13 \
  --expected-games Utah=13
```

Use `--no-readiness-gate` only for local diagnosis. Client-delivery runs should
keep the readiness gate enabled.

## Offline Or No-PFF Modes

Reuse an existing enrichment artifact:

```bash
python -m scripts.game_prep_brief.selected_matchup Michigan Utah \
  --season 2025 \
  --expected-games Michigan=13 \
  --expected-games Utah=13 \
  --expected-conference Michigan="Big Ten" \
  --expected-conference Utah="Big 12"
```

Run without enrichment only when explicitly approved:

```bash
python -m scripts.game_prep_brief.selected_matchup Michigan Utah \
  --season 2025 \
  --expected-games Michigan=13 \
  --expected-games Utah=13 \
  --no-enrichment
```

## Read The Result

Start with the operator summary JSON. It answers:

- overall status
- readiness registry pass/warning/fail counts
- preflight pass/warning/fail counts
- whether render passed
- which artifact paths were used
- whether enrichment was required

Then open the readiness checks in the operator summary. A client-ready run
should have:

- registry entries for both selected teams
- no readiness fail checks
- `production_ready*` status, or `existing_supported` with understood warnings
- no blocked deliverable status

Then open the preflight markdown. A client-ready run should also have:

- zero fail checks
- expected games matching found games
- CFBStats rankings for both teams
- no missing verification entries
- enrichment present when required

Warnings are allowed only when understood and documented. For example, bounded
CFBStats source/parity drift can be acceptable. Missing teams, missing game
counts, or missing core PFF fields are blockers.

## Quality Review

Before delivery, inspect the rendered markdown/html:

- top summary has a reasonable record and recent results for both teams
- rankings use the correct conference scope for each team
- no critical section is blank
- penalties are populated
- play-clock and hurry-up are populated when PFF is required
- warning banners are understandable
- team names and abbreviations are acceptable for the client

If a field is unavailable, make sure the brief says why. Do not silently deliver
`N/A` in a core section without a visible reason.

## Troubleshooting Flow

For full team-season onboarding, use
`docs/team-onboarding-troubleshooting-runbook.md`. The quick triage below is
for deciding which path is blocked.

If the bundle is missing a team:

1. Check the team readiness registry.
2. Backfill StatBroadcast/CollegePressBox game briefs.
3. Use documented fallback sources, such as SIDEARM boxscores, only when the
   primary source is missing or wrong.
4. Regenerate the bundle and rerun preflight.

If CFBStats is missing or in the wrong scope:

1. Confirm the canonical CFBStats team name.
2. Add or fix aliases.
3. Regenerate the snapshot and verification report.
4. Rerun preflight with expected conference checks.

If enrichment is missing:

1. Check Fly health with `fly logs -a yr-data-api`.
2. Smoke test live endpoints for both teams.
3. If PFF auth is broken, use the Mac mini PFF cookie restore operation.
4. Rerun with `--refresh-enrichment`.

If preflight has warning-only verification:

1. Confirm there are zero fail metrics.
2. Read the warning details in the brief.
3. Document accepted warning classes in the readiness registry.

## Current Boundaries

This command does not yet discover missing StatBroadcast links or regenerate
parser artifacts by itself. It is the delivery command once selected-team
artifacts exist. Missing-source cases still require onboarding mode.
