# Red Zone Fixes

## Problem 1: "Failed" Calculation is Wrong

**Current logic** (generate_data.py lines 759, 761):
```python
green_zone_failed = green_zone_trips - (green_zone_tds + green_zone_fgs)
tight_red_zone_failed = tight_red_zone_trips - (tight_red_zone_tds + tight_red_zone_fgs)
```

This counts EVERYTHING that's not a score as "failed", including:
- Punts
- End of half/game
- Successful 4th down conversions that don't score
- First downs

**Correct definition of "Failed":**
Only these outcomes should count as failures:
1. **Turnovers** — interceptions, fumbles lost
2. **Turnover on downs** — failed 4th down conversion
3. **Missed field goals**

**Fix needed in generate_data.py:**
- Track actual failures by examining drive outcomes in each zone
- For each zone (green_zone, red_zone, tight_red_zone), count only:
  - Drives that ended in turnover (check drive outcome)
  - Drives that ended in turnover on downs
  - Drives that ended in missed FG
- Update the failed count calculation around lines 759-761

## Problem 2: Visual Separation Between Zones

**Current state:** All three zones (Green Zone, Red Zone, Tight Red Zone) run together with minimal visual separation.

**Fix needed in index.html renderRedzone():**

Add visual demarcation between sections:

```javascript
html += renderZoneSection('Green Zone', '(30 yards & in)', gs, as_, 'green_zone', gf, af);

// Add separator
html += `<div class="border-t-2 border-zinc-700 my-6"></div>`;

html += renderZoneSection('Red Zone', '(20 yards & in)', gs, as_, 'red_zone', gf, af);

// Add separator
html += `<div class="border-t-2 border-zinc-700 my-6"></div>`;

html += renderZoneSection('Tight Red Zone', '(10 yards & in)', gs, as_, 'tight_red_zone', gf, af);
```

Or use colored headers:
- Green Zone → green accent
- Red Zone → red accent
- Tight Red Zone → orange/darker red accent

## Expected Results

After fixes:
- Teams should show ~80-90% scoring rate (TD + FG) in red zone
- Failed count should be much lower (typically 2-3 per season, not 10-15)
- Visual separation makes it easy to scan each zone

## Files to Edit
1. **generate_data.py** — fix failed calculation logic (lines 759-761 and surrounding)
2. **index.html** — add visual separators in renderRedzone() function (around line 498-500)

## Testing
After regenerating data.json:
- Check Georgia's red zone stats
- Verify: trips = TDs + FGs + failures (should add up)
- Verify: scoring rate (TDs + FGs) / trips should be ~80-90%
- Visual: clear separation between zone sections in UI
