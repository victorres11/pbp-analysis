"""Conference membership mapping used by pbp-analysis.

This module is the source of truth for FBS conference membership and common
alias handling within this repo.
"""

# Canonical team slugs by conference.
CONFERENCE_TEAMS = {
    "SEC": [
        "alabama",
        "arkansas",
        "auburn",
        "florida",
        "georgia",
        "kentucky",
        "lsu",
        "mississippi",
        "mississippi state",
        "missouri",
        "oklahoma",
        "south carolina",
        "tennessee",
        "texas",
        "texas a&m",
        "vanderbilt",
    ],
    "Big 12": [
        "baylor",
        "tcu",
        "utah",
        "texas tech",
        "houston",
        "iowa state",
        "west virginia",
        "colorado",
        "arizona",
        "arizona state",
    ],
    "Big Ten": [
        "illinois",
        "indiana",
        "iowa",
        "maryland",
        "michigan",
        "michigan state",
        "minnesota",
        "nebraska",
        "northwestern",
        "ohio state",
        "penn state",
        "purdue",
        "rutgers",
        "wisconsin",
        "ucla",
        "usc",
        "washington",
        "oregon",
    ],
    "ACC": [
        "boston college",
        "clemson",
        "duke",
        "florida state",
        "georgia tech",
        "louisville",
        "miami",
        "nc state",
        "north carolina",
        "pittsburgh",
        "syracuse",
        "virginia",
        "virginia tech",
        "wake forest",
        "stanford",
        "cal",
    ],
}

# Common abbreviations/variations mapped to canonical slugs above.
TEAM_ALIASES = {
    "a&m": "texas a&m",
    "tamu": "texas a&m",
    "uga": "georgia",
    "ole miss": "mississippi",
    "mississippi st": "mississippi state",
    "arizona st": "arizona state",
    "ttu": "texas tech",
    "uh": "houston",
    "isu": "iowa state",
    "wvu": "west virginia",
    "colo": "colorado",
    "michigan st": "michigan state",
    "ohio st": "ohio state",
    "penn st": "penn state",
    "florida st": "florida state",
    "pitt": "pittsburgh",
    "north carolina state": "nc state",
    "louisiana state": "lsu",
}

# List of FBS conferences represented in CONFERENCE_TEAMS.
FBS_CONFERENCES = [
    "SEC",
    "Big 12",
    "Big Ten",
    "ACC",
]
