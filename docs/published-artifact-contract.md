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

For example, the 2025 season core set is published at:

- release page: `https://github.com/victorres11/pbp-analysis/releases/tag/brief-artifacts-2025`
- direct asset base: `https://github.com/victorres11/pbp-analysis/releases/download/brief-artifacts-2025/`

This release is a rolling target. Each successful publishable live-refresh run updates the assets in place for that season. Operators should treat the current assets on that release as the authoritative published set.

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

## Workflow Mapping

The GitHub Actions live-refresh workflow writes artifacts into:

- `published/<season>/...` for the published core set
- `scratch/...` for run-scoped validation outputs

For publishable runs, the workflow then publishes the `published/<season>/...` contents to the season GitHub release.

Workflow artifacts remain useful, but they are not the canonical publication target:

- `brief-live-refresh-published-artifacts` and `brief-live-refresh-scratch-artifacts` are per-run operator/debug artifacts
- GitHub release assets are the stable retrieval path for the current season-core set

## Retention and Access

- GitHub release assets should be treated as persistent until intentionally replaced by a newer publishable run for the same season.
- GitHub Actions artifacts remain per-run provenance and follow the repository's workflow artifact retention policy.
- Read access to the `victorres11/pbp-analysis` repository is sufficient to retrieve the published artifact release assets.
