# Published Artifact Contract

This document defines the production artifact contract for the game prep brief refresh pipeline.

## Contract Version

- `artifact_contract.version = 2`

Version 2 adds the enrichment policy contract. The main schema change is that
`artifact_contract.scratch_artifacts.enrichment.required` is now policy-driven
instead of always `false`.

The machine-readable source of truth for the contract is the pipeline summary JSON written by `scripts/refresh-game-prep-pipeline.sh`.

## Published Artifact Set

The official published artifact set is the season-scoped core output required by downstream consumers:

- `bundle`: `published/<season>/pbp_stats_bundle_<season>.json`
- `cfbstats_snapshot`: `published/<season>/cfbstats_<season>.json`
- `cfbstats_verification_report`: `published/<season>/cfbstats_verification_<season>.json`
- `pipeline_summary`: `published/<season>/game_prep_pipeline_summary_<season>.json`

These are the only artifacts that should be treated as stable production inputs.

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

The summary JSON records this under:

- `artifact_contract.artifact_set_id`
- `artifact_contract.publishable`
- `artifact_contract.non_publishable_reasons`
- `artifact_contract.published_set_complete`

## Consumer Contract

Downstream consumers should:

- resolve stable production inputs from the `published/<season>/` set
- use `artifact_contract.published_artifacts` to discover the logical artifact names and expected relative paths
- ignore `artifact_contract.scratch_artifacts` for production consumption

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

This layout exists inside the uploaded workflow artifacts even before a persistent publishing service is added.
