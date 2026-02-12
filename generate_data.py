#!/usr/bin/env python3
"""
Generate data.json for PBP Matchup Analysis web app.
All data extracted from parsed PBP PDFs — no hardcoded scores.
"""

import json
import re
import sys
import glob
from pathlib import Path
from datetime import date
from collections import defaultdict

# Add src to path to import pbp_parser
repo_root = Path(__file__).parent.parent / "pbp-parser"
sys.path.insert(0, str(repo_root / "src"))

from pbp_parser.parse import parse_pdf
from pbp_parser.pdf_text import extract_pdf_text
from pbp_parser.red_zone import compute_team_red_zone_splits
from pbp_parser.explosives import compute_team_explosives


def extract_scores_from_pdf(pdf_path):
    """Extract final scores from SCORE BY QUARTERS section of PBP PDF."""
    text = extract_pdf_text(pdf_path)
    lines = text.split('\n')
    scores = {}
    
    score_re = re.compile(r'([A-Za-z][A-Za-z.\' &-]{1,30}?)\s{2,}(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$')
    for i, line in enumerate(lines):
        if 'score by quarters' in line.lower():
            for j in range(i+1, min(i+12, len(lines))):
                l = lines[j].rstrip()
                if not l:
                    continue
                m = score_re.search(l)
                if not m:
                    continue
                team_name = m.group(1).strip()
                if team_name.upper() in ['TOTAL', 'TEAM']:
                    continue
                final_score = int(m.group(6))
                scores[team_name] = final_score
            break
    
    return scores


def extract_header_info(pdf_path):
    """Extract date, attendance, and record from PDF header."""
    text = extract_pdf_text(pdf_path)
    lines = text.split('\n')
    info = {'date': '', 'attendance': '', 'records': {}}
    
    for line in lines[:10]:
        # Look for date pattern
        date_match = re.search(r'\((\w+ \d+, \d{4})\)', line)
        if date_match:
            info['date'] = date_match.group(1)
        
        # Look for records like "(8-4, 6-3)"
        record_matches = re.findall(r'(\w[\w\s.]+?)\s*\((\d+-\d+(?:,\s*\d+-\d+)?)\)', line)
        for team, record in record_matches:
            info['records'][team.strip()] = record
    
    return info


def identify_asu(teams):
    """Find ASU abbreviation from team list."""
    for t in teams:
        if t.upper() in ['ASU', 'ARIZ ST', 'ARIZONA ST', 'ARIZONA ST.']:
            return t
    return teams[1] if len(teams) > 1 else None


def identify_georgia(teams):
    """Find Georgia abbreviation from team list."""
    for t in teams:
        up = t.upper().replace('.', '').strip()
        if up in ['GEORGIA', 'UGA']:
            return t
    return teams[1] if len(teams) > 1 else None


def parse_clock_seconds(clock):
    if not clock or ':' not in clock:
        return None
    try:
        mins, secs = clock.split(':', 1)
        return int(mins) * 60 + int(secs)
    except ValueError:
        return None


def points_from_description(desc):
    u = (desc or '').upper()
    if 'TOUCHDOWN' in u:
        return 6
    if 'FIELD GOAL' in u and ('GOOD' in u or 'IS GOOD' in u or 'MADE' in u):
        return 3
    if 'SAFETY' in u:
        return 2
    if 'TWO-POINT' in u or 'TWO POINT' in u or '2-POINT' in u or '2PT' in u:
        if all(bad not in u for bad in ['FAILED', 'NO GOOD', 'UNSUCCESSFUL']):
            return 2
    if 'PAT' in u or 'EXTRA POINT' in u or 'POINT AFTER' in u:
        if 'GOOD' in u or 'MADE' in u:
            return 1
    return 0


def is_drive_marker(desc):
    return ' drive starts at ' in (desc or '').lower()


