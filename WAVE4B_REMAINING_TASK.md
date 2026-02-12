# Wave 4B Remaining Frontend Polish

## Overview
Complete 7 remaining Wave 4B items. Items 3+4 (Explosives chart, Red Zone) are already done. Data from Wave 4A is available, just need UI display.

---

## 1. Logo Light Background

**Problem:** VT logo may not render well on light backgrounds

**Fix:**
- Check if logo has transparent background
- If needed, add white/light variant or adjust opacity
- Test on various backgrounds

**File:** `assets/vt-logo-icon.png` or create alternate version

---

## 2. Middle 8: Sanity Check + Points Against

**Current state:** Middle 8 tab shows scoring plays from both teams

**Fixes needed:**
1. **Sanity check:** Verify Middle 8 definition (2nd Q 6:00-0:00 + 3rd Q 12:00-6:00) is correctly applied
2. **Add "Points Against" column** to opponent scoring tables
3. **Verify chronological order** of plays

**Files:** 
- `index.html` - `renderMiddle8()` function
- Data should already have this info in `play_tree`

---

## 3. ✅ Explosives: Run/Pass in Charts ✅
**DONE** - PR #7 merged

---

## 4. ✅ Red Zone: Visual Separation ✅
**DONE** - PR #6 merged

---

## 5. Penalties: Type Breakdown + Biggest Offenders

**Current state:** Shows total penalties and penalty yards

**Add:**
1. **Penalty type breakdown chart** - show counts for:
   - Pass interference (offensive + defensive)
   - Holding (offensive + defensive)
   - False start
   - Offsides
   - Illegal formation
   - Unsportsmanlike conduct
   - Other
2. **Accepted vs Declined** - show split
3. **Biggest offenders** - if penalty data includes play descriptions, try to extract player names

**Data available:**
- `game.penalty_breakdown` (from Wave 4A) should have type counts
- Check `data.json` structure to see what's available

**File:** `index.html` - `renderPenalties()` function

---

## 6. 4th Down: Display Fix

**Change:** Data now only includes "go for it" plays (not punts/FGs)

**Fix:**
- Update display text to clarify this
- Verify success rate calculation is correct
- May show fewer total plays now (this is expected)

**File:** `index.html` - `renderFourthDown()` function

---

## 7. Turnovers: Fumble/INT Breakdown Display

**Current state:** Shows turnover margin and basic counts

**Add:**
1. **Stat cards** showing INT vs fumble split
2. **Chart breakdown** - pie or bar chart showing:
   - INTs thrown vs caught
   - Fumbles lost vs recovered
3. **Visual distinction** in tables (if not already there)

**Data available:**
- `game.turnovers_int` and `game.turnovers_fumble` (from Wave 4A)

**File:** `index.html` - `renderTurnovers()` function

---

## 8. Post-Turnover: Points Off Turnovers Charts

**Current state:** Post-Turnover tab exists with drive data

**Add:**
1. **Chart showing points scored after forcing turnovers** (per game or total)
2. **Chart showing points allowed after committing turnovers**
3. Visual comparison between teams

**Data available:**
- `game.points_off_turnovers` (from Wave 4A)
- Post-turnover drive data already tracked

**File:** `index.html` - `renderPostTurnover()` function

---

## 9. Special Teams: Better Breakdowns

**Current state:** Special Teams tab exists but may be basic

**Improvements:**
1. **Punt stats:**
   - Average punt distance
   - Longest punt
   - Punts inside 20
   - Touchbacks
2. **Field Goal stats:**
   - FG% with made/attempted breakdown
   - By distance (0-29, 30-39, 40-49, 50+)
   - Longest made
3. **Kick Return:**
   - Average return yards
   - Longest return
   - Touchdowns
4. **Punt Return:**
   - Average return yards
   - Fair catches
   - Touchdowns

**Data available:**
- Wave 4A added special teams metrics
- Check `data.json` for field names

**File:** `index.html` - `renderSpecialTeams()` function

---

## Approach

For each item:
1. Check current data structure in `data.json`
2. Update the relevant render function in `index.html`
3. Add charts where appropriate (using ECharts like other tabs)
4. Maintain consistent styling with rest of app

## Testing

After changes:
1. Verify all tabs load without errors
2. Check that data displays correctly
3. Ensure charts render properly
4. Test filter interactions still work

## Note

Data pipeline (Wave 4A) is complete. All necessary data fields exist. This is purely frontend display work.
