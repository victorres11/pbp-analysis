# D1 Matchup Expansion Plan

## Goal

Generate broadcaster-grade game prep briefs for requested D1 matchups with the
same quality bar as the current Big Ten plus Notre Dame workflow.

The immediate deliverable is Michigan vs Utah for the 2025 season. The broader
system should support 2026 in-season requests where the requested teams may come
from any D1 conference and current-season source data only becomes available
after games are played.

## Operating Model

Use selected-matchup artifacts for client deliverables and maintain a separate
team readiness registry for confidence.

Selected-matchup artifacts means a client request for Michigan vs Utah generates
and validates artifacts for Michigan and Utah only:

- PBP stats bundle
- CFBStats snapshot
- CFBStats verification report
- PFF/enrichment payload
- final markdown/html brief

This prevents unrelated team issues from blocking a client deliverable. The
readiness registry tracks which teams are already safe to run and which teams
need onboarding or weekly data refresh.

## Readiness Layers

Readiness has two independent layers.

Team integration readiness answers whether the system can handle the team at
all:

- canonical slug and display name
- season-specific conference
- StatBroadcast/CollegePressBox discovery information
- known source abbreviations and aliases
- CFBStats team and conference mapping
- PFF mapping
- parser/normalizer compatibility

Weekly data readiness answers whether the team is current for the requested
brief:

- expected completed games for the run
- StatBroadcast games found
- CFBStats snapshot freshness
- PFF/enrichment freshness
- verification status for the selected teams

For 2026, do not infer expected games from the week number. BYE weeks, Week 0,
postponements, neutral sites, and bowls make that unsafe. Manual expected game
counts are allowed and take priority over any schedule-derived default.

## Decision Log

### Decision 001: Client Deliverables Use Selected-Matchup Artifacts

Production brief runs should generate and validate only the teams requested for
that client matchup. This keeps turnaround predictable and avoids unrelated
teams blocking delivery.

### Decision 002: Readiness Is Team-Season Specific

A team can be production-ready for 2025 while still only integration-ready for
2026 before new-season games exist. Readiness records must include the season.

### Decision 003: Weekly Freshness Uses Expected Game Counts

The production gate compares found games to expected completed games. The
operator may provide manual expected counts, especially around BYE weeks.

### Decision 004: New Teams Must Be Onboarded Before Routine Runs

If a client requests a team that is not production-ready, the system should
enter onboarding/troubleshooting mode rather than silently generating a brief
with empty sections.

### Decision 005: CFBStats Scope Is Per Team

Each team receives rankings from its own conference scope. A cross-conference
matchup must not force both teams into one conference. Utah should use Big 12;
Michigan should use Big Ten.

## Production Deliverable Gate

A client-ready matchup brief must satisfy these checks:

- both teams exist in the selected bundle
- both teams have nonzero source games
- found games match expected completed games unless an override is recorded
- both teams have CFBStats rankings
- CFBStats rankings use each team's own conference scope
- both teams have PFF/enrichment when PFF is required
- verification report includes both selected teams
- no unexplained verification fail metrics
- core sections are not blank or `N/A`-only
- markdown/html render successfully
- warnings are visible in the output and summary

Use the selected-matchup preflight command before a client run:

```bash
python -m scripts.game_prep_brief.matchup_preflight Michigan Utah \
  --season 2025 \
  --bundle ../yr-data-api/data/pbp_stats_bundle.json \
  --cfbstats-snapshot ../pbp-parser/data/cfbstats_snapshots/cfbstats_2025.json \
  --cfbstats-verification-report ../pbp-parser/data/cfbstats_reports/cfbstats_verification_2025.json \
  --enrichment-file outputs/game_prep_brief/michigan_vs_utah_2025_enrichment.json \
  --expected-games Michigan=13 \
  --expected-games Utah=13 \
  --expected-conference Michigan="Big Ten" \
  --expected-conference Utah="Big 12" \
  --require-expected-games
```

The preflight is intentionally selected-matchup scoped. It blocks on missing
teams, game-count mismatches, missing CFBStats ranking rows, missing verification
entries, verification fail metrics, and required enrichment gaps. Warning-level
verification findings remain visible without blocking.

Core sections are:

