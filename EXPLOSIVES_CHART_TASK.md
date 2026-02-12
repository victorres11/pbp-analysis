# Explosives Chart Run/Pass Breakdown

## Problem
The Explosives tab chart shows only total explosives per game. It should show separate lines for rush vs pass explosives to match the table breakdown.

## Data Available
Each game object has:
- `explosive_rushes` - count of 15+ yard rushes
- `explosive_passes` - count of 20+ yard passes
- `explosives` - total (sum of above)

## Task
Update `initExplosivesCharts()` function in `index.html` to show 4 lines instead of 2:

**Current (wrong):**
- Georgia total explosives (red)
- Arizona State total explosives (orange)

**New (correct):**
- Georgia rush (green line, solid)
- Georgia pass (blue line, solid)
- Arizona State rush (green line, dashed)
- Arizona State pass (blue line, dashed)

## Implementation Details

**Colors:**
- Run/rush: green (#22c55e or similar)
- Pass: blue (#3b82f6 or similar)
- Use solid lines for Georgia
- Use dashed lines for Arizona State (lineStyle: {type: 'dashed'})

**Legend:**
- "Georgia Rush", "Georgia Pass", "Arizona State Rush", "Arizona State Pass"

**Series data:**
- Georgia rush: `gf.map(g => g.explosive_rushes)`
- Georgia pass: `gf.map(g => g.explosive_passes)`
- Arizona State rush: `af.map(g => g.explosive_rushes)`
- Arizona State pass: `af.map(g => g.explosive_passes)`

**Tooltip:**
Keep the existing tooltip formatter logic but update to show run/pass breakdown for each team

## File to Edit
`index.html` - find `function initExplosivesCharts()` (around line 369)

## Acceptance Criteria
- [ ] Chart shows 4 lines (2 per team: rush + pass)
- [ ] Colors: green for rush, blue for pass
- [ ] Solid lines for Georgia, dashed for Arizona State
- [ ] Legend clearly shows all 4 series
- [ ] Tooltip shows opponent + date (keep existing logic)
- [ ] No other changes to the Explosives tab