def build_play_tree(plays):
    quarters = []
    quarter_map = {}
    current_drive = None
    current_quarter = None
    current_offense = None
    drive_counter = 0

    def get_quarter(q):
        if q not in quarter_map:
            entry = {'quarter': q, 'drives': []}
            quarter_map[q] = entry
            quarters.append(entry)
        return quarter_map[q]

    def start_drive(offense, quarter):
        nonlocal current_drive, current_offense, drive_counter
        drive_counter += 1
        current_offense = offense
        current_drive = {
            'drive_id': f'D{drive_counter}',
            'offense': offense or '',
            'plays': []
        }
        get_quarter(quarter)['drives'].append(current_drive)

    for p in plays:
        desc = p.description or ''
        if is_drive_marker(desc):
            start_drive(p.offense or current_offense, p.quarter)
            continue

        if current_quarter is None or p.quarter != current_quarter:
            current_quarter = p.quarter
            start_drive(p.offense or current_offense, p.quarter)

        if current_drive is None:
            start_drive(p.offense, p.quarter)

        if p.offense and current_drive['plays'] and p.offense != current_offense:
            start_drive(p.offense, p.quarter)

        current_drive['plays'].append({
            'quarter': p.quarter,
            'clock': p.clock or '',
            'offense': p.offense or '',
            'down_distance': p.down_distance or '',
            'spot': p.spot or '',
            'description': desc,
            'yards': p.yards if p.yards is not None else '',
            'is_scoring': bool(p.is_scoring),
            'is_turnover': bool(p.is_turnover),
            'is_no_play': bool(p.is_no_play),
        })

    return quarters


def compute_middle8_stats(plays, our_abbr, opp_abbr):
    points_for = 0
    points_against = 0
    scoring_plays = []
    q3_seen = 0

    for p in plays:
        if p.is_no_play:
            continue
        clock_secs = parse_clock_seconds(p.clock)
        in_window = False

        if p.quarter == 2 and clock_secs is not None and clock_secs <= 240:
            in_window = True
        elif p.quarter == 3:
            q3_seen += 1
            if clock_secs is not None and clock_secs >= 660:
                in_window = True
            elif clock_secs is None and q3_seen <= 5:
                in_window = True

        if not in_window or not p.is_scoring:
            continue

        pts = points_from_description(p.description)
        if pts <= 0:
            continue

        team = p.offense or ''
        if team == our_abbr:
            points_for += pts
        elif team == opp_abbr:
            points_against += pts

        scoring_plays.append({
            'quarter': p.quarter,
            'clock': p.clock or '',
            'team': team,
            'points': pts,
            'description': p.description or '',
        })

    return points_for, points_against, scoring_plays


def parse_yards_to_goal(spot, offense_abbr, opponent_abbr):
    """
    Parse spot field to determine yards-to-goal.
    
    Examples:
    - offense=UGA, spot="ALA15" → 15 yards to goal (opponent's side)
    - offense=UGA, spot="UGA40" → 60 yards to goal (own side)
    - spot="50" → 50 yards to goal (midfield)
    
    Returns yards-to-goal or None if spot is invalid.
    """
    if not spot or not offense_abbr:
        return None
    
    spot = spot.strip().upper()
    offense_abbr = offense_abbr.upper()
    opponent_abbr = (opponent_abbr or '').upper()
    
    # Handle midfield
    if spot == '50':
        return 50
    
    # Extract number from spot
    match = re.search(r'(\d+)', spot)
    if not match:
        return None
    
    yards_num = int(match.group(1))
    
    # If spot contains opponent's abbreviation, the number IS yards-to-goal
    if opponent_abbr and opponent_abbr in spot:
        return yards_num
    
    # If spot contains offense's abbreviation, yards-to-goal = 100 - number
    if offense_abbr in spot:
        return 100 - yards_num
    
    # Try to guess: if number is <= 50, assume it's on opponent's side
    # This is a fallback heuristic for ambiguous cases
    if yards_num <= 50:
        return yards_num
    else:
        return 100 - yards_num


def parse_fourth_distance(down_distance):
    m = re.match(r'^4-(\d+|Goal)', down_distance or '')
    if not m:
        return None
    if m.group(1).lower() == 'goal':
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def compute_fourth_down_stats(plays, our_abbr):
    attempts = 0
    conversions = 0
    for p in plays:
        if p.is_no_play or p.offense != our_abbr:
            continue
        dd = p.down_distance or ''
        if not dd.startswith('4-'):
            continue
        desc = (p.description or '').upper()
        # Only count "go for it" attempts (rush or pass)
        # Exclude punts, field goals, and penalties
        if 'PUNT' in desc or 'FIELD GOAL' in desc or ' FG' in desc:
            continue
        if 'PENALTY' in desc or 'PENALIZED' in desc:
            continue
        # Must be a rush or pass attempt
        is_rush_or_pass = ('RUSH' in desc or 'PASS' in desc or 'COMPLETE' in desc or 
                           'INCOMPLETE' in desc or 'SACK' in desc or 'RUN' in desc)
        if not is_rush_or_pass:
            continue
        attempts += 1
        converted = False
        if p.is_scoring:
            converted = True
        elif '1ST DOWN' in desc or 'FIRST DOWN' in desc:
            converted = True
        else:
            dist = parse_fourth_distance(dd)
            if dist is not None and p.yards is not None and p.yards >= dist:
                converted = True
        if converted:
            conversions += 1
    return attempts, conversions


