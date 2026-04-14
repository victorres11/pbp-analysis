# Michigan vs Utah 2025 Delivery Checklist

## Request

- Matchup: Michigan vs Utah
- Season: 2025
- Status: smoke brief passed with warnings
- Deliverable target: client-ready markdown and HTML brief

## Expected Inputs

- Michigan expected games: 13
- Utah expected games: 13
- PFF enrichment required: yes
- CFBStats required: yes
- Selected-matchup artifacts: yes

## Preflight

- [x] Michigan exists in selected bundle.
- [x] Utah exists in selected bundle.
- [x] Michigan found games equals expected games.
- [x] Utah found games equals expected games.
- [x] Michigan CFBStats rankings attach under Big Ten.
- [x] Utah CFBStats rankings attach under Big 12.
- [x] Michigan verification report is present.
- [x] Utah verification report is present.
- [x] Michigan PFF/enrichment is present.
- [x] Utah PFF/enrichment is present.

## Utah Backfill

- [x] Confirm Utah StatBroadcast group id.
- [x] Document Utah CollegePressBox URL and fallback source.
- [x] Build Utah 2025 schedule from StatBroadcast archive XML.
- [x] Review discovered event IDs and expected game count.
- [x] Fetch all Utah archive XML payloads.
- [x] Normalize Utah game briefs.
- [x] Promote Utah normalized files into canonical game brief directory.
- [x] Record Utah source abbreviations and aliases.
- [x] Generate Utah bundle row.
- [x] Run parity gate for Utah.

## Matchup Artifact Generation

- [x] Generate selected Michigan+Utah bundle.
- [x] Generate selected Michigan+Utah CFBStats snapshot.
- [x] Generate selected Michigan+Utah verification report.
- [x] Generate selected Michigan+Utah enrichment.
- [x] Render markdown.
- [x] Render HTML.

## Quality Gate

- [x] No critical section is blank for Michigan.
- [x] No critical section is blank for Utah.
- [x] No unexplained verification fail metrics.
- [x] Warnings are reviewed and either fixed or documented.
- [x] Schedule rows look sane for both teams.
- [x] Recent results look sane for both teams.
- [x] Ranking highlights use conference-relative context.
- [x] Penalty, turnover, situational, and special teams sections have real values.
- [x] Final files are ready for delivery.

## Issue Log

Use this section for reroutes during backfill or validation.

```text
Issue:
Impact:
Evidence:
Options:
Chosen path:
Follow-up:
```

```text
Issue: Live StatBroadcast webservice metadata returned Cloudflare 403, and CollegePressBox automation did not have a logged-in cookie.
Impact: The original handoff discovery path could not find Utah event IDs.
Evidence: Direct archive pages exposed Final Stats XML; archive XML header scan found 13 Utah football games.
Options: Require manual CollegePressBox HTML, broaden live ID scan, or use archive XML.
Chosen path: Added archive XML discovery/backfill and generated Utah schedule/game briefs from archive XML.
Follow-up: Keep CollegePressBox saved-HTML instructions as a troubleshooting path for future in-season cases.
```

```text
Issue: Utah appears as UTAH, UTA, and UTES across StatBroadcast XML.
Impact: Bundle initially split Utah into multiple pseudo-team abbreviations.
Evidence: Utah probe bundle showed UTAH/UTA/Utes before adapter canonicalization.
Options: Rewrite source files or canonicalize at adapter boundary.
Chosen path: Canonicalized Utah name/abbreviation variants to UTAH in the StatBroadcast adapter.
Follow-up: Add future team aliases as new non-Big-Ten teams are onboarded.
```

```text
Issue: Enrichment is partial.
Impact: Brief renders a warning for PFF FMT and Utah negative-play last-3 fields.
Evidence: Enrichment artifact status is ok for both teams, but provider status includes partial PFF/negative-play reasons.
Options: Block delivery, manually source missing fields, or deliver with documented warning.
Chosen path: Deliver with warning because core PFF tempo/plays/tackles/TFL/sack fields are populated and pipeline validation passes.
Follow-up: Investigate yr-data-api PFF FMT and Utah last-3 negative-play endpoints before broad non-Big-Ten rollout.
```
