# Big Ten + Notre Dame Readiness Matrix

Season: `2025`

This matrix is the operator-facing readiness view for the currently supported production set:
- Big Ten teams
- Notre Dame

Artifact coverage is auto-derived from the current production artifacts. Enrichment, warning triage, and confidence merge current artifact state with the latest supported-set validation sweep when one is available.

Current operator warning policy is documented in [bigten-nd-warning-triage.md](./bigten-nd-warning-triage.md).

## Sources

- Bundle: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025`
- CFBStats snapshot: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025`
- Verification report: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025`

## Coverage Summary

- Bundle coverage: `18/19` present
- Snapshot coverage: `19/19` present
- Verification coverage: `0/19` present

## Current Flagged Gaps

- Bundle artifact is missing supported teams: Northwestern.
- Verification artifact is missing supported teams: Illinois, Indiana, Iowa, Maryland, Michigan, Michigan State, Minnesota, Nebraska, Northwestern, Notre Dame, Ohio State, Oregon, Penn State, Purdue, Rutgers, UCLA, USC, Washington, Wisconsin.
- Verification artifact meta reports only 2 team entries for the current published set.
- Bundle source was generated at 2026-03-17T17:38:57.629363+00:00.
- Latest supported-set sweep (no-enrichment) recorded 10/10 successful matchup runs.

## Matrix

| Team | Conf | Bundle | Snapshot | Verification | Enrichment | Warning triage | Confidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Illinois | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 8 data-quality warning(s) |
| Indiana | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Iowa | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Maryland | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 2 data-quality warning(s) |
| Michigan | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 6 data-quality warning(s) |
| Michigan State | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 2 data-quality warning(s) |
| Minnesota | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 2 data-quality warning(s) |
| Nebraska | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Northwestern | Big Ten | missing | present | missing | not checked | must-fix | attention | artifact gap |
| Notre Dame | Independent | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Ohio State | Big Ten | present | present | missing | not checked | clean | attention | artifact gap |
| Oregon | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 5 data-quality warning(s) |
| Penn State | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 5 data-quality warning(s) |
| Purdue | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Rutgers | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 1 data-quality warning(s) |
| UCLA | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| USC | Big Ten | present | present | missing | not checked | known gap | attention | artifact gap, 4 data-quality warning(s) |
| Washington | Big Ten | present | present | missing | not checked | clean | attention | artifact gap |
| Wisconsin | Big Ten | present | present | missing | not checked | clean | attention | artifact gap |

## Notes

- `present` means the team resolves from the current artifact payload.
- `missing` means the team could not be found in that artifact and should be treated as a production gap.
- `pending sweep` means the supported-set validation sweep has not been recorded for that dimension yet.
- `not checked` means the current sweep intentionally skipped enrichment validation.
