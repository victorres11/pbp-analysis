# Demo Runbook

This runbook generates a demo-ready game brief package and a quick review checklist.

## Command

```bash
python3 scripts/game_prep_brief/demo_runner.py --matchup oregon-usc-2025
```

Optional:

```bash
python3 scripts/game_prep_brief/demo_runner.py \
  --matchup georgia-asu-2025 \
  --last-n 3 \
  --output-dir outputs/demo_briefs
```

## Pipeline

Use the pipeline helper when you want one canonical refresh or validation path.

### Live Refresh

This is the operator/manual path. It rebuilds the canonical parser-owned artifacts and refreshes enrichment before rendering a smoke brief.

```bash
./scripts/refresh-game-prep-pipeline.sh Washington "Ohio State" \
  --season 2025 \
  --mode live-refresh \
  --summary-json /tmp/game_prep_pipeline_summary.json
```

Default live-refresh behavior:

- regenerates `yr-data-api/data/pbp_stats_bundle.json`
- regenerates `pbp-parser/data/cfbstats_snapshots/cfbstats_<season>.json`
- regenerates `pbp-parser/data/cfbstats_reports/cfbstats_verification_<season>.json`
- refreshes the enrichment file
- renders a smoke brief
- writes a machine-readable summary JSON when `--summary-json` is provided
- expects the CFBStats stages to be network-bound and potentially slower than offline validation
- treats enrichment as required for a publishable run unless you explicitly pass `--no-enrichment`

Important: the `yr-data-api/data/pbp_stats_bundle.json` write is a **local handoff convenience**, not the official published bundle contract. The published bundle contract is the season-scoped `published/<season>/pbp_stats_bundle_<season>.json` artifact layout used by the workflow-backed live-refresh path.

### GitHub Actions Live Refresh

The official operator workflow is [`.github/workflows/brief-live-refresh.yml`](../.github/workflows/brief-live-refresh.yml). It runs the same `live-refresh` path as the local script, but publishes the season-core artifact set to a GitHub release instead of depending on `yr-data-api`.

Requirements:

- run it from `main`
- configure a `PBP_REPO_ACCESS_TOKEN` repository secret with read access to `victorres11/pbp-parser`

Workflow behavior:

- checks out `pbp-analysis` and `pbp-parser`
- runs `scripts/refresh-game-prep-pipeline.sh` in `live-refresh` mode
- publishes successful season-core outputs to the rolling GitHub release `brief-artifacts-<season>`
- archives the same publishable set to `brief-artifacts-archive-<artifact_set_id>`
- runs automatically every day at `13:17 UTC` in addition to manual dispatch
- uploads:
  - `brief-live-refresh-summary`
  - `brief-live-refresh-smoke-brief`
  - `brief-live-refresh-published-artifacts`
  - `brief-live-refresh-scratch-artifacts`

The published artifact upload contains the season-scoped core set:

- bundle
- CFBStats snapshot
- verification report
- pipeline summary JSON

This is the official published contract. It is distinct from the local `yr-data-api/data/pbp_stats_bundle.json` handoff path.

Canonical retrieval path for the current season set:

- release page: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-<season>`
- direct downloads:
  - `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/pbp_stats_bundle_<season>.json`
  - `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/cfbstats_<season>.json`
  - `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/cfbstats_verification_<season>.json`
  - `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/game_prep_pipeline_summary_<season>.json`

Archived rollback path for one publishable run:

- release page: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-archive-<artifact_set_id>`

The scratch artifact upload contains run-scoped helper outputs:

- enrichment file
- smoke brief outputs

By default the workflow refreshes and requires enrichment. If an operator intentionally disables enrichment, the run still completes, but the summary JSON marks it as non-publishable and the season GitHub release is not updated.

The rolling season release remains the current last-known-good set when a run fails or is non-publishable. Scheduled failures do not advance consumers to a new artifact set automatically.

### Scheduled Defaults

The scheduled run uses repository variables when present and falls back to these defaults:

- `BRIEF_LIVE_REFRESH_TEAM1` or `Washington`
- `BRIEF_LIVE_REFRESH_TEAM2` or `Ohio State`
- `BRIEF_LIVE_REFRESH_SEASON` or `2025`
- `BRIEF_LIVE_REFRESH_LAST_N` or `3`
- `BRIEF_LIVE_REFRESH_BRIEF_FORMAT` or `markdown`
- `BRIEF_LIVE_REFRESH_RUN_TESTS` or `false`
- `BRIEF_LIVE_REFRESH_STRICT_VERIFICATION` or `true`
- `BRIEF_LIVE_REFRESH_INCLUDE_ENRICHMENT` or `true`

