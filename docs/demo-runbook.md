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

Important: the `yr-data-api/data/pbp_stats_bundle.json` write is a **local handoff convenience**, not the official published bundle contract. The published bundle contract is the season-scoped `published/<season>/pbp_stats_bundle_<season>.json` artifact layout used by the workflow-backed live-refresh path.

### GitHub Actions Live Refresh

The official operator workflow is [`.github/workflows/brief-live-refresh.yml`](../.github/workflows/brief-live-refresh.yml). It runs the same `live-refresh` path as the local script, but writes every output into workflow artifacts instead of depending on `yr-data-api`.

Requirements:

- run it from `main`
- configure a `PBP_REPO_ACCESS_TOKEN` repository secret with read access to `victorres11/pbp-parser`

Workflow behavior:

- checks out `pbp-analysis` and `pbp-parser`
- runs `scripts/refresh-game-prep-pipeline.sh` in `live-refresh` mode
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

The scratch artifact upload contains run-scoped helper outputs:

- enrichment file
- smoke brief outputs

### Published Contract

The published artifact contract is documented in [published-artifact-contract.md](./published-artifact-contract.md).
The specific role of the `yr-data-api` bundle handoff path is documented in [yr-data-api-bundle-role.md](./yr-data-api-bundle-role.md).

Short version:

- published production inputs live under `published/<season>/`
- enrichment and smoke brief outputs are `scratch` artifacts, not part of the published contract
- `artifact_contract` inside the summary JSON is the machine-readable source of truth for whether a run is publishable
- `yr-data-api/data/pbp_stats_bundle.json` remains a local handoff path, not a published artifact path

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
- gates on verification `fail` metrics by default
- renders a smoke brief without live CFBStats access

If you already have a pinned bundle artifact, add `--reuse-bundle` to skip parser-side bundle regeneration. That is the mode the GitHub workflow uses so PR validation stays self-contained inside `pbp-analysis`.

### Summary JSON

The summary artifact is the machine-readable run contract for CI and operators. It includes:

- mode, season, teams, and git refs
- artifact paths for bundle, snapshot, verification report, enrichment, and smoke brief outputs
- per-stage status with `duration_seconds`, `started_at`, `finished_at`, `heartbeat_count`, and `expected_duration_seconds`
- smoke/test pass flags
- verification fail/warning counts
- collected `[warn]` lines from the run

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
