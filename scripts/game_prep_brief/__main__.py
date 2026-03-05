#!/usr/bin/env python3
"""
YR Game Prep Auto-Brief v2
Usage:
    python3 -m scripts.game_prep_brief "Georgia" "Arizona State" --week 6 --season 2025
    python3 scripts/game_prep_brief "Georgia" "Arizona State" --format both
    python3 -m scripts.game_prep_brief "Oregon" "USC" --matchup-slug oregon-usc-week10
"""
import argparse
import sys
from pathlib import Path

from .loaders import (
    OUTPUT_DIR,
    slugify,
    build_enrichment_payload,
    merge_enrichment_payload,
    load_enrichment_file,
    write_enrichment_file,
    gather_team_data,
    load_pbp_data,
    fetch_ncaa_scoreboard,
    find_ncaa_game,
)
from .sections import (
    overview,
    matchups,
    schedule,
    explosives,
    zones,
    turnovers,
    middle8,
    situational,
    special_teams,
    rankings,
    penalties,
)
from .renderers import html as html_renderer, markdown as md_renderer


def parse_args():
    p = argparse.ArgumentParser(description="Game Prep Brief v2")
    p.add_argument("team1")
    p.add_argument("team2")
    p.add_argument("--week", type=int, default=None)
    p.add_argument("--season", type=int, default=2025)
    p.add_argument("--format", choices=["markdown", "html", "both"], default="both")
    p.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    p.add_argument(
        "--matchup-slug",
        default=None,
        help="Load matchup-specific data from matchups/<slug>/data.json",
    )
    p.add_argument(
        "--last-n",
        type=int,
        default=3,
        help="Number of last games for trending (default 3)",
    )
    p.add_argument("--print", action="store_true")
    p.add_argument(
        "--enrichment-file",
        type=Path,
        default=None,
        help="JSON file containing per-team enrichment payload (blitz/PFF/API snapshot).",
    )
    p.add_argument(
        "--refresh-enrichment",
        action="store_true",
        help="Refresh enrichment file from live API before rendering.",
    )
    p.add_argument(
        "--allow-live-enrichment",
        action="store_true",
        help="Allow live enrichment fetch during render if enrichment file is missing/stale.",
    )
    return p.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pbp_teams = load_pbp_data(matchup_slug=args.matchup_slug)
    bundle_meta = pbp_teams.pop("_meta", None) or {}
    team_specs = [
        {"slug": slugify(args.team1), "display_name": args.team1},
        {"slug": slugify(args.team2), "display_name": args.team2},
    ]
    enrichment_file = args.enrichment_file or (
        args.output_dir
        / f"{team_specs[0]['slug']}_vs_{team_specs[1]['slug']}_{args.season}_enrichment.json"
    )
    enrichment_by_slug = load_enrichment_file(enrichment_file)
    if args.refresh_enrichment or not enrichment_by_slug:
        refreshed = build_enrichment_payload(team_specs)
        if refreshed:
            enrichment_by_slug = merge_enrichment_payload(enrichment_by_slug, refreshed)
            write_enrichment_file(enrichment_file, enrichment_by_slug)
            print(f"[ok] Enrichment → {enrichment_file}", file=sys.stderr)
        else:
            print(f"[warn] Enrichment fetch returned empty payload; continuing.", file=sys.stderr)

    team1 = gather_team_data(
        pbp_teams,
        args.team1,
        args.season,
        last_n=args.last_n,
        enrichment_by_slug=enrichment_by_slug,
        allow_live_enrichment=args.allow_live_enrichment,
    )
    team2 = gather_team_data(
        pbp_teams,
        args.team2,
        args.season,
        last_n=args.last_n,
        enrichment_by_slug=enrichment_by_slug,
        allow_live_enrichment=args.allow_live_enrichment,
    )

    if args.week:
        games = fetch_ncaa_scoreboard(args.season, args.week)
        matchup = find_ncaa_game(games, team1["slug"], team2["slug"])
        if matchup:
            print(
                f"[info] Found this matchup in NCAA Week {args.week} scoreboard",
                file=sys.stderr,
            )

    section_list = [
        s for s in [
            overview.build(team1, team2, args.week, args.season, bundle_meta=bundle_meta),
            matchups.build(team1, team2),
            schedule.build(team1, team2),
            rankings.build(team1, team2),
            explosives.build(team1, team2),
            zones.build(team1, team2),
            turnovers.build(team1, team2),
            middle8.build(team1, team2),
            situational.build(team1, team2),
            special_teams.build(team1, team2),
            penalties.build(team1, team2),
        ] if s is not None
    ]

    slug1 = team1["slug"]
    slug2 = team2["slug"]
    week_tag = f"_week{args.week}" if args.week else ""
    base_name = f"{slug1}_vs_{slug2}{week_tag}_{args.season}_v2"

    if args.format in ("markdown", "both"):
        md = md_renderer.render(section_list, team1, team2, args.week, args.season)
        path = args.output_dir / f"{base_name}.md"
        path.write_text(md)
        print(f"[ok] Markdown → {path}", file=sys.stderr)
        if args.print:
            print(md)

    if args.format in ("html", "both"):
        html = html_renderer.render(section_list, team1, team2, args.week, args.season)
        path = args.output_dir / f"{base_name}.html"
        path.write_text(html)
        print(f"[ok] HTML → {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