def parse_turnover_breakdown(plays, our_abbr, opp_abbr):
    """Parse turnovers into INT and fumble breakdowns for both teams."""
    our_ints_lost = 0
    our_fumbles_lost = 0
    our_ints_gained = 0
    our_fumbles_gained = 0
    
    for p in plays:
        if not p.is_turnover:
            continue
        
        desc = (p.description or '').upper()
        is_interception = 'INTERC' in desc or 'INT ' in desc or ' INT' in desc
        is_fumble = 'FUMBLE' in desc or 'FUM' in desc
        
        # Determine who lost the ball
        lost_by = p.offense or '?'
        
        if lost_by == our_abbr:
            # We lost the turnover
            if is_interception:
                our_ints_lost += 1
            elif is_fumble:
                our_fumbles_lost += 1
        elif lost_by == opp_abbr:
            # Opponent lost the turnover (we gained it)
            if is_interception:
                our_ints_gained += 1
            elif is_fumble:
                our_fumbles_gained += 1
    
    return our_ints_lost, our_fumbles_lost, our_ints_gained, our_fumbles_gained


def parse_penalty_details(plays, our_abbr, opp_abbr):
    """Extract detailed penalty information from plays."""
    penalty_details = []
    
    # Common penalty patterns
    penalty_patterns = [
        (r'HOLDING', 'Holding'),
        (r'FALSE START', 'False Start'),
        (r'PASS INTERFERENCE', 'Pass Interference'),
        (r'OFFSIDE', 'Offside'),
        (r'ILLEGAL (FORMATION|PROCEDURE|MOTION|SHIFT|BLOCK)', 'Illegal \\1'),
        (r'ROUGHING THE (PASSER|KICKER)', 'Roughing the \\1'),
        (r'FACEMASK', 'Facemask'),
        (r'UNSPORTSMANLIKE', 'Unsportsmanlike Conduct'),
        (r'TARGETING', 'Targeting'),
        (r'DELAY OF GAME', 'Delay of Game'),
        (r'ENCROACHMENT', 'Encroachment'),
        (r'NEUTRAL ZONE INFRACTION', 'Neutral Zone Infraction'),
        (r'ILLEGAL HANDS', 'Illegal Hands'),
        (r'CLIPPING', 'Clipping'),
        (r'INTENTIONAL GROUNDING', 'Intentional Grounding'),
    ]
    
    for p in plays:
        desc = p.description or ''
        desc_upper = desc.upper()
        
        if 'PENALTY' not in desc_upper and 'PENALIZED' not in desc_upper:
            continue
        
        # Parse penalty type
        penalty_type = 'Unknown'
        for pattern, name in penalty_patterns:
            if re.search(pattern, desc_upper):
                penalty_type = re.sub(pattern, name, desc_upper, count=1)
                # Clean up the penalty type
                penalty_type = re.sub(r'.*?(HOLDING|FALSE START|PASS INTERFERENCE|OFFSIDE|ILLEGAL.*?|ROUGHING.*?|FACEMASK|UNSPORTSMANLIKE.*?|TARGETING|DELAY OF GAME|ENCROACHMENT|NEUTRAL ZONE.*?|ILLEGAL HANDS|CLIPPING|INTENTIONAL GROUNDING).*', r'\1', penalty_type)
                penalty_type = penalty_type.title()
                break
        
        # Parse yards
        yards_match = re.search(r'(\d+)\s*YARD', desc_upper)
        yards = int(yards_match.group(1)) if yards_match else 0
        
        # Parse accepted/declined
        accepted = 'DECLINED' not in desc_upper and 'OFFSETTING' not in desc_upper
        
        # Determine penalized team
        penalized_team = None
        if p.offense == our_abbr:
            # Check if it says opponent team name in penalty
            if opp_abbr and opp_abbr.upper() in desc_upper:
                penalized_team = opp_abbr
            else:
                penalized_team = our_abbr
        elif p.offense == opp_abbr:
            if our_abbr and our_abbr.upper() in desc_upper:
                penalized_team = our_abbr
            else:
                penalized_team = opp_abbr
        
        # Determine offense or defense
        # If the penalized team is the offense team, it's an offensive penalty
        offense_or_defense = 'offense' if penalized_team == p.offense else 'defense'
        
        penalty_details.append({
            'type': penalty_type,
            'team': penalized_team or '?',
            'yards': yards,
            'accepted': accepted,
            'description': desc,
            'quarter': p.quarter,
            'clock': p.clock or '',
            'offense_or_defense': offense_or_defense,
        })
    
    return penalty_details


