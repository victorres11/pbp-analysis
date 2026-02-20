#!/usr/bin/env python3
"""Validate pbp-analysis data.json shape used by the frontend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_RANKING_FIELDS = {"rank", "conference", "value", "label", "total"}
REQUIRED_SPLITS = ("all", "conf", "nonconf")
REQUIRED_TEAMS = ("georgia", "asu")
REQUIRED_TWO_POINT_GAME_FIELDS = (
    "two_pt_attempts",
    "two_pt_conversions",
    "two_pt_rush_attempts",
    "two_pt_rush_conversions",
    "two_pt_pass_attempts",
    "two_pt_pass_conversions",
    "two_pt_details",
    "opp_two_pt_attempts",
    "opp_two_pt_conversions",
)
REQUIRED_TWO_POINT_AGG_FIELDS = (
    "two_pt_attempts",
    "two_pt_conversions",
    "two_pt_pct",
)


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate data.json schema for pbp-analysis UI.")
    parser.add_argument("--path", default="data.json", help="Path to data.json (default: ./data.json)")
    args = parser.parse_args()

    data_path = Path(args.path)
    if not data_path.exists():
        fail(f"missing data file: {data_path}")

    payload = json.loads(data_path.read_text(encoding="utf-8"))
    teams = payload.get("teams")
    if not isinstance(teams, dict):
        fail("top-level 'teams' object is missing or invalid")

    for team_id in REQUIRED_TEAMS:
        if team_id not in teams:
            fail(f"required team missing: teams.{team_id}")

    for team_id, team_data in teams.items():
        games = team_data.get("games", [])
        if not isinstance(games, list):
            fail(f"teams.{team_id}.games must be a list")
        for idx, game in enumerate(games, 1):
            if "conference" not in game or not isinstance(game["conference"], bool):
                fail(f"teams.{team_id}.games[{idx}] missing boolean 'conference'")
            if "is_power4" not in game or not isinstance(game["is_power4"], bool):
                fail(f"teams.{team_id}.games[{idx}] missing boolean 'is_power4'")
            for field in REQUIRED_TWO_POINT_GAME_FIELDS:
                if field not in game:
                    fail(f"teams.{team_id}.games[{idx}] missing '{field}'")
            if not isinstance(game.get("two_pt_details"), list):
                fail(f"teams.{team_id}.games[{idx}].two_pt_details must be a list")

        aggregates = team_data.get("aggregates")
        if not isinstance(aggregates, dict):
            fail(f"teams.{team_id}.aggregates missing or invalid")
        for field in REQUIRED_TWO_POINT_AGG_FIELDS:
            if field not in aggregates:
                fail(f"teams.{team_id}.aggregates missing '{field}'")

        rankings = (team_data.get("cfbstats") or {}).get("rankings")
        if not isinstance(rankings, dict):
            fail(f"teams.{team_id}.cfbstats.rankings missing or invalid")

        for split in REQUIRED_SPLITS:
            split_rankings = rankings.get(split)
            if not isinstance(split_rankings, dict):
                fail(f"teams.{team_id}.cfbstats.rankings.{split} missing or invalid")
            for metric, entry in split_rankings.items():
                if not isinstance(entry, dict):
                    fail(f"teams.{team_id}.cfbstats.rankings.{split}.{metric} must be an object")
                missing = REQUIRED_RANKING_FIELDS - set(entry)
                if missing:
                    fail(
                        f"teams.{team_id}.cfbstats.rankings.{split}.{metric} "
                        f"missing fields: {sorted(missing)}"
                    )

    print(f"[OK] Schema validated for {data_path}")


if __name__ == "__main__":
    main()
