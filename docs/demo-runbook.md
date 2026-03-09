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

### Offline Validate

This is the deterministic CI/check path. It rebuilds the bundle locally, reuses pinned snapshot/report artifacts, skips live CFBStats refreshes, and can skip enrichment entirely.

```bash
./scripts/refresh-game-prep-pipeline.sh Washington "Ohio State" \
  --season 2025 \
  --mode offline-validate \
  --bundle-path /tmp/pbp_stats_bundle.json \
  --cfbstats-snapshot tests/fixtures/pipeline/cfbstats_2025_snapshot.json \
  --cfbstats-verification-report tests/fixtures/pipeline/cfbstats_verification_2025_report.json \
  --no-enrichment \
  --run-tests \
  --summary-json /tmp/game_prep_pipeline_summary.json
```

Default offline-validate behavior:

- regenerates a local bundle instead of touching `yr-data-api`
- validates that the supplied snapshot and verification artifacts have the expected schema
- gates on verification `fail` metrics by default
- renders a smoke brief without live CFBStats access

### Summary JSON

The summary artifact is the machine-readable run contract for CI and operators. It includes:

- mode, season, teams, and git refs
- artifact paths for bundle, snapshot, verification report, enrichment, and smoke brief outputs
- per-stage status with `duration_seconds`
- smoke/test pass flags
- verification fail/warning counts
- collected `[warn]` lines from the run

## Outputs

The runner writes:

- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.md`
- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.html`
- `outputs/demo_briefs/DEMO_SUMMARY.md`

## Source Policy

- StatBroadcast-derived data is the preferred **input data source**.
- Legacy PDF **input parsing** is retained for fallback/debug only and should remain disabled by default.
- PDF **output/export of generated briefs** is still supported and is not being removed.