- overview
- schedule
- rankings
- matchup rows
- explosives
- scoring zones
- turnovers
- middle 8
- situational downs
- special teams
- penalties

## Immediate Milestone: Michigan vs Utah 2025

1. Done: backfilled Utah 2025 StatBroadcast game briefs from archive XML.
2. Done: confirmed Utah expected game count for the deliverable scope is 13.
3. Done: added Utah aliases/metadata needed for bundle aggregation.
4. Done: generated a bundle containing Michigan and Utah.
5. Done: generated a CFBStats snapshot including Utah.
6. Done: generated a verification report including Utah.
7. Done: refreshed selected-team PFF/enrichment, with partial-provider warnings documented.
8. Done: rendered markdown and HTML.
9. Done: reviewed warnings and final content quality.
10. Done: marked Utah 2025 ready with documented warnings.

Definition of done:

- Michigan vs Utah brief has meaningful data for both teams.
- Utah CFBStats rankings show Big 12 context.
- no critical section is blank for Utah.
- verification failures are either fixed or explicitly documented.
- delivery checklist is completed.

## Second Proof: Notre Dame vs UConn 2025

Use Notre Dame vs UConn as the second expansion proof because it exercises a
different risk profile:

- UConn/Connecticut canonical naming
- independent conference scope behavior
- PFF mapping outside current Big Ten-heavy path
- non-Big-Ten deliverable after Utah

Current status:

1. Done: backfilled 13 UConn games for 2025.
2. Done: used StatBroadcast archive XML for 12 games and SIDEARM boxscore data
   for the Buffalo game that was missing from the archive links.
3. Done: added UConn/Connecticut aliases in parser, API, and analysis lookup
   paths.
4. Done: generated a 21-team 2025 bundle including UConn, Utah, Notre Dame,
   and the current supported Big Ten set.
5. Done: generated a CFBStats snapshot where UConn resolves as Connecticut in
   the Independents scope.
6. Done: generated a verifier report with zero fail metrics; UConn carries 12
   warning-level source/parity special cases.
7. Done: preflighted Notre Dame vs UConn with expected games
   `Notre Dame=12`, `UConn=13`, and expected conference `Independents` for both
   teams. The run exits 0 when enrichment is not required.
8. Done: rendered markdown and HTML with `--no-enrichment`; penalties,
   rankings, schedule, explosives, zones, turnovers, middle 8, situational,
   and special teams sections populate.
9. Blocked: PFF enrichment has not been validated for this matchup. Local
   `yr-data-api` needs `PFF_COOKIE`, and deployed PFF endpoints timed out during
   proof testing on April 14, 2026.

Definition of done before UConn is fully production-ready:

- PFF enrichment refresh succeeds for Notre Dame and UConn, or an explicit
  delivery policy allows a no-PFF brief with visible API-unavailable notices.
- The final deliverable preflight passes with the policy selected for that
  client request.
- Any remaining warning-level verification findings are documented in the
  readiness registry.

## 2026 In-Season Model

Before the 2026 season starts, teams can be integration-ready but not weekly
data-ready. Once the season starts, a matchup run must include expected
completed game counts.

Example Week 5 run:

```text
Michigan expected completed games: 3
Utah expected completed games: 4
```

The system should block if a selected team has fewer or more games than
expected, unless the operator explicitly records why partial/stale/extra data is
acceptable.

Early-season modes:

- preseason: previous-season data only
- early season: current season to date plus prior-season context
- in season: current season to date

The current milestone uses 2025 data only. 2026 support should be added as a
separate migration, not by overwriting 2025 assumptions.

## Expansion Strategy

Expand by demand and readiness, not by promising all D1 immediately.

Recommended sequence:

1. Michigan vs Utah deliverable.
2. Notre Dame vs UConn deliverable.
3. Weekly watchlist support for likely client-requested teams.
4. Big 12 cohort, if Utah is the first successful non-Big-Ten proof.
5. Broader FBS.
6. FCS only after source coverage and validation behavior are understood.

## Issue Log Template

When a reroute is needed, record it in the delivery checklist or readiness
notes:

```text
Issue:
Impact:
Evidence:
Options:
Chosen path:
Follow-up:
```

This keeps troubleshooting visible and prevents one-off fixes from becoming
undocumented assumptions.
