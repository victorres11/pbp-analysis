# D1 Matchup Expansion Report

Plan: `config/d1-matchup-expansion-2025.json`
Readiness registry: `config/team-readiness-2025.json`
Status: `ready`

## Summary

- Waves: `3`
- Matchups: `8`
- Teams touched: `12`
- Pass: `38`
- Warning: `8`
- Fail: `0`

## Matchups

| Wave | Matchup | Status | Readiness | Teams | Coverage |
| --- | --- | --- | --- | --- | --- |
| wave0-current-proofs | michigan-utah | complete | ready | Michigan vs Utah | Big Ten, Big 12, cross-conference, non-Big-Ten team, PFF partial acceptable with notes |
| wave0-current-proofs | notre-dame-uconn | complete | ready | Notre Dame vs UConn | Independents, alias handling, PFF partial acceptable with notes, non-Big-Ten matchup |
| wave1-next-onboarding | michigan-texas | next | needs_onboarding | Michigan vs Texas | Big Ten, SEC, high-profile cross-conference, new PFF slug, full-season backfill from missing registry team |
| wave1-next-onboarding | notre-dame-miami-fl | next | needs_onboarding | Notre Dame vs Miami (FL) | Independents, ACC, ambiguous team name, independent comparison policy |
| wave1-next-onboarding | utah-byu | planned | needs_onboarding | Utah vs BYU | Big 12, no Big Ten team, rivalry naming, conference-only matchup |
| wave1-next-onboarding | michigan-boise-state | planned | needs_onboarding | Michigan vs Boise State | Big Ten, Mountain West, Group of Five, new PFF slug |
| wave2-any-request-drills | two-new-power-teams | deferred | needs_onboarding | TBD Power Team A vs TBD Power Team B | two missing teams, same-conference or cross-conference, 24-hour turnaround drill |
| wave2-any-request-drills | two-new-g5-or-fcs-edge-teams | deferred | needs_onboarding | TBD G5 Team A vs TBD G5 Team B | two missing teams, Group of Five, source-discovery stress test |

## Findings

| Status | Wave | Matchup | Team | Check | Message |
| --- | --- | --- | --- | --- | --- |
| warning | wave1-next-onboarding | michigan-texas | Texas | readiness_entry | team is missing from readiness registry. |
| warning | wave1-next-onboarding | notre-dame-miami-fl | Miami (FL) | readiness_entry | team is missing from readiness registry. |
| warning | wave1-next-onboarding | utah-byu | BYU | readiness_entry | team is missing from readiness registry. |
| warning | wave1-next-onboarding | michigan-boise-state | Boise State | readiness_entry | team is missing from readiness registry. |
| warning | wave2-any-request-drills | two-new-power-teams | TBD Power Team A | readiness_entry | team is missing from readiness registry. |
| warning | wave2-any-request-drills | two-new-power-teams | TBD Power Team B | readiness_entry | team is missing from readiness registry. |
| warning | wave2-any-request-drills | two-new-g5-or-fcs-edge-teams | TBD G5 Team A | readiness_entry | team is missing from readiness registry. |
| warning | wave2-any-request-drills | two-new-g5-or-fcs-edge-teams | TBD G5 Team B | readiness_entry | team is missing from readiness registry. |
