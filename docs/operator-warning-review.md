# Operator Warning Review

This document defines how operators should read and investigate warnings from the brief pipeline.

## Principle

Warnings are part of the review surface, not noise to hide.

Some warnings are acceptable special cases. Some are real defects. The operator job is to be able to explain the difference from the available evidence.

For operator launches, strict verification blocks on the selected matchup teams.
If the season-wide verification report still contains failures for unrelated teams, those should appear as warnings and stay reviewable.

## Primary Evidence Sources

Review warnings in this order:

1. latest run status artifact
2. latest run pipeline summary artifact
3. rolling release pipeline summary JSON
4. rolling release verification report
5. smoke brief artifact

If a warning cannot be explained from those sources, treat it as investigate-first.

## Common Warning Families

### Turnover reconciliation

Examples:

- turnover reconciliation mismatch
- turnover game mismatches

Interpretation:

- these indicate disagreement between derived turnover accounting and the comparison source
- some isolated mismatches can be explainable from source quirks or game-level parsing edge cases
- repeated or large mismatches across the same team are a real review target

Evidence to inspect:

- pipeline summary warnings
- brief turnover section
- parser-side turnover diagnostics if deeper debugging is needed

### Parity deltas

Examples:

- 4th-down parity delta
- XML parity gaps
- metric mismatch language tied to CFBStats verification

Interpretation:

- some parity gaps are expected and already modeled as warnings or special cases
- a parity warning is acceptable only when the explanation is stable and repeatable
- parity warnings that appear sporadically across matchups without a known reason are not acceptable

Evidence to inspect:

- verification report
- status artifact publication section
- team section alerts inside the smoke brief

### Enrichment gaps

Examples:

- enrichment unavailable
- partial PFF/API snapshot
- unavailable situational or trenches fields

Interpretation:

- enrichment can be partially unavailable without meaning the base brief is wrong
- operators should confirm the missing data is clearly surfaced as unavailable rather than silently substituted

Evidence to inspect:

- enrichment artifact status in the summary
- warning text in the brief header and affected sections
- enrichment contract document

### Runtime or observability warnings

Examples:

- stage exceeded expected duration budget
- interrupted stage

Interpretation:

- these are operational warnings first
- they do not automatically mean the brief is wrong, but they do mean the run deserves a closer look

Evidence to inspect:

- status artifact runtime section
- workflow run page
- whether the rolling release advanced or stayed on the prior artifact set

## Acceptable vs Not Yet Acceptable

Acceptable:

- warning is visible
- evidence source explains it
- the same condition is handled the same way across matchups
- the client-facing brief still reads clearly and does not hide missing data

Not yet acceptable:

- warning has no clear explanation
- operator judgment depends on memory instead of artifact evidence
- the same warning flips between acceptable and blocking with no stated rule
- the brief appears clean while underlying artifacts disagree materially

## Delivery Standard

Before sending a brief as an email attachment, the operator should be able to say:

- what warnings were present
- whether they were expected or not
- which artifact justified that conclusion

If that answer is not available, the run is not in reliable process mode yet.
