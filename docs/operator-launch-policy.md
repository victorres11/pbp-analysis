# Operator Launch Policy

This document defines the official v1 operator path for launching a game brief run.

## Goal

Keep the launcher narrow, repeatable, and explicit:

- one operator surface
- one GitHub workflow
- one published last-known-good release contract
- warnings visible by default

The launcher is not a sandbox and does not introduce a second pipeline path.

## Supported Scope

The operator launcher is intentionally restricted to:

- Big Ten teams
- Notre Dame

Anything outside that scope should be treated as exploratory and launched manually from GitHub only when there is a deliberate reason to do so.

## Launcher Defaults

The operator dashboard dispatches `brief-live-refresh.yml` on `main` with these defaults:

- supported teams only
- `season` explicitly selected
- `last_n=3`
- enrichment enabled
- strict verification enabled
- smoke brief format chosen explicitly

Recommended normal posture:

- leave enrichment enabled
- leave strict verification enabled
- do not treat a warning-free UI as proof by itself; inspect the published summary or latest run artifacts when the run is unusual

Strict verification for operator launches is scoped to the selected matchup teams.
Season-wide verification failures for unrelated teams are still surfaced as warnings, but they do not block the selected matchup run by themselves.

## Source Of Truth

The authoritative operator state is:

1. the latest workflow run
2. the latest run status artifact
3. the rolling release `brief-artifacts-<season>`
4. the published pipeline summary JSON on that rolling release

The dashboard is only a control plane over those sources.

## Publishable vs Reviewable

A run can complete and still require review.

Treat these separately:

- workflow success
- publishable artifact contract
- warning review posture

A healthy workflow run is not enough if:

- the artifact contract is non-publishable
- verification fail metrics are present
- warnings are present and cannot be explained from the artifacts

## Standard Operator Flow

1. Launch the run from the operator dashboard.
2. Open the latest workflow run if it is still in flight or if dispatch context matters.
3. Review the latest run status artifact and pipeline summary artifact.
4. Review published warnings and verification counts on the rolling release summary.
5. Open the smoke brief artifact when the client-facing attachment needs inspection.
6. If warnings are explainable and acceptable, proceed with delivery.
7. If warnings are unexplained, stop and investigate before delivery.

## Non-Goals

This v1 launcher does not try to:

- support custom team text input
- provide local preview mode
- create a second approval workflow inside the dashboard
- hide warnings behind a simplified pass/fail status
