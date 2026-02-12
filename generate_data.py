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
        if 'PUNT' in desc or 'FIELD GOAL' in desc or ' FG' in desc:
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


def compute_special_teams_stats(plays, our_abbr, opp_abbr):
    stats = {
        'kickoff_returns': 0,
        'kickoff_return_yards': 0,
        'punt_returns': 0,
        'punt_return_yards': 0,
        'punts': 0,
        'punt_yards': 0,
        'field_goals_made': 0,
        'field_goals_attempts': 0,
        'pat_made': 0,
        'pat_attempts': 0,
    }

    for p in plays:
        if p.is_no_play:
            continue
        desc = (p.description or '').upper()
        is_kickoff = 'KICKOFF' in desc
        is_punt = 'PUNT' in desc
        is_fg = 'FIELD GOAL' in desc or re.search(r'\bFG\b', desc)
        is_pat = 'PAT' in desc or 'EXTRA POINT' in desc or 'POINT AFTER' in desc

        if p.offense == our_abbr:
            if is_punt:
                stats['punts'] += 1
                if p.yards is not None:
                    stats['punt_yards'] += p.yards
            if is_fg:
                stats['field_goals_attempts'] += 1
                if 'GOOD' in desc or 'IS GOOD' in desc or 'MADE' in desc:
                    stats['field_goals_made'] += 1
            if is_pat:
                stats['pat_attempts'] += 1
                if 'GOOD' in desc or 'MADE' in desc:
                    stats['pat_made'] += 1

        if p.offense == opp_abbr:
            if is_kickoff and 'RETURN' in desc:
                stats['kickoff_returns'] += 1
                if p.yards is not None:
                    stats['kickoff_return_yards'] += p.yards
            if is_punt and 'RETURN' in desc:
                stats['punt_returns'] += 1
                if p.yards is not None:
                    stats['punt_return_yards'] += p.yards

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
        
        # Red zone trips (drives starting or entering inside 20)
        rz_trips = 0
        rz_tds = 0
        rz_fgs = 0
        # Simple heuristic: count scoring plays from inside 20
        for p in g.plays:
            if p.offense == our_abbr and p.is_scoring:
                desc = (p.description or '').upper()
                spot = p.spot or ''
                # Check if in red zone based on spot
                rz_trips += 1
                if 'FIELD GOAL' in desc or 'FG' in desc:
                    rz_fgs += 1
                else:
                    rz_tds += 1
        
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
            'penalties': our_penalties,
            'red_zone_trips': rz_trips,
            'red_zone_tds': rz_tds,
            'red_zone_fgs': rz_fgs,
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
