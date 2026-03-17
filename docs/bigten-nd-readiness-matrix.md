# Big Ten + Notre Dame Readiness Matrix

Season: `2025`

This matrix is the operator-facing readiness view for the currently supported production set:
- Big Ten teams
- Notre Dame

Artifact coverage is auto-derived from the current production artifacts. Enrichment, warning triage, and confidence are intentionally left as `pending sweep` until the supported-set validation pass is completed.

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

## Matrix

| Team | Conf | Bundle | Snapshot | Verification | Enrichment | Warning triage | Confidence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Illinois | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Indiana | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Iowa | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Maryland | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Michigan | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Michigan State | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Minnesota | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Nebraska | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Northwestern | Big Ten | missing | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Notre Dame | Independent | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Ohio State | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Oregon | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Penn State | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Purdue | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Rutgers | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| UCLA | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| USC | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Washington | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |
| Wisconsin | Big Ten | present | present | missing | pending sweep | pending sweep | pending sweep | artifact gap |

## Notes

- `present` means the team resolves from the current artifact payload.
- `missing` means the team could not be found in that artifact and should be treated as a production gap.
- `pending sweep` means the validation and operator triage work has not been completed for that dimension yet.
