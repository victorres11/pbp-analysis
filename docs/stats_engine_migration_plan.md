# Shared Stats Engine Migration Plan (Game Brief + Web App)

## Goal
Keep the **current parser path** as primary, while eliminating duplicated stat logic between:
- `scripts/game_prep_brief/*`
- `generate_data.py` (feeds `data.json` for `index.html`)

So both outputs consume the same canonical derived stats and stop drifting.

## Current State
- Web app (`index.html`) reads `data.json` fields like:
  - `4th_down_attempts`, `4th_down_conversions`
  - `middle8_points_for/against`, `middle8_scoring_plays`
  - `red_zone_*`, `tight_red_zone_*`, `green_zone_*`
  - `turnovers_*`, `points_off_turnovers_*`
  - `negative_plays_*`, `special_teams`
- Game brief currently re-derives many of these from `play_tree` in `loaders.py`.
- `generate_data.py` already uses multiple parser helpers (and upstream modules), but still has custom logic in places.

Result: behavior drift and section-by-section fixes.

## Architecture Decision
Use a shared, canonical "stats engine" layer in this repo that both consumers call:

1. **Source of truth for stat logic**
   - Prefer `pbp_parser` helper modules where available (red zone, fourth down, turnovers, penalties, negative plays, special teams).
2. **Adapter layer**
   - Build one normalized adapter for game input shapes (`ParsedGame` or `play_tree`-derived plays).
3. **Consumers**
   - `generate_data.py` calls shared engine to populate `data.json`.
   - `game_prep_brief/loaders.py` calls same engine for game-level derived fields.

## Reuse Matrix

### Already in parser modules (should be reused directly)
- `pbp_parser.fourth_down`
- `pbp_parser.red_zone`
- `pbp_parser.turnovers`
- `pbp_parser.negative_plays`
- `pbp_parser.special_teams`
- `pbp_parser.penalty_agg`

### Currently duplicated in `pbp-analysis` (candidates to retire)
- `loaders.py:_derive_game_detail_stats`
- `loaders.py:_derive_turnover_drive_stats`
- `loaders.py:_rollup_game_from_play_tree`
- parts of `generate_data.py` custom per-game derivations

## Phased Rollout

### Phase 1 (Low risk, immediate)
- Keep current outputs stable.
- Introduce a shared engine module (in `pbp-analysis`) for one metric family at a time.
- Start with **4th down, red zone, middle8** (highest visible drift recently).

Acceptance:
- Game brief and `data.json` emit identical values for those fields on same games.

### Phase 2
- Move **turnovers + POT** chain logic into shared engine.
- Keep existing reconciliation warnings against XML/CFBStats.

Acceptance:
- residuals do not worsen; discrepancies are definition-labeled.

### Phase 3
- Move penalties/negative plays/special teams derivations.
- Remove dead duplicate helpers from brief loader.

Acceptance:
- No section uses bespoke one-off derivation logic for fields already in shared engine.

## Testing Strategy
- Add parity tests on a fixed matchup (e.g., Washington vs Ohio State 2025):
  - game brief derived fields vs `data.json` derived fields
  - selected per-game invariants (zone subset logic, go-for-it 4th down attempts)
- Keep current warning-based reconciliation output for turnovers/POT.

## Practical Notes
- This does **not** make "legacy parser" canonical.
- It preserves current primary path; it just centralizes helper logic so both products stay consistent.
- XML/CFBStats remain external truth for published ranks/official stat checks.
