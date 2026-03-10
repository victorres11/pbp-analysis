# Published Artifact Contract

This document defines the production artifact contract for the game prep brief refresh pipeline.

## Contract Version

- `artifact_contract.version = 2`

Version 2 adds the enrichment policy contract. The main schema change is that
`artifact_contract.scratch_artifacts.enrichment.required` is now policy-driven
instead of always `false`.

The machine-readable source of truth for the contract is the pipeline summary JSON written by `scripts/refresh-game-prep-pipeline.sh`.

The local `yr-data-api/data/pbp_stats_bundle.json` handoff path is documented separately in [yr-data-api-bundle-role.md](./yr-data-api-bundle-role.md). It is not part of the official published artifact set.

## Canonical Publication Target

The canonical publication target is a season-scoped GitHub release in `victorres11/pbp-analysis`:

- release tag: `brief-artifacts-<season>`
- release title: `Brief Published Artifacts <season>`
- role: rolling current last-known-good pointer for that season

Each publishable run also creates an immutable archive release:

- release tag: `brief-artifacts-archive-<artifact_set_id>`
- release title: `Brief Published Artifacts Archive <season> <artifact_set_id>`
- role: rollback and historical inspection target for one publishable artifact set

For example, the 2025 season core set is published at:

- release page: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025`
- direct asset base: `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-2025/`

The season release is a rolling target. Each successful publishable live-refresh run updates the assets in place for that season. Operators and consumers should treat the current assets on that release as the authoritative last-known-good published set.

Archive releases do not replace the rolling release. They preserve each publishable run so operators can inspect or restore a prior artifact set if a later publishable run needs to be backed out.

## Published Artifact Set

The official published artifact set is the season-scoped core output required by downstream consumers:

- `bundle`: `published/<season>/pbp_stats_bundle_<season>.json`
- `cfbstats_snapshot`: `published/<season>/cfbstats_<season>.json`
- `cfbstats_verification_report`: `published/<season>/cfbstats_verification_<season>.json`
- `pipeline_summary`: `published/<season>/game_prep_pipeline_summary_<season>.json`

These are the only artifacts that should be treated as stable production inputs.

Specifically, the sibling local path:

- `yr-data-api/data/pbp_stats_bundle.json`

is **not** a published production artifact. It remains a local handoff path for direct brief workflows.

When published to GitHub Releases, these files are uploaded as flat release assets using the same filenames:

- `pbp_stats_bundle_<season>.json`
- `cfbstats_<season>.json`
- `cfbstats_verification_<season>.json`
- `game_prep_pipeline_summary_<season>.json`

## Scratch Outputs

The pipeline also produces run-scoped scratch outputs:

- enrichment JSON
- smoke brief output directory
- smoke brief markdown/html files

These outputs are useful for operator validation, but they are not part of the published contract and downstream consumers should not depend on their paths.

This distinction is intentional:

- enrichment is now a first-class run-scoped artifact, but not part of the published season-core set
- smoke briefs are validation outputs, not canonical data inputs

The enrichment-specific policy is documented in [enrichment-artifact-contract.md](./enrichment-artifact-contract.md).

## Publishable Run Criteria

A run is considered `publishable` only when all of the following are true:

- `mode == "live-refresh"`
- `exit_code == 0`
- `validation.verification_fail_count == 0`
- `validation.smoke_brief_passed == true`
- every required published artifact exists

Only publishable runs update the season GitHub release. Non-publishable runs still upload workflow artifacts for debugging, but they do not mutate the canonical published release.

That means failed or non-publishable refreshes leave the existing season release in place as the last-known-good artifact set.

The summary JSON records this under:

- `artifact_contract.artifact_set_id`
- `artifact_contract.publishable`
- `artifact_contract.non_publishable_reasons`
- `artifact_contract.published_set_complete`

## Consumer Contract

Downstream consumers should:

- resolve stable production inputs from the `brief-artifacts-<season>` GitHub release
- use `artifact_contract.published_artifacts` to discover the logical artifact names and expected relative paths
- ignore `artifact_contract.scratch_artifacts` for production consumption

Consumers should not follow workflow artifacts from failed or non-publishable runs. If the latest refresh is unhealthy, they should continue using the current `brief-artifacts-<season>` release until a new publishable run replaces it.

Consumers that need direct download URLs can combine the release tag with the published filenames:

- `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/pbp_stats_bundle_<season>.json`
- `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/cfbstats_<season>.json`
- `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/cfbstats_verification_<season>.json`
- `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-<season>/game_prep_pipeline_summary_<season>.json`

The one exception is the brief pipeline itself, which may require the run-scoped enrichment artifact depending on `enrichment_contract.policy`.

If a consumer needs to distinguish a scratch/local run from a publishable run, it should read:

- `mode`
- `exit_code`
- `artifact_contract.publishable`
- `artifact_contract.non_publishable_reasons`

## Freshness Policy

Freshness is evaluated from the published pipeline summary asset:

- file: `game_prep_pipeline_summary_<season>.json`
- field: `generated_at`

Default thresholds:

- `fresh`: published summary age is `<= 36h`
- `stale_warning`: published summary age is `> 36h` and `<= 72h`
- `stale_critical`: published summary age is `> 72h`

Expected operator/consumer behavior:

- `fresh`
  - consumers use the current rolling season release normally
- `stale_warning`
  - consumers still use the current rolling season release
  - operators investigate why a new publishable run has not replaced it
- `stale_critical`
  - consumers still use the current rolling season release because it remains the last-known-good set
  - operators should either restore the refresh pipeline or intentionally place the season on hold

This policy is intentionally conservative: freshness warnings do not cause consumers to switch away from the current last-known-good set automatically.

## Hold and Rollback Policy

### Hold

If operators need to freeze publication intentionally:

- set repository variable `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false`
- continue serving the current `brief-artifacts-<season>` release
- investigate or repair upstream data/logic before re-enabling the schedule

Manual dispatch remains available while the schedule is paused.

### Rollback

If a publishable run lands but operators decide the new rolling release should be backed out:

1. Pause the schedule with `BRIEF_LIVE_REFRESH_SCHEDULE_ENABLED=false`
2. Identify the desired archive release `brief-artifacts-archive-<artifact_set_id>`
3. Republish that archived asset set back onto the rolling season release `brief-artifacts-<season>`
4. Confirm the rolling release notes and pipeline summary match the restored artifact set
5. Re-enable the schedule when the pipeline is healthy again

The archive release exists specifically to make this rollback path actionable without relying on expiring workflow artifacts.

## Workflow Mapping

The GitHub Actions live-refresh workflow writes artifacts into:

- `published/<season>/...` for the published core set
- `scratch/...` for run-scoped validation outputs

For publishable runs, the workflow publishes the `published/<season>/...` contents to:

- the rolling season release `brief-artifacts-<season>`
- an immutable archive release `brief-artifacts-archive-<artifact_set_id>`

Workflow artifacts remain useful, but they are not the canonical publication target:

- `brief-live-refresh-published-artifacts` and `brief-live-refresh-scratch-artifacts` are per-run operator/debug artifacts
- GitHub release assets are the stable retrieval path for the current season-core set

## Retention and Access

- GitHub release assets should be treated as persistent until intentionally replaced by a newer publishable run for the same season.
- Archive release assets should be treated as immutable historical snapshots for rollback and inspection.
- GitHub Actions artifacts remain per-run provenance and follow the repository's workflow artifact retention policy.
- Read access to the `victorres11/pbp-analysis` repository is sufficient to retrieve the published artifact release assets.
