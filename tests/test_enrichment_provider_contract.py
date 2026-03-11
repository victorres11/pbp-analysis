from __future__ import annotations

from pathlib import Path

from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.renderers import html as html_renderer
from scripts.game_prep_brief.renderers import markdown as markdown_renderer


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"


def test_fetch_pff_snapshot_treats_zero_placeholder_as_partial_provider(monkeypatch) -> None:
    def _fake_fetch(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        payloads = {
            "pff/plays?side=both&format=text": "70,68",
            "pff/tackling-per-game?format=text": "0\t0\t0",
            "pff/sacks-allowed?format=text": "1.4",
            "pff/fmt?format=text": "11\t1.2",
            "pff/play-clock?format=text": "16.8\t0.27",
        }
        text = payloads.get(suffix)
        return {"text": text, "status": "ok" if text else "unavailable", "reason": None, "url": suffix}

    monkeypatch.setattr(loaders, "_fetch_text_result_from_candidates", _fake_fetch)

    values, provider = loaders._fetch_pff_snapshot("washington", team_name="Washington")

    assert values["pff_plays_offense_pg"] == "70"
    assert values["pff_plays_defense_pg"] == "68"
    assert values["pff_missed_tackles_pg"] == "N/A"
    assert values["pff_tfl_pg"] == "N/A"
    assert values["pff_sacks_pg"] == "N/A"
    assert values["pff_hurry_up_pct"] == "27.0%"
    assert provider["status"] == "partial"
    assert "pff_tackling:zero_placeholder_response" in provider["reasons"]


def test_merge_enrichment_payload_preserves_prior_values_and_failure_metadata() -> None:
    existing = {
        "washington": {
            "blitz_pct": "31.2%",
            "pff_missed_tackles_pg": "4.1",
            "pff_tfl_pg": "7.2",
            "pff_sacks_pg": "2.9",
            "_source": "artifact",
        }
    }
    refreshed = {
        "washington": {
            "blitz_pct": "31.2%",
            "blitz_pct_last3": "29.8%",
            "pff_missed_tackles_pg": "N/A",
            "pff_tfl_pg": "N/A",
            "pff_sacks_pg": "N/A",
            "_providers": {
                "blitz": {
                    "status": "ok",
                    "fields": {"blitz_pct": "31.2%", "blitz_pct_last3": "29.8%"},
                    "reasons": [],
                },
                "negative_plays": {
                    "status": "unavailable",
                    "fields": {},
                    "reasons": ["negative_plays_pg_api:empty_response"],
                },
                "pff": {
                    "status": "unavailable",
                    "fields": {
                        "pff_missed_tackles_pg": "N/A",
                        "pff_tfl_pg": "N/A",
                        "pff_sacks_pg": "N/A",
                    },
                    "reasons": ["pff_tackling:HTTPError: 403"],
                },
            },
            "_source": "yr-data-api",
        }
    }

    merged = loaders.merge_enrichment_payload(existing, refreshed)

    washington = merged["washington"]
    assert washington["pff_missed_tackles_pg"] == "4.1"
    assert washington["pff_tfl_pg"] == "7.2"
    assert washington["pff_sacks_pg"] == "2.9"
    assert washington["_status"] == "ok"
    assert washington["_providers"]["pff"]["status"] == "unavailable"
    assert washington["_providers"]["pff"]["fields"]["pff_missed_tackles_pg"] == "4.1"
    assert washington["_providers"]["pff"]["reasons"] == ["pff_tackling:HTTPError: 403"]


def test_gather_team_data_exposes_enrichment_provider_metadata() -> None:
    pbp_teams = loaders.load_pbp_data(
        season=2025,
        bundle_source=PIPELINE_FIXTURES / "pbp_stats_bundle_2025.json",
    )
    team = loaders.gather_team_data(
        pbp_teams,
        "Washington",
        2025,
        enrichment_by_slug={
            "washington": {
                "pff_missed_tackles_pg": "4.1",
                "_providers": {
                    "pff": {
                        "status": "partial",
                        "fields": {"pff_missed_tackles_pg": "4.1"},
                        "reasons": ["pff_tackling:zero_placeholder_response"],
                    }
                },
            }
        },
    )

    assert team["stats"]["pff_missed_tackles_pg"] == "4.1"
    assert team["enrichment"]["_status"] == "ok"
    assert team["enrichment"]["_providers"]["pff"]["status"] == "partial"
    assert "pff_tackling:zero_placeholder_response" in team["enrichment"]["_providers"]["pff"]["reasons"]


def test_renderers_prefer_provider_metadata_for_enrichment_warning() -> None:
    team1 = {
        "display_name": "Washington",
        "stats": {},
        "enrichment": {
            "_providers": {
                "pff": {
                    "status": "partial",
                    "fields": {},
                    "reasons": ["pff_tackling:zero_placeholder_response"],
                }
            }
        },
    }
    team2 = {
        "display_name": "Ohio State",
        "stats": {},
        "enrichment": {
            "_providers": {
                "blitz": {
                    "status": "unavailable",
                    "fields": {},
                    "reasons": ["blitz_pct:TimeoutError"],
                }
            }
        },
    }

    markdown_warning = markdown_renderer._missing_warning(team1, team2)
    html_warning = html_renderer._missing_warning(team1, team2)

    for warning in (markdown_warning, html_warning):
        assert "Enrichment snapshot issues:" in warning
        assert "Washington (PFF partial (placeholder zeros))" in warning
        assert "Ohio State (Blitz unavailable (timeout))" in warning
