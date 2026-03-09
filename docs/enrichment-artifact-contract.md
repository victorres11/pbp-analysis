# Enrichment Artifact Contract

This document defines how enrichment is generated, stored, consumed, and disabled in the game prep brief pipeline.

## Scope

Enrichment covers the non-parser supplemental values used by the brief, including:

- blitz rate snapshots
- negative-play API values
- PFF-derived pace / sack / tackle / TFL summary fields

It does not replace the canonical parser-owned bundle, CFBStats snapshot, or verification report.

## Artifact Shape

The enrichment artifact is a JSON object keyed by team slug:

```json
{
  "washington": {
    "_status": "ok",
    "_source": "yr-data-api",
    "_fetched_at": "2026-03-09T00:00:00+00:00",
    "blitz_pct": "31.2%",
    "negative_plays_pg_api": 6.3,
    "pff_tfl_pg": 7.1
  }
}
```

Per-team entries may contain any of the enrichment keys currently consumed by the brief plus metadata:

- `_status`
  - `ok`: at least one enrichment field has signal
  - `unavailable`: the artifact exists for the team but the fetched values were empty / unavailable
- `_source`
  - `yr-data-api` for refreshed artifacts
  - `artifact` for normalized legacy artifacts that did not carry explicit metadata
- `_fetched_at`
  - UTC timestamp from the refresh step when available

## Runtime Policy

Default brief behavior is:

- enrichment is enabled
- enrichment must come from an artifact file
- the brief does not fetch enrichment live at render time

The only supported live enrichment path is explicit refresh:

- `--refresh-enrichment`

The only supported way to bypass enrichment is explicit opt-out:

- `--no-enrichment`

There is no runtime equivalent of “artifact missing, go fetch live anyway.”

## Mode Behavior

### Local / Direct Brief CLI

- default: require a usable enrichment artifact for both teams
- `--refresh-enrichment`: fetch, merge, validate, and write the artifact before rendering
- `--no-enrichment`: skip enrichment entirely

If the artifact is missing or does not contain both teams, the brief exits with a clear message telling the operator to use `--refresh-enrichment` or `--no-enrichment`.

### Pipeline `live-refresh`

- enrichment is refreshed by default
- the refreshed artifact is validated before the smoke brief runs
- `--no-enrichment` disables enrichment, but that run is treated as non-publishable

### Pipeline `offline-validate`

- enrichment is artifact-only
- if enrichment is enabled, the artifact must already exist and contain both teams
- `--no-enrichment` disables enrichment explicitly for deterministic CI/offline validation

## Publishability

Enrichment remains a run-scoped scratch artifact, not part of the published season-core artifact set.

However, enrichment is still part of the run contract:

- a live-refresh run with enrichment disabled is not publishable
- a live-refresh run with an invalid or missing enrichment artifact is not publishable

The pipeline summary records this under:

- `enrichment_contract`
- `validation.enrichment_artifact_validated`
- `artifact_contract.scratch_artifacts.enrichment.required`
- `artifact_contract.non_publishable_reasons`

`_status: "unavailable"` is still considered a valid artifact entry. The
artifact contract requires explicit team entries for both matchup teams; it
does not currently require every enrichment source to have signal. When one or
more required teams are present but marked `unavailable`, the summary reports:

- `enrichment_contract.artifact_status = "validated_with_unavailable_teams"`
- `enrichment_contract.team_statuses`

## Summary Contract

The pipeline summary JSON exposes enrichment state through:

- `enrichment_contract.policy`
  - `required` or `disabled`
- `enrichment_contract.required_for_publishable_run`
- `enrichment_contract.runtime_live_fetch_allowed`
  - always `false`
- `enrichment_contract.artifact_status`
  - `validated`, `validated_with_unavailable_teams`, `disabled`, `invalid`, `interrupted`, or `missing`
- `enrichment_contract.team_statuses`
- `enrichment_contract.live_refresh_behavior`
- `enrichment_contract.offline_validate_behavior`

This is the machine-readable source of truth for how enrichment was handled in a given run.
