from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = ROOT.parent
DEFAULT_BUNDLE = WORKSPACE_ROOT / "yr-data-api" / "data" / "pbp_stats_bundle.json"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "game_prep_brief"

STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_FAIL = "fail"

TEAM_ALIASES: dict[str, set[str]] = {
    "connecticut": {"uconn", "u-conn", "connecticut"},
    "uconn": {"uconn", "u-conn", "connecticut"},
    "notre-dame": {"notre-dame", "notre dame", "notredame", "nd"},
}


@dataclass(frozen=True)
class TeamRequest:
    name: str
    slug: str
    expected_games: int | None = None
    expected_conference: str | None = None


@dataclass(frozen=True)
class CheckResult:
    status: str
    check: str
    team_slug: str | None
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "check": self.check,
            "team_slug": self.team_slug,
            "message": self.message,
            "details": self.details,
        }


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _norm(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _slug_variants(team_name: str) -> set[str]:
    slug = slugify(team_name)
    variants = {slug, _norm(team_name), _norm(slug)}
    variants.update(TEAM_ALIASES.get(slug, set()))
    for alias_slug, aliases in TEAM_ALIASES.items():
        if slug in aliases or _norm(team_name) in {_norm(alias) for alias in aliases}:
            variants.add(alias_slug)
            variants.update(aliases)
    return {variant for variant in variants if variant}


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _artifact_team_map(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    teams = artifact.get("teams")
    if not isinstance(teams, dict):
        return {}
    nested_teams = teams.get("teams")
    nested_meta = teams.get("_meta")
    if isinstance(nested_teams, dict) and isinstance(nested_meta, dict):
        return nested_teams
    return teams


def _team_candidates(key: str, payload: Any) -> set[str]:
    candidates = {key, slugify(key), _norm(key)}
    if isinstance(payload, dict):
        for field in ("team_slug", "team_name", "name", "display_name", "canonical_name"):
            value = payload.get(field)
            if isinstance(value, str):
                candidates.update({value, slugify(value), _norm(value)})
    return {candidate for candidate in candidates if candidate}


def find_team_payload(artifact: dict[str, Any] | None, team_name: str) -> tuple[str, dict[str, Any]] | None:
    teams = _artifact_team_map(artifact)
    variants = _slug_variants(team_name)
    for key, payload in teams.items():
        if not isinstance(key, str) or not isinstance(payload, dict):
            continue
        candidates = _team_candidates(key, payload)
        if variants & candidates:
            return key, payload
    return None


def _game_count(bundle_payload: dict[str, Any]) -> int:
    games_parsed = bundle_payload.get("games_parsed")
    if isinstance(games_parsed, int):
        return games_parsed
    games = bundle_payload.get("games")
    if isinstance(games, list):
        return len(games)
    stats = bundle_payload.get("stats")
    if isinstance(stats, dict):
        schedule = stats.get("schedule")
        if isinstance(schedule, dict):
            counts = [
                len(row.get("games") or [])
                for row in schedule.values()
                if isinstance(row, dict) and isinstance(row.get("games"), list)
            ]
            if counts:
                return max(counts)
    return 0


def _latest_game_date(bundle_payload: dict[str, Any]) -> str | None:
    games = bundle_payload.get("games")
    if not isinstance(games, list):
        return None
    dates = [
        str(game.get("game_date") or game.get("date"))
        for game in games
        if isinstance(game, dict) and (game.get("game_date") or game.get("date"))
    ]
    return max(dates) if dates else None


def _nonempty_rankings(snapshot_payload: dict[str, Any]) -> bool:
    rankings = snapshot_payload.get("rankings")
    if not isinstance(rankings, dict):
        return False
    all_rankings = rankings.get("all")
    if not isinstance(all_rankings, dict):
        return False
    for row in all_rankings.values():
        if isinstance(row, dict) and row.get("rank") not in (None, "") and row.get("value") not in (None, ""):
            return True
    return False


def _verification_metric_counts(verification_payload: dict[str, Any]) -> dict[str, int]:
    summary = verification_payload.get("summary")
    if not isinstance(summary, dict):
        return {"pass": 0, "warning": 0, "fail": 0}
    metric_results = summary.get("metric_results")
    if not isinstance(metric_results, dict):
        return {"pass": 0, "warning": 0, "fail": 0}
    return {
        "pass": int(metric_results.get("pass") or 0),
        "warning": int(metric_results.get("warning") or 0),
        "fail": int(metric_results.get("fail") or 0),
    }


def _enrichment_status(enrichment_payload: dict[str, Any] | None, team: TeamRequest) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(enrichment_payload, dict):
        return None, None
    variants = _slug_variants(team.name)
    for key, payload in enrichment_payload.items():
        if not isinstance(key, str) or not isinstance(payload, dict):
            continue
        if variants & {key, slugify(key), _norm(key)}:
            status = payload.get("_status")
            return str(status) if status is not None else None, payload
    return None, None


def _check(status: str, check: str, team_slug: str | None, message: str, **details: Any) -> CheckResult:
    return CheckResult(status=status, check=check, team_slug=team_slug, message=message, details=details)


def build_preflight_report(
    *,
    season: int,
    team1: TeamRequest,
    team2: TeamRequest,
    bundle: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    verification: dict[str, Any] | None,
    enrichment: dict[str, Any] | None,
    require_expected_games: bool,
    require_enrichment: bool,
    artifact_paths: dict[str, str | None],
) -> dict[str, Any]:
    checks: list[CheckResult] = []
    requests = [team1, team2]

    if team1.slug == team2.slug:
        checks.append(_check(STATUS_FAIL, "matchup", None, "Selected teams must be different.", team=team1.name))

    for team in requests:
        bundle_match = find_team_payload(bundle, team.name)
        if bundle_match is None:
            checks.append(_check(STATUS_FAIL, "bundle_team", team.slug, "Team is missing from the bundle."))
            continue

        bundle_key, bundle_payload = bundle_match
        games_found = _game_count(bundle_payload)
        checks.append(
            _check(
                STATUS_PASS if games_found > 0 else STATUS_FAIL,
                "bundle_games",
                team.slug,
                f"Bundle has {games_found} game(s) for {team.name}.",
                bundle_key=bundle_key,
                games_found=games_found,
                latest_game_date=_latest_game_date(bundle_payload),
            )
        )
        if team.expected_games is None:
            status = STATUS_FAIL if require_expected_games else STATUS_WARNING
            checks.append(
                _check(
                    status,
                    "expected_games",
                    team.slug,
                    "Expected completed games was not provided.",
                    games_found=games_found,
                )
            )
        else:
            checks.append(
                _check(
                    STATUS_PASS if games_found == team.expected_games else STATUS_FAIL,
                    "expected_games",
                    team.slug,
                    f"Expected {team.expected_games} completed game(s); found {games_found}.",
                    expected_games=team.expected_games,
                    games_found=games_found,
                )
            )

    for team in requests:
        snapshot_match = find_team_payload(snapshot, team.name)
        if snapshot_match is None:
            checks.append(_check(STATUS_FAIL, "cfbstats_snapshot", team.slug, "Team is missing from CFBStats snapshot."))
            continue
        snapshot_key, snapshot_payload = snapshot_match
        conference = snapshot_payload.get("conference")
        checks.append(
            _check(
                STATUS_PASS if conference else STATUS_WARNING,
                "cfbstats_conference",
                team.slug,
                f"CFBStats conference is {conference or 'missing'}.",
                snapshot_key=snapshot_key,
                conference=conference,
            )
        )
        if team.expected_conference:
            checks.append(
                _check(
                    STATUS_PASS if _norm(conference) == _norm(team.expected_conference) else STATUS_FAIL,
                    "cfbstats_expected_conference",
                    team.slug,
                    f"Expected CFBStats conference {team.expected_conference}; found {conference or 'missing'}.",
                    expected_conference=team.expected_conference,
                    conference=conference,
                )
            )
        checks.append(
            _check(
                STATUS_PASS if _nonempty_rankings(snapshot_payload) else STATUS_FAIL,
                "cfbstats_rankings",
                team.slug,
                "CFBStats ranking rows are available." if _nonempty_rankings(snapshot_payload) else "CFBStats ranking rows are missing.",
            )
        )

    for team in requests:
        verification_match = find_team_payload(verification, team.name)
        if verification_match is None:
            checks.append(
                _check(STATUS_FAIL, "verification_team", team.slug, "Team is missing from CFBStats verification report.")
            )
            continue
        _, verification_payload = verification_match
        counts = _verification_metric_counts(verification_payload)
        fail_count = counts["fail"]
        warning_count = counts["warning"]
        if fail_count:
            status = STATUS_FAIL
            message = f"Verification has {fail_count} fail metric(s)."
        elif warning_count:
            status = STATUS_WARNING
            message = f"Verification has {warning_count} warning metric(s) and zero fails."
        else:
            status = STATUS_PASS
            message = "Verification has zero fail metrics."
        checks.append(_check(status, "verification_metrics", team.slug, message, **counts))

    for team in requests:
        status, payload = _enrichment_status(enrichment, team)
        if payload is None:
            check_status = STATUS_FAIL if require_enrichment else STATUS_WARNING
            checks.append(_check(check_status, "enrichment", team.slug, "Team is missing from enrichment artifact."))
            continue
        provider_statuses = {
            key: value.get("status")
            for key, value in (payload.get("_providers") or {}).items()
            if isinstance(value, dict)
        }
        core_fields = {
            field: payload.get(field)
            for field in ("pff_avg_play_clock", "pff_hurry_up_pct", "pff_plays_offense_pg", "pff_plays_defense_pg")
        }
        missing_core = [field for field, value in core_fields.items() if value in (None, "", "N/A")]
        if missing_core:
            check_status = STATUS_FAIL if require_enrichment else STATUS_WARNING
            message = "Enrichment artifact is missing core PFF fields."
        else:
            check_status = STATUS_PASS if status in {"ok", "partial"} else STATUS_WARNING
            message = f"Enrichment status is {status or 'unknown'}."
        checks.append(
            _check(
                check_status,
                "enrichment",
                team.slug,
                message,
                enrichment_status=status,
                provider_statuses=provider_statuses,
                core_fields=core_fields,
                missing_core_fields=missing_core,
            )
        )

    status_counts = {
        STATUS_PASS: sum(1 for check in checks if check.status == STATUS_PASS),
        STATUS_WARNING: sum(1 for check in checks if check.status == STATUS_WARNING),
        STATUS_FAIL: sum(1 for check in checks if check.status == STATUS_FAIL),
    }
    ready = status_counts[STATUS_FAIL] == 0
    return {
        "meta": {
            "artifact": "matchup_preflight",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "season": season,
            "artifact_paths": artifact_paths,
            "require_expected_games": require_expected_games,
            "require_enrichment": require_enrichment,
        },
        "matchup": {
            "team1": team1.__dict__,
            "team2": team2.__dict__,
        },
        "summary": {
            "ready": ready,
            "status": "ready" if ready else "blocked",
            "status_counts": status_counts,
        },
        "checks": [check.to_dict() for check in checks],
    }


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    matchup = report["matchup"]
    summary = report["summary"]
    lines = [
        "# Matchup Preflight",
        "",
        f"Season: `{meta['season']}`",
        f"Matchup: `{matchup['team1']['name']}` vs `{matchup['team2']['name']}`",
        f"Status: `{summary['status']}`",
        "",
        "## Summary",
        "",
        f"- Pass: `{summary['status_counts']['pass']}`",
        f"- Warning: `{summary['status_counts']['warning']}`",
        f"- Fail: `{summary['status_counts']['fail']}`",
        "",
        "## Checks",
        "",
        "| Status | Check | Team | Message |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    check["status"],
                    check["check"],
                    check.get("team_slug") or "",
                    str(check["message"]).replace("|", "\\|"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _parse_keyed_values(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError(f"Expected TEAM=VALUE, got {value!r}")
        key, raw = value.split("=", 1)
        parsed[slugify(key)] = raw.strip()
    return parsed


def _expected_games_for(team_name: str, expected_games: dict[str, str]) -> int | None:
    variants = {slugify(v) for v in _slug_variants(team_name)}
    for key, raw in expected_games.items():
        if key in variants:
            return int(raw)
    return None


def _expected_conference_for(team_name: str, expected_conferences: dict[str, str]) -> str | None:
    variants = {slugify(v) for v in _slug_variants(team_name)}
    for key, raw in expected_conferences.items():
        if key in variants:
            return raw
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight a selected D1 matchup against local artifacts.")
    parser.add_argument("team1")
    parser.add_argument("team2")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument(
        "--cfbstats-snapshot",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--cfbstats-verification-report",
        type=Path,
        default=None,
    )
    parser.add_argument("--enrichment-file", type=Path, default=None)
    parser.add_argument(
        "--expected-games",
        action="append",
        default=[],
        metavar="TEAM=COUNT",
        help="Expected completed games for a selected team. Repeat for each team.",
    )
    parser.add_argument(
        "--expected-conference",
        action="append",
        default=[],
        metavar="TEAM=CONFERENCE",
        help="Expected CFBStats conference for a selected team. Repeat as needed.",
    )
    parser.add_argument("--require-expected-games", action="store_true")
    parser.add_argument("--no-require-enrichment", action="store_true")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_path = args.cfbstats_snapshot or WORKSPACE_ROOT / "pbp-parser" / "data" / "cfbstats_snapshots" / f"cfbstats_{args.season}.json"
    verification_path = (
        args.cfbstats_verification_report
        or WORKSPACE_ROOT / "pbp-parser" / "data" / "cfbstats_reports" / f"cfbstats_verification_{args.season}.json"
    )
    expected_games = _parse_keyed_values(args.expected_games)
    expected_conferences = _parse_keyed_values(args.expected_conference)

    team1 = TeamRequest(
        name=args.team1,
        slug=slugify(args.team1),
        expected_games=_expected_games_for(args.team1, expected_games),
        expected_conference=_expected_conference_for(args.team1, expected_conferences),
    )
    team2 = TeamRequest(
        name=args.team2,
        slug=slugify(args.team2),
        expected_games=_expected_games_for(args.team2, expected_games),
        expected_conference=_expected_conference_for(args.team2, expected_conferences),
    )
    report = build_preflight_report(
        season=args.season,
        team1=team1,
        team2=team2,
        bundle=_load_json(args.bundle),
        snapshot=_load_json(snapshot_path),
        verification=_load_json(verification_path),
        enrichment=_load_json(args.enrichment_file),
        require_expected_games=args.require_expected_games,
        require_enrichment=not args.no_require_enrichment,
        artifact_paths={
            "bundle": str(args.bundle),
            "cfbstats_snapshot": str(snapshot_path),
            "cfbstats_verification_report": str(verification_path),
            "enrichment": str(args.enrichment_file) if args.enrichment_file else None,
        },
    )

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(report), encoding="utf-8")
    if not args.output_json and not args.output_md:
        print(render_markdown(report), end="")
    return 0 if report["summary"]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
