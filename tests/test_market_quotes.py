import numpy as np
import pandas as pd
import pytest

from champions_league.data import load_market_quotes
from champions_league.strengths import _market_terms, fit_strengths, market_quotes
from standing_prediction.dixon_coles import score_matrix_from_rates

from test_league_offsets import history


def test_market_loss_is_cross_entropy_of_the_model_outcome_probabilities():
    mu_home, mu_away, rho = np.array([1.7, 0.4, 2.9]), np.array([1.1, 2.2, 0.3]), -0.08
    quoted = np.array([[0.5, 0.25, 0.25], [0.2, 0.3, 0.5], [0.7, 0.2, 0.1]])
    weights = np.array([1.0, 2.0, 0.5])
    expected = 0.0
    for i in range(3):
        _, matrix = score_matrix_from_rates(mu_home[i], mu_away[i], rho)
        probs = np.array([np.tril(matrix, -1).sum(), np.trace(matrix), np.triu(matrix, 1).sum()])
        expected -= weights[i] * np.dot(quoted[i], np.log(probs))
    loss, *_ = _market_terms(mu_home, mu_away, rho, quoted, weights)
    assert loss == pytest.approx(expected)


def test_only_the_latest_quote_before_origin_and_kickoff_counts():
    quotes = pd.DataFrame({
        "homeTeam": ["A0", "A0", "A0", "B0", "Z9"], "awayTeam": ["B0", "B0", "B0", "C0", "A0"],
        "p_home": [0.5, 0.6, 0.9, 0.4, 0.5], "p_draw": [0.25, 0.25, 0.05, 0.3, 0.25], "p_away": [0.25, 0.15, 0.05, 0.3, 0.25],
        "observed_at": ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-03", "2026-10-01"],
        "commence_time": ["2026-10-04"] * 3 + ["2026-10-02", "2026-10-04"],
    })
    kept = market_quotes(quotes, {"A0": 0, "B0": 1, "C0": 2}, pd.Timestamp("2026-10-06", tz="UTC"))
    # The 5 Oct quote came after kickoff, B0-C0 was quoted after its kickoff, and Z9 is unknown.
    assert len(kept) == 1 and kept.loc[0, "p_home"] == pytest.approx(0.6)


def test_quotes_move_league_levels_toward_the_market():
    data, leagues, origin = history()
    # Bookmakers price league B's clubs level with league A's, unlike the European results.
    quotes = pd.DataFrame({"homeTeam": [f"A{i}" for i in range(4)] + [f"B{i}" for i in range(4)],
                           "awayTeam": [f"B{i}" for i in range(4)] + [f"A{(i + 1) % 4}" for i in range(4)],
                           "p_home": 0.46, "p_draw": 0.27, "p_away": 0.27, "competition": "CL",
                           "observed_at": origin - pd.Timedelta(hours=6), "commence_time": origin + pd.Timedelta(days=2)})
    fits = {name: fit_strengths(data, teams=list(leagues), team_leagues=leagues, as_of=origin, xg_weight=0, market=market)
            for name, market in (("results", None), ("market", quotes))}
    gap = {name: fit.metadata["league_offsets"]["A"] - fit.metadata["league_offsets"]["B"] for name, fit in fits.items()}
    assert fits["market"].metadata["market_quotes"] == 8
    assert gap["results"] > 0.3
    assert gap["market"] < gap["results"] - 0.15
    # The results-only offsets are kept for comparison.
    results = fits["market"].metadata["results_league_offsets"]
    assert results["A"] - results["B"] > gap["market"]


def test_archive_names_map_to_model_clubs(tmp_path):
    (tmp_path / "2026").mkdir()
    pd.DataFrame({"home_team": ["Inter Milan"], "away_team": ["Club Brugge"], "p_home_book": [0.76], "p_draw_book": [0.15],
                  "p_away_book": [0.09], "observed_at": ["2026-10-13T01:23:38Z"], "commence_time": ["2026-10-13T19:00:00Z"]}
                 ).to_csv(tmp_path / "2026" / "CL.csv", index=False)
    fixtures = pd.DataFrame({"homeTeam": ["internazionale milano"], "awayTeam": ["club brugge"], "neutral": [False]})
    quotes = load_market_quotes(2026, ["internazionale milano", "club brugge"], fixtures=fixtures, archive=tmp_path)
    assert quotes[["homeTeam", "awayTeam", "neutral"]].values.tolist() == [["internazionale milano", "club brugge", False]]
    assert load_market_quotes(2025, ["club brugge"], archive=tmp_path) is None
