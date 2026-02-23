#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT_DIR / "outputs" / "demo_briefs"

DEMO_MATCHUPS = {
    "oregon-usc-2025": {
        "team1": "Oregon",
        "team2": "USC",
        "season": 2025,
        "matchup_slug": "oregon-vs-usc-2025",
        "label": "Oregon vs USC (2025)",
    },
    "georgia-asu-2025": {
        "team1": "Georgia",
        "team2": "Arizona State",
        "season": 2025,
        "matchup_slug": None,
        "label": "Georgia vs Arizona State (2025)",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate demo-ready Game Prep Brief artifacts.")
    parser.add_argument(
        "--matchup",
        choices=sorted(DEMO_MATCHUPS.keys()),
        default="oregon-usc-2025",
        help="Preset demo matchup profile.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for generated demo artifacts.",
    )
    parser.add_argument("--last-n", type=int, default=3, help="Last-N trend window.")
    return parser.parse_args()


def _run_brief(cfg: dict, output_dir: Path, last_n: int) -> tuple[Path, Path]:
    cmd = [
        sys.executable,
        "-m",
        "scripts.game_prep_brief",
        cfg["team1"],
        cfg["team2"],
        "--season",
        str(cfg["season"]),
        "--format",
        "both",
        "--last-n",
        str(last_n),
        "--output-dir",
        str(output_dir),
    ]
    if cfg.get("matchup_slug"):
        cmd.extend(["--matchup-slug", str(cfg["matchup_slug"])])
    subprocess.run(cmd, cwd=ROOT_DIR, check=True)

    slug1 = cfg["team1"].lower().replace(" ", "-")
    slug2 = cfg["team2"].lower().replace(" ", "-")
    base = f"{slug1}_vs_{slug2}_{cfg['season']}_v2"
    return output_dir / f"{base}.md", output_dir / f"{base}.html"


def _write_summary(cfg: dict, md_path: Path, html_path: Path, output_dir: Path) -> Path:
    summary = output_dir / "DEMO_SUMMARY.md"
    summary.write_text(
        "\n".join(
            [
                f"# Demo Brief Package: {cfg['label']}",
                "",
                "## Generated Artifacts",
                f"- Markdown brief: `{md_path}`",
                f"- HTML brief: `{html_path}`",
                "",
                "## Review Checklist",
                "- Opening storyline and matchup-signal quality in Overview",
                "- Schedule relative-performance columns (green/red) sanity check",
                "- Two-point, penalties, and middle-8 consistency with known game logs",
                "- Trench metrics caveat: defensive TFL currently uses PBP-derived run TFL proxy",
                "",
                "## Known Gaps (Current)",
                "- Situational receiver targets (3rd down / red zone) require PFF integration",
                "- Some opponent-relative schedule rows may use fallback baseline when opponent season profile is unavailable",
                "- StatBroadcast is the intended input data source moving forward",
                "- PDF output/export of generated briefs remains supported",
                "",
            ]
        )
    )
    return summary


def main() -> None:
    args = parse_args()
    cfg = DEMO_MATCHUPS[args.matchup]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    md_path, html_path = _run_brief(cfg, args.output_dir, args.last_n)
    summary_path = _write_summary(cfg, md_path, html_path, args.output_dir)
    print(f"[ok] Demo summary → {summary_path}")


if __name__ == "__main__":
    main()