def compute_special_teams_stats(plays, our_abbr, opp_abbr):
    stats = {
        'kickoff_returns': 0,
        'kickoff_return_yards': 0,
        'kickoff_return_long': 0,
        'punt_returns': 0,
        'punt_return_yards': 0,
        'punt_return_long': 0,
        'punts': 0,
        'punt_yards': 0,
        'punts_inside_20': 0,
        'field_goals_made': 0,
        'field_goals_attempts': 0,
        'pat_made': 0,
        'pat_attempts': 0,
        'onside_kicks_attempted': 0,
        'onside_kicks_recovered': 0,
    }

    for p in plays:
        if p.is_no_play:
            continue
        desc = (p.description or '').upper()
        is_kickoff = 'KICKOFF' in desc
        is_punt = 'PUNT' in desc
        is_fg = 'FIELD GOAL' in desc or re.search(r'\bFG\b', desc)
        is_pat = 'PAT' in desc or 'EXTRA POINT' in desc or 'POINT AFTER' in desc
        is_onside = 'ONSIDE' in desc

        if p.offense == our_abbr:
            # Our punts
            if is_punt and 'RETURN' not in desc:
                stats['punts'] += 1
                if p.yards is not None:
                    stats['punt_yards'] += p.yards
                # Check for inside 20
                if 'INSIDE 20' in desc or re.search(r'(OUT OF BOUNDS|DOWNED|FAIR CATCH).*?(\d+)', desc):
                    # Try to determine if ball ended inside 20
                    spot_match = re.search(r'AT\s+[A-Z]*(\d+)', desc)
                    if spot_match and int(spot_match.group(1)) <= 20:
                        stats['punts_inside_20'] += 1
            
            # Our field goals (include even if not marked as scrimmage play)
            if is_fg:
                stats['field_goals_attempts'] += 1
                if 'GOOD' in desc or 'IS GOOD' in desc or 'MADE' in desc:
                    stats['field_goals_made'] += 1
            
            # Our PATs
            if is_pat:
                stats['pat_attempts'] += 1
                if 'GOOD' in desc or 'MADE' in desc:
                    stats['pat_made'] += 1
            
            # Our onside kicks
            if is_kickoff and is_onside:
                stats['onside_kicks_attempted'] += 1
                if 'RECOVER' in desc and our_abbr in desc:
                    stats['onside_kicks_recovered'] += 1

        # Opponent's kicks that we return
        if p.offense == opp_abbr or is_kickoff:  # Kickoffs might not have offense set correctly
            if is_kickoff and 'RETURN' in desc and our_abbr in desc:
                stats['kickoff_returns'] += 1
                if p.yards is not None:
                    stats['kickoff_return_yards'] += p.yards
                    stats['kickoff_return_long'] = max(stats['kickoff_return_long'], p.yards)
            
            if is_punt and 'RETURN' in desc and our_abbr in desc:
                stats['punt_returns'] += 1
                if p.yards is not None:
                    stats['punt_return_yards'] += p.yards
                    stats['punt_return_long'] = max(stats['punt_return_long'], p.yards)

    # Calculate averages
    if stats['kickoff_returns'] > 0:
        stats['kickoff_return_avg'] = round(stats['kickoff_return_yards'] / stats['kickoff_returns'], 1)
    else:
        stats['kickoff_return_avg'] = 0.0
    
    if stats['punt_returns'] > 0:
        stats['punt_return_avg'] = round(stats['punt_return_yards'] / stats['punt_returns'], 1)
    else:
        stats['punt_return_avg'] = 0.0
    
    if stats['punts'] > 0:
        stats['punt_avg'] = round(stats['punt_yards'] / stats['punts'], 1)
    else:
        stats['punt_avg'] = 0.0
    
    if stats['field_goals_attempts'] > 0:
        stats['field_goal_pct'] = round(stats['field_goals_made'] / stats['field_goals_attempts'] * 100, 1)
    else:
        stats['field_goal_pct'] = 0.0

    return stats


