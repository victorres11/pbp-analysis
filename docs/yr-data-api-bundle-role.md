# `yr-data-api` Bundle Role

This note defines the role of `yr-data-api/data/pbp_stats_bundle.json` in the current brief pipeline.

## Decision

`yr-data-api/data/pbp_stats_bundle.json` is **not** part of the official published artifact set.

It is a **local handoff / convenience file** used to keep the direct brief workflow pointed at a refreshed parser bundle without requiring operators to pass `--bundle-path` on every local run.

## What Is Officially Published

The official published bundle artifact is the season-scoped path produced by the refresh pipeline:

- `published/<season>/pbp_stats_bundle_<season>.json`

This is the bundle path that should be treated as the production artifact contract alongside:

- `published/<season>/cfbstats_<season>.json`
- `published/<season>/cfbstats_verification_<season>.json`
- `published/<season>/game_prep_pipeline_summary_<season>.json`

## Why `yr-data-api` Still Exists In The Local Flow

`pbp-analysis` still defaults the XML bundle input to:

- `../yr-data-api/data/pbp_stats_bundle.json`

That default remains useful for local operator workflows because:

- direct brief commands can run without extra bundle-path flags
- a local live-refresh can keep the sibling handoff file current
- it preserves a simple developer experience while the published artifact path remains separate

## Refresh Expectations

### Local live-refresh

When `scripts/refresh-game-prep-pipeline.sh` runs in `live-refresh` mode **without** an explicit `--bundle-path`, and a sibling `yr-data-api` checkout exists, the bundle is written to:

- `yr-data-api/data/pbp_stats_bundle.json`

That write should be understood as:

- keeping the local default brief input warm
- not publishing a production artifact
- not changing the published artifact contract

### GitHub Actions live-refresh

The workflow-backed live-refresh path does **not** publish into `yr-data-api`.

It writes the season bundle to the workflow artifact layout under:

- `published/<season>/pbp_stats_bundle_<season>.json`

### Offline validate

Offline validation should use either:

- a pinned fixture bundle, or
- an explicitly supplied local bundle path

It should not rely on `yr-data-api` being current unless the operator intentionally wants that local handoff file.

## Operator Guidance

Use `yr-data-api/data/pbp_stats_bundle.json` when:

- running briefs locally via the default path
- keeping a local handoff copy up to date after a parser refresh

Do **not** treat it as:

- the canonical published bundle location
- the source of truth for artifact publication status
- evidence that a run is publishable

For publication and downstream contract reasoning, use the season-scoped `published/<season>/...` artifact set and the pipeline summary JSON.
