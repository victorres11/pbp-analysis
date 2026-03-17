from __future__ import annotations

from scripts.game_prep_brief.supported_team_readiness import build_readiness_rows, render_markdown


def test_build_readiness_rows_marks_artifact_presence_and_missing() -> None:
    bundle = {"teams": {"washington": {"team_name": "Washington"}}}
    snapshot = {"teams": {"washington": {"team_name": "Washington"}, "notre-dame": {"team_name": "Notre Dame"}}}
    verification = {"teams": {"washington": {"team_name": "Washington"}}}

    rows = build_readiness_rows(
        season=2025,
        bundle=bundle,
        snapshot=snapshot,
        verification=verification,
    )
    washington = next(row for row in rows if row.slug == "washington")
    notre_dame = next(row for row in rows if row.slug == "notre-dame")

    assert washington.bundle == "present"
    assert washington.snapshot == "present"
    assert washington.verification == "present"
    assert washington.enrichment == "pending sweep"
    assert washington.confidence == "pending sweep"

    assert notre_dame.bundle == "missing"
    assert notre_dame.snapshot == "present"
    assert notre_dame.verification == "missing"
    assert notre_dame.notes == "artifact gap"


def test_render_markdown_summarizes_supported_set() -> None:
    rows = build_readiness_rows(
        season=2025,
        bundle={"teams": {"washington": {"team_name": "Washington"}}},
        snapshot={"teams": {"washington": {"team_name": "Washington"}}},
        verification={"teams": {"washington": {"team_name": "Washington"}}},
    )

    markdown = render_markdown(
        season=2025,
        rows=rows,
        bundle_source=None,
        snapshot_source=None,
        verification_source=None,
        findings=["Bundle artifact is missing supported teams: Northwestern."],
    )

    assert "# Big Ten + Notre Dame Readiness Matrix" in markdown
    assert "## Current Flagged Gaps" in markdown
    assert "Bundle artifact is missing supported teams: Northwestern." in markdown
    assert "Big Ten teams" in markdown
    assert "Notre Dame" in markdown
    assert "| Team | Conf | Bundle | Snapshot | Verification | Enrichment | Warning triage | Confidence | Notes |" in markdown
    assert "| Washington | Big Ten | present | present | present | pending sweep | pending sweep | pending sweep |  |" in markdown
