# Wave 3: Red Zone Overhaul + Post-Turnover Analysis

## TASK 7: RED ZONE OVERHAUL

### Data Generation (generate_data.py)
The current red zone logic (around line 410-421) is BROKEN — it counts all scoring plays as "red zone trips" without checking field position. Fix this:

1. Use the `spot` field on plays to determine actual field position
2. Parse spot to get yards-to-goal (e.g., "OPP15" = 15 yards to goal, inside red zone)
3. Track three zones:
   - Green Zone: 30 yards and in
   - Red Zone: 20 yards and in  
   - Tight Red Zone: 10 yards and in
4. For each zone, track:
   - Trips (drive that enters the zone)
   - TDs scored
   - FGs scored
   - Failed (no score)
   - 3rd down conversions in zone
   - 4th down go-for-it attempts in zone
5. Also collect the actual plays in each zone for play tables
6. Add to game_data: `green_zone_*`, `tight_red_zone_*`, `red_zone_plays` (list of play objects with full detail)

Note: The parser's `compute_team_red_zone_splits` function in pbp_parser/red_zone.py already does proper field-position-based RZ detection. Consider importing and using it, or replicating its spot-parsing logic.

### Frontend (index.html)
1. Red Zone tab should show three sub-sections: Green Zone (30 & in), Red Zone (20 & in), Tight Red Zone (10 & in)
2. Each section: summary stats (trips, TDs, FGs, TD%, conversion rates) + collapsible play tables
3. Play tables: Game, Opponent, Quarter, Clock, Down/Distance, Yards-to-Goal, Play Type, Yards, Scoring (yes/no), Description
4. Reference: https://victorres11.github.io/football-data-adhoc/indiana_purdue_analysis_app.html (Red Zone / Green Zone section)

## TASK 8: POST-TURNOVER ANALYSIS

### Data Generation (generate_data.py)
1. For each turnover (interception, fumble), track what happened AFTER:
   - Which team got the ball
   - What was the drive result (TD, FG, punt, turnover, etc.)
   - Points scored on the post-turnover drive
2. Add to game_data: `post_turnover_drives` list with objects:
   ```json
   {
     "turnover_type": "INT" or "FUM",
     "turnover_by": "team_abbr",
     "recovered_by": "team_abbr", 
     "drive_result": "TD" / "FG" / "Punt" / "Turnover" / etc,
     "points_scored": 7,
     "play_description": "original turnover play description"
   }
   ```

### Frontend (index.html)  
1. Add new tab: Post-Turnover Analysis (icon: 🔄, id: 'postturnovers')
2. Add to TABS array and tab renderer mapping
3. Summary stats: turnovers gained/lost, points off turnovers for/against
4. Play table: Game, Opponent, Turnover Type, Team that recovered, Drive Result, Points, Description
5. Show for BOTH teams

After completing both tasks, regenerate data.json by running: python3 generate_data.py
(The script processes PDFs from the obsidian vault)
