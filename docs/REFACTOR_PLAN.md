# Game Prep Brief Refactor Plan

## Problem Statement

The bundle currently stores **both** StatBroadcast rollup aggregates **and** raw play-by-play data, with rollups configured as the source of truth (`metrics_profile="statbroadcast_source_of_truth"`). When rollups are missing or wrong — which happens frequently — the brief falls back to re-deriving metrics from play descriptions at render time. This creates:

- **Conflicting data paths**: OSU fumble recoveries — per-game rollup rows sum to 3, season rollup says 6, CFBStats says 7. Three paths, three answers.
- **A 3500-line `loaders.py`** that mixes data loading, live scraping, reconciliation, and fallback derivation in a single file, all at runtime.
- **Non-deterministic brief generation**: Same bundle can produce different output depending on whether CFBStats is reachable, which Python version is running (upstream verifier needs 3.10+), and whether enrichment is cached.

## Core Insight

The play-by-play data is the right foundation — it's what enables granular queries like "turnovers in Q2" or "penalties in the last 3 games." StatBroadcast rollups are redundant at best and misleading at worst. CFBStats is the validation target, not a data source.

**Target architecture:**
```
StatBroadcast PBP → parse plays → compute ALL metrics → bundle.json
CFBStats scrape → validation_report.json (separate step)
bundle.json + validation_report.json → brief (pure render, no live fetching)
```

## Current State (What Exists Today)

### Bundle Generation (`pbp-parser`)
- `stats_bundle.py` (line 1120): `penalties_mode = "source_summary"` means rollup tables are primary
- `source_team_stats` (lines 725-890): Stores BOTH rollup values AND `play_derived_*` audit columns side by side
- Penalty overlay (lines 1143-1202): Adds play-derived holding/PI on top of rollup summary
- Turnover/explosive/red-zone stats: Already computed from plays

### Brief Rendering (`pbp-analysis`)
- `loaders.py` has 32+ functions across 4 categories, all invoked at brief generation time:
  - **A. Data Loading** (5 functions): `get_team_pbp`, `_extract_pbp_stats`, `compute_last_n_stats`, etc.
  - **B. Live Scraping** (11 functions): `_fetch_live_rankings`, `_fetch_cfbstats_rows`, `_fetch_live_turnover_split`, yr-data-api enrichment, etc.
  - **C. Reconciliation** (6 functions): `_turnover_reconciliation`, `_verify_cfbstats_metrics`, `_collect_parity_gaps`, etc.
  - **D. Fallback Derivation** (10+ functions): `_derive_turnover_drive_stats`, `_turnover_recovery_side`, `_derive_cfbstats_reference_metrics`, play-text regex parsing, etc.

### Known Data Conflicts
| Metric | Rollup | Play-Derived | CFBStats | Notes |
|--------|--------|-------------|----------|-------|
| OSU fumbles recovered | 6 (season) / 3 (per-game sum) | — | 7 | Internal rollup inconsistency |
| WAS fumbles lost | 5 | 5 | 6 | Missing from both rollup AND plays |
| Penalties (proc/live) | 0 / null | Correct via play-tree | — | Rollup fields empty, play-tree works |
| Holding | null | Correct via play-tree | — | Same pattern as proc/live |
| POT | Inconsistent with own play-tree | Correct via play-tree | — | Already switched to play-derived |

## Refactor Phases

### Phase 1: Flip Bundle to Play-Derived Primary

**Where:** `pbp-parser/src/pbp_parser/stats_bundle.py`

**What:**
- Change `penalties_mode` from `"source_summary"` to `"play_derived"` (or equivalent)
- For `source_team_stats`: use `play_derived_*` columns as the primary values, keep rollup columns as `rollup_*` for audit only
- For turnovers: the bundle already computes these from plays — verify the play-tree derivation is complete and drop the rollup `turnovers` dict as authoritative
- For penalties: compute procedural/live-ball/holding/PI entirely from `penalty_details` (per-play data), not `penalty_summary` (rollup)

