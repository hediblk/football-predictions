import pandas as pd
import pytest

from champions_league.data import matches_from_api, merge_refresh, repeated_fixtures
from champions_league.identities import canonical_team

# (football-data.org or openfootball name, football-data.co.uk name) for one club. The first block split
# into two clubs in the 11 October 2026 history, so their current-season games counted twice.
SAME_CLUB = [
    ("NEC", "Nijmegen"), ("FC Twente '65", "Twente"), ("Fortuna Sittard", "For Sittard"), ("PEC Zwolle", "Zwolle"),
    ("SBV Excelsior", "Excelsior"), ("Telstar 1963", "Telstar"), ("Willem II Tilburg", "Willem II"),
    ("SC Cambuur-Leeuwarden", "Cambuur"), ("ADO Den Haag", "Den Haag"),
    ("Vitória SC", "Guimaraes"), ("GD Estoril Praia", "Estoril"), ("CF Estrela da Amadora", "Estrela"),
    ("CS Marítimo", "Maritimo"), ("Heart of Midlothian", "Hearts"),
    ("Coventry City FC", "Coventry"), ("SV 07 Elversberg", "Elversberg"),
    ("PSV", "PSV Eindhoven"), ("Feyenoord Rotterdam", "Feyenoord"), ("Sporting Clube de Portugal", "Sp Lisbon"),
    ("FC Porto", "Porto"), ("SL Benfica", "Benfica"),
]


@pytest.mark.parametrize("provider, csv", SAME_CLUB)
def test_provider_spellings_are_one_club(provider, csv):
    assert canonical_team(provider) == canonical_team(csv)


def csv_results(rows):
    out = pd.DataFrame(rows, columns=["utcDate", "homeTeam", "awayTeam", "homeGoals", "awayGoals"])
    out["utcDate"] = pd.to_datetime(out["utcDate"], utc=True)
    for side in ("homeTeam", "awayTeam"):
        out[side] = out[side].map(canonical_team)
    return out.assign(competition="N1", season=2026, source="csv")


def api_results(rows):
    matches = [{"id": i, "utcDate": day, "status": "FINISHED", "homeTeam": {"name": home}, "awayTeam": {"name": away},
                "score": {"duration": "REGULAR", "fullTime": {"home": hg, "away": ag}}}
               for i, (day, home, away, hg, ag) in enumerate(rows)]
    return matches_from_api(matches, season=2026).assign(competition="N1", source="api")


CSV = [("2026-08-08 18:00", "Ajax", "Nijmegen", 2, 1), ("2026-08-08 20:00", "Twente", "PSV Eindhoven", 0, 0),
       ("2026-08-15 18:00", "Nijmegen", "Twente", 1, 1), ("2026-08-15 20:00", "PSV Eindhoven", "Ajax", 3, 0)]


def test_refresh_maps_an_unknown_api_spelling_to_the_csv_club_and_counts_each_fixture_once():
    # "N.E.C." has no alias: it joins the CSV's "nijmegen" through the two fixtures both sources hold.
    api = api_results([("2026-08-08T18:00:00Z", "AFC Ajax", "N.E.C.", 2, 1), ("2026-08-08T20:00:00Z", "FC Twente '65", "PSV", 0, 0),
                       ("2026-08-15T18:00:00Z", "N.E.C.", "FC Twente '65", 1, 1), ("2026-08-15T20:00:00Z", "PSV", "AFC Ajax", 3, 0),
                       ("2026-08-22T18:00:00Z", "AFC Ajax", "FC Twente '65", 1, 0), ("2026-08-22T20:00:00Z", "N.E.C.", "PSV", 0, 2)])
    merged, renamed, disagreements = merge_refresh(csv_results(CSV), api)
    assert renamed == {"n e c": "nijmegen"}
    assert disagreements == []
    assert len(merged) == 6 and merged["source"].eq("api").all()
    assert set(merged["homeTeam"]) | set(merged["awayTeam"]) == {"ajax", "nijmegen", "twente", "psv"}
    assert repeated_fixtures(merged).empty


def test_refresh_refuses_to_count_a_fixture_twice():
    # The CSV and API disagree on the only score that could link "N.E.C." to "nijmegen", so Ajax would play twice.
    api = api_results([("2026-08-08T18:00:00Z", "AFC Ajax", "N.E.C.", 2, 2)])
    with pytest.raises(ValueError, match=r"\['ajax'\]"):
        merge_refresh(csv_results(CSV[:1]), api)


def test_repeated_fixtures_flags_an_opponent_split_across_two_names():
    history = csv_results([("2026-09-27", "Ajax", "Nijmegen", 1, 1), ("2026-12-26", "Ajax", "PSV Eindhoven", 1, 0),
                           ("2026-12-28", "Twente", "Ajax", 0, 2)])
    assert repeated_fixtures(history).empty  # two days apart is a congested schedule, not a duplicate
    api = api_results([("2026-09-27T12:15:00Z", "AFC Ajax", "N.E.C.", 1, 1)])
    repeated = repeated_fixtures(pd.concat([history, api], ignore_index=True))
    assert repeated[["competition", "team"]].values.tolist() == [["N1", "ajax"]]