The workflow treats `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false` as a pause switch for the scheduled trigger. Manual dispatch remains available even when the schedule is paused.

### Scheduled Failure Notifications

Scheduled runs notify operators only when a run is unhealthy:

- workflow failure
- non-publishable run
- verification fail metrics
- missing required published artifacts
- missing pipeline summary JSON

Notification channel:

- the workflow maintains a GitHub issue thread titled `Brief Live Refresh Alerts`
- if the issue does not exist, the workflow creates it with labels `overnight` and `game-brief`
- each unhealthy scheduled run adds a comment with:
  - run URL
  - season and matchup
  - publishable status
  - verification counts
  - interrupted / slow stages
  - non-publishable reasons

This keeps scheduled operator alerts inside the repo without requiring an external webhook service.

To pause scheduled operations when needed:

- set repository variable `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false`, or
- disable the workflow in the Actions UI

### Published Contract

The published artifact contract is documented in [published-artifact-contract.md](./published-artifact-contract.md).
The specific role of the `yr-data-api` bundle handoff path is documented in [yr-data-api-bundle-role.md](./yr-data-api-bundle-role.md).

Short version:

- published production inputs are retrieved from the rolling release `brief-artifacts-<season>`
- rolling release `brief-artifacts-<season>` is the current last-known-good published set
- archive releases `brief-artifacts-archive-<artifact_set_id>` preserve each publishable run for rollback
- enrichment is a first-class run-scoped artifact, but not part of the published season-core set
- smoke brief outputs remain scratch validation outputs
- `artifact_contract` inside the summary JSON is the machine-readable source of truth for whether a run is publishable
- `yr-data-api/data/pbp_stats_bundle.json` remains a local handoff path, not a published artifact path
- `enrichment_contract` inside the summary JSON is the machine-readable source of truth for enrichment policy and status

Direct brief runs follow the same contract by default:

- `python -m scripts.game_prep_brief ...` resolves bundle, snapshot, and verification from `brief-artifacts-<season>` unless you explicitly override them
- local overrides remain available through `--xml-bundle`, `--cfbstats-snapshot`, `--cfbstats-verification-report`, and their matching `GAME_PREP_*` env vars
- local direct runs against the private repo should provide GitHub auth via `GAME_PREP_PUBLISHED_ARTIFACT_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, or an authenticated `gh` CLI session

The enrichment-specific contract is documented in [enrichment-artifact-contract.md](./enrichment-artifact-contract.md).

### Freshness and Hold Policy

Freshness is determined from the published pipeline summary asset:

- `fresh`: `generated_at` age `<= 36h`
- `stale_warning`: `> 36h` and `<= 72h`
- `stale_critical`: `> 72h`

Consumer policy:

- always keep using the current `brief-artifacts-<season>` release unless operators explicitly roll back or republish
- do not follow failed or non-publishable workflow artifacts

Operator policy:

- `stale_warning`: investigate the refresh pipeline, but keep serving the current season release
- `stale_critical`: either restore the pipeline quickly or intentionally place the season on hold
- hold procedure: set `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false`

Pause command example:

```bash
gh variable set BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED \
  --repo victorres11/pbp-analysis \
  --body false
```

### Rollback Procedure

If the rolling release needs to be backed out after a publishable run:

1. Pause the schedule with `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false`
2. Identify the desired archive release `brief-artifacts-archive-<artifact_set_id>`
3. Restore that archive release's assets onto the rolling release `brief-artifacts-<season>`
4. Confirm the rolling release notes and `game_prep_pipeline_summary_<season>.json` now match the restored archive set
5. Re-enable the schedule when the pipeline is healthy again

The archive release is the supported rollback source. Workflow artifacts are still useful for debugging, but they are not the intended rollback mechanism.

CLI rollback example:

```bash
ARCHIVE_TAG="brief-artifacts-archive-<artifact_set_id>"
ROLLING_TAG="brief-artifacts-<season>"
TMP_DIR=$(mktemp -d)

gh release download "${ARCHIVE_TAG}" \
  --repo victorres11/pbp-analysis \
  --dir "${TMP_DIR}"

