import json

import pandas as pd
import pytest

from standing_prediction import odds
from standing_prediction.odds import PROB_COLUMNS, match_odds, the_odds_api_snapshot

EVENT = {
    "id": "abc", "commence_time": "2026-10-18T14:00:00Z", "home_team": "Arsenal", "away_team": "Chelsea",
    "bookmakers": [
        {"key": "pinnacle", "last_update": "2026-10-13T05:00:00Z", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Arsenal", "price": 2.0}, {"name": "Draw", "price": 4.0}, {"name": "Chelsea", "price": 4.0}]}]},
        {"key": "unibet", "last_update": "2026-10-13T05:10:00Z", "markets": [{"key": "h2h", "outcomes": [
            {"name": "Arsenal", "price": 1.9}, {"name": "Draw", "price": 3.8}, {"name": "Chelsea", "price": 3.9}]}]},
    ],
}


def test_snapshot_summarizes_bookmakers_and_keeps_pinnacle(monkeypatch):
    monkeypatch.setattr(odds, "cached_get", lambda url, params=None, timeout=30: json.dumps([EVENT]))
    snapshot = the_odds_api_snapshot(sport_key="soccer_epl", competition="PL", api_key="test",
                                     fetched_at="2026-10-13T05:30:00Z")
    row = snapshot.iloc[0]
    assert (row.competition, row.books, row.observed_at) == ("PL", 2, "2026-10-13T05:30:00+00:00")
    assert (row.pinnacle_home, row.pinnacle_draw, row.pinnacle_away) == pytest.approx((0.5, 0.25, 0.25))
    assert row[PROB_COLUMNS].sum() == pytest.approx(1)
    assert 0.5 < row.p_home_book < 0.51  # mean of Pinnacle's 0.5 and the other book's de-margined price


def test_archived_snapshot_is_a_valid_odds_snapshot(monkeypatch):
    monkeypatch.setattr(odds, "cached_get", lambda url, params=None, timeout=30: json.dumps([EVENT]))
    snapshot = the_odds_api_snapshot(sport_key="soccer_epl", competition="PL", api_key="test",
                                     fetched_at="2026-10-13T05:30:00Z")
    fixtures = pd.DataFrame({"homeTeam": ["Arsenal FC"], "awayTeam": ["Chelsea FC"],
                             "utcDate": [pd.Timestamp("2026-10-18T14:00:00Z")]})
    assert ("Arsenal FC", "Chelsea FC") in match_odds(fixtures, snapshot, as_of="2026-10-14")
    assert match_odds(fixtures, snapshot, as_of="2026-10-12") == {}  # not yet observed at that origin
