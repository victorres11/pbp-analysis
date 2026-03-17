# Big Ten + Notre Dame Warning Triage

Season: `2025`

This document translates the supported-set sweep output into operator-facing severity classes for the current production scope:

- Big Ten teams
- Notre Dame

Source inputs:

- validation sweep: [bigten-nd-validation-sweep.md](./bigten-nd-validation-sweep.md)
- readiness matrix: [bigten-nd-readiness-matrix.md](./bigten-nd-readiness-matrix.md)

## Triage Summary

- `must-fix`: blocks client-facing confidence for the affected team or release
- `known gap`: acceptable to keep visible to operators; does not block supported-set brief delivery on its own
- `noise`: should be suppressed or reworded because it does not represent an operator action item

## Must-Fix

### Northwestern missing team payload in published bundle

- Current warning: `Northwestern: missing team payload in XML bundle`
- Why it matters: the brief renders with a placeholder Northwestern side instead of a complete supported-team payload
- Follow-up: [#229](https://github.com/victorres11/pbp-analysis/issues/229)

### Published verification artifact missing supported-set coverage

- Current readiness finding: published verification coverage is `0/19` and artifact metadata reports only `2` team entries
- Why it matters: this is a release-contract gap across the supported production set, even when direct brief rendering succeeds
- Follow-up: [#230](https://github.com/victorres11/pbp-analysis/issues/230)

## Acceptable Known Gaps

These should remain visible to operators for now, but they are not treated as release blockers by themselves.

### Turnover reconciliation mismatch

- Example: `Turnover reconciliation mismatch for Illinois ...`
- Meaning: season-level bundle-derived turnover totals do not exactly match XML/source reconciliation rows
- Operator action: note it, but do not block a supported-set brief solely on this warning

### Turnover game mismatches

- Example: `Turnover game mismatches for Indiana ...`
- Meaning: one or more game-level turnover/POT details differ from XML/source rows
- Operator action: treat as a known data-quality warning unless it is tied to a must-fix artifact gap

### Fourth-down parity delta

- Example: `Illinois: 4th-down parity delta +5.4 pts ...`
- Meaning: parser-derived fourth-down rate differs modestly from CFBStats/source parity
- Operator action: keep visible, but do not block client-facing use for the supported set on this warning alone

### Derived two-point totals differ from XML

- Example: `Oregon: derived two-point totals differ from XML ...`
- Meaning: parser-derived two-point totals do not fully match the XML source totals
- Operator action: keep visible to operators as a known gap

## Noise To Suppress Or Reword

### Duplicate XML parity summary lines in sweep inventory

- The sweep inventory can show both direct warning lines and split `XML parity` summary lines for the same underlying warning family
- Operator action: no extra action required; this is duplicate presentation, not new severity

### Enrichment-partial banner when the sweep intentionally skips enrichment

- In `--no-enrichment` mode, the rendered brief can include enrichment-partial messaging even though the sweep is intentionally validating the core artifact-backed path only
- Operator action: treat as expected for the no-enrichment sweep baseline, not as a supported-set blocker

## Operator Guidance

- `must-fix`: do not treat the affected team or published release as client-ready until the linked follow-up issue is resolved
- `known gap`: acceptable to proceed for Big Ten + Notre Dame client delivery while leaving the warning visible to operators
- `noise`: should not affect readiness decisions; clean it up in reporting when convenient