gh release upload "${ROLLING_TAG}" \
  "${TMP_DIR}"/* \
  --repo victorres11/pbp-analysis \
  --clobber
```

After uploading, update the rolling release notes so they reflect the restored archive release metadata before re-enabling the schedule.

### Offline Validate

This is the deterministic CI/check path. It reuses pinned artifacts, skips live CFBStats refreshes, and can skip enrichment entirely.

```bash
./scripts/refresh-game-prep-pipeline.sh Washington "Ohio State" \
  --season 2025 \
  --mode offline-validate \
  --bundle-path /tmp/pbp_stats_bundle.json \
  --reuse-bundle \
  --cfbstats-snapshot tests/fixtures/pipeline/cfbstats_2025_snapshot.json \
  --cfbstats-verification-report tests/fixtures/pipeline/cfbstats_verification_2025_report.json \
  --no-enrichment \
  --run-tests \
  --summary-json /tmp/game_prep_pipeline_summary.json
```

Default offline-validate behavior:

- can regenerate a local bundle, or reuse a pinned bundle with `--reuse-bundle`
- validates that the supplied snapshot and verification artifacts have the expected schema
- requires an existing enrichment artifact unless `--no-enrichment` is set
- gates on verification `fail` metrics by default
- renders a smoke brief without live CFBStats access

If you already have a pinned bundle artifact, add `--reuse-bundle` to skip parser-side bundle regeneration. That is the mode the GitHub workflow uses so PR validation stays self-contained inside `pbp-analysis`.

### Summary JSON

The summary artifact is the machine-readable run contract for CI and operators. It includes:

- mode, season, teams, and git refs
- artifact paths for bundle, snapshot, verification report, enrichment, and smoke brief outputs
- `enrichment_contract` policy/status for the run
- per-stage status with `duration_seconds`, `started_at`, `finished_at`, `heartbeat_count`, and `expected_duration_seconds`
- smoke/test pass flags
- verification fail/warning counts
- collected `[warn]` lines from the run

### Enrichment Policy

The brief and pipeline now follow one deterministic enrichment policy:

- default behavior requires an enrichment artifact
- `--refresh-enrichment` is the only live enrichment fetch path
- `--no-enrichment` is the only opt-out path
- missing enrichment never triggers an implicit runtime fetch

That means:

- local brief generation without an enrichment file should fail fast with a clear message
- local brief generation with `--refresh-enrichment` should write/update the file first
- offline validation can remain deterministic by passing `--no-enrichment`

### Live Stage Observability

Long-running stages now emit periodic heartbeat lines while they are still running:

```text
[heartbeat] cfbstats_snapshot still running (elapsed=60s, expected<=1200s)
```

The pipeline also assigns expected-duration budgets to each stage. Current defaults:

- `parser_tests`: 1200s
- `analysis_tests`: 900s
- `bundle_generation`: 900s
- `cfbstats_snapshot`: 1200s
- `cfbstats_verification_report`: 900s
- `enrichment_refresh`: 600s
- `smoke_brief`: 300s

These budgets are observability thresholds, not hard kills. If a stage runs long, the pipeline logs:

```text
[warn] cfbstats_snapshot exceeded expected duration budget (1200s); waiting for completion
```

Interpretation:

- heartbeat lines mean the stage is still alive, not stalled silently
- an exceeded-duration warning means upstream latency or markup drift is more likely than a total hang
- `run_state.interrupted` in the summary JSON means the run exited while a stage was still active
- `observability.slow_stages` lists stages that exceeded their expected duration budget

The GitHub Actions live-refresh workflow still enforces the outer hard cap with `timeout-minutes: 90`. If a run is canceled or terminated mid-stage, the pipeline summary should record that stage as `interrupted` when cleanup runs.

Optional overrides:

- `PBP_PIPELINE_STAGE_HEARTBEAT_SECONDS=<seconds>` changes the heartbeat cadence
- `PBP_PIPELINE_STAGE_BUDGET_OVERRIDES=cfbstats_snapshot=1800,cfbstats_verification_report=1200` overrides expected-duration budgets for specific stages

## Outputs

The runner writes:

- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.md`
- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.html`
- `outputs/demo_briefs/DEMO_SUMMARY.md`

## Source Policy

- StatBroadcast-derived data is the preferred **input data source**.
- Legacy PDF **input parsing** is retained for fallback/debug only and should remain disabled by default.
- PDF **output/export of generated briefs** is still supported and is not being removed.
