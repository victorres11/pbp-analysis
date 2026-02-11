# PBP Matchup Analysis Web App

A production-ready static web app for analyzing play-by-play matchups between two teams.

## Features

### Data Processing (`generate_data.py`)
- Parses all ASU 2025 season PDFs using the pbp-parser library
- Generates realistic mock data for Georgia (top SEC team, 13 games)
- Extracts per-game stats:
  - Points for/against
  - Total plays
  - Explosive plays (runs 15+, passes 20+) with details
  - Turnovers (lost/gained)
  - Penalties
  - Red zone efficiency (trips, TDs, FGs)

### Interactive Web Interface (`index.html`)
- **Self-contained** - Single HTML file with inline JavaScript, loads ECharts + Tailwind from CDN
- **Dark theme** - #09090b background, Inter font, glass-effect cards
- **Team colors** - Georgia (red #ef4444) vs Arizona State (orange #f97316)
- **Responsive** - Works on desktop and mobile

#### Navigation Tabs
1. **Overview** - Head-to-head comparison bars, schedules, points by game charts
2. **Middle 8** - Critical scoring window analysis (placeholder)
3. **Explosive Plays** - Runs 15+, passes 20+ with collapsible detail tables
4. **Red Zone** - Scoring efficiency inside opponent 20-yard line with donut charts
5. **Penalties** - Penalty breakdowns (placeholder)
6. **4th Down** - Conversion analysis (placeholder)
7. **Post-Turnover** - Drive results after turnovers (placeholder)
8. **Special Teams** - Returns, FGs, punts (placeholder)
9. **Situational Receiving** - 3rd down, red zone targets (placeholder)
10. **All Plays Browser** - Searchable play-by-play (placeholder)

#### Global Filters (apply to all tabs)
- **Game Type:** All Games, Conference, Non-Conference, Power 4
- **Recency:** Full Season, Last 3 games

## Usage

### Generate Data
```bash
cd ~/clawd/pbp-parser
python3 app/generate_data.py
```

This will:
1. Parse all PDFs in `data/asu-2025/`
2. Generate mock Georgia data
3. Output `app/data.json`

### View the App
Simply open `app/index.html` in a web browser:
```bash
open app/index.html
# or
python3 -m http.server 8000 --directory app
# Then visit http://localhost:8000
```

## Data Structure

`data.json` contains:
```json
{
  "teams": {
    "georgia": {
      "name": "Georgia",
      "abbr": "UGA",
      "conference": "SEC",
      "color": "#ef4444",
      "aggregates": {
        "games": 13,
        "record": "12-1",
        "ppg": 40.0,
        "opp_ppg": 14.3,
        "explosives_per_game": 9.1,
        "turnover_margin": -4,
        "red_zone_td_pct": 80.9,
        ...
      },
      "games": [
        {
          "game_number": 1,
          "opponent": "Marshall",
          "conference": "Non-Conference",
          "is_power4": false,
          "date": "2025-08-30",
          "points_for": 43,
          "points_against": 3,
          "explosives": 5,
          "explosive_details": [...],
          "red_zone_trips": 4,
          "red_zone_tds": 3,
          ...
        },
        ...
      ]
    },
    "asu": { ... }
  }
}
```

## Technical Details

### Dependencies
- **Tailwind CSS** (CDN) - Utility-first styling
- **ECharts** (CDN) - Interactive charts
- **Inter Font** (Google Fonts) - Typography

### Browser Compatibility
- Modern browsers (Chrome, Firefox, Safari, Edge)
- ES6+ JavaScript features (fetch, async/await, arrow functions)

### Styling
- Glass-morphism cards with `rgba(255,255,255,0.03)` backgrounds
- Smooth transitions on hover (200ms ease)
- Sticky navigation (top bar + tab nav)
- Custom scrollbars (6px width, subtle)
- Color-coded comparison bars
- Responsive grid layouts

## Development

### Adding New Tabs
1. Add a new `<button>` in the category nav with `onclick="showSection('newtab')"`
2. Add a new `<section id="section-newtab" class="hidden section-enter">` in main
3. Update `showSection()` to handle the new tab if it needs data/charts

### Customizing Filters
Edit the filter setup in `setupFilters()` and update `filterGames()` logic.

### Chart Theming
All charts use a consistent dark theme defined in `renderPointsChart()` / `renderTeamRedZone()`:
- Background: transparent
- Text: #a1a1aa (zinc-400)
- Grid lines: rgba(255,255,255,0.06)
- Tooltip: rgba(24,24,27,0.95)

## Future Enhancements
- Complete placeholder tabs (Middle 8, Penalties, 4th Down, etc.)
- Add play-by-play browser with search
- Implement drive-level analysis
- Add player-level receiving stats
- Export charts as images
- Dark/light theme toggle
- Mobile-optimized layout

## Credits
Built with pbp-parser library for football play-by-play analysis.