def process_team_games(pdf_dir, team_identifier):
    """Process all PDFs for a team, extracting all data from the parser."""
    pdf_files = sorted(glob.glob(str(pdf_dir / "*.pdf")))
    
    games = []
    parsed_games = []
    
    for pdf_path in pdf_files:
        pdf_path = Path(pdf_path)
        print(f"  Parsing {pdf_path.name}...")
        
        try:
            g = parse_pdf(pdf_path)
            parsed_games.append(g)
        except Exception as e:
            print(f"    WARNING: Failed to parse: {e}")
            continue
        
        # Extract scores from PDF
        scores = extract_scores_from_pdf(pdf_path)
        header = extract_header_info(pdf_path)
        
        # Identify our team and opponent
        if team_identifier == 'asu':
            our_abbr = identify_asu(g.teams)
        elif team_identifier == 'georgia':
            our_abbr = identify_georgia(g.teams)
        else:
            our_abbr = None
        if not our_abbr and len(g.teams) >= 2:
            our_abbr = g.teams[0]  # fallback
        
        opp_abbr = [t for t in g.teams if t != our_abbr][0] if len(g.teams) >= 2 else '?'
        
        # Match score names to abbreviations
        our_score = 0
        opp_score = 0
        score_teams = list(scores.keys())
        score_vals = list(scores.values())
        
        if len(score_teams) >= 2:
            # Find which score line is ours
            our_idx = -1
            for idx, st in enumerate(score_teams):
                stl = st.lower()
                if team_identifier == 'asu' and ('arizona st' in stl or our_abbr.lower() in stl):
                    our_idx = idx
                    break
                if team_identifier == 'georgia' and ('georgia' in stl or 'uga' in stl or our_abbr.lower() in stl):
                    our_idx = idx
                    break
            if our_idx == -1:
                our_idx = 1 if team_identifier == 'asu' else 0
            
            opp_idx = 1 - our_idx
            our_score = score_vals[our_idx]
            opp_score = score_vals[opp_idx]
            opp_name = score_teams[opp_idx]
        else:
            opp_name = opp_abbr
        
        # Get team stats
        our_stats = g.team_stats.get(our_abbr, None)
        opp_stats = g.team_stats.get(opp_abbr, None)
        
        # Count turnovers from team_stats
        our_turnovers_lost = our_stats.turnovers if our_stats and our_stats.turnovers else 0
        opp_turnovers_lost = opp_stats.turnovers if opp_stats and opp_stats.turnovers else 0
        
        # Count penalties from plays
        our_penalties = 0
        opp_penalties = 0
        for p in g.plays:
            desc = (p.description or '').upper()
            if 'PENALTY' in desc or 'PENALIZED' in desc:
                if p.offense == our_abbr:
                    our_penalties += 1
                elif p.offense == opp_abbr:
                    opp_penalties += 1
        
        # Count explosive plays
        our_explosives = 0
        our_explosive_details = []
        for p in g.plays:
            if p.offense == our_abbr and p.yards and not p.is_no_play:
                desc = (p.description or '').upper()
                is_pass = 'PASS' in desc or 'COMPLETE' in desc or 'CAUGHT' in desc
                is_rush = not is_pass
                threshold = 20 if is_pass else 15
                if p.yards >= threshold:
                    our_explosives += 1
                    our_explosive_details.append({
                        'description': p.description or '',
                        'yards': p.yards,
                        'type': 'pass' if is_pass else 'rush'
                    })
        
        # Zone tracking: Green (30 & in), Red (20 & in), Tight Red (10 & in)
        # Track trips, TDs, FGs, and failed attempts for each zone
        green_zone_trips = 0
        green_zone_tds = 0
        green_zone_fgs = 0
        green_zone_failed = 0
        
        red_zone_trips = 0
        red_zone_tds = 0
        red_zone_fgs = 0
        red_zone_failed = 0
        
        tight_red_zone_trips = 0
        tight_red_zone_tds = 0
        tight_red_zone_fgs = 0
        tight_red_zone_failed = 0
        
        red_zone_plays = []
        
        # Track drives that enter each zone
        drives_by_zone = {
            'green': set(),
            'red': set(),
            'tight_red': set()
        }
        
        # Track drive results (need to track per drive)
        drive_results = {}  # drive_id -> {'zone': str, 'result': 'TD'/'FG'/'FAILED'}
        
        current_drive = 0
        for i, p in enumerate(g.plays):
            if p.offense != our_abbr:
                if i > 0 and g.plays[i-1].offense == our_abbr:
                    current_drive += 1
                continue
            
            ytg = parse_yards_to_goal(p.spot, our_abbr, opp_abbr)
            if ytg is None:
                continue
            
            # Track which zones this drive entered
            if ytg <= 30:
                drives_by_zone['green'].add(current_drive)
                # Add play to red_zone_plays if it's in any tracked zone
                play_dict = {
                    'quarter': p.quarter,
                    'clock': p.clock or '',
                    'down_distance': p.down_distance or '',
                    'yards_to_goal': ytg,
                    'play_type': 'pass' if 'PASS' in (p.description or '').upper() else 'rush',
                    'yards': p.yards or 0,
                    'scoring': p.is_scoring,
                    'description': p.description or '',
                    'zone': 'green' if ytg <= 30 else ''
                }
                
                if ytg <= 20:
                    drives_by_zone['red'].add(current_drive)
                    play_dict['zone'] = 'red'
                    
                    if ytg <= 10:
                        drives_by_zone['tight_red'].add(current_drive)
                        play_dict['zone'] = 'tight_red'
                
                red_zone_plays.append(play_dict)
            
            # Check for scoring on this play to determine drive result
            desc = (p.description or '').upper()
            is_fg = 'FIELD GOAL' in desc or re.search(r'\bFG\b', desc)
            is_td = 'TOUCHDOWN' in desc or 'TD' in desc
            
            # Include FG attempts even if not marked as scrimmage play
            is_scoring_play = p.is_scoring or (is_fg and ('GOOD' in desc or 'IS GOOD' in desc or 'MADE' in desc))
            
            if is_scoring_play:
                
                # Determine which zone this score came from
                if ytg <= 10:
                    if is_td:
                        drive_results[current_drive] = {'zone': 'tight_red', 'result': 'TD'}
                    elif is_fg:
                        drive_results[current_drive] = {'zone': 'tight_red', 'result': 'FG'}
                elif ytg <= 20:
                    if is_td:
                        drive_results[current_drive] = {'zone': 'red', 'result': 'TD'}
                    elif is_fg:
                        drive_results[current_drive] = {'zone': 'red', 'result': 'FG'}
                elif ytg <= 30:
                    if is_td:
                        drive_results[current_drive] = {'zone': 'green', 'result': 'TD'}
                    elif is_fg:
                        drive_results[current_drive] = {'zone': 'green', 'result': 'FG'}
        
        # Count trips and outcomes
        green_zone_trips = len(drives_by_zone['green'])
        red_zone_trips = len(drives_by_zone['red'])
        tight_red_zone_trips = len(drives_by_zone['tight_red'])
        
        # Count successful outcomes per zone (cumulative: tight_red ⊂ red ⊂ green)
        for drive_id, result_info in drive_results.items():
            zone = result_info['zone']
            result = result_info['result']
            
            # If scored from tight red, it counts for all three zones
            if zone == 'tight_red':
                if result == 'TD':
                    tight_red_zone_tds += 1
                    red_zone_tds += 1
                    green_zone_tds += 1
                elif result == 'FG':
                    tight_red_zone_fgs += 1
                    red_zone_fgs += 1
                    green_zone_fgs += 1
            # If scored from red (but not tight red), counts for red and green
            elif zone == 'red':
                if result == 'TD':
                    red_zone_tds += 1
                    green_zone_tds += 1
                elif result == 'FG':
                    red_zone_fgs += 1
                    green_zone_fgs += 1
            # If scored from green (but not red), counts only for green
            elif zone == 'green':
                if result == 'TD':
                    green_zone_tds += 1
                elif result == 'FG':
                    green_zone_fgs += 1
        
        # Calculate failed attempts (trips - TDs - FGs)
        green_zone_failed = green_zone_trips - (green_zone_tds + green_zone_fgs)
        red_zone_failed = red_zone_trips - (red_zone_tds + red_zone_fgs)
        tight_red_zone_failed = tight_red_zone_trips - (tight_red_zone_tds + tight_red_zone_fgs)
        
        # For backward compatibility, keep old rz_ fields as red zone (20 & in)
        rz_trips = red_zone_trips
        rz_tds = red_zone_tds
        rz_fgs = red_zone_fgs
        
        # Post-Turnover Drive Tracking
        post_turnover_drives = []
        points_off_turnovers_for = 0
        points_off_turnovers_against = 0
        
        for i, p in enumerate(g.plays):
            if not p.is_turnover:
                continue
            
            # Identify turnover details
            desc = (p.description or '').upper()
            turnover_type = 'INT' if 'INTERC' in desc else 'FUM' if 'FUMBLE' in desc else 'TO'
            lost_by = p.offense or '?'
            recovered_by = opp_abbr if lost_by == our_abbr else our_abbr
            
            # Find the next play by the recovering team (start of their drive)
            drive_start_idx = None
            for j in range(i + 1, len(g.plays)):
                next_play = g.plays[j]
                if next_play.offense == recovered_by:
                    drive_start_idx = j
                    break
            
            if drive_start_idx is None:
                continue
            
            # Track this drive until possession changes
            drive_result = 'NO SCORE'
            points_scored = 0
            drive_plays = []
            
            for k in range(drive_start_idx, len(g.plays)):
                dp = g.plays[k]
                
                # Stop if possession changes
                if dp.offense != recovered_by:
                    break
                
                drive_plays.append(dp)
                
                # Check for scoring
                if dp.is_scoring:
                    dp_desc = (dp.description or '').upper()
                    if 'TOUCHDOWN' in dp_desc or 'TD' in dp_desc:
                        drive_result = 'TD'
                        points_scored = 6  # simplified, not counting PAT
                    elif 'FIELD GOAL' in dp_desc or re.search(r'\bFG\b', dp_desc):
                        drive_result = 'FG'
                        points_scored = 3
                    break
            
            # Accumulate points
            if recovered_by == our_abbr:
                points_off_turnovers_for += points_scored
            else:
                points_off_turnovers_against += points_scored
            
            # Build description for the drive
            if drive_plays:
                first_play = drive_plays[0]
                drive_desc = f"{turnover_type} by {lost_by}, recovered by {recovered_by}. Drive: {drive_result}"
                
                post_turnover_drives.append({
                    'quarter': p.quarter,
                    'clock': p.clock or '',
                    'turnover_type': turnover_type,
                    'lost_by': lost_by,
                    'recovered_by': recovered_by,
                    'drive_result': drive_result,
                    'points_scored': points_scored,
                    'description': drive_desc,
                    'turnover_description': p.description or '',
                })
        
        # Determine conference membership
        sec_teams = [
            'alabama', 'arkansas', 'auburn', 'florida', 'georgia', 'kentucky', 'lsu',
            'mississippi', 'ole miss', 'mississippi st', 'mississippi state', 'missouri',
            'oklahoma', 'south carolina', 'tennessee', 'texas', 'texas a&m', 'vanderbilt',
            'a&m', 'tamu', 'uga'
        ]
        big12_teams = [
            'baylor', 'tcu', 'utah', 'texas tech', 'houston', 'iowa state',
            'west virginia', 'colorado', 'arizona', 'arizona st', 'arizona state',
            'ttu', 'uh', 'isu', 'wvu', 'colo'
        ]
        big10_teams = [
            'illinois', 'indiana', 'iowa', 'maryland', 'michigan', 'michigan st',
            'minnesota', 'nebraska', 'northwestern', 'ohio st', 'ohio state',
            'penn st', 'penn state', 'purdue', 'rutgers', 'wisconsin', 'ucla', 'usc',
            'washington', 'oregon'
        ]
        acc_teams = [
            'boston college', 'clemson', 'duke', 'florida st', 'florida state', 'georgia tech',
            'louisville', 'miami', 'nc state', 'north carolina', 'pitt', 'pittsburgh',
            'syracuse', 'virginia', 'virginia tech', 'wake forest', 'stanford', 'cal'
        ]

        if team_identifier == 'asu':
            conf_list = big12_teams
        else:
            conf_list = sec_teams

        is_conference = any(t in opp_name.lower() or t in opp_abbr.lower() for t in conf_list)

        # Power 4 check (Big 12, SEC, Big Ten, ACC)
        p4_list = sec_teams + big12_teams + big10_teams + acc_teams
        is_power4 = any(t in opp_name.lower() or t in opp_abbr.lower() for t in p4_list)
        non_p4 = ['northern ariz', 'texas st', 'nau', 'txst', 'umass', 'tenn tech', 'tennessee tech']
        if any(t in opp_name.lower() or t in opp_abbr.lower() for t in non_p4):
            is_power4 = False
        
        middle8_for, middle8_against, middle8_scoring = compute_middle8_stats(g.plays, our_abbr, opp_abbr)
        fourth_attempts, fourth_conversions = compute_fourth_down_stats(g.plays, our_abbr)
        special_teams = compute_special_teams_stats(g.plays, our_abbr, opp_abbr)
        penalty_details = parse_penalty_details(g.plays, our_abbr, opp_abbr)
        ints_lost, fum_lost, ints_gained, fum_gained = parse_turnover_breakdown(g.plays, our_abbr, opp_abbr)
        play_tree = build_play_tree(g.plays)

        game_data = {
            'game_number': len(games) + 1,
            'opponent': opp_name,
            'opponent_abbr': opp_abbr,
            'conference': is_conference,
            'is_power4': is_power4,
            'date': header.get('date', ''),
            'points_for': our_score,
            'points_against': opp_score,
            'total_plays': our_stats.total_plays if our_stats and our_stats.total_plays else len([p for p in g.plays if p.offense == our_abbr]),
            'total_yards': our_stats.total_yards if our_stats and our_stats.total_yards else 0,
            'explosives': our_explosives,
            'explosive_details': our_explosive_details,
            'turnovers_lost': our_turnovers_lost,
            'turnovers_gained': opp_turnovers_lost,
            'interceptions_lost': ints_lost,
            'fumbles_lost': fum_lost,
            'interceptions_gained': ints_gained,
            'fumbles_gained': fum_gained,
            'penalties': our_penalties,
            'penalty_details': penalty_details,
            'red_zone_trips': rz_trips,
            'red_zone_tds': rz_tds,
            'red_zone_fgs': rz_fgs,
            'green_zone_trips': green_zone_trips,
            'green_zone_tds': green_zone_tds,
            'green_zone_fgs': green_zone_fgs,
            'green_zone_failed': green_zone_failed,
            'tight_red_zone_trips': tight_red_zone_trips,
            'tight_red_zone_tds': tight_red_zone_tds,
            'tight_red_zone_fgs': tight_red_zone_fgs,
            'tight_red_zone_failed': tight_red_zone_failed,
            'red_zone_plays': red_zone_plays,
            'post_turnover_drives': post_turnover_drives,
            'points_off_turnovers_for': points_off_turnovers_for,
            'points_off_turnovers_against': points_off_turnovers_against,
            'middle8_points_for': middle8_for,
            'middle8_points_against': middle8_against,
            'middle8_scoring_plays': middle8_scoring,
            '4th_down_attempts': fourth_attempts,
            '4th_down_conversions': fourth_conversions,
            'special_teams': special_teams,
            'play_tree': play_tree,
        }
        games.append(game_data)
    
    # Compute aggregates
    n = len(games) or 1
    wins = sum(1 for g in games if g['points_for'] > g['points_against'])
    losses = n - wins
    total_pf = sum(g['points_for'] for g in games)
    total_pa = sum(g['points_against'] for g in games)
    total_expl = sum(g['explosives'] for g in games)
    total_tof = sum(g['turnovers_gained'] for g in games)
    total_tol = sum(g['turnovers_lost'] for g in games)
    total_pen = sum(g['penalties'] for g in games)
    total_rzt = sum(g['red_zone_trips'] for g in games)
    total_rztd = sum(g['red_zone_tds'] for g in games)
    total_rzfg = sum(g['red_zone_fgs'] for g in games)
    
    conf_wins = sum(1 for g in games if g['conference'] and g['points_for'] > g['points_against'])
    conf_losses = sum(1 for g in games if g['conference'] and g['points_for'] <= g['points_against'])
    
    aggregates = {
        'games': n,
        'record': f'{wins}-{losses}',
        'conf_record': f'{conf_wins}-{conf_losses}',
        'ppg': round(total_pf / n, 1),
        'opp_ppg': round(total_pa / n, 1),
        'explosives_per_game': round(total_expl / n, 1),
        'turnover_margin': total_tof - total_tol,
        'penalties_per_game': round(total_pen / n, 1),
        'red_zone_trips': total_rzt,
        'red_zone_tds': total_rztd,
        'red_zone_fgs': total_rzfg,
        'red_zone_td_pct': round(total_rztd / max(1, total_rzt) * 100, 1),
    }
    
    return games, aggregates, parsed_games