**Validation:** After regenerating the bundle, compare play-derived totals against CFBStats. The delta should be small and explainable. Document any known gaps (like WAS's missing fumble) as `known_gaps.json`.

**Key files:**
- `pbp-parser/src/pbp_parser/stats_bundle.py` — lines 577-587 (penalties mode), 725-890 (source_team_stats)
- `pbp-parser/src/pbp_parser/statbroadcast/adapter.py` — lines 284-340 (penalty detail parsing)
- `pbp-parser/scripts/generate_statbroadcast_bundle.py` — metrics profile flag

### Phase 2: Snapshot CFBStats Separately

**Where:** New script `pbp-parser/scripts/snapshot_cfbstats.py` (or `pbp-analysis/scripts/snapshot_cfbstats.py`)

**What:**
- Extract CFBStats scraping functions from `loaders.py` into a standalone script
- Functions to extract (~200 lines): `_fetch_cfbstats_rows`, `_parse_cfbstats_table`, `_fetch_live_rankings_fallback`, `_fetch_live_turnover_split`, `_parse_turnover_split_all_games`
- Script produces `cfbstats_{season}.json` with all team rankings, turnover splits, and any other CFBStats data
- During the season: run weekly (cron or manual) to refresh
- After season: run once, never changes

**Output format:**
```json
{
  "season": 2025,
  "scraped_at": "2025-10-15T12:00:00Z",
  "teams": {
    "ohio-state": {
      "rankings": { "scoring_offense": {"value": 38.2, "rank": 5}, ... },
      "turnover_split": { "fumbles_gained": 7, "fumbles_lost": 3, "margin": 4, ... }
    }
  }
}
```

### Phase 3: Separate Validation Script

**Where:** New script `pbp-analysis/scripts/validate_bundle.py` (or in `pbp-parser`)

**What:**
- Takes `pbp_stats_bundle.json` + `cfbstats_{season}.json` as inputs
- Produces `validation_report.json` with per-team, per-metric comparison
- Extract from `loaders.py` (~300 lines): `_verify_cfbstats_metrics`, `_derive_cfbstats_reference_metrics`, `_turnover_reconciliation`, `_turnover_game_reconciliation`, `_collect_parity_gaps`
- Reports deltas, flags mismatches, identifies known gaps
- Runs independently of brief generation — once per bundle update

**Output format:**
```json
{
  "ohio-state": {
    "metrics": [
      {"key": "turnover_margin", "bundle": 3, "cfbstats": 4, "delta": -1, "status": "mismatch"}
    ],
    "summary": {"match": 12, "mismatch": 2, "known_gap": 1}
  }
}
```

### Phase 4: Simplify loaders.py

**Where:** `pbp-analysis/scripts/game_prep_brief/loaders.py`

**What:** After phases 1-3, `loaders.py` shrinks to ~800-1000 lines:
- **Keep (Category A):** `gather_team_data`, `get_team_pbp`, `_extract_pbp_stats`, `compute_last_n_stats` — read bundle, shape for sections
- **Keep (simplified):** Read pre-computed CFBStats snapshot and validation report from JSON files instead of live scraping
- **Remove (Category B):** All `_fetch_*` functions for CFBStats scraping (moved to Phase 2 script)
- **Remove (Category C):** All reconciliation/verification functions (moved to Phase 3 script)
- **Remove (Category D):** All fallback derivation functions — no longer needed because Phase 1 makes the bundle self-sufficient
- **Keep:** yr-data-api enrichment functions (blitz, PFF) as optional overlay, but make them clearly optional with graceful N/A

**Result:** Brief generation becomes: read bundle → read validation report → shape data → render HTML/MD. No network calls required (enrichment is optional). Deterministic output.

### Phase 5: Enrichment as Bundle Overlay (Optional, Lower Priority)

**Where:** `pbp-analysis/scripts/game_prep_brief/loaders.py` or new `enrichment.py`

**What:**
- yr-data-api enrichment (blitz, PFF, negative plays) stays as an optional overlay
- Either bake into bundle at generation time, or keep as runtime fetch with caching
- Lower priority because enrichment data is clearly marked as `pff` source in the brief

## Migration Notes

- **Don't break demos this week.** All changes are backward-compatible if you keep the existing `loaders.py` working while building the new pipeline alongside it.
- **Phase 1 is the highest leverage change.** Flipping to play-derived primary in the bundle eliminates most of the fallback derivation code in loaders.py and fixes the rollup inconsistencies.
- **Phase 2-3 can happen in parallel.** Snapshotting CFBStats and building the validation script are independent of each other and of Phase 1.
- **Test with WAS/OSU first**, then expand to all 18 Big Ten teams in the bundle.

## Related Issues

- [#176](https://github.com/victorres11/pbp-analysis/issues/176) — Turnover margin off by 1 (missing fumble in StatBroadcast XML)
- PR #175 — POT play-tree derivation, penalty fixes, --no-alerts flag
