# PBP Data Validation System

## Overview
Use cfbstats.com game logs as source-of-truth to validate our PBP parser accuracy.

## cfbstats Game Log URLs

### Pattern
`https://cfbstats.com/{year}/team/{team_id}/{category}/gamelog.html`

### Available Categories
- `turnovermargin` - Turnovers by game (INT/Fum gained/lost)
- `penalties` - Penalty stats by game
- `redzone` - Red zone performance by game
- `thirddown` - 3rd down conversion by game
- `fourthdown` - 4th down conversion by game
- `scoring` - Points scored by game
- `totaloffense` - Total yards by game
- `passing` - Passing stats by game
- `rushing` - Rushing stats by game
- `sacks` - Sack stats by game

### Example Data (ASU Turnovers)
```
Date       Opponent              Fum.G  INT.G  Tot.G  Fum.L  INT.L  Tot.L  Margin
08/30/25   Northern Arizona      0      1      1      0      1      1      0
09/06/25   @ Mississippi State   0      0      0      0      2      2      -2
09/13/25   Texas State           2      0      2      0      0      0      +2
```

## Validation Script Architecture

### 1. Scraper (`scripts/cfbstats_validator.py`)

```python
def fetch_game_log(team_id, year, category):
    """Fetch cfbstats game log for validation."""
    url = f"https://cfbstats.com/{year}/team/{team_id}/{category}/gamelog.html"
    # Parse HTML table
    # Return list of game dicts with standardized keys
    return games

def compare_game_stats(our_data, cfbstats_data, tolerance=0):
    """Compare our parsed data vs cfbstats."""
    mismatches = []
    for game_num, (our, theirs) in enumerate(zip(our_data, cfbstats_data), 1):
        if our['int_gained'] != theirs['int_gain']:
            mismatches.append({
                'game': game_num,
                'opponent': our['opponent'],
                'stat': 'INT Gained',
                'ours': our['int_gained'],
                'cfbstats': theirs['int_gain'],
                'diff': our['int_gained'] - theirs['int_gain']
            })
        # ... check all stats
    return mismatches
```

### 2. Validation Report

```
=== PBP Validation Report ===
Team: Arizona State (2025)
Source: cfbstats.com

Turnover Stats:
✓ 11/13 games match perfectly
✗ 2 discrepancies found:

Game 5 vs TCU:
  Fum Lost: Ours=2, cfbstats=1 (+1)
  → Check: Game05_vs_TCU.pdf

Game 12 vs Arizona:
  INT Lost: Ours=3, cfbstats=2 (+1)
  Fum Lost: Ours=2, cfbstats=1 (+1)
  → Check: Game12_vs_Arizona.pdf

Summary:
  INT Gained: Ours=10, cfbstats=8 (+2)
  INT Lost: Ours=9, cfbstats=9 (✓)
  Fum Gained: Ours=11, cfbstats=7 (+4)
  Fum Lost: Ours=19, cfbstats=12 (+7)
  Total Margin: Ours=-7, cfbstats=-6 (off by 1)
```

### 3. Team ID Mapping

Need to build mapping of our team names → cfbstats team IDs:

```json
{
  "asu": 28,
  "arizona state": 28,
  "georgia": 61,
  "oregon": 483,
  "washington": 264
}
```

Can scrape from cfbstats team list or ESPN API.

## Implementation Phases

### Phase 1: Turnover Validation (1 hour)
- Build cfbstats game log scraper
- Compare ASU turnover data game-by-game
- Generate mismatch report
- Investigate the 2 INT gained + 4 Fum gained + 7 Fum lost discrepancies

### Phase 2: Multi-Category Validation (2 hours)
- Add penalty validation
- Add red zone validation
- Add 3rd/4th down validation
- Add scoring validation

### Phase 3: Automated QA (2 hours)
- CLI tool: `python validate.py asu 2025 --category turnovers`
- CI integration (run validation on data.json changes)
- HTML report generator

### Phase 4: Parser Improvements (ongoing)
- Fix discovered bugs based on validation findings
- Add regression tests
- Document known limitations

## Benefits

1. **Data Accuracy** - Catch parser bugs early
2. **Confidence** - Know our numbers are right
3. **Debugging** - Pinpoint exact games with issues
4. **Documentation** - Understand parser limitations
5. **Source of Truth** - Rely on cfbstats as authoritative

## Usage

```bash
# Validate ASU 2025 turnovers
python scripts/cfbstats_validator.py asu 2025 turnovers

# Validate all categories
python scripts/cfbstats_validator.py asu 2025 --all

# Generate HTML report
python scripts/cfbstats_validator.py asu 2025 --all --report validation-report.html
```

## Next Steps

1. **Build turnover validator first** - solve the ASU discrepancy
2. **Expand to other categories** once turnover validation works
3. **Integrate into generate_data.py** - auto-validate on generation
4. **Document findings** - known issues, parser limitations

## Questions for Victor

1. Should validation be **blocking** (fail if mismatches) or **warning only**?
2. Acceptable tolerance? (e.g., ±1 turnover per season okay?)
3. Which categories are highest priority to validate?
4. Should we show validation results in the UI? (e.g., "Data validated ✓" badge)
