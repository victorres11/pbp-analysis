from __future__ import annotations

from pathlib import Path

from scripts.game_prep_brief import loaders
from scripts.game_prep_brief.renderers import html as html_renderer
from scripts.game_prep_brief.renderers import markdown as markdown_renderer
from scripts.game_prep_brief.sections import situational


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_FIXTURES = ROOT / "tests" / "fixtures" / "pipeline"


def test_fetch_pff_snapshot_treats_zero_placeholder_as_partial_provider(monkeypatch) -> None:
    seen_suffixes: list[str] = []

    def _fake_fetch(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        seen_suffixes.append(suffix)
        payloads = {
            "pff/plays?side=off&format=text": "70",
            "pff/plays?side=def&format=text": "68",
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
    assert seen_suffixes[:3] == [
        "games-played?format=text",
        "pff/plays?side=off&format=text",
        "pff/plays?side=def&format=text",
    ]

def test_fetch_pff_snapshot_uses_json_payloads_and_games_played_fallback(monkeypatch) -> None:
    def _fake_fetch_text(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        payloads = {
            "games-played?format=text": "13",
            "pff/plays?side=off&format=text": "66.7",
            "pff/plays?side=def&format=text": "68.2",
            "pff/play-clock?format=text": "13.463\t0.2803\t0.308\t0.2561",
        }
        text = payloads.get(suffix)
        return {"text": text, "status": "ok" if text else "unavailable", "reason": None, "url": suffix}

    def _fake_fetch_json(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        payloads = {
            "pff/tackling-per-game": {
                "data": {
                    "games": 0,
                    "missed_tackles": 139,
                    "missed_tackles_per_game": 0,
                    "tfl": 79,
                    "tfl_per_game": 0,
                    "sacks": 30,
                    "sacks_per_game": 0,
                }
            },
            "pff/fmt": {
                "data": {
                    "games": 0,
                    "fmt": 102,
                    "fmt_per_game": 0,
                }
            },
            "pff/sacks-allowed": {
                "data": {
                    "games": 0,
                    "sacks_allowed": 13,
                    "sacks_allowed_per_game": 0,
                }
            },
        }
        payload = payloads.get(suffix)
        return {"json": payload, "status": "ok" if payload else "unavailable", "reason": None, "url": suffix}

    monkeypatch.setattr(loaders, "_fetch_text_result_from_candidates", _fake_fetch_text)
    monkeypatch.setattr(loaders, "_fetch_json_result_from_candidates", _fake_fetch_json)

    values, provider = loaders._fetch_pff_snapshot("michigan", team_name="Michigan")

    assert values["pff_missed_tackles_pg"] == "10.7"
    assert values["pff_tfl_pg"] == "6.1"
    assert values["pff_sacks_pg"] == "2.3"
    assert values["pff_fmt_total"] == "102"
    assert values["pff_fmt_pg"] == "7.8"
    assert values["pff_sacks_allowed_pg"] == "1.0"
    assert values["pff_hurry_up_pct"] == "28.0%"
    assert provider["status"] == "ok"
    assert provider["reasons"] == []


def test_fetch_pff_snapshot_uses_games_hint_when_games_endpoint_is_missing(monkeypatch) -> None:
    def _fake_fetch_text(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        payloads = {
            "pff/plays?side=off&format=text": "68.4",
            "pff/plays?side=def&format=text": "62.6",
            "pff/play-clock?format=text": "10.1554\t0.5523\t0.198\t0.1125",
        }
        text = payloads.get(suffix)
        if text:
            return {"text": text, "status": "ok", "reason": None, "url": suffix}
        return {
            "text": None,
            "status": "unavailable",
            "reason": "HTTPError: HTTP Error 404: Not Found",
            "url": suffix,
        }

    def _fake_fetch_json(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        payloads = {
            "pff/tackling-per-game": {
                "data": {
                    "games": 0,
                    "missed_tackles": 223,
                    "missed_tackles_per_game": 0,
                    "tfl": 75,
                    "tfl_per_game": 0,
                    "sacks": 40,
                    "sacks_per_game": 0,
                }
            },
            "pff/fmt": {
                "data": {
                    "games": 0,
                    "fmt": 117,
                    "fmt_per_game": 0,
                }
            },
            "pff/sacks-allowed": {
                "data": {
                    "games": 0,
                    "sacks_allowed": 15,
                    "sacks_allowed_per_game": 0,
                }
            },
        }
        payload = payloads.get(suffix)
        return {"json": payload, "status": "ok" if payload else "unavailable", "reason": None, "url": suffix}

    monkeypatch.setattr(loaders, "_fetch_text_result_from_candidates", _fake_fetch_text)
    monkeypatch.setattr(loaders, "_fetch_json_result_from_candidates", _fake_fetch_json)

    values, provider = loaders._fetch_pff_snapshot(
        "washington-state",
        team_name="Washington State",
        games_played_hint=13,
    )

    assert values["pff_missed_tackles_pg"] == "17.2"
    assert values["pff_tfl_pg"] == "5.8"
    assert values["pff_sacks_pg"] == "3.1"
    assert values["pff_sacks_allowed_pg"] == "1.2"
    assert values["pff_fmt_total"] == "117"
    assert values["pff_fmt_pg"] == "9.0"
    assert values["pff_hurry_up_pct"] == "55.2%"
    assert provider["status"] == "ok"
    assert provider["reasons"] == ["pff_games_played:HTTPError: HTTP Error 404: Not Found"]


def test_fetch_negative_play_stats_uses_supported_side_parameters(monkeypatch) -> None:
    seen_suffixes: list[str] = []

    def _fake_fetch(_candidates: list[str], suffix: str, **_kwargs) -> dict[str, object]:
        seen_suffixes.append(suffix)
        payloads = {
            "pbp/negative-plays?side=off&scope=season&format=text": "6.3",
            "pbp/negative-plays?side=def&scope=season&format=text": "7.1",
            "pbp/negative-plays?side=off&scope=last3&format=text": "5.0",
            "pbp/negative-plays?side=def&scope=last3&format=text": "8.0",
        }
        text = payloads.get(suffix)
        return {"text": text, "status": "ok" if text else "unavailable", "reason": None, "url": suffix}

    monkeypatch.setattr(loaders, "_fetch_text_result_from_candidates", _fake_fetch)

    values, provider = loaders._fetch_negative_play_stats("ucla", team_name="UCLA")

    assert values == {
        "negative_plays_pg_api": "6.3",
        "negative_plays_forced_pg_api": "7.1",
        "negative_plays_pg_last3_api": "5.0",
        "negative_plays_forced_pg_last3_api": "8.0",
    }
    assert provider["status"] == "ok"
    assert seen_suffixes == [
        "pbp/negative-plays?side=off&scope=season&format=text",
        "pbp/negative-plays?side=def&scope=season&format=text",
        "pbp/negative-plays?side=off&scope=last3&format=text",
        "pbp/negative-plays?side=def&scope=last3&format=text",
    ]


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


def test_situational_display_preserves_percent_strings() -> None:
    assert situational._display_or_unavailable("28.0%") == "28.0%"
