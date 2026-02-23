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

## Outputs

The runner writes:

- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.md`
- `outputs/demo_briefs/<team1>_vs_<team2>_<season>_v2.html`
- `outputs/demo_briefs/DEMO_SUMMARY.md`

## Source Policy

- StatBroadcast-derived data is the preferred source path.
- Legacy PDF parsing code is retained for fallback/debug only and should remain disabled by default.