def main():
    print("Generating PBP Matchup Analysis data...\n")
    
    asu_dir = repo_root / "data" / "asu-2025"
    georgia_dir = repo_root / "data" / "georgia-2025"
    
    print("=== Parsing ASU Games ===")
    asu_games, asu_agg, _ = process_team_games(asu_dir, 'asu')
    
    print("\n=== Parsing Georgia Games ===")
    georgia_games, georgia_agg, _ = process_team_games(georgia_dir, 'georgia')
    
    data = {
        "teams": {
            "georgia": {
                "name": "Georgia",
                "abbr": "UGA",
                "conference": "SEC",
                "color": "#ef4444",
                "aggregates": georgia_agg,
                "games": georgia_games,
            },
            "asu": {
                "name": "Arizona State",
                "abbr": "ASU",
                "conference": "Big 12",
                "color": "#f97316",
                "aggregates": asu_agg,
                "games": asu_games,
            }
        },
        "metadata": {
            "generated": date.today().isoformat(),
            "version": "2.1"
        }
    }
    
    output_path = Path(__file__).parent / "data.json"
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✓ Generated {output_path}")
    print(f"\nGeorgia: {georgia_agg['record']} ({georgia_agg['conf_record']} conf) - {georgia_agg['ppg']} PPG")
    print(f"ASU: {asu_agg['record']} ({asu_agg['conf_record']} conf) - {asu_agg['ppg']} PPG")


if __name__ == "__main__":
    main()
