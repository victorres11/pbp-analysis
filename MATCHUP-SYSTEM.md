# PBP Matchup System - Architecture Plan

## Overview
Generate and deploy head-to-head matchup analysis pages from PBP PDFs for any two teams.

**Use case:** 3-4 matchups per week during season, with partial/different game counts.

## Architecture Decisions

### 1. Hosting & URLs
**Model:** Dynamic routes on single domain
- Production: `pbp-analysis.vercel.app/matchups/oregon-washington`
- Current Georgia-ASU becomes: `pbp-analysis.vercel.app/matchups/georgia-asu`

**Implementation:**
- Next.js dynamic routes or client-side routing with hash
- Single build, multiple matchup data files
- Matchup selector dropdown on homepage

### 2. Data Organization

```
pbp-data/
  teams/
    oregon/
      2024/
        game01-vs-idaho.pdf
        game02-at-boise-state.pdf
        ...
    washington/
      2024/
        game01-vs-weber-state.pdf
        ...
  matchups/
    oregon-washington-2024/
      data.json          # Generated matchup analysis
      metadata.json      # Teams, date created, week
    georgia-asu-2024/    # Existing matchup
      data.json
```

**Notes:**
- Victor stores PDFs in Obsidian, but shared team folders work for processing
- Script copies PDFs from Obsidian to team folders during generation

### 3. Team Metadata

**Source:** Auto-generate from ESPN API (or cfbstats) on first use, store in `teams.json`

```json
{
  "teams": {
    "oregon": {
      "name": "Oregon",
      "abbr": "ORE",
      "conference": "Big Ten",
      "primary_color": "#154733",
      "secondary_color": "#FEE123",
      "logo_url": "https://...",
      "espn_id": "2483"
    },
    "washington": {
      "name": "Washington",
      "abbr": "UW",
      "conference": "Big Ten",
      "primary_color": "#4B2E83",
      "secondary_color": "#B7A57A",
      "espn_id": "264"
    }
  }
}
```

**Initial population:**
- Fetch from ESPN Teams API: `http://site.api.espn.com/apis/site/v2/sports/football/college-football/teams/{id}`
- Extract: name, abbreviation, conference, colors
- Store locally for future use
- Manual override possible

### 4. Workflow (Interactive CLI)

**Command:**
```bash
pbp-matchup create
```

**Interactive prompts:**
```
Team 1 name (e.g., 'Oregon'): oregon
Team 2 name (e.g., 'Washington'): washington

📁 Where are Oregon's PDFs?
  [1] ~/Documents/Obsidian/Football/Oregon-2024/
  [2] Enter custom path
  > 1

📁 Where are Washington's PDFs?
  [1] ~/Documents/Obsidian/Football/Washington-2024/
  [2] Enter custom path
  > 1

Season year [2024]: 2024
Week/context (optional): Week 7

🔍 Found:
  Oregon: 6 games
  Washington: 7 games

✓ Team metadata loaded (Oregon: Big Ten, Washington: Big Ten)

Proceed? [Y/n]: y

🏈 Processing matchup...
  ✓ Copied PDFs to pbp-data/teams/
  ✓ Parsed Oregon games (6/6)
  ✓ Parsed Washington games (7/7)
  ✓ Generated matchup data
  ✓ Fetched cfbstats rankings
  ✓ Built matchup page
  ✓ Committed to git
  ✓ Deployed to Vercel

🎉 Matchup live: https://pbp-analysis.vercel.app/matchups/oregon-washington
```

**Script location:** `~/clawd/scripts/pbp-matchup.sh` (or Python)

### 5. Partial Season Handling

**Approach:** Show all available games for each team

**Display:**
- Oregon: 6 games played
- Washington: 7 games played
- No filtering, no warnings
- Stats are season-to-date for each team

**Note on schedule cards:**
- Show full schedule for each team
- Gray out games not yet played
- Clearly label bye weeks

### 6. Deployment Strategy

**Auto-deploy on generation:**
1. Generate matchup data → `matchups/oregon-washington-2024/data.json`
2. Update matchup index → `matchups/index.json` (list of all matchups)
3. Git commit: "Add Oregon vs Washington matchup"
4. Git push origin main
5. Vercel auto-deploys
6. Matchup live immediately

**Benefits:**
- Zero friction workflow
- Immediate feedback
- Easy to regenerate if needed

**Safety:**
- Local preview available before generating
- Can delete/regenerate if issues found

### 7. Caching Strategy

**Simple approach: Cache parsed PDFs per game file**

```
pbp-data/
  .cache/
    oregon/
      game01-vs-idaho.json    # Parsed drives/plays
    washington/
      game01-vs-weber.json
```

**Cache invalidation:** Check PDF file modification time
- If PDF unchanged → use cache
- If PDF modified → re-parse

**Complexity:** Minimal (just check mtime, load JSON if exists)

**Maintenance:** None (automatic invalidation)

**Benefit:** Regenerating Oregon-Washington after Oregon-USC won't re-parse Oregon games

---

## Implementation Phases

### Phase 1: Core Infrastructure (2-3 hours)
- [ ] Create `pbp-matchup` CLI script
- [ ] Build `teams.json` with ESPN API integration
- [ ] Set up matchup data directory structure
- [ ] Update `generate_data.py` to accept team parameters

### Phase 2: Dynamic Routing (2 hours)
- [ ] Convert to Next.js or add hash routing
- [ ] Create matchup index page with selector
- [ ] Dynamic matchup viewer (loads data.json based on route)
- [ ] Update Vercel config for routing

### Phase 3: Caching Layer (1 hour)
- [ ] Simple file-based cache in `.cache/`
- [ ] Check mtime before parsing
- [ ] Save parsed output as JSON

### Phase 4: Auto-deployment (1 hour)
- [ ] Git integration in CLI
- [ ] Automatic commit with descriptive message
- [ ] Push to trigger Vercel deploy
- [ ] Success confirmation with live URL

### Phase 5: Testing & Refinement (1 hour)
- [ ] Test with Oregon-Washington
- [ ] Test with partial seasons (5 vs 8 games)
- [ ] Test cache invalidation
- [ ] Verify deployment flow

**Total estimate:** 7-8 hours

---

## File Structure After Implementation

```
pbp-analysis/
  src/
    pages/
      matchups/
        [slug].js          # Dynamic matchup viewer
        index.js           # Matchup selector page
  public/
    matchups/
      oregon-washington/
        data.json
      georgia-asu/
        data.json
      index.json           # List of all matchups
  teams.json               # Team metadata cache

pbp-parser/
  data/
    teams/
      oregon/2024/*.pdf
      washington/2024/*.pdf
    .cache/
      oregon/*.json        # Parsed game data
      washington/*.json

scripts/
  pbp-matchup.py           # CLI tool
  espn_teams.py            # ESPN API fetcher
```

---

## Next Steps

1. **Review this plan** - any changes needed?
2. **Start Phase 1** - build the CLI tool
3. **Test with Oregon-Washington** once basic infrastructure works
4. **Iterate** based on real usage

**Questions?**
